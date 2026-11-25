"""End-to-end check: bootstrap both databases, round-trip data through each."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homepy.storage.timescale_service import TimescaleService

ROOT = Path(__file__).resolve().parent.parent
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "homepy")
NEO4J_TEST_DB = "homepy_e2e"
DSN = "postgresql://homepy:homepy@localhost:5432/homepy"
TS = datetime(2026, 1, 15, tzinfo=timezone.utc)
TRADE_ID = "e2e-test-trade"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "bootstrap_db", ROOT / "scripts" / "bootstrap_db.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_full_infrastructure_roundtrip():
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        driver.verify_connectivity()
        driver.close()
    except Exception:
        pytest.skip("Neo4j server not reachable at bolt://localhost:7687")

    from homepy.storage.neo4j_service import Neo4jService

    bootstrap = _load_bootstrap()

    # 1. Bootstrap (separate Neo4j db so real data is untouched); run twice => idempotent
    try:
        info = bootstrap.bootstrap_neo4j(NEO4J_URI, NEO4J_AUTH, NEO4J_TEST_DB)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    bootstrap.bootstrap_neo4j(NEO4J_URI, NEO4J_AUTH, NEO4J_TEST_DB)
    assert info["node_labels"] >= 37
    ts_info = await bootstrap.bootstrap_timescale(DSN)
    await bootstrap.bootstrap_timescale(DSN)
    assert ts_info["tables"] >= 13

    try:
        # 2. Neo4j: region + district + dong with hierarchy
        with Neo4jService(NEO4J_URI, NEO4J_AUTH) as svc:
            svc.execute_write(
                NEO4J_TEST_DB,
                'CREATE (r:Region {regionCode: "E2E-R", regionName: "테스트시"}) '
                'CREATE (d:District {districtCode: "E2E-D", districtName: "테스트구"}) '
                'CREATE (n:Dong {dongCode: "E2E-N", dongName: "테스트동"}) '
                'CREATE (r)-[:SPATIAL_HIERARCHY]->(d) '
                'CREATE (d)-[:SPATIAL_HIERARCHY]->(n)',
            )
            rows = svc.execute_read(
                NEO4J_TEST_DB,
                'MATCH (r:Region {regionCode: "E2E-R"})-[:SPATIAL_HIERARCHY]->(d:District) '
                '-[:SPATIAL_HIERARCHY]->(n:Dong) '
                'RETURN r.regionName AS rn, d.districtName AS dn, n.dongName AS nn',
            )
            assert len(rows) == 1
            assert rows[0]["rn"] == "테스트시"
            assert rows[0]["dn"] == "테스트구"
            assert rows[0]["nn"] == "테스트동"

        # 3. TimescaleDB: price record
        async with TimescaleService(DSN) as ts:
            await ts.execute("DELETE FROM ts_real_trade WHERE trade_id = $1", TRADE_ID)
            try:
                n = await ts.insert_batch(
                    "ts_real_trade",
                    [{
                        "ts": TS.isoformat(),
                        "trade_id": TRADE_ID,
                        "complex_id": "E2E-C",
                        "district_code": "E2E-D",
                        "price_krw": 1_200_000_000,
                    }],
                )
                assert n == 1
                got = await ts.execute(
                    "SELECT price_krw, district_code FROM ts_real_trade WHERE trade_id = $1",
                    TRADE_ID,
                )
                assert len(got) == 1
                assert got[0]["price_krw"] == 1_200_000_000
                assert got[0]["district_code"] == "E2E-D"
            finally:
                await ts.execute("DELETE FROM ts_real_trade WHERE trade_id = $1", TRADE_ID)
            assert await ts.execute(
                "SELECT 1 FROM ts_real_trade WHERE trade_id = $1", TRADE_ID
            ) == []
    finally:
        # 4. Cleanup: drop the throwaway Neo4j database
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        try:
            with driver.session(database="system") as session:
                session.run(f"DROP DATABASE {NEO4J_TEST_DB} IF EXISTS")
        finally:
            driver.close()
