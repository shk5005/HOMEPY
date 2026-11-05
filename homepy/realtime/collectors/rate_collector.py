"""RSS polling stub for Bank of Korea rates (1 hour)."""
from __future__ import annotations

import logging

from homepy.realtime.base_collector import PollingCollector, RealTimeEvent

logger = logging.getLogger(__name__)


class RateCollector(PollingCollector):
    poll_interval_seconds = 3600

    async def _poll_once(self) -> list[RealTimeEvent]:
        logger.info("polling BOK RSS (stub) source=%s", self.source_name)
        return [RealTimeEvent(
            source=self.source_name, event_type="rate_change",
            district_code="11680", data={"base_rate": 3.5, "mock": True},
        )]
