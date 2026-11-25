"""WebSocket stub for securities-firm API (Kiwoom / Korea Investment)."""
from __future__ import annotations

import asyncio
import logging

from homepy.realtime.base_collector import BaseCollector, RealTimeEvent

logger = logging.getLogger(__name__)


class StockCollector(BaseCollector):
    poll_interval_seconds = 0  # streaming

    async def _collect_loop(self) -> None:
        logger.info("connecting to stock API (stub) source=%s", self.source_name)
        while self._running:
            await self.publish(RealTimeEvent(
                source=self.source_name, event_type="price_update",
                district_code="11680", data={"price": 950000000, "mock": True},
            ))
            await asyncio.sleep(1)
