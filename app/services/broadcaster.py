from typing import Set
from fastapi import WebSocket
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

class TradeBroadcaster:
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.connections.add(websocket)
            logger.info("WebSocket connected, total connections=%d", len(self.connections))

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.connections.discard(websocket)
            logger.info("WebSocket disconnected, total connections=%d", len(self.connections))

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        async with self._lock:
            conns = list(self.connections)
        logger.info("Broadcasting message type=%s to %d connections", message.get('type'), len(conns))
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                logger.exception("Failed to send websocket message")

# singleton
broadcaster = TradeBroadcaster()
