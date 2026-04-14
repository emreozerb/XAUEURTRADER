"""MetaTrader 5 connection, data reading, and order execution."""

import MetaTrader5 as mt5
import pandas as pd
import threading
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# MT5 operations must run in a single thread
_mt5_lock = threading.Lock()


class MT5Connector:
    def __init__(self):
        self.connected = False
        self.symbol = "XAUEUR"
        self.symbol_info = None
        self.account_info_data = None
        self._retry_count = 0
        self._max_retries = 5

    def initialize(self, account: int, password: str, server: str, symbol: str = "XAUEUR") -> dict:
        """Initialize MT5 and login."""
        with _mt5_lock:
            self.symbol = symbol
            if not mt5.initialize():
                return {"success": False, "error": "MT5 initialization failed. Is MetaTrader 5 running?"}

            if not mt5.login(account, password=password, server=server):
                error = mt5.last_error()
                mt5.shutdown()
                return {"success": False, "error": f"MT5 login failed: {error}"}

            # Select the symbol
            if not mt5.symbol_select(self.symbol, True):
                mt5.shutdown()
                return {"success": False, "error": f"Symbol '{self.symbol}' not available on this broker."}

            # Read symbol info
            info = mt5.symbol_info(self.symbol)
            if info is None:
                mt5.shutdown()
                return {"success": False, "error": f"Cannot read symbol info for '{self.symbol}'."}

            self.symbol_info = {
                "pip_value": info.trade_tick_value,
                "tick_size": info.trade_tick_size,
                "min_lot": info.volume_min,
                "max_lot": info.volume_max,
                "lot_step": info.volume_step,
                "contract_size": info.trade_contract_size,
                "digits": info.digits,
                "spread": info.spread,
                "point": info.point,
            }

            # Read account info
            acc = mt5.account_info()
            if acc is None:
                mt5.shutdown()
                return {"success": False, "error": "Cannot read account info."}

            is_live = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL
            if not acc.trade_allowed:
                mt5.shutdown()
                return {"success": False, "error": "Trading is not allowed on this account."}

            self.account_info_data = {
                "balance": acc.balance,
                "equity": acc.equity,
                "free_margin": acc.margin_free,
                "margin_level": acc.margin_level,
                "leverage": acc.leverage,
                "currency": acc.currency,
                "is_live": is_live,
                "trade_allowed": acc.trade_allowed,
            }

            self.connected = True
            self._retry_count = 0
            return {
                "success": True,
                "account_info": self.account_info_data,
                "symbol_info": self.symbol_info,
                "is_live": is_live,
            }

    def shutdown(self):
        with _mt5_lock:
            mt5.shutdown()
            self.connected = False

    def check_connection(self) -> bool:
        """Check if MT5 is still connected."""
        with _mt5_lock:
            info = mt5.account_info()
            if info is None:
                self.connected = False
                return False
            self.connected = True
            return True

    def reconnect(self, account: int, password: str, server: str) -> bool:
        """Attempt reconnection."""
        with _mt5_lock:
            mt5.shutdown()
            time.sleep(1)
            if not mt5.initialize():
                return False
            if not mt5.login(account, password=password, server=server):
                return False
            if not mt5.symbol_select(self.symbol, True):
                return False
            self.connected = True
            self._retry_count = 0
            return True

    def get_account_info(self) -> dict | None:
        with _mt5_lock:
            acc = mt5.account_info()
            if acc is None:
                return None
            return {
                "balance": acc.balance,
                "equity": acc.equity,
                "free_margin": acc.margin_free,
                "margin_level": acc.margin_level,
                "leverage": acc.leverage,
                "currency": acc.currency,
            }

    def get_positions(self) -> list[dict]:
        with _mt5_lock:
            positions = mt5.positions_get(symbol=self.symbol)
            if positions is None:
                return []
            result = []
            for p in positions:
                result.append({
                    "ticket": p.ticket,
                    "direction": "buy" if p.type == mt5.ORDER_TYPE_BUY else "sell",
                    "entry_price": p.price_open,
                    "current_price": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "lot_size": p.volume,
                    "pnl": p.profit,
                    "swap": p.swap,
                    "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                })
            return result

    def get_candles(self, timeframe: str, count: int) -> pd.DataFrame | None:
        """Get OHLCV candles. timeframe: 'M15', 'H1', or 'H4'."""
        with _mt5_lock:
            tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
            tf = tf_map.get(timeframe)
            if tf is None:
                return None

            rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
            if rates is None or len(rates) == 0:
                return None

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.rename(columns={
                "time": "timestamp", "open": "open", "high": "high",
                "low": "low", "close": "close", "tick_volume": "volume"
            }, inplace=True)
            return df[["timestamp", "open", "high", "low", "close", "volume"]]

    def get_candles_range(self, timeframe: str, date_from: datetime, date_to: datetime) -> pd.DataFrame | None:
        """Get historical candles for backtesting."""
        with _mt5_lock:
            tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
            tf = tf_map.get(timeframe)
            if tf is None:
                return None

            rates = mt5.copy_rates_range(self.symbol, tf, date_from, date_to)
            if rates is None or len(rates) == 0:
                return None

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.rename(columns={
                "time": "timestamp", "open": "open", "high": "high",
                "low": "low", "close": "close", "tick_volume": "volume"
            }, inplace=True)
            return df[["timestamp", "open", "high", "low", "close", "volume"]]

    def get_current_price(self) -> dict | None:
        with _mt5_lock:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return None
            return {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": round(tick.ask - tick.bid, 5),
                "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
            }

    def is_market_open(self) -> bool:
        with _mt5_lock:
            info = mt5.symbol_info(self.symbol)
            if info is None:
                return False
            # Check if trading session is active
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return False
            # If the last tick is more than 5 minutes old, market is likely closed
            now = time.time()
            return (now - tick.time) < 300

    def send_order(self, direction: str, lot_size: float, sl: float, tp: float,
                   comment: str = "XAUEUR Bot") -> dict:
        """Send a market order."""
        with _mt5_lock:
            price_info = mt5.symbol_info_tick(self.symbol)
            if price_info is None:
                return {"success": False, "error": "Cannot get current price."}

            if direction == "buy":
                order_type = mt5.ORDER_TYPE_BUY
                price = price_info.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = price_info.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": lot_size,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": 123456,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None:
                return {"success": False, "error": "Order send returned None."}

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                # Map common retcodes to actionable messages
                retcode_hints = {
                    10027: "AutoTrading is disabled in MetaTrader 5 — click the AutoTrading button in the MT5 toolbar to enable it.",
                    10014: "Invalid lot size.",
                    10015: "Invalid price.",
                    10016: "Invalid SL or TP.",
                    10019: "Not enough money.",
                    10025: "Trade context busy — MT5 is processing another request.",
                    10026: "AutoTrading disabled by server.",
                    10030: "Invalid order fill type — try a different filling mode.",
                }
                hint = retcode_hints.get(result.retcode, result.comment)
                return {
                    "success": False,
                    "error": f"Order failed ({result.retcode}): {hint}",
                    "retcode": result.retcode,
                }

            # Verify SL is set by reading back the position
            time.sleep(0.5)
            positions = mt5.positions_get(ticket=result.order)
            if positions and len(positions) > 0:
                pos = positions[0]
                if pos.sl == 0:
                    # SL not set - close the trade immediately
                    self._close_position(pos.ticket)
                    return {
                        "success": False,
                        "error": "SL failed to set. Trade closed for safety.",
                    }

            return {
                "success": True,
                "ticket": result.order,
                "price": result.price,
                "volume": result.volume,
            }

    def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> dict:
        """Modify SL/TP of an existing position."""
        with _mt5_lock:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return {"success": False, "error": "Position not found."}

            pos = positions[0]
            new_sl = sl if sl is not None else pos.sl
            new_tp = tp if tp is not None else pos.tp

            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": self.symbol,
                "position": ticket,
                "sl": new_sl,
                "tp": new_tp,
            }

            result = mt5.order_send(request)
            if result is None:
                return {"success": False, "error": "Modify returned None."}

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return {"success": False, "error": f"Modify failed: {result.retcode} - {result.comment}"}

            return {"success": True}

    def close_position(self, ticket: int) -> dict:
        """Close a specific position."""
        with _mt5_lock:
            return self._close_position(ticket)

    def _close_position(self, ticket: int) -> dict:
        """Internal close (already holding lock)."""
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"success": False, "error": "Position not found."}

        pos = positions[0]
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(self.symbol).bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(self.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "XAUEUR Bot Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "error": "Close returned None."}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"success": False, "error": f"Close failed: {result.retcode} - {result.comment}"}

        return {"success": True, "price": result.price}

    def close_all_positions(self) -> list[dict]:
        """Close all XAUEUR positions."""
        with _mt5_lock:
            positions = mt5.positions_get(symbol=self.symbol)
            if not positions:
                return []
            results = []
            for pos in positions:
                r = self._close_position(pos.ticket)
                results.append({"ticket": pos.ticket, **r})
            return results


# Singleton
mt5_connector = MT5Connector()
