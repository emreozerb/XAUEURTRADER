"""Strategy rules: trend identification, entry signals, SL/TP, filters."""

from datetime import datetime, timezone, timedelta


def identify_trend(h4_indicators: dict) -> str:
    """Identify trend from H4 indicators."""
    ema50 = h4_indicators.get("ema_50")
    ema200 = h4_indicators.get("ema_200")
    atr = h4_indicators.get("atr_14")

    if ema50 is None or ema200 is None or atr is None:
        return "unknown"

    diff = abs(ema50 - ema200)
    if diff < 0.5 * atr:
        return "sideways"
    elif ema50 > ema200:
        return "uptrend"
    else:
        return "downtrend"


def get_current_session(utc_now: datetime | None = None) -> str:
    """Determine current trading session."""
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    hour = utc_now.hour

    # London: 07:00-16:00 UTC
    # New York: 12:00-21:00 UTC
    # Asian: 21:00-07:00 UTC (wraps midnight)
    if 7 <= hour < 12:
        return "london"
    elif 12 <= hour < 16:
        return "london_newyork"  # overlap
    elif 16 <= hour < 21:
        return "new_york"
    else:
        return "asian"


def is_trading_session(session: str) -> bool:
    """Check if current session allows new trades."""
    return session in ("london", "london_newyork", "new_york")


def check_buy_signal(h1_indicators: dict, h4_trend: str, session: str,
                     news_clear: bool) -> dict:
    """Check if all BUY entry conditions are met."""
    reasons = []

    # 1. 4H trend must be uptrend
    if h4_trend != "uptrend":
        return {"signal": False, "reasons": [f"Trend is {h4_trend}, need uptrend"]}

    ema50 = h1_indicators.get("ema_50")
    atr = h1_indicators.get("atr_14")
    rsi = h1_indicators.get("rsi_14")
    rsi_prev = h1_indicators.get("rsi_14_prev")
    current_close = h1_indicators.get("current_close")

    if any(v is None for v in [ema50, atr, rsi, rsi_prev, current_close]):
        return {"signal": False, "reasons": ["Insufficient indicator data"]}

    # 2. Price pulled back to within 1x ATR of EMA 50
    distance = abs(current_close - ema50)
    if distance > atr:
        reasons.append(f"Price too far from EMA50 ({distance:.2f} > ATR {atr:.2f})")

    # 3. RSI dipped below 40 and crossed back above
    rsi_cross = rsi_prev < 40 and rsi > 40
    if not rsi_cross:
        reasons.append(f"RSI no bullish cross (prev={rsi_prev:.1f}, curr={rsi:.1f})")

    # 4. Current candle closes above EMA 50
    if current_close <= ema50:
        reasons.append(f"Close {current_close:.2f} below EMA50 {ema50:.2f}")

    # 5. No high-impact news within 30 min
    if not news_clear:
        reasons.append("High-impact news event nearby")

    # 6. Trading session
    if not is_trading_session(session):
        reasons.append(f"Outside trading session ({session})")

    if reasons:
        return {"signal": False, "reasons": reasons}

    return {"signal": True, "reasons": ["All BUY conditions met"]}


def check_sell_signal(h1_indicators: dict, h4_trend: str, session: str,
                      news_clear: bool) -> dict:
    """Check if all SELL entry conditions are met."""
    reasons = []

    if h4_trend != "downtrend":
        return {"signal": False, "reasons": [f"Trend is {h4_trend}, need downtrend"]}

    ema50 = h1_indicators.get("ema_50")
    atr = h1_indicators.get("atr_14")
    rsi = h1_indicators.get("rsi_14")
    rsi_prev = h1_indicators.get("rsi_14_prev")
    current_close = h1_indicators.get("current_close")

    if any(v is None for v in [ema50, atr, rsi, rsi_prev, current_close]):
        return {"signal": False, "reasons": ["Insufficient indicator data"]}

    distance = abs(current_close - ema50)
    if distance > atr:
        reasons.append(f"Price too far from EMA50 ({distance:.2f} > ATR {atr:.2f})")

    # RSI pushed above 60 and crossed back below
    rsi_cross = rsi_prev > 60 and rsi < 60
    if not rsi_cross:
        reasons.append(f"RSI no bearish cross (prev={rsi_prev:.1f}, curr={rsi:.1f})")

    if current_close >= ema50:
        reasons.append(f"Close {current_close:.2f} above EMA50 {ema50:.2f}")

    if not news_clear:
        reasons.append("High-impact news event nearby")

    if not is_trading_session(session):
        reasons.append(f"Outside trading session ({session})")

    if reasons:
        return {"signal": False, "reasons": reasons}

    return {"signal": True, "reasons": ["All SELL conditions met"]}


def calculate_sl_tp(direction: str, entry_price: float, atr: float,
                    ema50: float) -> dict:
    """Calculate stop-loss and take-profit levels."""
    sl_distance = 1.5 * atr
    tp_distance = 2.5 * atr

    if direction == "buy":
        sl = entry_price - sl_distance
        tp = entry_price + tp_distance
        # SL must be below EMA50 for a buy
        if sl >= ema50:
            sl = ema50 - (0.1 * atr)  # Just beyond EMA50
    else:
        sl = entry_price + sl_distance
        tp = entry_price - tp_distance
        # SL must be above EMA50 for a sell
        if sl <= ema50:
            sl = ema50 + (0.1 * atr)

    return {
        "stop_loss": round(sl, 5),
        "take_profit": round(tp, 5),
        "sl_distance": round(sl_distance, 5),
        "tp_distance": round(tp_distance, 5),
        "risk_reward": round(tp_distance / sl_distance, 2),
    }


def calculate_trailing_stop(direction: str, ema50: float, atr: float,
                           current_sl: float, entry_price: float,
                           current_price: float) -> float | None:
    """
    Calculate new trailing stop level.
    Returns new SL or None if no update needed.
    """
    profit_distance = abs(current_price - entry_price)
    activation_distance = 1.5 * atr

    # Only activate trailing after 1.5x ATR profit
    if profit_distance < activation_distance:
        return None

    if direction == "buy":
        new_sl = ema50 - (1.0 * atr)
        # Trailing stop only moves up for buys
        if new_sl > current_sl:
            return round(new_sl, 5)
    else:
        new_sl = ema50 + (1.0 * atr)
        # Trailing stop only moves down for sells
        if new_sl < current_sl:
            return round(new_sl, 5)

    return None


def check_weekend_close(positions: list[dict], atr: float,
                        utc_now: datetime | None = None) -> list[dict]:
    """
    Check positions for weekend close logic.
    Friday, 30 min before market close.
    Returns list of actions.
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)

    # Only on Friday, after 21:30 UTC (30 min before typical 22:00 close)
    if utc_now.weekday() != 4 or utc_now.hour < 21 or (utc_now.hour == 21 and utc_now.minute < 30):
        return []

    actions = []
    for pos in positions:
        profit = abs(pos["current_price"] - pos["entry_price"])
        if profit < atr:
            actions.append({"ticket": pos["ticket"], "action": "close", "reason": "weekend_close"})
        else:
            # Tighten trailing stop
            if pos["direction"] == "buy":
                tight_sl = pos["current_price"] - (0.5 * atr)
                if tight_sl > pos["sl"]:
                    actions.append({
                        "ticket": pos["ticket"], "action": "tighten_sl",
                        "new_sl": round(tight_sl, 5), "reason": "weekend_tighten"
                    })
            else:
                tight_sl = pos["current_price"] + (0.5 * atr)
                if tight_sl < pos["sl"]:
                    actions.append({
                        "ticket": pos["ticket"], "action": "tighten_sl",
                        "new_sl": round(tight_sl, 5), "reason": "weekend_tighten"
                    })

    return actions


def check_cooldown(last_sl_hit_time: str | None, utc_now: datetime | None = None) -> bool:
    """Check if cooldown period (2 H1 candles = 2 hours) has passed."""
    if last_sl_hit_time is None:
        return True  # No cooldown active

    if utc_now is None:
        utc_now = datetime.now(timezone.utc)

    try:
        sl_time = datetime.fromisoformat(last_sl_hit_time)
        if sl_time.tzinfo is None:
            sl_time = sl_time.replace(tzinfo=timezone.utc)
        elapsed = utc_now - sl_time
        return elapsed >= timedelta(hours=2)
    except (ValueError, TypeError):
        return True
