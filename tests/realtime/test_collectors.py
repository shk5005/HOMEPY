import asyncio
from datetime import datetime, timezone

import pytest

from homepy.realtime.base_collector import RealTimeEvent
from homepy.realtime.collectors.listing_collector import ListingCollector
from homepy.realtime.collectors.news_collector import NewsCollector
from homepy.realtime.collectors.rate_collector import RateCollector
from homepy.realtime.collectors.stock_collector import StockCollector


async def test_base_collector_publishes_to_redis(mock_redis):
    collector = StockCollector(mock_redis, "stock_api")
    event = RealTimeEvent(source="stock_api", event_type="price_update",
                          district_code="11680", data={"price": 950000000},
                          timestamp=datetime.now(timezone.utc))
    await collector.publish(event)
    published = mock_redis.published_messages["events:stock_api"]
    assert len(published) == 1
    assert published[0]["district_code"] == "11680"


async def test_listing_collector_polls_at_interval(mock_redis):
    assert ListingCollector(mock_redis, "naver_listing").poll_interval_seconds == 300


async def test_rate_collector_polls_hourly(mock_redis):
    assert RateCollector(mock_redis, "bok_rate").poll_interval_seconds == 3600


async def test_news_collector_polls_30min(mock_redis):
    assert NewsCollector(mock_redis, "gov_news").poll_interval_seconds == 1800


async def test_collector_graceful_shutdown(mock_redis):
    collector = StockCollector(mock_redis, "stock_api")
    await collector.start()
    assert collector.running is True
    await collector.stop()
    assert collector.running is False


@pytest.mark.parametrize("cls,name,etype", [
    (StockCollector, "stock_api", "price_update"),
    (ListingCollector, "naver_listing", "new_listing"),
    (RateCollector, "bok_rate", "rate_change"),
    (NewsCollector, "gov_news", "news"),
])
async def test_stub_collectors_emit_events(mock_redis, cls, name, etype):
    c = cls(mock_redis, name)
    await c.start()
    await asyncio.sleep(0.05)
    await c.stop()
    msgs = mock_redis.published_messages[f"events:{name}"]
    assert msgs[0]["source"] == name and msgs[0]["event_type"] == etype


@pytest.mark.skip(reason="requires live Redis")
async def test_live_redis_publish():
    ...
