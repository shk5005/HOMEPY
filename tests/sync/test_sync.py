import json
import socket
from datetime import datetime, timezone

import pytest

from homepy.sync import LineageTracker, sync_aggregates_to_typedb, sync_signals_to_timescale
from homepy.sync.timescale_to_typedb import AggregateMapping, build_statements


class FakeTimescale:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries, self.inserts = [], []

    async def execute(self, sql, *args):
        self.queries.append(sql)
        return self.rows

    async def insert_batch(self, table, records):
        self.inserts.append((table, records))
        return len(records)


class FakeTypeDB:
    def __init__(self, read_results=None):
        self.read_results = read_results or {}
        self.reads, self.writes = [], []

    def execute_read(self, db, query):
        self.reads.append(query)
        for rel, res in self.read_results.items():
            if f"isa {rel};" in query:
                return res
        return []

    def execute_write_many(self, db, statements):
        self.writes.append(list(statements))


def _typedb_up():
    try:
        socket.create_connection(("localhost", 1729), timeout=0.5).close()
        return True
    except OSError:
        return False


needs_typedb = pytest.mark.skipif(not _typedb_up(), reason="TypeDB not reachable on localhost:1729")

M = AggregateMapping("m", "SELECT 1", "complex", "complex-id", "price-per-sqm")


async def test_sync_aggregates_builds_upsert_statements():
    ts = FakeTimescale([{"key": "C1", "value": 1234.5}, {"key": None, "value": 1.0}])
    tdb = FakeTypeDB()
    report = await sync_aggregates_to_typedb(ts, tdb, mappings=(M,))
    assert report.mappings == {"m": 1} and report.batches == 1 and not report.errors
    assert [k for k, _ in tdb.writes[0]] == ["delete", "insert"]
    assert 'has complex-id "C1"' in tdb.writes[0][1][1]
    assert "has price-per-sqm 1234.5" in tdb.writes[0][1][1]


async def test_sync_aggregates_batches_of_500():
    ts = FakeTimescale([{"key": f"C{i}", "value": float(i)} for i in range(1201)])
    tdb = FakeTypeDB()
    report = await sync_aggregates_to_typedb(ts, tdb, mappings=(M,), batch_size=5000)  # clamped
    assert report.batches == 3 and report.mappings["m"] == 1201
    inserts = [sum(1 for k, _ in w if k == "insert") for w in tdb.writes]
    assert inserts == [500, 500, 201]


async def test_sync_aggregates_escapes_and_records_errors():
    ts = FakeTimescale([{"key": 'a"b', "value": 1}])

    class Boom(FakeTypeDB):
        def execute_write_many(self, db, statements):
            raise RuntimeError("timeout")

    report = await sync_aggregates_to_typedb(ts, Boom(), mappings=(M,))
    assert report.errors and report.mappings["m"] == 0
    assert 'a\\"b' in build_statements(M, 'a"b', 1)[1][1]


async def test_sync_signals_writes_rows():
    tdb = FakeTypeDB({"undervalued-signal": [{"id": "C1"}, {"id": "C1"}, {"id": "C2"}],
                      "gap-risk-signal": [{"id": "11680"}]})
    ts = FakeTimescale()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert await sync_signals_to_timescale(tdb, ts, now=now) == 3
    table, rows = ts.inserts[0]
    assert table == "ts_signals"
    by = {(r["signal_type"], r["target_id"]): r for r in rows}
    assert by[("undervalued-signal", "C1")]["target_type"] == "complex"
    assert by[("gap-risk-signal", "11680")]["district_code"] == "11680"
    assert all(r["ts"] == now and r["rule_name"] for r in rows)


async def test_sync_signals_empty():
    ts = FakeTimescale()
    assert await sync_signals_to_timescale(FakeTypeDB(), ts) == 0
    assert ts.inserts == []


def test_lineage_append_only(tmp_path):
    path = tmp_path / "catalog" / "lineage.jsonl"
    t = LineageTracker(path)
    t.record("molit", "clean", "out/a.parquet", {"passed": True, "row_count": 10}, input_path="in/a.csv")
    t.record("molit", "load", "ts_real_trade", False, row_count=3)
    a, b = (json.loads(x) for x in path.read_text().splitlines())
    assert a["row_count"] == 10 and a["quality_passed"] is True and a["input_path"] == "in/a.csv"
    assert b["quality_passed"] is False and b["stage"] == "load"
    assert set(a) == {"timestamp", "source", "stage", "input_path", "output_path",
                      "row_count", "quality_passed"}
    assert len(t.read_all()) == 2


@needs_typedb
def test_typedb_execute_write_many_live():
    from homepy.storage.typedb_service import TypeDBService
    with TypeDBService("localhost:1729") as svc:
        svc.execute_write_many("homepy_test", [])
