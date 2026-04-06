"""Claude API integration, prompt building, response parsing."""

import json
import logging
import anthropic

logger = logging.getLogger(__name__)

# =============================================================================
# OLD SYSTEM PROMPT (kept for rollback reference)
# =============================================================================
# SYSTEM_PROMPT_OLD = """You are a professional XAUEUR trading analyst...
#   - Only BUY in an uptrend (4H EMA 50 > EMA 200)
#   - Only SELL in a downtrend (4H EMA 50 < EMA 200)
#   - No trades in sideways markets
#   - Entry: price pulls back to EMA 50 on H1 with RSI confirmation
#   - [single confidence threshold of 70%]
# """

SYSTEM_PROMPT = """You are a professional XAUEUR trading analyst using a dual-mode strategy. Your job is to analyze the current market data and decide whether to enter a trade, hold, or close an existing position.

DUAL-MODE STRATEGY (you must follow these strictly):

MODE DETECTION:
- The system tells you which mode is active: TREND or RANGE.
- TREND MODE: 4H EMA50 and EMA200 are clearly separated (>0.3% of price). Trade pullbacks in the direction of the trend.
  - Only BUY in an uptrend (4H EMA 50 > EMA 200)
  - Only SELL in a downtrend (4H EMA 50 < EMA 200)
- RANGE MODE: 4H EMA50 and EMA200 are close together (<=0.3% of price). Trade mean reversion.
  - Both BUY and SELL are allowed based on RSI zone and MACD confirmation.

ENTRY CONDITIONS (all must be met):
1. Price is within 0.15% of EMA20 on H1 (proximity confirmed — see ema20_proximity field)
2. RSI zone:
   - BUY: RSI 14 between 25 and 42 (see rsi_zone field)
   - SELL: RSI 14 between 58 and 75
3. MACD histogram (12, 26, 9):
   - BUY: histogram turning positive (current > previous — see macd_direction field)
   - SELL: histogram turning negative (current < previous)
   - In TREND mode, MACD is a bonus confirmation. In RANGE mode, MACD is required.
4. No high-impact news within 30 min before / 15 min after
5. Valid session: Early London (06-08 UTC), London (08-16 UTC), or New York (12-21 UTC)

RISK MANAGEMENT (unchanged):
- Stop-loss: 1.5x ATR from entry
- Take-profit: 2.5x ATR from entry, then trail at 1x ATR below/above EMA 50
- No trading during Asian session unless confidence > 85

CONFIDENCE THRESHOLDS:
- TREND mode: minimum 70% to recommend a trade
- RANGE mode: minimum 60% to recommend a trade

ANALYSIS FRAMEWORK (evaluate each point):
1. Which mode is active (Trend or Range) and is the setup appropriate for that mode?
2. Is price near EMA20? Is the RSI in the correct zone?
3. Is the MACD histogram confirming the direction?
4. Is there a news event that could invalidate this setup?
5. Is the risk-reward ratio at least 1:1.67?
6. Does the current session support this trade?
7. What do recent trade results suggest about current market conditions?
8. For open positions: should the trailing stop be updated? Should the position be closed early?

In your reasoning, EXPLICITLY STATE which conditions are met and which are not.

RESPOND WITH ONLY THIS JSON (no other text):
{
  "action": "buy or sell or hold or close or update_sl",
  "confidence": "0-100",
  "entry_price": "number or null",
  "stop_loss": "number or null",
  "take_profit": "number or null",
  "recommended_lot": "number or null",
  "new_sl": "number or null (only for update_sl action)",
  "reasoning": "2-3 sentence explanation — state which conditions are met/not met"
}"""


class AIEngine:
    def __init__(self):
        self.client = None
        self.consecutive_failures = 0
        self.last_analysis_candle = None

    def initialize(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.consecutive_failures = 0

    async def analyze(self, data_packet: dict) -> dict | None:
        """Send market data to Claude and get trading decision."""
        if self.client is None:
            return None

        # Build the user message with all market data
        user_message = f"""Current market data for XAUEUR analysis:

{json.dumps(data_packet, indent=2, default=str)}

Analyze this data according to the dual-mode strategy rules and provide your trading decision."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            # Parse the response
            text = response.content[0].text.strip()

            # Try to extract JSON from the response
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)
            self.consecutive_failures = 0

            # Validate required fields
            required = ["action", "confidence", "reasoning"]
            for field in required:
                if field not in result:
                    logger.error(f"AI response missing field: {field}")
                    return None

            # Ensure confidence is an integer
            result["confidence"] = int(result["confidence"])

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            self.consecutive_failures += 1
            return None
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            self.consecutive_failures += 1
            return None
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            self.consecutive_failures += 1
            return None

    def build_data_packet(self, price: dict, h1_candles_json: list,
                          h4_candles_json: list, h1_indicators: dict,
                          h4_indicators: dict, trend: str, account: dict,
                          positions: list, upcoming_events: list,
                          session: str, last_trades: list,
                          risk_pct: float, max_lot: float,
                          market_mode: str = "trend",
                          session_display: str = "",
                          ema20_proximity: bool = False,
                          rsi_zone: str = "neutral",
                          macd_direction: str = "neutral") -> dict:
        """Build the data packet to send to Claude."""
        return {
            "current_price": price,
            "h1_candles": f"[{len(h1_candles_json)} candles, latest: {h1_candles_json[-1] if h1_candles_json else 'none'}]",
            "h4_candles": f"[{len(h4_candles_json)} candles, latest: {h4_candles_json[-1] if h4_candles_json else 'none'}]",
            "indicators": {
                "h1": h1_indicators,
                "h4": h4_indicators,
            },
            "trend": trend,
            "market_mode": market_mode,
            "active_session": session_display or session,
            "ema20_proximity": ema20_proximity,
            "rsi_zone": rsi_zone,
            "macd_direction": macd_direction,
            "account": account,
            "open_positions": positions,
            "upcoming_events": upcoming_events,
            "current_session": session,
            "last_5_trades": last_trades,
            "risk_per_trade_pct": risk_pct,
            "max_lot_calculated": max_lot,
        }

    def is_available(self) -> bool:
        return self.client is not None and self.consecutive_failures < 3


ai_engine = AIEngine()
