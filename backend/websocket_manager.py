"""WebSocket manager for real-time UI updates."""

import json
import logging
from fastapi import WebSocket
from typing import Any

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        if not self.active_connections:
            return

        text = json.dumps(message, default=str)
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_text(text)
            except Exception:
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception:
            self.disconnect(websocket)

    async def broadcast_status(self, data: dict):
        await self.broadcast({"type": "status", "data": data})

    async def broadcast_signal(self, data: dict):
        await self.broadcast({"type": "signal", "data": data})

    async def broadcast_trade_update(self, data: dict):
        await self.broadcast({"type": "trade_update", "data": data})

    async def broadcast_alert(self, message: str, level: str = "info"):
        await self.broadcast({"type": "alert", "data": {"message": message, "level": level}})


ws_manager = WebSocketManager()
