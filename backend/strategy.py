"""Strategy rules: trend identification, entry signals, SL/TP, filters.

# =============================================================================
# DUAL-MODE STRATEGY (April 2026)
# =============================================================================
#
# MODE DETECTION (4H chart):
#   - Trend Mode: 4H EMA50 and EMA200 separated by > 0.3% of price.
#     Trade pullbacks to EMA20 on H1 in the direction of the trend.
#   - Range Mode: 4H EMA50 and EMA200 within 0.3% of price.
#     Trade mean reversion off EMA20 on H1 with MACD histogram confirmation.
#
# ENTRY (H1 chart):
#   - Proximity: price within 0.15% of EMA20 on H1
#   - RSI zone-based (not crossover):
#       Buy zone:  RSI between 25 and 42
#       Sell zone: RSI between 58 and 75
#   - MACD histogram (12, 26, 9):
#       Buy:  histogram turning positive (current > previous)
#       Sell: histogram turning negative (current < previous)
#   - In Trend Mode: EMA20 proximity + RSI zone required
#   - In Range Mode: EMA20 proximity + RSI zone + MACD histogram required
#
# SESSION WINDOWS:
#   - Early London: 06:00-08:00 UTC
#   - London:       08:00-16:00 UTC  (overlap with NY 12:00-16:00)
#   - New York:     12:00-21:00 UTC
#   - Asian:        21:00-06:00 UTC  (no new trades unless AI conf > 85)
#
# CONFIDENCE THRESHOLDS:
#   - Trend Mode: 70%  (higher bar for bigger trend trades)
#   - Range Mode: 60%  (lower bar for predictable mean reversion)
#
# SL/TP: unchanged from original (1.5x ATR SL, 2.5x ATR TP, trailing logic)
# =============================================================================
"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


# =============================================================================
# MODE DETECTION
# =============================================================================

def identify_trend(h4_indicators: dict, current_price: float | None = None) -> str:
    """
    Identify market mode from H4 indicators.
    Returns: "uptrend", "downtrend", or "range"
    """
    ema50 = h4_indicators.get("ema_50")
    ema200 = h4_indicators.get("ema_200")

    if ema50 is None or ema200 is None:
        return "unknown"

    # Use current_price for percentage calc, fall back to midpoint of EMAs
    ref_price = current_price if current_price else (ema50 + ema200) / 2
    if ref_price == 0:
        return "unknown"

    separation_pct = abs(ema50 - ema200) / ref_price * 100

    if separation_pct < 0.3:
        return "range"
    elif ema50 > ema200:
        return "uptrend"
    else:
        return "downtrend"


def get_market_mode(trend: str) -> str:
    """Return 'trend' or 'range' based on trend classification."""
    if trend in ("uptrend", "downtrend"):
        return "trend"
    return "range"


def get_confidence_threshold(mode: str) -> int:
    """Get minimum confidence threshold based on market mode."""
    if mode == "trend":
        return 70
    return 60  # range mode


# =============================================================================
# SESSION DETECTION
# =============================================================================

def get_current_session(utc_now: datetime | None = None) -> str:
    """Determine current trading session."""
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    hour = utc_now.hour

    if 6 <= hour < 8:
        return "early_london"
    elif 8 <= hour < 12:
        return "london"
    elif 12 <= hour < 16:
        return "london_newyork"  # overlap
    elif 16 <= hour < 21:
        return "new_york"
    else:
        return "asian"


def is_trading_session(session: str) -> bool:
    """Check if current session allows new trades."""
    return session in ("early_london", "london", "london_newyork", "new_york")


def get_session_display_name(session: str) -> str:
    """Friendly session name for UI/AI."""
    return {
        "early_london": "Early London",
        "london": "London",
        "london_newyork": "London/New York Overlap",
        "new_york": "New York",
        "asian": "Asian",
    }.get(session, session)


# =============================================================================
# ENTRY SIGNAL HELPERS
# =============================================================================

def check_ema20_proximity(current_close: float, ema20: float) -> bool:
    """Check if price is within 0.15% of EMA20."""
    if ema20 == 0:
        return False
    distance_pct = abs(current_close - ema20) / ema20 * 100
    return distance_pct <= 0.15


def check_rsi_buy_zone(rsi: float) -> bool:
    """RSI between 25 and 42 = buy zone."""
    return 25 <= rsi <= 42


def check_rsi_sell_zone(rsi: float) -> bool:
    """RSI between 58 and 75 = sell zone."""
    return 58 <= rsi <= 75


def check_macd_turning_positive(macd_hist: float, macd_hist_prev: float) -> bool:
    """MACD histogram turning positive (current > previous)."""
    return macd_hist > macd_hist_prev


def check_macd_turning_negative(macd_hist: float, macd_hist_prev: float) -> bool:
    """MACD histogram turning negative (current < previous)."""
    return macd_hist < macd_hist_prev


# =============================================================================
# BUY / SELL SIGNAL CHECKS
# =============================================================================

def check_buy_signal(h1_indicators: dict, h4_trend: str, session: str,
                     news_clear: bool) -> dict:
    """Check if all BUY entry conditions are met under dual-mode strategy."""
    reasons = []
    mode = get_market_mode(h4_trend)

    # Trend mode requires uptrend; range mode allows buys regardless of EMA order
    if mode == "trend" and h4_trend != "uptrend":
        return {"signal": False, "reasons": [f"Trend mode active but trend is {h4_trend}, need uptrend for BUY"]}

    ema20 = h1_indicators.get("ema_20")
    rsi = h1_indicators.get("rsi_14")
    current_close = h1_indicators.get("current_close")
    macd_hist = h1_indicators.get("macd_histogram")
    macd_hist_prev = h1_indicators.get("macd_histogram_prev")

    if any(v is None for v in [ema20, rsi, current_close]):
        return {"signal": False, "reasons": ["Insufficient indicator data"]}

    # EMA20 proximity check
    if not check_ema20_proximity(current_close, ema20):
        distance_pct = abs(current_close - ema20) / ema20 * 100 if ema20 else 0
        reasons.append(f"Price not near EMA20 ({distance_pct:.3f}% away, need <= 0.15%)")

    # RSI zone check
    if not check_rsi_buy_zone(rsi):
        reasons.append(f"RSI {rsi:.1f} outside buy zone (25-42)")

    # MACD confirmation — required in Range Mode, optional boost in Trend Mode
    if macd_hist is not None and macd_hist_prev is not None:
        if mode == "range" and not check_macd_turning_positive(macd_hist, macd_hist_prev):
            reasons.append(f"MACD histogram not turning positive ({macd_hist:.5f} <= {macd_hist_prev:.5f})")
    elif mode == "range":
        reasons.append("MACD data unavailable for range mode confirmation")

    # News filter
    if not news_clear:
        reasons.append("High-impact news event nearby")

    # Session filter
    if not is_trading_session(session):
        reasons.append(f"Outside trading session ({session})")

    if reasons:
        return {"signal": False, "reasons": reasons, "mode": mode}

    return {"signal": True, "reasons": ["All BUY conditions met"], "mode": mode}


def check_sell_signal(h1_indicators: dict, h4_trend: str, session: str,
                      news_clear: bool) -> dict:
    """Check if all SELL entry conditions are met under dual-mode strategy."""
    reasons = []
    mode = get_market_mode(h4_trend)

    # Trend mode requires downtrend; range mode allows sells regardless
    if mode == "trend" and h4_trend != "downtrend":
        return {"signal": False, "reasons": [f"Trend mode active but trend is {h4_trend}, need downtrend for SELL"]}

    ema20 = h1_indicators.get("ema_20")
    rsi = h1_indicators.get("rsi_14")
    current_close = h1_indicators.get("current_close")
    macd_hist = h1_indicators.get("macd_histogram")
    macd_hist_prev = h1_indicators.get("macd_histogram_prev")

    if any(v is None for v in [ema20, rsi, current_close]):
        return {"signal": False, "reasons": ["Insufficient indicator data"]}

    # EMA20 proximity check
    if not check_ema20_proximity(current_close, ema20):
        distance_pct = abs(current_close - ema20) / ema20 * 100 if ema20 else 0
        reasons.append(f"Price not near EMA20 ({distance_pct:.3f}% away, need <= 0.15%)")

    # RSI zone check
    if not check_rsi_sell_zone(rsi):
        reasons.append(f"RSI {rsi:.1f} outside sell zone (58-75)")

    # MACD confirmation — required in Range Mode
    if macd_hist is not None and macd_hist_prev is not None:
        if mode == "range" and not check_macd_turning_negative(macd_hist, macd_hist_prev):
            reasons.append(f"MACD histogram not turning negative ({macd_hist:.5f} >= {macd_hist_prev:.5f})")
    elif mode == "range":
        reasons.append("MACD data unavailable for range mode confirmation")

    # News filter
    if not news_clear:
        reasons.append("High-impact news event nearby")

    # Session filter
    if not is_trading_session(session):
        reasons.append(f"Outside trading session ({session})")

    if reasons:
        return {"signal": False, "reasons": reasons, "mode": mode}

    return {"signal": True, "reasons": ["All SELL conditions met"], "mode": mode}


# =============================================================================
# SL / TP / TRAILING (unchanged from original)
# =============================================================================

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


# =============================================================================
# WEEKEND / COOLDOWN FILTERS (unchanged from original)
# =============================================================================

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


# =============================================================================
# OLD STRATEGY (commented out for rollback reference)
# =============================================================================
#
# def identify_trend_OLD(h4_indicators: dict) -> str:
#     """OLD STRATEGY: Identify trend from H4 indicators using ATR-based threshold."""
#     ema50 = h4_indicators.get("ema_50")
#     ema200 = h4_indicators.get("ema_200")
#     atr = h4_indicators.get("atr_14")
#
#     if ema50 is None or ema200 is None or atr is None:
#         return "unknown"
#
#     diff = abs(ema50 - ema200)
#     if diff < 0.5 * atr:
#         return "sideways"
#     elif ema50 > ema200:
#         return "uptrend"
#     else:
#         return "downtrend"
#
#
# def get_current_session_OLD(utc_now: datetime | None = None) -> str:
#     """OLD STRATEGY: Session detection without early London window."""
#     if utc_now is None:
#         utc_now = datetime.now(timezone.utc)
#     hour = utc_now.hour
#
#     if 7 <= hour < 12:
#         return "london"
#     elif 12 <= hour < 16:
#         return "london_newyork"
#     elif 16 <= hour < 21:
#         return "new_york"
#     else:
#         return "asian"
#
#
# def check_buy_signal_OLD(h1_indicators: dict, h4_trend: str, session: str,
#                          news_clear: bool) -> dict:
#     """OLD STRATEGY: BUY signal using EMA50 proximity + RSI crossover."""
#     reasons = []
#
#     if h4_trend != "uptrend":
#         return {"signal": False, "reasons": [f"Trend is {h4_trend}, need uptrend"]}
#
#     ema50 = h1_indicators.get("ema_50")
#     atr = h1_indicators.get("atr_14")
#     rsi = h1_indicators.get("rsi_14")
#     rsi_prev = h1_indicators.get("rsi_14_prev")
#     current_close = h1_indicators.get("current_close")
#
#     if any(v is None for v in [ema50, atr, rsi, rsi_prev, current_close]):
#         return {"signal": False, "reasons": ["Insufficient indicator data"]}
#
#     # Price pulled back to within 1x ATR of EMA 50
#     distance = abs(current_close - ema50)
#     if distance > atr:
#         reasons.append(f"Price too far from EMA50 ({distance:.2f} > ATR {atr:.2f})")
#
#     # RSI dipped below 40 and crossed back above
#     rsi_cross = rsi_prev < 40 and rsi > 40
#     if not rsi_cross:
#         reasons.append(f"RSI no bullish cross (prev={rsi_prev:.1f}, curr={rsi:.1f})")
#
#     # Current candle closes above EMA 50
#     if current_close <= ema50:
#         reasons.append(f"Close {current_close:.2f} below EMA50 {ema50:.2f}")
#
#     if not news_clear:
#         reasons.append("High-impact news event nearby")
#
#     if not is_trading_session(session):
#         reasons.append(f"Outside trading session ({session})")
#
#     if reasons:
#         return {"signal": False, "reasons": reasons}
#
#     return {"signal": True, "reasons": ["All BUY conditions met"]}
#
#
# def check_sell_signal_OLD(h1_indicators: dict, h4_trend: str, session: str,
#                           news_clear: bool) -> dict:
#     """OLD STRATEGY: SELL signal using EMA50 proximity + RSI crossover."""
#     reasons = []
#
#     if h4_trend != "downtrend":
#         return {"signal": False, "reasons": [f"Trend is {h4_trend}, need downtrend"]}
#
#     ema50 = h1_indicators.get("ema_50")
#     atr = h1_indicators.get("atr_14")
#     rsi = h1_indicators.get("rsi_14")
#     rsi_prev = h1_indicators.get("rsi_14_prev")
#     current_close = h1_indicators.get("current_close")
#
#     if any(v is None for v in [ema50, atr, rsi, rsi_prev, current_close]):
#         return {"signal": False, "reasons": ["Insufficient indicator data"]}
#
#     distance = abs(current_close - ema50)
#     if distance > atr:
#         reasons.append(f"Price too far from EMA50 ({distance:.2f} > ATR {atr:.2f})")
#
#     # RSI pushed above 60 and crossed back below
#     rsi_cross = rsi_prev > 60 and rsi < 60
#     if not rsi_cross:
#         reasons.append(f"RSI no bearish cross (prev={rsi_prev:.1f}, curr={rsi:.1f})")
#
#     if current_close >= ema50:
#         reasons.append(f"Close {current_close:.2f} above EMA50 {ema50:.2f}")
#
#     if not news_clear:
#         reasons.append("High-impact news event nearby")
#
#     if not is_trading_session(session):
#         reasons.append(f"Outside trading session ({session})")
#
#     if reasons:
#         return {"signal": False, "reasons": reasons}
#
#     return {"signal": True, "reasons": ["All SELL conditions met"]}
