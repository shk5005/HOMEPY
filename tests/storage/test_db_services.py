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


def test_neo4j_service_read_entities():
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "homepy"))
        driver.verify_connectivity()
        driver.close()
    except Exception:
        pytest.skip("Neo4j server not reachable at bolt://localhost:7687")

    from homepy.storage.neo4j_service import Neo4jService

    with Neo4jService("bolt://localhost:7687", ("neo4j", "homepy")) as svc:
        results = svc.execute_read(
            "homepy", "MATCH (r:Region) RETURN r LIMIT 5"
        )
        assert isinstance(results, list)
