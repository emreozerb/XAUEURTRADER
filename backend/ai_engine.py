"""Claude API integration, prompt building, response parsing."""

import json
import logging
import re
import anthropic

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> str | None:
    """
    Extract the first balanced JSON object from a string.
    Handles AI responses that wrap JSON in prose, code fences, or extra text.
    Returns the JSON substring or None if no object found.
    """
    if not text:
        return None

    # Strip markdown code fences anywhere in the string
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)

    # Find first '{' and walk forward to its matching '}', respecting strings
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None

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

SYSTEM_PROMPT = """You are a professional XAUEUR trading analyst using a trend-aligned high-frequency strategy. Your job is to analyze the current market data and decide whether to enter a trade, hold, or close an existing position.

PHASE 5 STRATEGY (follow these rules strictly):

TIMEFRAMES:
- Signals are evaluated on M15 candle closes (15-minute chart)
- Trend direction is derived from the H4 chart and DOES filter trades

ENTRY CONDITIONS (all must be met):
1. EMA50 proximity: price is within 1.5% of M15 EMA50
2. RSI zone (M15 RSI 14):
   - BUY:  RSI between 25 and 65
   - SELL: RSI between 35 and 75
3. No high-impact news within 30 min before / 15 min after (see upcoming_events)
4. No open position at all — only one trade at a time (BUY or SELL)

TREND FILTER (RESTORED in Phase 5):
- BUY is allowed only when H4 trend is "uptrend" or "range"
- SELL is allowed only when H4 trend is "downtrend" or "range"
- Trading against the H4 trend is not permitted

SESSION: No session restriction — trade all sessions 24/5 (session shown for context only).

RISK MANAGEMENT (Phase 5 — small frequent wins):
- Stop-loss: 1.5× ATR from entry  (wider stop → smaller lots per fixed risk)
- Take-profit: 1.0× ATR from entry  (closer target → higher win rate)
- Risk/reward ≈ 1.5:1 (≈ 1:0.67) — strategy depends on >60% win rate
- Trailing stop: activates after 1.5× ATR profit, trails at 1× ATR below/above M15 EMA50
- Maximum drawdown: 20% of balance — bot stops if exceeded (enforced by system)

CONFIDENCE THRESHOLD: minimum 65% to recommend a trade. Express genuine confidence — do not inflate scores.

ANALYSIS FRAMEWORK (evaluate each point explicitly):
1. Is the proposed direction aligned with the H4 trend (uptrend → BUY only, downtrend → SELL only, range → either)?
2. Is price within 1.5% of M15 EMA50?
3. Is M15 RSI in the correct zone (25-65 buy / 35-75 sell)?
4. Are any high-impact news events nearby?
5. Is any position already open? (If yes, no new entry permitted.)
6. Is the risk-reward acceptable given the win-rate-dependent design (SL 1.5× ATR, TP 1.0× ATR)?
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
        import os
        import inspect
        caller_file = inspect.stack()[1].filename
        masked = f"{api_key[:18]}...{api_key[-6:]}" if len(api_key) > 24 else f"({len(api_key)} chars — too short)"
        env_key = (os.environ.get("ANTHROPIC_API_KEY") or "")
        env_masked = f"{env_key[:18]}...{env_key[-6:]}" if len(env_key) > 24 else f"not set or too short"
        logger.info(
            f"AI engine initialising | caller={caller_file} | "
            f"key-in-use={masked} | env-key={env_masked} | match={'YES' if api_key == env_key else 'NO'}"
        )
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

Analyze this data according to the Phase 5 strategy rules and provide your trading decision."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = (response.content[0].text or "").strip() if response.content else ""

            if not raw_text:
                stop_reason = getattr(response, "stop_reason", "unknown")
                usage = getattr(response, "usage", None)
                logger.error(
                    f"AI returned empty response | stop_reason={stop_reason} | usage={usage}"
                )
                self.last_error_reason = (
                    f"AI returned empty response (stop_reason={stop_reason}). "
                    "Likely max_tokens too low or content filter."
                )
                self.last_error_is_fatal = False
                self.consecutive_failures += 1
                return None

            # Extract JSON object from the response (handles prose-wrapped or fenced output)
            json_text = _extract_json_object(raw_text)
            if json_text is None:
                preview = raw_text[:500].replace("\n", " ")
                logger.error(
                    f"AI response contained no JSON object. Raw text (first 500 chars): {preview}"
                )
                self.last_error_reason = (
                    "AI returned prose without JSON. See logs for raw response."
                )
                self.last_error_is_fatal = False
                self.consecutive_failures += 1
                return None

            try:
                result = json.loads(json_text)
            except json.JSONDecodeError as e:
                preview = json_text[:500].replace("\n", " ")
                logger.error(
                    f"AI returned malformed JSON: {e} | extracted: {preview}"
                )
                self.last_error_reason = f"AI returned malformed JSON — {e}"
                self.last_error_is_fatal = False
                self.consecutive_failures += 1
                return None

            # Validate required fields
            required = ["action", "confidence", "reasoning"]
            for field in required:
                if field not in result:
                    logger.error(f"AI response missing field: {field} | raw: {raw_text[:300]}")
                    self.last_error_reason = f"AI returned incomplete JSON (missing '{field}')."
                    self.consecutive_failures += 1
                    return None

            try:
                result["confidence"] = int(float(result["confidence"]))
            except (ValueError, TypeError):
                logger.error(f"AI returned non-numeric confidence: {result.get('confidence')!r}")
                self.last_error_reason = "AI returned non-numeric confidence value."
                self.consecutive_failures += 1
                return None

            self.consecutive_failures = 0
            self.last_error_reason = None
            self.last_error_is_fatal = False
            return result

        except anthropic.AuthenticationError as e:
            import os
            key_in_client = (self.client.api_key if hasattr(self.client, "api_key") else "unknown")
            env_key = (os.environ.get("ANTHROPIC_API_KEY") or "")
            masked_client = f"{key_in_client[:18]}...{key_in_client[-6:]}" if len(key_in_client) > 24 else f"({len(key_in_client)} chars)"
            masked_env = f"{env_key[:18]}...{env_key[-6:]}" if len(env_key) > 24 else "not set"
            reason = "Invalid Anthropic API key — check Settings."
            logger.error(
                f"{reason} | key-sent-to-api={masked_client} | env-ANTHROPIC_API_KEY={masked_env} | {e}"
            )
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
