"""Redis Pub/Sub consumer: persists events and fans out to signal channels."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from homepy.realtime.base_collector import RealTimeEvent

logger = logging.getLogger(__name__)

_INSERT_SQL = (
    "INSERT INTO ts_realtime_events (ts, event_id, source, event_type, district_code, data) "
    "VALUES ($1, $2, $3, $4, $5, $6::jsonb)"
)
# Event types whose TypeDB snapshot update is critical enough to await.
_CRITICAL_TYPES = {"rate_change"}


class EventProcessor:
    def __init__(self, redis: Any, timescale_svc: Any, typedb_svc: Any):
        self.redis = redis
        self.timescale = timescale_svc
        self.typedb = typedb_svc
        self._pubsub: Any = None
        self._task: asyncio.Task | None = None
        self._bg: set[asyncio.Task] = set()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._pubsub = self.redis.pubsub()
        await self._pubsub.psubscribe("events:*")
        self._running = True
        self._task = asyncio.create_task(self._listen(), name="event-processor")

    async def _listen(self) -> None:
        while self._running:
            msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is None:
                await asyncio.sleep(0.01)
                continue
            if msg.get("type") not in ("message", "pmessage"):
                continue
            try:
                await self.process_event(RealTimeEvent.from_json(msg["data"]))
            except Exception:
                logger.exception("failed to process event")

    async def process_event(self, event: RealTimeEvent) -> None:
        event_id = f"{event.source}-{uuid.uuid4().hex[:16]}"
        await self.timescale.execute(
            _INSERT_SQL, event.timestamp, event_id, event.source, event.event_type,
            event.district_code, json.dumps(event.data, ensure_ascii=False, default=str),
        )
        if event.district_code:
            await self.redis.publish(f"signals:{event.district_code}", event.to_json())
        if event.event_type in _CRITICAL_TYPES:
            await self._update_typedb(event)
        else:
            task = asyncio.create_task(self._update_typedb(event))
            self._bg.add(task)
            task.add_done_callback(self._bg.discard)

    async def _update_typedb(self, event: RealTimeEvent) -> None:
        """Snapshot update; best-effort. TypeDBService is sync -> thread."""
        fn = getattr(self.typedb, "update_snapshot", None)
        if fn is None:
            return
        try:
            await asyncio.to_thread(fn, event.district_code, event.event_type, event.data)
        except Exception:
            logger.warning("typedb snapshot update failed", exc_info=True)

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._bg:
            await asyncio.gather(*self._bg, return_exceptions=True)
        if self._pubsub is not None:
            try:
                await self._pubsub.punsubscribe("events:*")
                await self._pubsub.close()
            except Exception:
                logger.debug("pubsub close failed", exc_info=True)
            self._pubsub = None
