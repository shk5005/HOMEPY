from datetime import datetime, timezone

import pytest

from homepy.storage.timescale_service import TimescaleService

DSN = "postgresql://homepy:homepy@localhost:5432/homepy"
TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def test_timescale_service_insert_and_query():
    async with TimescaleService(DSN) as svc:
        await svc.execute("DELETE FROM ts_interest_rate WHERE ts = $1", TS)
        try:
            count = await svc.insert_batch(
                "ts_interest_rate",
                [{"ts": "2026-01-01T00:00:00+00:00", "base_rate": 3.25}],
            )
            assert count == 1
            rows = await svc.execute(
                "SELECT base_rate FROM ts_interest_rate WHERE ts = $1", TS
            )
            assert len(rows) == 1
            assert float(rows[0]["base_rate"]) == 3.25
        finally:
            await svc.execute("DELETE FROM ts_interest_rate WHERE ts = $1", TS)


def test_typedb_service_read_entities():
    pytest.importorskip("typedb.driver")
    from typedb.driver import TypeDB
    try:
        driver = TypeDB.core_driver("localhost:1729")
        driver.close()
    except Exception:
        pytest.skip("TypeDB server not reachable at localhost:1729")

    from homepy.storage.typedb_service import TypeDBService

    with TypeDBService("localhost:1729") as svc:
        results = svc.execute_read(
            "homepy", "match $x isa region; get $x; limit 5;"
        )
        assert isinstance(results, list)
