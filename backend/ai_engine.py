"""Claude API integration, prompt building, response parsing."""

import json
import logging
import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional XAUEUR trading analyst. Your job is to analyze the current market data and decide whether to enter a trade, hold, or close an existing position.

STRATEGY RULES (you must follow these strictly):
- Only BUY in an uptrend (4H EMA 50 > EMA 200)
- Only SELL in a downtrend (4H EMA 50 < EMA 200)
- No trades in sideways markets
- Entry: price pulls back to EMA 50 on H1 with RSI confirmation
- Stop-loss: 1.5x ATR from entry
- Take-profit: 2.5x ATR from entry, then trail at 1x ATR below/above EMA 50
- No trading 30 min before/15 min after high-impact news
- No trading during Asian session unless confidence > 85

ANALYSIS FRAMEWORK (evaluate each point):
1. Is the 4H trend clear and strong, or are the EMAs tangled?
2. Is the H1 pullback clean with a proper RSI signal?
3. Is the entry candle pattern supportive?
4. Is there a news event that could invalidate this setup?
5. Is the risk-reward ratio at least 1:1.67?
6. Does the current session support this trade?
7. What do recent trade results suggest about current market conditions?
8. For open positions: should the trailing stop be updated? Should the position be closed early?

RESPOND WITH ONLY THIS JSON (no other text):
{
  "action": "buy or sell or hold or close or update_sl",
  "confidence": "0-100",
  "entry_price": "number or null",
  "stop_loss": "number or null",
  "take_profit": "number or null",
  "recommended_lot": "number or null",
  "new_sl": "number or null (only for update_sl action)",
  "reasoning": "2-3 sentence explanation of your decision"
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

Analyze this data according to the strategy rules and provide your trading decision."""

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
                          risk_pct: float, max_lot: float) -> dict:
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
