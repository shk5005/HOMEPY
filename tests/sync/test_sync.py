import json
import socket
from datetime import datetime, timezone

import pytest

from homepy.sync import LineageTracker, sync_aggregates_to_neo4j, sync_signals_to_timescale
from homepy.sync.timescale_to_neo4j import AggregateMapping, build_cypher


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


class FakeNeo4j:
    def __init__(self, read_results=None):
        self.read_results = read_results or {}
        self.reads, self.writes = [], []

    def execute_read(self, db, query, infer=False):
        self.reads.append(query)
        for rel, res in self.read_results.items():
            if rel in query:
                return res
        return []

    def execute_write(self, db, query, params=None):
        self.writes.append((query, params))


def _neo4j_up():
    try:
        socket.create_connection(("localhost", 7687), timeout=0.5).close()
        return True
    except OSError:
        return False


needs_neo4j = pytest.mark.skipif(not _neo4j_up(), reason="Neo4j not reachable on localhost:7687")

M = AggregateMapping("m", "SELECT 1", "Complex", "complexId", "pricePerSqm")


async def test_sync_aggregates_builds_upsert():
    ts = FakeTimescale([{"key": "C1", "value": 1234.5}, {"key": None, "value": 1.0}])
    neo = FakeNeo4j()
    report = await sync_aggregates_to_neo4j(ts, neo, mappings=(M,))
    assert report.mappings == {"m": 1} and report.batches == 1 and not report.errors
    assert len(neo.writes) >= 1
    query, params = neo.writes[0]
    assert "MERGE" in query
    assert params["key"] == "C1"


async def test_sync_aggregates_batches_of_500():
    ts = FakeTimescale([{"key": f"C{i}", "value": float(i)} for i in range(1201)])
    neo = FakeNeo4j()
    report = await sync_aggregates_to_neo4j(ts, neo, mappings=(M,), batch_size=5000)  # clamped
    assert report.batches == 3 and report.mappings["m"] == 1201
    assert len(neo.writes) == 1201


async def test_sync_aggregates_escapes_and_records_errors():
    ts = FakeTimescale([{"key": 'a"b', "value": 1}])

    class Boom(FakeNeo4j):
        def execute_write(self, db, query, params=None):
            raise RuntimeError("timeout")

    report = await sync_aggregates_to_neo4j(ts, Boom(), mappings=(M,))
    assert report.errors and report.mappings["m"] == 0
    query, params = build_cypher(M, 'a"b', 1)
    assert params["key"] == 'a"b'


async def test_sync_signals_writes_rows():
    neo = FakeNeo4j({"UNDERVALUED_SIGNAL": [{"id": "C1"}, {"id": "C1"}, {"id": "C2"}],
                     "GAP_RISK_SIGNAL": [{"id": "11680"}]})
    ts = FakeTimescale()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert await sync_signals_to_timescale(neo, ts, now=now) == 3
    table, rows = ts.inserts[0]
    assert table == "ts_signals"
    by = {(r["signal_type"], r["target_id"]): r for r in rows}
    assert by[("UNDERVALUED_SIGNAL", "C1")]["target_type"] == "Complex"
    assert by[("GAP_RISK_SIGNAL", "11680")]["district_code"] == "11680"
    assert all(r["ts"] == now and r["rule_name"] for r in rows)


async def test_sync_signals_empty():
    ts = FakeTimescale()
    assert await sync_signals_to_timescale(FakeNeo4j(), ts) == 0
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


@needs_neo4j
def test_neo4j_execute_write_live():
    from homepy.storage.neo4j_service import Neo4jService
    with Neo4jService("bolt://localhost:7687", "neo4j", "homepy") as svc:
        svc.execute_write("homepy", "RETURN 1")


async def test_signals_read_with_inference():
    calls = []

    class T(FakeNeo4j):
        def execute_read(self, db, query, infer=False):
            calls.append(infer)
            return []

    await sync_signals_to_timescale(T(), FakeTimescale())
    assert calls and all(calls)


def test_lineage_numpy_types(tmp_path):
    import numpy as np
    t = LineageTracker(tmp_path / "l.jsonl")
    t.record("s", "clean", "o", {"passed": np.bool_(True), "row_count": np.int64(7)})
    r = t.read_all()[0]
    assert r["quality_passed"] is True and r["row_count"] == 7
