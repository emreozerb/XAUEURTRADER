"""Trade execution, modification, trailing stop management."""

import logging
from datetime import datetime, timezone

from .mt5_connector import mt5_connector
from .risk_manager import risk_manager
from .strategy import calculate_sl_tp, calculate_trailing_stop
from .database import log_trade, update_trade_exit, get_last_n_trades
from .config import bot_config

logger = logging.getLogger(__name__)

MAX_CONCURRENT_POSITIONS = 1  # hardcoded — approval flow removed


class TradeManager:
    def __init__(self):
        self.active_trade_db_id: int | None = None

    async def execute_trade(self, direction: str, lot_size: float,
                            sl: float, tp: float, ai_confidence: int,
                            ai_reasoning: str) -> dict:
        """Execute a trade via MT5."""
        account = mt5_connector.get_account_info()
        if account is None:
            return {"success": False, "error": "MT5 not connected."}

        # Final validation
        positions = mt5_connector.get_positions()
        validation = risk_manager.validate_trade(
            lot_size=lot_size,
            account_balance=account["balance"],
            free_margin=account["free_margin"],
            equity=account["equity"],
            open_positions=positions,
            risk_pct=bot_config.validate_risk(),
            max_positions=MAX_CONCURRENT_POSITIONS,
            symbol_info=mt5_connector.symbol_info or {},
        )
        if not validation["valid"]:
            return {"success": False, "error": "; ".join(validation["errors"])}

        # Send order
        result = mt5_connector.send_order(direction, lot_size, sl, tp)
        if not result["success"]:
            return result

        # Log to database
        entry_data = {
            "entry_timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "entry_price": result["price"],
            "stop_loss": sl,
            "take_profit": tp,
            "lot_size": lot_size,
            "risk_eur": self._calculate_risk_eur(lot_size, abs(result["price"] - sl)),
            "ai_confidence": ai_confidence,
            "ai_reasoning": ai_reasoning,
            "account_balance_at_entry": account["balance"],
        }
        await log_trade(entry_data)

        trades = await get_last_n_trades(1)
        if trades:
            self.active_trade_db_id = trades[0]["id"]

        return {
            "success": True,
            "ticket": result["ticket"],
            "price": result["price"],
            "lot_size": lot_size,
        }

    async def update_trailing_stop(self, h1_indicators: dict):
        """Check and update trailing stops for open positions."""
        positions = mt5_connector.get_positions()
        if not positions:
            return

        ema50 = h1_indicators.get("ema_50")
        atr = h1_indicators.get("atr_14")
        if ema50 is None or atr is None:
            return

        for pos in positions:
            new_sl = calculate_trailing_stop(
                direction=pos["direction"],
                ema50=ema50,
                atr=atr,
                current_sl=pos["sl"],
                entry_price=pos["entry_price"],
                current_price=pos["current_price"],
            )
            if new_sl is not None:
                result = mt5_connector.modify_position(pos["ticket"], sl=new_sl)
                if result["success"]:
                    logger.info(f"Trailing stop updated for {pos['ticket']}: {pos['sl']} -> {new_sl}")
                else:
                    logger.error(f"Failed to update trailing stop: {result['error']}")

    async def close_position(self, ticket: int, reason: str) -> dict:
        """Close a specific position and log it."""
        positions = mt5_connector.get_positions()
        pos = next((p for p in positions if p["ticket"] == ticket), None)
        if pos is None:
            return {"success": False, "error": "Position not found."}

        result = mt5_connector.close_position(ticket)
        if not result["success"]:
            return result

        account = mt5_connector.get_account_info()
        exit_price = result.get("price", pos["current_price"])
        pips = (exit_price - pos["entry_price"]) if pos["direction"] == "buy" else (pos["entry_price"] - exit_price)
        pnl = pos["pnl"]

        if self.active_trade_db_id:
            await update_trade_exit(self.active_trade_db_id, {
                "exit_timestamp": datetime.now(timezone.utc).isoformat(),
                "exit_price": exit_price,
                "result": "win" if pnl > 0 else "loss",
                "pips": round(pips, 2),
                "pnl_eur": round(pnl, 2),
                "duration_minutes": 0,
                "exit_reason": reason,
                "account_balance_at_exit": account["balance"] if account else None,
            })
            self.active_trade_db_id = None

        if pnl <= 0:
            bot_config.consecutive_losses += 1
            bot_config.last_sl_hit_time = datetime.now(timezone.utc).isoformat()
        else:
            bot_config.consecutive_losses = 0

        return {"success": True, "pnl": pnl, "pips": pips}

    async def close_all_positions(self) -> list[dict]:
        """Emergency close all positions."""
        results = mt5_connector.close_all_positions()
        for r in results:
            if r.get("success") and self.active_trade_db_id:
                account = mt5_connector.get_account_info()
                await update_trade_exit(self.active_trade_db_id, {
                    "exit_timestamp": datetime.now(timezone.utc).isoformat(),
                    "exit_price": 0,
                    "result": "emergency",
                    "pips": 0,
                    "pnl_eur": 0,
                    "duration_minutes": 0,
                    "exit_reason": "emergency_close",
                    "account_balance_at_exit": account["balance"] if account else None,
                })
                self.active_trade_db_id = None
        return results

    def _calculate_risk_eur(self, lot_size: float, sl_distance: float) -> float:
        symbol_info = mt5_connector.symbol_info or {}
        pip_value = symbol_info.get("pip_value", 1.0)
        tick_size = symbol_info.get("tick_size", 0.01)
        if tick_size > 0:
            pips = sl_distance / tick_size
            return round(lot_size * pips * pip_value, 2)
        return 0


trade_manager = TradeManager()
