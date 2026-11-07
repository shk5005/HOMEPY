"""End-to-end check: bootstrap both databases, round-trip data through each."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homepy.storage.timescale_service import TimescaleService

ROOT = Path(__file__).resolve().parent.parent
TYPEDB_ADDRESS = "localhost:1729"
TYPEDB_TEST_DB = "homepy_e2e"
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
    pytest.importorskip("typedb.driver")
    from typedb.driver import TypeDB
    try:
        driver = TypeDB.core_driver(TYPEDB_ADDRESS)
        driver.close()
    except Exception:
        pytest.skip("TypeDB server not reachable at localhost:1729")

    from homepy.storage.typedb_service import TypeDBService

    bootstrap = _load_bootstrap()

    # 1. Bootstrap (separate TypeDB db so real data is untouched); run twice => idempotent
    try:
        info = bootstrap.bootstrap_typedb(TYPEDB_ADDRESS, TYPEDB_TEST_DB)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    bootstrap.bootstrap_typedb(TYPEDB_ADDRESS, TYPEDB_TEST_DB)
    assert info["entity_types"] >= 37
    ts_info = await bootstrap.bootstrap_timescale(DSN)
    await bootstrap.bootstrap_timescale(DSN)
    assert ts_info["tables"] >= 13

    try:
        # 2. TypeDB: region + district + dong with hierarchy
        with TypeDBService(TYPEDB_ADDRESS) as svc:
            svc.execute_write(
                TYPEDB_TEST_DB,
                'insert $r isa region, has region-code "E2E-R", has region-name "테스트시"; '
                '$d isa district, has district-code "E2E-D", has district-name "테스트구"; '
                '$n isa dong, has dong-code "E2E-N", has dong-name "테스트동"; '
                '(parent: $r, child: $d) isa spatial-hierarchy; '
                '(parent: $d, child: $n) isa spatial-hierarchy;',
            )
            rows = svc.execute_read(
                TYPEDB_TEST_DB,
                '''match $r isa region, has region-code "E2E-R", has region-name $rn;
                   $d isa district, has district-name $dn;
                   $n isa dong, has dong-name $nn;
                   (parent: $r, child: $d) isa spatial-hierarchy;
                   (parent: $d, child: $n) isa spatial-hierarchy;
                   get $rn, $dn, $nn;''',
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
        # 4. Cleanup: drop the throwaway TypeDB database
        driver = TypeDB.core_driver(TYPEDB_ADDRESS)
        try:
            if driver.databases.contains(TYPEDB_TEST_DB):
                driver.databases.get(TYPEDB_TEST_DB).delete()
        finally:
            driver.close()
