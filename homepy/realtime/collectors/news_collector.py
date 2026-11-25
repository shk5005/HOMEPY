"""RSS polling stub for government press releases (30 min)."""
from __future__ import annotations

import logging

from homepy.realtime.base_collector import PollingCollector, RealTimeEvent

logger = logging.getLogger(__name__)


class NewsCollector(PollingCollector):
    poll_interval_seconds = 1800

    async def _poll_once(self) -> list[RealTimeEvent]:
        logger.info("polling government press RSS (stub) source=%s", self.source_name)
        return [RealTimeEvent(
            source=self.source_name, event_type="news",
            district_code="11680", data={"title": "mock press release", "mock": True},
        )]
