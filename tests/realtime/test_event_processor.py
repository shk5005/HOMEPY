import asyncio
from datetime import datetime, timezone

from homepy.realtime.base_collector import RealTimeEvent
from homepy.realtime.collectors.stock_collector import StockCollector
from homepy.realtime.event_processor import EventProcessor


def _event(**kw):
    d = dict(source="stock_api", event_type="price_update", district_code="11680",
             data={"price": 950000000}, timestamp=datetime.now(timezone.utc))
    d.update(kw)
    return RealTimeEvent(**d)


async def test_event_processor_writes_to_timescale(mock_redis, mock_timescale, mock_typedb):
    p = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    await p.process_event(_event())
    assert mock_timescale.inserted_count("ts_realtime_events") == 1


async def test_event_processor_publishes_signal(mock_redis, mock_timescale, mock_typedb):
    p = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    await p.process_event(_event())
    assert len(mock_redis.published_messages.get("signals:11680", [])) >= 1


async def test_typedb_update_fire_and_forget(mock_redis, mock_timescale, mock_typedb):
    p = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    await p.process_event(_event())
    await p.stop()
    assert mock_typedb.updates and mock_typedb.updates[0][0] == "11680"


async def test_typedb_failure_does_not_break(mock_redis, mock_timescale):
    class Bad:
        def update_snapshot(self, *a):
            raise RuntimeError("down")
    p = EventProcessor(mock_redis, mock_timescale, Bad())
    await p.process_event(_event())
    await p.stop()
    assert mock_timescale.inserted_count("ts_realtime_events") == 1


async def test_end_to_end_pubsub(mock_redis, mock_timescale, mock_typedb):
    p = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    await p.start()
    await StockCollector(mock_redis, "stock_api").publish(_event())
    for _ in range(100):
        if mock_timescale.calls:
            break
        await asyncio.sleep(0.02)
    await p.stop()
    assert mock_timescale.inserted_count("ts_realtime_events") == 1
    assert p.running is False
