"""Base collector: lifecycle + Redis publish of RealTimeEvent."""
from __future__ import annotations

import abc
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RealTimeEvent:
    source: str
    event_type: str
    district_code: str
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "event_type": self.event_type,
            "district_code": self.district_code,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "RealTimeEvent":
        return cls(
            source=d["source"],
            event_type=d["event_type"],
            district_code=d.get("district_code", ""),
            data=d.get("data", {}),
            timestamp=datetime.fromisoformat(d["timestamp"]),
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> "RealTimeEvent":
        if isinstance(raw, bytes):
            raw = raw.decode()
        return cls.from_dict(json.loads(raw))


class BaseCollector(abc.ABC):
    """Abstract collector. Subclasses implement `_collect_loop`."""

    poll_interval_seconds: int = 0  # 0 = streaming (no polling)

    def __init__(self, redis: Any, source_name: str):
        self.redis = redis
        self.source_name = source_name
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def channel(self) -> str:
        return f"events:{self.source_name}"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"collector:{self.source_name}")

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def publish(self, event: RealTimeEvent) -> None:
        await self.redis.publish(self.channel, event.to_json())

    async def _run(self) -> None:
        try:
            await self._collect_loop()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("collector %s crashed", self.source_name)
            self._running = False

    @abc.abstractmethod
    async def _collect_loop(self) -> None:
        """Gather data and call `self.publish(...)` until cancelled."""


class PollingCollector(BaseCollector):
    """Collector that polls `_poll_once()` every `poll_interval_seconds`."""

    async def _collect_loop(self) -> None:
        while self._running:
            for event in await self._poll_once():
                await self.publish(event)
            await asyncio.sleep(self.poll_interval_seconds)

    @abc.abstractmethod
    async def _poll_once(self) -> list[RealTimeEvent]:
        ...
