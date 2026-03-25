"""Historical backtesting engine."""

import logging
import pandas as pd
from datetime import datetime, timezone, timedelta

from .indicators import get_full_series
from .strategy import (
    identify_trend, get_current_session, is_trading_session,
    calculate_sl_tp, check_cooldown,
)

logger = logging.getLogger(__name__)


class BacktestResult:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.starting_balance: float = 0
        self.final_balance: float = 0


def run_backtest(h1_candles: pd.DataFrame, h4_candles: pd.DataFrame,
                 starting_balance: float, risk_pct: float,
                 max_positions: int = 1, pip_value: float = 1.0,
                 tick_size: float = 0.01) -> dict:
    """
    Run a backtest on historical data using pure rule-based logic.
    No Claude API calls.
    """
    if h1_candles is None or h4_candles is None:
        return {"error": "Insufficient historical data."}

    if len(h1_candles) < 200 or len(h4_candles) < 50:
        return {"error": "Need at least 200 H1 candles and 50 H4 candles."}

    # Calculate full indicator series
    h1_series = get_full_series(h1_candles)
    h4_series = get_full_series(h4_candles)

    balance = starting_balance
    equity_curve = [{"time": h1_candles["timestamp"].iloc[0].isoformat(), "balance": balance}]
    trades = []
    open_trade = None
    last_sl_time = None
    consecutive_losses = 0

    # Start from index 200 to ensure all indicators have values
    start_idx = 200

    for i in range(start_idx, len(h1_candles)):
        candle = h1_candles.iloc[i]
        ts = candle["timestamp"]
        close = candle["close"]
        high = candle["high"]
        low = candle["low"]

        # Get H1 indicators at this point
        h1_ema50 = _safe_get(h1_series["ema_50"], i)
        h1_ema200 = _safe_get(h1_series["ema_200"], i)
        h1_atr = _safe_get(h1_series["atr_14"], i)
        h1_rsi = _safe_get(h1_series["rsi_14"], i)
        h1_rsi_prev = _safe_get(h1_series["rsi_14"], i - 1)

        if any(v is None for v in [h1_ema50, h1_atr, h1_rsi, h1_rsi_prev]):
            continue

        # Find corresponding H4 candle
        h4_idx = _find_h4_index(h4_candles, ts)
        if h4_idx is None or h4_idx < 50:
            continue

        h4_ema50 = _safe_get(h4_series["ema_50"], h4_idx)
        h4_ema200 = _safe_get(h4_series["ema_200"], h4_idx)
        h4_atr = _safe_get(h4_series["atr_14"], h4_idx)

        if any(v is None for v in [h4_ema50, h4_ema200, h4_atr]):
            continue

        # Determine trend
        h4_indicators = {"ema_50": h4_ema50, "ema_200": h4_ema200, "atr_14": h4_atr}
        trend = identify_trend(h4_indicators)
        session = get_current_session(ts.to_pydatetime() if hasattr(ts, 'to_pydatetime') else ts)

        # Check open trade for SL/TP hit
        if open_trade is not None:
            hit = _check_sl_tp_hit(open_trade, high, low)
            if hit:
                pnl = _calc_pnl(open_trade, hit["exit_price"], pip_value, tick_size)
                balance += pnl
                trade_result = {
                    **open_trade,
                    "exit_timestamp": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                    "exit_price": hit["exit_price"],
                    "result": "win" if pnl > 0 else "loss",
                    "pips": round((hit["exit_price"] - open_trade["entry_price"])
                                  if open_trade["direction"] == "buy"
                                  else (open_trade["entry_price"] - hit["exit_price"]), 2),
                    "pnl_eur": round(pnl, 2),
                    "exit_reason": hit["reason"],
                }
                trades.append(trade_result)
                equity_curve.append({"time": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts), "balance": round(balance, 2)})

                if pnl <= 0:
                    consecutive_losses += 1
                    last_sl_time = ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                else:
                    consecutive_losses = 0

                open_trade = None
                continue

            # Update trailing stop
            profit_dist = abs(close - open_trade["entry_price"])
            if profit_dist > 1.5 * h1_atr:
                if open_trade["direction"] == "buy":
                    new_sl = h1_ema50 - h1_atr
                    if new_sl > open_trade["stop_loss"]:
                        open_trade["stop_loss"] = round(new_sl, 5)
                else:
                    new_sl = h1_ema50 + h1_atr
                    if new_sl < open_trade["stop_loss"]:
                        open_trade["stop_loss"] = round(new_sl, 5)

            continue  # Don't open new trades while one is open

        # Skip if max positions reached or in cooldown
        if consecutive_losses >= 3:
            if not check_cooldown(last_sl_time,
                                  ts.to_pydatetime().replace(tzinfo=timezone.utc) if hasattr(ts, 'to_pydatetime') else ts):
                continue
            consecutive_losses = 0

        if not is_trading_session(session):
            continue

        # Check BUY signal
        if trend == "uptrend":
            distance = abs(close - h1_ema50)
            rsi_cross = h1_rsi_prev < 40 and h1_rsi > 40
            close_above = close > h1_ema50

            if distance <= h1_atr and rsi_cross and close_above:
                sl_tp = calculate_sl_tp("buy", close, h1_atr, h1_ema50)
                lot = _calc_lot(balance, risk_pct, sl_tp["sl_distance"], pip_value, tick_size)
                if lot > 0:
                    open_trade = {
                        "entry_timestamp": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                        "direction": "buy",
                        "entry_price": close,
                        "stop_loss": sl_tp["stop_loss"],
                        "take_profit": sl_tp["take_profit"],
                        "lot_size": lot,
                    }

        # Check SELL signal
        elif trend == "downtrend":
            distance = abs(close - h1_ema50)
            rsi_cross = h1_rsi_prev > 60 and h1_rsi < 60
            close_below = close < h1_ema50

            if distance <= h1_atr and rsi_cross and close_below:
                sl_tp = calculate_sl_tp("sell", close, h1_atr, h1_ema50)
                lot = _calc_lot(balance, risk_pct, sl_tp["sl_distance"], pip_value, tick_size)
                if lot > 0:
                    open_trade = {
                        "entry_timestamp": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                        "direction": "sell",
                        "entry_price": close,
                        "stop_loss": sl_tp["stop_loss"],
                        "take_profit": sl_tp["take_profit"],
                        "lot_size": lot,
                    }

    # Close any remaining open trade at last price
    if open_trade is not None:
        last_close = h1_candles["close"].iloc[-1]
        pnl = _calc_pnl(open_trade, last_close, pip_value, tick_size)
        balance += pnl
        trades.append({
            **open_trade,
            "exit_timestamp": h1_candles["timestamp"].iloc[-1].isoformat()
            if hasattr(h1_candles["timestamp"].iloc[-1], 'isoformat')
            else str(h1_candles["timestamp"].iloc[-1]),
            "exit_price": last_close,
            "result": "win" if pnl > 0 else "loss",
            "pips": round((last_close - open_trade["entry_price"])
                          if open_trade["direction"] == "buy"
                          else (open_trade["entry_price"] - last_close), 2),
            "pnl_eur": round(pnl, 2),
            "exit_reason": "backtest_end",
        })

    # Calculate summary
    total = len(trades)
    wins = sum(1 for t in trades if t["result"] == "win")
    losses = sum(1 for t in trades if t["result"] == "loss")
    net_pips = sum(t["pips"] for t in trades)
    net_pnl = sum(t["pnl_eur"] for t in trades)
    pips_list = [t["pips"] for t in trades]

    gross_profit = sum(t["pnl_eur"] for t in trades if t["pnl_eur"] > 0)
    gross_loss = abs(sum(t["pnl_eur"] for t in trades if t["pnl_eur"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Max drawdown
    peak = starting_balance
    max_dd = 0
    running = starting_balance
    for t in trades:
        running += t["pnl_eur"]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = (max_dd / starting_balance * 100) if starting_balance > 0 else 0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
        "net_pips": round(net_pips, 1),
        "net_pnl_eur": round(net_pnl, 2),
        "max_drawdown_eur": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 1),
        "best_trade_pips": round(max(pips_list), 1) if pips_list else 0,
        "worst_trade_pips": round(min(pips_list), 1) if pips_list else 0,
        "avg_trade_duration": 0,
        "profit_factor": round(profit_factor, 2),
        "starting_balance": starting_balance,
        "final_balance": round(balance, 2),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _safe_get(series, idx):
    if series is None or idx >= len(series):
        return None
    val = series.iloc[idx]
    return float(val) if pd.notna(val) else None


def _find_h4_index(h4_candles: pd.DataFrame, h1_timestamp) -> int | None:
    """Find the H4 candle that corresponds to (or is just before) the H1 timestamp."""
    mask = h4_candles["timestamp"] <= h1_timestamp
    if mask.any():
        return mask.values.nonzero()[0][-1]
    return None


def _check_sl_tp_hit(trade: dict, high: float, low: float) -> dict | None:
    """Check if SL or TP was hit during a candle."""
    if trade["direction"] == "buy":
        if low <= trade["stop_loss"]:
            return {"exit_price": trade["stop_loss"], "reason": "hit_sl"}
        if high >= trade["take_profit"]:
            return {"exit_price": trade["take_profit"], "reason": "hit_tp"}
    else:
        if high >= trade["stop_loss"]:
            return {"exit_price": trade["stop_loss"], "reason": "hit_sl"}
        if low <= trade["take_profit"]:
            return {"exit_price": trade["take_profit"], "reason": "hit_tp"}
    return None


def _calc_pnl(trade: dict, exit_price: float, pip_value: float, tick_size: float) -> float:
    """Calculate P&L in EUR."""
    if trade["direction"] == "buy":
        pips = (exit_price - trade["entry_price"]) / tick_size
    else:
        pips = (trade["entry_price"] - exit_price) / tick_size
    return pips * pip_value * trade["lot_size"]


def _calc_lot(balance: float, risk_pct: float, sl_distance: float,
              pip_value: float, tick_size: float) -> float:
    """Calculate lot size for backtesting."""
    risk_pct = min(risk_pct, 5.0)
    risk_amount = balance * (risk_pct / 100)
    if sl_distance <= 0 or tick_size <= 0 or pip_value <= 0:
        return 0
    sl_pips = sl_distance / tick_size
    raw_lot = risk_amount / (sl_pips * pip_value)
    lot = int(raw_lot / 0.01) * 0.01
    return max(lot, 0.01) if lot >= 0.01 else 0
