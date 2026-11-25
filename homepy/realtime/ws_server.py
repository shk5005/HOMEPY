"""WebSocket push server: per-district signal streaming with backpressure (Plan F Task 5)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from homepy.auth import AuthenticationError

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 30.0
WS_POLICY_VIOLATION = 1008
WS_TRY_AGAIN_LATER = 1013


class ConnectionManager:
    """Tracks WebSocket clients per district and fans messages out to them.

    Backpressure: a client whose previous send is still in flight has the new
    message dropped; a send blocked longer than ``send_timeout`` disconnects it.
    """

    def __init__(self, send_timeout: float = SEND_TIMEOUT_SECONDS) -> None:
        self.send_timeout = send_timeout
        self._connections: dict[str, set[Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._sending: set[int] = set()
        self.dropped = 0

    def _lock(self, district_code: str) -> asyncio.Lock:
        return self._locks.setdefault(district_code, asyncio.Lock())

    async def connect(self, ws: Any, district_code: str, accept: bool = True) -> None:
        if accept:
            await ws.accept()
        async with self._lock(district_code):
            self._connections.setdefault(district_code, set()).add(ws)

    async def disconnect(self, ws: Any, district_code: str) -> None:
        async with self._lock(district_code):
            conns = self._connections.get(district_code)
            if conns is not None:
                conns.discard(ws)
                if not conns:
                    del self._connections[district_code]
        self._sending.discard(id(ws))

    def get_connection_count(self, district_code: str) -> int:
        return len(self._connections.get(district_code, ()))

    async def _send(self, ws: Any, district_code: str, data: dict) -> None:
        if id(ws) in self._sending:
            self.dropped += 1  # slow consumer still busy: drop this message
            return
        self._sending.add(id(ws))
        try:
            await asyncio.wait_for(ws.send_json(data), timeout=self.send_timeout)
        except asyncio.TimeoutError:
            logger.warning("slow consumer disconnected (district=%s)", district_code)
            await self._drop_client(ws, district_code)
        except Exception:
            logger.info("send failed; removing client (district=%s)", district_code, exc_info=True)
            await self._drop_client(ws, district_code)
        finally:
            self._sending.discard(id(ws))

    async def _drop_client(self, ws: Any, district_code: str) -> None:
        await self.disconnect(ws, district_code)
        try:
            await ws.close(code=WS_TRY_AGAIN_LATER)
        except Exception:
            pass

    async def broadcast(self, district_code: str, data: dict) -> None:
        targets = list(self._connections.get(district_code, ()))
        if targets:
            await asyncio.gather(*(self._send(ws, district_code, data) for ws in targets))


manager = ConnectionManager()


async def signal_stream(ws: WebSocket, district_code: str, token: str | None = None) -> None:
    """``/ws/signals/{district_code}?token=...``: JWT-authenticated signal stream."""
    jwt_handler = getattr(ws.app.state, "jwt_handler", None)
    if not token or jwt_handler is None:
        await ws.close(code=WS_POLICY_VIOLATION)
        return
    try:
        await jwt_handler.verify_token(token)
    except AuthenticationError:
        await ws.close(code=WS_POLICY_VIOLATION)
        return

    redis = getattr(ws.app.state, "redis", None)
    if redis is None:
        await ws.close(code=WS_TRY_AGAIN_LATER)
        return

    await manager.connect(ws, district_code)
    pubsub = redis.pubsub()
    channel = f"signals:{district_code}"
    await pubsub.subscribe(channel)

    async def pump() -> None:
        # Each client has its own subscription and is sent to individually, so
        # one slow client never delays or duplicates messages for the others.
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                continue
            raw = msg.get("data")
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            await manager._send(ws, district_code, event)
            if ws not in manager._connections.get(district_code, ()):
                return

    async def drain() -> None:
        while True:
            await ws.receive_text()  # raises WebSocketDisconnect on client close

    tasks = [asyncio.create_task(pump()), asyncio.create_task(drain())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await manager.disconnect(ws, district_code)
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            logger.debug("pubsub cleanup failed", exc_info=True)
