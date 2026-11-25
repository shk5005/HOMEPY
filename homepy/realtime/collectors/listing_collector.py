"""HTTP polling stub for Naver real estate listings (5 min)."""
from __future__ import annotations

import logging

from homepy.realtime.base_collector import PollingCollector, RealTimeEvent

logger = logging.getLogger(__name__)


class ListingCollector(PollingCollector):
    poll_interval_seconds = 300

    async def _poll_once(self) -> list[RealTimeEvent]:
        logger.info("polling Naver listings (stub) source=%s", self.source_name)
        return [RealTimeEvent(
            source=self.source_name, event_type="new_listing",
            district_code="11680", data={"listings": 1, "mock": True},
        )]
