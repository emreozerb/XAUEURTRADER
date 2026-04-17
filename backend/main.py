"""FastAPI app entry point — XAUEUR AI Trading Bot."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings, bot_config
from .database import (
    init_db, log_analysis, log_event, get_event_log,
    get_trade_log, get_performance_summary, get_last_n_trades,
)
from .mt5_connector import mt5_connector
from .indicators import calculate_indicators
from .strategy import (
    identify_trend, get_current_session,
    check_buy_signal, check_sell_signal, check_ema50_proximity,
    calculate_sl_tp, check_weekend_close, check_cooldown,
    get_market_mode, get_session_display_name, get_test_signal,
)
from .ai_engine import ai_engine
from .risk_manager import risk_manager
from .trade_manager import trade_manager
from .calendar import economic_calendar
from .websocket_manager import ws_manager
from .backtester import run_backtest
from .logger import setup_logging, attach_ws_handler

setup_logging()
logger = logging.getLogger(__name__)

# =============================================================================
# TEST MODE — set True to fire an unconditional BUY on every H1 candle close.
# Bypasses all strategy/session/news/cooldown filters so you can verify the
# full order-execution pipeline on a demo account within one hour.
# Set back to False once execution is confirmed working.
# =============================================================================
TEST_MODE = False


async def log_and_alert(message: str, level: str = "info", source: str = "system") -> None:
    """Persist event to DB and broadcast to all connected WebSocket clients."""
    await log_event(level, message, source)
    await ws_manager.broadcast_alert(message, level)
    log_fn = logger.error if level == "error" else logger.warning if level == "warning" else logger.info
    log_fn(f"[{source}] {message}")


async def soft_pause(hours: float, reason: str, source: str = "system") -> None:
    """
    Soft pause: keep bot_running=True so the loop stays alive,
    but set bot_status='paused' + pause_until timestamp.
    The analysis loop will skip candles until the timer expires then auto-resume.
    """
    pause_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    bot_config.bot_status = "paused"
    bot_config.pause_until = pause_until.isoformat()
    resume_str = pause_until.strftime("%H:%M UTC")
    msg = f"{reason} — bot paused for {hours:.0f}h, resumes at {resume_str}."
    await log_and_alert(msg, "warning", source)
    await ws_manager.broadcast_status({
        "bot_status": "paused",
        "pause_until": bot_config.pause_until,
    })


# Background tasks
_bot_task: asyncio.Task | None = None
_monitor_task: asyncio.Task | None = None
_connection_task: asyncio.Task | None = None
_connection_monitor_task: asyncio.Task | None = None  # runs always while connected
_analysis_running: bool = False  # guard against concurrent analysis cycles


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized.")
    attach_ws_handler(ws_manager)
    yield
    # Shutdown
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
    if _connection_task and not _connection_task.done():
        _connection_task.cancel()
    mt5_connector.shutdown()
    logger.info("Shutdown complete.")


app = FastAPI(title="XAUEUR Trading Bot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic models ───────────────────────────────────────────────

class MT5Credentials(BaseModel):
    account: int
    password: str
    server: str
    symbol: str = "XAUEUR"


class BotSettings(BaseModel):
    risk_per_trade_pct: float = 2.0
    finnhub_api_key: str = ""


class BacktestConfig(BaseModel):
    period_months: int = 3
    starting_balance: float = 10000


# ─── REST endpoints ────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    account = mt5_connector.get_account_info() if mt5_connector.connected else None
    positions = mt5_connector.get_positions() if mt5_connector.connected else []
    price = mt5_connector.get_current_price() if mt5_connector.connected else None

    return {
        "connected": mt5_connector.connected,
        "bot_status": bot_config.bot_status,
        "bot_running": bot_config.bot_running,
        "error_message": bot_config.error_message,
        "pause_until": bot_config.pause_until,
        "account": account,
        "positions": positions,
        "current_price": price,
        "symbol": bot_config.symbol,
        "risk_per_trade_pct": bot_config.risk_per_trade_pct,
    }


@app.post("/api/connect")
async def connect_mt5(creds: MT5Credentials):
    global _connection_monitor_task
    result = mt5_connector.initialize(creds.account, creds.password, creds.server, creds.symbol)
    if result["success"]:
        bot_config.mt5_account = creds.account
        bot_config.mt5_password = creds.password
        bot_config.mt5_server = creds.server
        bot_config.symbol = creds.symbol
        await log_and_alert("MT5 connected successfully.", "success", "mt5")
        # Start passive connection monitor — runs for the whole session, not just while bot is running
        if _connection_monitor_task is None or _connection_monitor_task.done():
            _connection_monitor_task = asyncio.create_task(_connection_monitor_loop())
    return result


@app.post("/api/disconnect")
async def disconnect_mt5():
    global _connection_monitor_task
    if _connection_monitor_task and not _connection_monitor_task.done():
        _connection_monitor_task.cancel()
    mt5_connector.shutdown()
    bot_config.bot_running = False
    bot_config.bot_status = "stopped"
    return {"success": True}


@app.post("/api/settings")
async def update_settings(s: BotSettings):
    bot_config.risk_per_trade_pct = min(max(s.risk_per_trade_pct, 1.0), 10.0)
    if s.finnhub_api_key:
        settings.finnhub_api_key = s.finnhub_api_key
    return {"success": True}


@app.post("/api/bot/start")
async def start_bot():
    global _bot_task, _monitor_task, _connection_task

    if not mt5_connector.connected:
        raise HTTPException(400, "MT5 not connected.")
    if not settings.anthropic_api_key:
        raise HTTPException(400, "ANTHROPIC_API_KEY not set in .env file.")
    # Always (re-)initialize from .env — key is never taken from the UI
    ai_engine.initialize(settings.anthropic_api_key)

    account = mt5_connector.get_account_info()
    if account:
        bot_config.start_balance = account["balance"]

    # Cancel any existing tasks before starting new ones — prevents duplicate loops
    for task in [_bot_task, _monitor_task, _connection_task]:
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    bot_config.bot_running = True
    bot_config.bot_status = "running"
    bot_config.error_message = None
    bot_config.consecutive_losses = 0
    bot_config.last_user_interaction = datetime.now(timezone.utc).isoformat()

    # Start background loops
    _bot_task = asyncio.create_task(_analysis_loop())
    _monitor_task = asyncio.create_task(_position_monitor_loop())
    _connection_task = asyncio.create_task(_connection_check_loop())

    await log_and_alert("Bot started.", "success", "bot")
    return {"success": True}


@app.post("/api/bot/stop")
async def stop_bot():
    global _bot_task, _monitor_task, _connection_task
    bot_config.bot_running = False
    bot_config.bot_status = "stopped"
    for task in [_bot_task, _monitor_task, _connection_task]:
        if task and not task.done():
            task.cancel()

    await log_and_alert("Bot stopped. Open positions remain with SL/TP.", "info", "bot")
    return {"success": True}


@app.post("/api/emergency-close")
async def emergency_close():
    bot_config.last_user_interaction = datetime.now(timezone.utc).isoformat()
    results = await trade_manager.close_all_positions()
    bot_config.bot_running = False
    bot_config.bot_status = "stopped"

    global _bot_task, _monitor_task
    for task in [_bot_task, _monitor_task]:
        if task and not task.done():
            task.cancel()

    await log_and_alert("ALL POSITIONS CLOSED. Bot stopped.", "error", "emergency")
    return {"success": True, "results": results}


@app.get("/api/events")
async def get_events(limit: int = 200):
    """Return persisted event log (alerts, errors, status changes) newest first."""
    return await get_event_log(limit)


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    return await get_trade_log(limit)


@app.get("/api/performance")
async def get_performance():
    return await get_performance_summary()


@app.post("/api/backtest")
async def run_backtest_endpoint(config: BacktestConfig):
    if not mt5_connector.connected:
        raise HTTPException(400, "MT5 not connected.")

    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=config.period_months * 30)

    m15_candles = mt5_connector.get_candles_range("M15", from_date, now)
    h4_candles = mt5_connector.get_candles_range("H4", from_date, now)

    if m15_candles is None or h4_candles is None:
        raise HTTPException(400, "Could not fetch historical data from MT5.")

    symbol_info = mt5_connector.symbol_info or {}
    result = run_backtest(
        m15_candles=m15_candles,
        h4_candles=h4_candles,
        starting_balance=config.starting_balance,
        risk_pct=bot_config.validate_risk(),
        max_positions=1,
        pip_value=symbol_info.get("pip_value", 1.0),
        tick_size=symbol_info.get("tick_size", 0.01),
    )
    return result


@app.get("/api/calendar")
async def get_calendar():
    events = await economic_calendar.fetch_events(settings.finnhub_api_key)
    return {"events": events}


@app.get("/api/candles")
async def get_candles(timeframe: str = "M15", count: int = 800):
    """Fetch OHLCV candles from MT5 for the chart view."""
    if not mt5_connector.connected:
        raise HTTPException(400, "MT5 not connected.")
    count = min(count, 1000)
    df = mt5_connector.get_candles(timeframe, count)
    if df is None or df.empty:
        raise HTTPException(400, "Could not fetch candle data.")
    records = []
    for _, row in df.iterrows():
        records.append({
            "time": int(row["timestamp"].timestamp()),
            "open": round(float(row["open"]), 5),
            "high": round(float(row["high"]), 5),
            "low": round(float(row["low"]), 5),
            "close": round(float(row["close"]), 5),
            "volume": int(row["volume"]),
        })
    return records


@app.get("/api/chart/trades")
async def get_chart_trades():
    """Return trades formatted for chart markers."""
    from .database import get_trade_log as _get_trade_log
    raw = await _get_trade_log(200)
    trades = []
    for t in raw:
        trades.append({
            "id": t.get("id"),
            "direction": t.get("direction"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "entry_time": t.get("entry_timestamp"),
            "exit_time": t.get("exit_timestamp"),
            "result": t.get("result"),
            "pnl_eur": t.get("pnl_eur"),
            "pips": t.get("pips"),
            "lot_size": t.get("lot_size"),
        })
    return trades


# ─── WebSocket ──────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Heartbeat / user interaction tracking
            bot_config.last_user_interaction = datetime.now(timezone.utc).isoformat()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ─── Background loops ──────────────────────────────────────────────

async def _analysis_loop():
    """Main analysis loop — triggers every M15 candle close."""
    last_candle_time = None
    logger.info("Analysis loop started.")

    while bot_config.bot_running:
        try:
            await asyncio.sleep(10)  # Check every 10 seconds

            if not bot_config.bot_running or not mt5_connector.connected:
                continue

            # Hard error — stay stopped until user manually restarts
            if bot_config.bot_status == "error":
                continue

            # Soft pause — skip candles until timer expires, then auto-resume
            if bot_config.bot_status == "paused":
                if bot_config.pause_until:
                    pause_end = datetime.fromisoformat(bot_config.pause_until)
                    if datetime.now(timezone.utc) < pause_end:
                        continue
                    bot_config.bot_status = "running"
                    bot_config.pause_until = None
                    await log_and_alert("Bot resumed after pause.", "info", "bot")
                    await ws_manager.broadcast_status({"bot_status": "running", "pause_until": None})
                else:
                    continue

            # Get M15 candles and check for new candle
            m15_candles = mt5_connector.get_candles("M15", 300)
            if m15_candles is None or m15_candles.empty:
                continue

            current_candle_time = m15_candles["timestamp"].iloc[-1]
            if last_candle_time is not None and current_candle_time <= last_candle_time:
                continue  # No new candle

            last_candle_time = current_candle_time
            logger.info(f"New M15 candle detected: {current_candle_time}")

            # Run analysis
            await _run_analysis_cycle(m15_candles)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Analysis loop error: {e}", exc_info=True)
            await asyncio.sleep(30)

    logger.info("Analysis loop stopped.")


async def _run_analysis_cycle(m15_candles):
    """Execute one full analysis cycle. Re-entrancy guard prevents concurrent runs."""
    global _analysis_running
    if _analysis_running:
        logger.warning("Analysis cycle already running — skipping this candle (re-entrancy guard).")
        return
    _analysis_running = True
    try:
        await _run_analysis_cycle_inner(m15_candles)
    finally:
        _analysis_running = False


async def _run_analysis_cycle_inner(m15_candles):
    """Inner analysis logic — called exclusively from _run_analysis_cycle."""
    bot_config.bot_status = "analyzing"
    await ws_manager.broadcast_status({"bot_status": "analyzing"})

    utc_now = datetime.now(timezone.utc)

    # Fetch data
    h4_candles = mt5_connector.get_candles("H4", 50)
    price = mt5_connector.get_current_price()
    account = mt5_connector.get_account_info()
    positions = mt5_connector.get_positions()

    if any(x is None for x in [h4_candles, price, account]):
        bot_config.bot_status = "running"
        return

    # Calculate indicators
    m15_ind = calculate_indicators(m15_candles, "M15")
    h4_ind = calculate_indicators(h4_candles, "H4")

    # Determine trend, mode, and session
    current_price_val = price.get("bid") or price.get("ask") or m15_ind.get("current_close")
    trend = identify_trend(h4_ind, current_price=current_price_val)
    market_mode = get_market_mode(trend)
    session = get_current_session(utc_now)
    session_display = get_session_display_name(session)
    logger.info(f"Mode: {market_mode} | Trend: {trend} | Session: {session_display}")

    # Safety checks
    dd_check = risk_manager.check_drawdown_limit(account["equity"], bot_config.start_balance)
    if dd_check["exceeded"]:
        bot_config.bot_running = False
        bot_config.bot_status = "error"
        bot_config.error_message = f"Max drawdown reached ({dd_check['drawdown_pct']:.1f}%). Bot stopped — restart manually."
        await log_and_alert(bot_config.error_message, "error", "risk")
        await ws_manager.broadcast_status({"bot_status": "error", "error_message": bot_config.error_message})
        return

    # Inactivity — soft pause for 1 hour if no user interaction in 24h
    if bot_config.last_user_interaction:
        last_interact = datetime.fromisoformat(bot_config.last_user_interaction)
        if last_interact.tzinfo is None:
            last_interact = last_interact.replace(tzinfo=timezone.utc)
        if (utc_now - last_interact) > timedelta(hours=24) and bot_config.bot_status != "paused":
            await soft_pause(1, "No user interaction for 24h", "bot")
            return

    # Margin safety
    if not risk_manager.check_margin_safety(account["free_margin"], account["equity"]):
        await log_and_alert("Low margin — no new trades.", "warning", "risk")
        bot_config.bot_status = "running"
        return

    # ── TEST MODE ────────────────────────────────────────────────────────────
    # Fires an unconditional BUY on every M15 candle to verify the execution
    # pipeline end-to-end. All strategy/AI/session/cooldown filters are skipped.
    # Safety guardrails (drawdown, margin) still apply above.
    if TEST_MODE:
        logger.warning("TEST MODE ACTIVE — real strategy bypassed")
        # Pipeline confirmed if a position is already open — skip to avoid hedging errors
        if positions:
            logger.warning("TEST MODE: open position exists, skipping this candle. Set TEST_MODE = False to switch to real strategy.")
            bot_config.bot_status = "running"
            await ws_manager.broadcast_status({"bot_status": "running"})
            return
        ask    = price.get("ask") or price.get("bid", 0)
        atr    = m15_ind.get("atr_14") or 1.0
        sl     = round(ask - 1.5 * atr, 5)
        tp     = round(ask + 2.5 * atr, 5)
        min_lot = (mt5_connector.symbol_info or {}).get("min_lot", 0.01)

        test_analysis = {
            "timestamp": utc_now.isoformat(),
            "xaueur_price": price.get("bid"),
            "trend": trend, "session": session,
            "ai_action": "buy", "ai_confidence": 99,
            "ai_reasoning": "TEST MODE — unconditional BUY to verify execution pipeline",
        }

        if True:  # always auto-execute
            result = await trade_manager.execute_trade("buy", min_lot, sl, tp, 99, "TEST MODE")
            await log_analysis({**test_analysis,
                                 "executed": 1 if result["success"] else 0,
                                 "skipped_reason": None if result["success"] else result.get("error")})
            if result["success"]:
                await log_and_alert(f"TEST: BUY {min_lot} lots @ {result['price']}", "success", "bot")
            else:
                await log_and_alert(f"TEST: Trade failed: {result['error']}", "error", "bot")
        else:
            # Approval flow removed — always execute directly
            result = await trade_manager.execute_trade("buy", min_lot, sl, tp, 99, "TEST MODE")
            await log_analysis({**test_analysis,
                                 "executed": 1 if result["success"] else 0,
                                 "skipped_reason": None if result["success"] else result.get("error")})
            if result["success"]:
                await log_and_alert(f"TEST: BUY {min_lot} lots @ {result['price']}", "success", "bot")
            else:
                await log_and_alert(f"TEST: Trade failed: {result['error']}", "error", "bot")

        if bot_config.bot_status == "analyzing":
            bot_config.bot_status = "running"
        await ws_manager.broadcast_status({"bot_status": bot_config.bot_status})
        return
    # ── END TEST MODE ────────────────────────────────────────────────────────

    # Weekend check
    if positions:
        atr = m15_ind.get("atr_14", 0)
        weekend_actions = check_weekend_close(positions, atr, utc_now)
        for wa in weekend_actions:
            if wa["action"] == "close":
                await trade_manager.close_position(wa["ticket"], wa["reason"])
                await log_and_alert(f"Weekend close: position {wa['ticket']}", "info", "risk")
            elif wa["action"] == "tighten_sl":
                mt5_connector.modify_position(wa["ticket"], sl=wa["new_sl"])

    # Fetch economic calendar
    await economic_calendar.fetch_events(settings.finnhub_api_key)
    news_clear = economic_calendar.is_news_clear(utc_now)
    upcoming_events = economic_calendar.get_upcoming_events(24)

    # Get last 5 trades for AI context
    last_trades = await get_last_n_trades(5)

    # ── Per-candle diagnostic log ─────────────────────────────────────────────
    rsi        = m15_ind.get("rsi_14")
    close_p    = m15_ind.get("current_close")
    ema50_m15  = m15_ind.get("ema_50")
    ema50_dist_pct = (
        abs(close_p - ema50_m15) / ema50_m15 * 100
        if close_p and ema50_m15 else None
    )
    buy_chk  = check_buy_signal(m15_ind, trend, session, news_clear, positions)
    sell_chk = check_sell_signal(m15_ind, trend, session, news_clear, positions)

    def _fmt_checks(chk: dict) -> str:
        return " | ".join(
            f"{'✓' if v else '✗'} {k}" for k, v in chk.get("checks", {}).items()
        )

    logger.info(
        f"CANDLE | trend={trend} mode={market_mode} session={session} | "
        f"RSI={f'{rsi:.1f}' if rsi is not None else 'n/a'} | "
        f"EMA50 dist={f'{ema50_dist_pct:.2f}%' if ema50_dist_pct is not None else 'n/a'} | "
        f"BUY=[{_fmt_checks(buy_chk)}] | "
        f"SELL=[{_fmt_checks(sell_chk)}]"
    )

    # ── Simplified strategy pre-filter ───────────────────────────────────────
    # Only call the AI if at least one direction clears all rule-based conditions.
    # This reduces unnecessary API calls and ensures the AI focuses on valid setups.
    signal_direction: str | None = None
    if buy_chk["signal"]:
        signal_direction = "buy"
    elif sell_chk["signal"]:
        signal_direction = "sell"

    if signal_direction is None:
        # Neither direction qualifies — log top reason and skip AI call
        top_reason = (buy_chk["reasons"] + sell_chk["reasons"])[0] if (buy_chk["reasons"] or sell_chk["reasons"]) else "no setup"
        logger.info(f"No signal this candle. Buy: {buy_chk['reasons']} | Sell: {sell_chk['reasons']}")
        await log_analysis({
            "timestamp": utc_now.isoformat(), "xaueur_price": price.get("bid"),
            "m15_ema50": ema50_m15, "m15_ema200": m15_ind.get("ema_200"),
            "h4_ema50": h4_ind.get("ema_50"), "h4_ema200": h4_ind.get("ema_200"),
            "rsi_14": rsi, "atr_14": m15_ind.get("atr_14"),
            "trend": trend, "session": session,
            "ai_action": "hold", "ai_confidence": 0, "ai_reasoning": top_reason,
            "executed": 0, "skipped_reason": "no_strategy_signal",
        })
        bot_config.bot_status = "running"
        return

    # ── Call AI for confidence + SL/TP validation ────────────────────────────
    m15_json = m15_candles.tail(10).to_dict("records") if m15_candles is not None else []
    h4_json = h4_candles.tail(5).to_dict("records") if h4_candles is not None else []

    data_packet = ai_engine.build_data_packet(
        price=price, m15_candles_json=m15_json, h4_candles_json=h4_json,
        m15_indicators=m15_ind, h4_indicators=h4_ind, trend=trend,
        account=account, positions=positions,
        upcoming_events=upcoming_events, session=session,
        last_trades=last_trades, risk_pct=bot_config.validate_risk(),
        max_lot=0,
        market_mode=market_mode,
        session_display=session_display,
    )

    ai_result = await ai_engine.analyze(data_packet)

    if ai_result is None:
        reason = ai_engine.last_error_reason or "Unknown AI error."
        if ai_engine.last_error_is_fatal:
            # Fatal errors (bad key, no credits) will never self-heal — hard stop immediately
            bot_config.bot_running = False
            bot_config.bot_status = "error"
            bot_config.error_message = reason
            await log_and_alert(f"Bot stopped: {reason}", "error", "ai")
            await ws_manager.broadcast_status({"bot_status": "error", "error_message": reason})
        elif ai_engine.consecutive_failures >= 3:
            ai_engine.consecutive_failures = 0  # reset so it retries after resume
            await soft_pause(0.25, f"AI unavailable — {reason}", "ai")  # 15-minute soft pause
        else:
            await log_and_alert(f"AI call failed (attempt {ai_engine.consecutive_failures}/3): {reason}", "warning", "ai")
            bot_config.bot_status = "running"
        return

    # Log analysis data
    analysis_data = {
        "timestamp": utc_now.isoformat(),
        "xaueur_price": price["bid"],
        "m15_ema50": ema50_m15,
        "m15_ema200": m15_ind.get("ema_200"),
        "h4_ema50": h4_ind.get("ema_50"),
        "h4_ema200": h4_ind.get("ema_200"),
        "rsi_14": rsi,
        "atr_14": m15_ind.get("atr_14"),
        "trend": trend,
        "session": session,
        "ai_action": ai_result["action"],
        "ai_confidence": ai_result["confidence"],
        "ai_reasoning": ai_result["reasoning"],
    }

    confidence = ai_result["confidence"]
    action = ai_result["action"]

    # Handle AI actions
    MIN_CONFIDENCE = 45  # Phase 3 — lowered from 60%, flat regardless of mode/session

    if action in ("buy", "sell"):
        # Check cooldown
        if not check_cooldown(bot_config.last_sl_hit_time, utc_now):
            await log_analysis({**analysis_data, "executed": 0, "skipped_reason": "cooldown_active"})
            bot_config.bot_status = "running"
            return

        # Flat 45% confidence threshold
        if confidence < MIN_CONFIDENCE:
            await log_analysis({**analysis_data, "executed": 0, "skipped_reason": f"low_confidence_{confidence}_min_{MIN_CONFIDENCE}"})
            logger.info(f"AI confidence {confidence}% below threshold {MIN_CONFIDENCE}% — skipping")
            bot_config.bot_status = "running"
            return

        # Calculate SL/TP
        entry_price = ai_result.get("entry_price") or price["ask" if action == "buy" else "bid"]
        atr = m15_ind.get("atr_14", 1)
        ema50 = m15_ind.get("ema_50", entry_price)
        sl_tp = calculate_sl_tp(action, entry_price, atr, ema50)

        # Use AI-suggested levels if provided and reasonable
        sl = ai_result.get("stop_loss") or sl_tp["stop_loss"]
        tp = ai_result.get("take_profit") or sl_tp["take_profit"]

        # Calculate lot size
        lot_calc = risk_manager.calculate_lot_size(
            account_balance=account["balance"],
            free_margin=account["free_margin"],
            risk_pct=bot_config.validate_risk(),
            sl_distance=abs(entry_price - sl),
            symbol_info=mt5_connector.symbol_info or {},
        )

        if not lot_calc["valid"]:
            await log_analysis({**analysis_data, "executed": 0, "skipped_reason": lot_calc["error"]})
            await log_and_alert(lot_calc["error"], "warning", "risk")
            bot_config.bot_status = "running"
            return

        lot_size = min(
            ai_result.get("recommended_lot") or lot_calc["lot_size"],
            lot_calc["lot_size"],
        )

        # Always auto-execute — approval flow removed
        result = await trade_manager.execute_trade(
            action, lot_size, sl, tp, confidence, ai_result["reasoning"]
        )
        await log_analysis({**analysis_data, "executed": 1 if result["success"] else 0,
                           "skipped_reason": result.get("error")})
        if result["success"]:
            await log_and_alert(
                f"{action.upper()} {lot_size} lots @ {result['price']}", "success", "trade"
            )
        else:
            await log_and_alert(f"Trade failed: {result['error']}", "error", "trade")

    elif action == "update_sl" and ai_result.get("new_sl"):
        # Update trailing stop
        for pos in positions:
            new_sl = ai_result["new_sl"]
            if pos["direction"] == "buy" and new_sl > pos["sl"]:
                mt5_connector.modify_position(pos["ticket"], sl=new_sl)
            elif pos["direction"] == "sell" and new_sl < pos["sl"]:
                mt5_connector.modify_position(pos["ticket"], sl=new_sl)
        await log_analysis({**analysis_data, "executed": 1})

    elif action == "close":
        for pos in positions:
            await trade_manager.close_position(pos["ticket"], "ai_close")
            await log_and_alert(f"AI closed position {pos['ticket']}", "info", "trade")
        await log_analysis({**analysis_data, "executed": 1})

    else:
        # Hold
        await log_analysis({**analysis_data, "executed": 0, "skipped_reason": "hold"})

    if bot_config.bot_status == "analyzing":
        bot_config.bot_status = "running"

    # Broadcast updated status
    await ws_manager.broadcast_status({
        "bot_status": bot_config.bot_status,
        "trend": trend,
        "market_mode": market_mode,
        "session": session,
        "session_display": session_display,
        "last_analysis": utc_now.isoformat(),
        "ai_action": action,
        "ai_confidence": confidence,
    })


async def _position_monitor_loop():
    """Monitor open positions every 5 seconds for live P&L updates."""
    logger.info("Position monitor started.")
    while bot_config.bot_running:
        try:
            await asyncio.sleep(5)
            if not mt5_connector.connected:
                continue

            positions = mt5_connector.get_positions()
            account = mt5_connector.get_account_info()

            await ws_manager.broadcast_trade_update({
                "positions": positions,
                "account": account,
            })
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Position monitor error: {e}")
            await asyncio.sleep(10)

    logger.info("Position monitor stopped.")


async def _connection_monitor_loop():
    """
    Passive MT5 connection monitor — runs the entire session (not just while bot is running).
    Checks every 30 seconds. On failure: attempts reconnect up to 3 times (10s apart).
    If all retries fail → stops the bot and force-logs out the frontend.
    """
    retry_count = 0
    logger.info("MT5 connection monitor started.")

    while mt5_connector.connected:
        try:
            await asyncio.sleep(30)

            if not mt5_connector.check_connection():
                retry_count += 1
                logger.warning(f"MT5 connection lost (monitor). Retry {retry_count}/3")
                await log_and_alert(
                    f"MT5 connection lost. Reconnecting ({retry_count}/3)...", "warning", "mt5"
                )

                if retry_count <= 3:
                    success = mt5_connector.reconnect(
                        bot_config.mt5_account, bot_config.mt5_password, bot_config.mt5_server
                    )
                    if success:
                        retry_count = 0
                        await log_and_alert("MT5 reconnected.", "success", "mt5")
                else:
                    # Give up — stop bot and log out frontend
                    reason = "MT5 disconnected — could not reconnect after 3 attempts. Logging out."
                    bot_config.bot_running = False
                    bot_config.bot_status = "stopped"
                    mt5_connector.connected = False
                    await log_and_alert(reason, "error", "mt5")
                    await ws_manager.broadcast_force_logout(reason)
                    break
            else:
                retry_count = 0

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Connection monitor error: {e}")
            await asyncio.sleep(30)

    logger.info("MT5 connection monitor stopped.")


async def _connection_check_loop():
    """Check MT5 connection every 10 seconds (runs while bot is running)."""
    retry_count = 0
    logger.info("Connection checker started.")

    while bot_config.bot_running:
        try:
            await asyncio.sleep(10)
            if not mt5_connector.check_connection():
                retry_count += 1
                logger.warning(f"MT5 connection lost. Retry {retry_count}/5")
                await log_and_alert(
                    f"MT5 connection lost. Retrying ({retry_count}/5)...", "warning", "mt5"
                )

                if retry_count <= 5:
                    success = mt5_connector.reconnect(
                        bot_config.mt5_account, bot_config.mt5_password, bot_config.mt5_server
                    )
                    if success:
                        retry_count = 0
                        await log_and_alert("MT5 reconnected.", "success", "mt5")
                else:
                    reason = "MT5 connection lost after 5 retries — check MetaTrader and log back in."
                    bot_config.bot_running = False
                    bot_config.bot_status = "stopped"
                    await log_and_alert(reason, "error", "mt5")
                    await ws_manager.broadcast_force_logout(reason)
                    break
            else:
                retry_count = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Connection check error: {e}")
            await asyncio.sleep(10)

    logger.info("Connection checker stopped.")


# ─── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
