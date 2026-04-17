"""Logging configuration for the trading bot."""

import asyncio
import logging
import sys
from datetime import datetime, timezone


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trading_bot.log", encoding="utf-8"),
        ],
    )
    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class WebSocketLogHandler(logging.Handler):
    """
    Python logging handler that streams log records to all connected
    WebSocket clients via ws_manager.broadcast_log.

    Uses asyncio.ensure_future so it's safe to call from sync logging
    code running inside an async event loop.
    """

    def __init__(self, ws_manager):
        super().__init__()
        self.ws_manager = ws_manager

    def emit(self, record: logging.LogRecord):
        try:
            # Map Python log levels to frontend-friendly strings
            level_map = {
                logging.DEBUG:    "debug",
                logging.INFO:     "info",
                logging.WARNING:  "warning",
                logging.ERROR:    "error",
                logging.CRITICAL: "error",
            }
            level = level_map.get(record.levelno, "info")

            # Derive a short source name from the logger name
            # e.g. "backend.main" -> "main", "backend.strategy" -> "strategy"
            parts = record.name.split(".")
            source = parts[-1] if parts else record.name

            message = self.format(record)
            timestamp = datetime.now(timezone.utc).isoformat()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    self.ws_manager.broadcast_log(level, source, message, timestamp)
                )
        except Exception:
            self.handleError(record)


def attach_ws_handler(ws_manager) -> None:
    """
    Attach a WebSocketLogHandler at INFO level to all backend.* loggers
    so every log line is also streamed live to the frontend Logs tab.
    Called once from the FastAPI lifespan after the DB is ready.
    """
    handler = WebSocketLogHandler(ws_manager)
    handler.setLevel(logging.INFO)
    # Simple format for the WS message — no timestamp prefix (frontend adds its own)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))

    # Attach to the root "backend" logger so all sub-loggers inherit it
    root_backend = logging.getLogger("backend")
    # Avoid duplicate handlers if called more than once
    if not any(isinstance(h, WebSocketLogHandler) for h in root_backend.handlers):
        root_backend.addHandler(handler)
