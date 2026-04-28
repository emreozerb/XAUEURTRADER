"""Lot size calculator, risk validation, and safety checks."""

import logging

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self):
        pass

    def calculate_lot_size(self, account_balance: float, free_margin: float,
                          risk_pct: float, sl_distance: float,
                          symbol_info: dict,
                          min_trade_lot_floor: float = 0.0) -> dict:
        """
        Calculate recommended lot size based on risk parameters.
        Returns lot size and risk details.

        min_trade_lot_floor: optional Phase 5 floor — when risk-based lot
        falls below this (but above broker min), bump up to this floor.
        Result will exceed the configured risk_pct; reported as
        floor_applied=True for caller logging.
        """
        # Cap risk at 10% (Phase 4 — raised from 5%)
        risk_pct = min(risk_pct, 10.0)
        risk_amount = account_balance * (risk_pct / 100)

        pip_value = symbol_info.get("pip_value", 1.0)
        tick_size = symbol_info.get("tick_size", 0.01)
        min_lot = symbol_info.get("min_lot", 0.01)
        max_lot = symbol_info.get("max_lot", 100.0)
        lot_step = symbol_info.get("lot_step", 0.01)
        contract_size = symbol_info.get("contract_size", 100)

        if sl_distance <= 0 or pip_value <= 0:
            return {"valid": False, "error": "Invalid SL distance or pip value."}

        # Calculate pip value per lot
        sl_pips = sl_distance / tick_size
        pip_value_per_lot = pip_value  # Per lot per tick

        if pip_value_per_lot <= 0 or sl_pips <= 0:
            return {"valid": False, "error": "Cannot calculate lot size with current values."}

        # Lot size = risk amount / (SL in pips * pip value per lot)
        raw_lot = risk_amount / (sl_pips * pip_value_per_lot)

        # Round DOWN to nearest lot step
        lot = int(raw_lot / lot_step) * lot_step
        lot = round(lot, 2)

        # PHASE 5 — minimum trade lot floor (opt-in via min_trade_lot_floor)
        floor_applied = False
        if min_trade_lot_floor > 0 and lot < min_trade_lot_floor and min_trade_lot_floor >= min_lot:
            logger.info(
                f"[lot] Risk-based lot {lot} below configured floor {min_trade_lot_floor} — "
                f"bumping up. This will EXCEED configured risk of {risk_pct}%."
            )
            lot = round(min_trade_lot_floor, 2)
            floor_applied = True

        # Diagnostic log so we can always tell why the lot came out the way it did
        logger.info(
            f"[lot calc] balance={account_balance:.2f} risk_pct={risk_pct}% "
            f"risk_eur={risk_amount:.2f} | sl_dist={sl_distance:.5f} tick={tick_size} "
            f"sl_pips={sl_pips:.1f} pip_val/lot={pip_value_per_lot} | "
            f"raw_lot={raw_lot:.4f} -> final_lot={lot} (broker_min={min_lot}, floor={min_trade_lot_floor}, applied={floor_applied})"
        )

        # Check minimum lot
        if lot < min_lot:
            return {
                "valid": False,
                "error": f"Insufficient balance. Calculated lot {lot} below minimum {min_lot}.",
                "calculated_lot": lot,
                "min_lot": min_lot,
                "risk_eur": round(risk_amount, 2),
            }

        # Cap at max lot
        lot = min(lot, max_lot)

        # Margin check: no single trade > 50% of free margin
        # Approximate margin per lot
        estimated_margin = lot * contract_size * symbol_info.get("tick_size", 1)
        if free_margin > 0 and estimated_margin > (0.5 * free_margin):
            # Reduce lot to fit within 50% margin
            max_lot_by_margin = (0.5 * free_margin) / (contract_size * symbol_info.get("tick_size", 1))
            max_lot_by_margin = int(max_lot_by_margin / lot_step) * lot_step
            max_lot_by_margin = round(max_lot_by_margin, 2)
            if max_lot_by_margin < min_lot:
                return {
                    "valid": False,
                    "error": "Insufficient free margin for this trade.",
                    "risk_eur": round(risk_amount, 2),
                }
            lot = min(lot, max_lot_by_margin)

        actual_risk = lot * sl_pips * pip_value_per_lot
        actual_risk_pct = (actual_risk / account_balance * 100) if account_balance > 0 else 0

        return {
            "valid": True,
            "lot_size": lot,
            "risk_eur": round(actual_risk, 2),
            "risk_pct": round(actual_risk_pct, 2),
            "sl_pips": round(sl_pips, 1),
            "risk_reward": None,  # Set by caller
            "floor_applied": floor_applied,
        }

    def validate_trade(self, lot_size: float, account_balance: float,
                       free_margin: float, equity: float,
                       open_positions: list, risk_pct: float,
                       max_positions: int, symbol_info: dict) -> dict:
        """Validate a trade against all hard rules."""
        errors = []

        # Max concurrent positions
        if len(open_positions) >= max_positions:
            errors.append(f"Max positions reached ({max_positions}).")

        # Check for existing XAUEUR positions (no hedging)
        for pos in open_positions:
            if pos.get("direction"):
                errors.append("Cannot hedge - already have an open XAUEUR position.")
                break

        # Total risk across all positions
        total_risk_pct = sum(
            abs(p.get("pnl", 0)) / account_balance * 100
            for p in open_positions
        ) if account_balance > 0 else 0
        if total_risk_pct + risk_pct > 10.0:
            errors.append(f"Total risk would exceed 10% ({total_risk_pct + risk_pct:.1f}%).")

        # Low margin check
        if free_margin < (0.3 * equity) and equity > 0:
            errors.append(f"Low margin: free margin {free_margin:.2f} < 30% of equity {equity:.2f}.")

        # Lot size bounds
        min_lot = symbol_info.get("min_lot", 0.01)
        max_lot = symbol_info.get("max_lot", 100.0)
        if lot_size < min_lot:
            errors.append(f"Lot size {lot_size} below minimum {min_lot}.")
        if lot_size > max_lot:
            errors.append(f"Lot size {lot_size} above maximum {max_lot}.")

        return {"valid": len(errors) == 0, "errors": errors}

    def check_drawdown_limit(self, current_equity: float, start_balance: float) -> dict:
        """Check if max drawdown (20%) has been reached."""
        if start_balance <= 0:
            return {"exceeded": False}

        drawdown_pct = ((start_balance - current_equity) / start_balance) * 100
        return {
            "exceeded": drawdown_pct >= 20,
            "drawdown_pct": round(drawdown_pct, 2),
            "drawdown_eur": round(start_balance - current_equity, 2),
        }

    def check_margin_safety(self, free_margin: float, equity: float) -> bool:
        """Check if free margin is above 30% of equity."""
        if equity <= 0:
            return False
        return free_margin >= (0.3 * equity)


risk_manager = RiskManager()
