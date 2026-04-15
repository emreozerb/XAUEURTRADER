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

SYSTEM_PROMPT = """You are a professional XAUEUR trading analyst using an aggressive max-frequency strategy. Your job is to analyze the current market data and decide whether to enter a trade, hold, or close an existing position.

PHASE 4 STRATEGY (follow these rules strictly):

TIMEFRAMES:
- Signals are evaluated on M15 candle closes (15-minute chart)
- H4 indicators are provided as context only — they do NOT filter trades

ENTRY CONDITIONS (all must be met):
1. EMA50 proximity: price is within 1.5% of M15 EMA50
2. RSI zone (M15 RSI 14):
   - BUY:  RSI between 25 and 65
   - SELL: RSI between 35 and 75
3. No high-impact news within 30 min before / 15 min after (see upcoming_events)
4. No duplicate position in the same direction already open

TREND FILTER: NONE — BUY and SELL are both allowed in any market condition (uptrend, downtrend, range). H4 EMA50/EMA200 trend data is provided for your situational awareness and reasoning only. Do not use it to block trades.

SESSION: No session restriction — trade all sessions 24/5 (session shown for context only).

RISK MANAGEMENT:
- Stop-loss: 0.75× ATR from entry (tight stop — high frequency)
- Take-profit: 2.5× ATR from entry
- Risk/reward ≈ 1:3.3
- Trailing stop: activates after 1.5× ATR profit, trails at 1× ATR below/above M15 EMA50
- Maximum drawdown: 20% of balance — bot stops if exceeded (enforced by system)

CONFIDENCE THRESHOLD: minimum 45% to recommend a trade. Express genuine confidence — do not inflate scores.

ANALYSIS FRAMEWORK (evaluate each point explicitly):
1. Is price within 1.5% of M15 EMA50?
2. Is M15 RSI in the correct zone (25-65 buy / 35-75 sell)?
3. Are any high-impact news events nearby?
4. Is there already an open position in the same direction?
5. What does the H4 trend context suggest about likely direction? (informational only)
6. Is the risk-reward favourable (SL 0.75× ATR, TP 2.5× ATR, R:R ≈ 1:3.3)?
7. What do recent trade results suggest about current conditions?
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
        self.last_error_reason: str | None = None  # human-readable cause of last failure
        self.last_error_is_fatal: bool = False      # True = will never self-heal (bad key, no credits)

    def initialize(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.consecutive_failures = 0
        self.last_error_reason = None
        self.last_error_is_fatal = False

    def _classify_api_error(self, exc: anthropic.APIError) -> str:
        """Return a clear human-readable reason for an Anthropic API error."""
        # Out-of-credits: status 402, or 400/403 with billing message
        if hasattr(exc, "status_code"):
            code = exc.status_code
            body = str(exc).lower()
            if code == 402 or (code in (400, 403) and any(
                kw in body for kw in ("credit", "billing", "balance", "payment")
            )):
                return (
                    "Anthropic credits exhausted — add credits at "
                    "console.anthropic.com/settings/billing"
                )
            if code == 401:
                return "Invalid Anthropic API key — check Settings."
            if code == 403:
                return "Anthropic API access denied — check your API key permissions."
            if code == 429:
                return "Anthropic rate limit reached — too many requests. Bot will retry."
            if code == 529 or code >= 500:
                return f"Anthropic API overloaded or down (HTTP {code}) — will retry."
        if isinstance(exc, anthropic.APIConnectionError):
            return "Cannot reach Anthropic API — check internet connection."
        if isinstance(exc, anthropic.APITimeoutError):
            return "Anthropic API request timed out — will retry."
        return f"Anthropic API error: {exc}"

    async def analyze(self, data_packet: dict) -> dict | None:
        """Send market data to Claude and get trading decision."""
        if self.client is None:
            self.last_error_reason = "AI engine not initialised — API key missing."
            return None

        user_message = f"""Current M15 candle close — XAUEUR market data:

{json.dumps(data_packet, indent=2, default=str)}

Analyze this data according to the Phase 3 strategy rules and provide your trading decision."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)

            # Validate required fields
            required = ["action", "confidence", "reasoning"]
            for field in required:
                if field not in result:
                    logger.error(f"AI response missing field: {field}")
                    self.last_error_reason = f"AI returned incomplete JSON (missing '{field}')."
                    self.consecutive_failures += 1
                    return None

            result["confidence"] = int(result["confidence"])
            self.consecutive_failures = 0
            self.last_error_reason = None
            self.last_error_is_fatal = False
            return result

        except json.JSONDecodeError as e:
            reason = f"AI returned invalid JSON — could not parse response: {e}"
            logger.error(reason)
            self.last_error_reason = reason
            self.last_error_is_fatal = False
            self.consecutive_failures += 1
            return None

        except anthropic.AuthenticationError as e:
            reason = "Invalid Anthropic API key — check Settings."
            logger.error(f"{reason} | {e}")
            self.last_error_reason = reason
            self.last_error_is_fatal = True   # key won't fix itself
            self.consecutive_failures += 1
            return None

        except anthropic.PermissionDeniedError as e:
            reason = self._classify_api_error(e)
            logger.error(f"{reason} | {e}")
            # Credits exhausted is fatal; other 403s may be transient
            self.last_error_is_fatal = "credit" in reason.lower() or "billing" in reason.lower()
            self.last_error_reason = reason
            self.consecutive_failures += 1
            return None

        except anthropic.RateLimitError as e:
            reason = self._classify_api_error(e)
            logger.warning(f"{reason} | {e}")
            self.last_error_reason = reason
            self.last_error_is_fatal = False  # rate limit is transient
            self.consecutive_failures += 1
            return None

        except anthropic.APIStatusError as e:
            reason = self._classify_api_error(e)
            logger.error(f"{reason} | status={e.status_code} | {e}")
            # 401 via generic status path is also fatal
            self.last_error_is_fatal = e.status_code == 401 or e.status_code == 402
            self.last_error_reason = reason
            self.consecutive_failures += 1
            return None

        except anthropic.APIConnectionError as e:
            reason = "Cannot reach Anthropic API — check internet connection."
            logger.error(f"{reason} | {e}")
            self.last_error_reason = reason
            self.last_error_is_fatal = False
            self.consecutive_failures += 1
            return None

        except anthropic.APITimeoutError as e:
            reason = "Anthropic API request timed out — will retry next candle."
            logger.warning(f"{reason} | {e}")
            self.last_error_reason = reason
            self.last_error_is_fatal = False
            self.consecutive_failures += 1
            return None

        except anthropic.APIError as e:
            reason = self._classify_api_error(e)
            logger.error(f"{reason} | {e}")
            self.last_error_reason = reason
            self.last_error_is_fatal = False
            self.consecutive_failures += 1
            return None

        except Exception as e:
            reason = f"Unexpected AI error: {type(e).__name__}: {e}"
            logger.error(reason, exc_info=True)
            self.last_error_reason = reason
            self.last_error_is_fatal = False
            self.consecutive_failures += 1
            return None

    def build_data_packet(self, price: dict, m15_candles_json: list,
                          h4_candles_json: list, m15_indicators: dict,
                          h4_indicators: dict, trend: str, account: dict,
                          positions: list, upcoming_events: list,
                          session: str, last_trades: list,
                          risk_pct: float, max_lot: float,
                          market_mode: str = "trend",
                          session_display: str = "",
                          ema50_proximity: bool = False,
                          rsi_zone: str = "neutral") -> dict:
        """Build the data packet to send to Claude."""
        return {
            "current_price": price,
            "m15_candles": f"[{len(m15_candles_json)} candles, latest: {m15_candles_json[-1] if m15_candles_json else 'none'}]",
            "h4_candles": f"[{len(h4_candles_json)} candles, latest: {h4_candles_json[-1] if h4_candles_json else 'none'}]",
            "indicators": {
                "m15": m15_indicators,
                "h4": h4_indicators,
            },
            "trend": trend,
            "market_mode": market_mode,
            "active_session": session_display or session,
            "ema50_proximity": ema50_proximity,
            "rsi_zone": rsi_zone,
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
