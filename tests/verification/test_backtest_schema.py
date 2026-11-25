from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from homepy.verification.models import (
    BacktestRecord,
    CalibrationProposal,
    ImprovementRecord,
    RecoveryEvent,
)

ROOT = Path(__file__).resolve().parents[2]
NEW_TABLES = ["ts_backtest_results", "ts_calibration_log", "ts_system_metrics"]
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _names(cls):
    return [f.name for f in dataclasses.fields(cls)]


def test_backtest_record():
    assert len(_names(BacktestRecord)) == 14
    r = BacktestRecord("v1", "c1", date(2026, 1, 1), "BUY", 80.0)
    assert r.predicted_scenarios == {} and r.actual_price_change_3m is None
    assert r.bias_warnings_issued == 0


def test_calibration_proposal():
    assert len(_names(CalibrationProposal)) == 11
    p = CalibrationProposal("p1", NOW, "weights", {"a": 1}, {"a": 2}, "why")
    assert p.status == "proposed"


def test_improvement_record():
    assert len(_names(ImprovementRecord)) == 11
    i = ImprovementRecord("r1", NOW, "rule", "scorer", {}, {}, "drift")
    assert i.rollback_possible is True and i.approved_by is None


def test_recovery_event():
    assert len(_names(RecoveryEvent)) == 8
    e = RecoveryEvent("e1", NOW, "timeout", "typedb", "retry", True)
    assert e.human_escalated is False


def test_defaults_not_shared():
    a = BacktestRecord("v1", "c1", date(2026, 1, 1), "BUY", 1.0)
    b = BacktestRecord("v2", "c1", date(2026, 1, 1), "BUY", 1.0)
    a.predicted_scenarios["x"] = 1
    assert b.predicted_scenarios == {}


def test_sql_files_declare_new_tables():
    schema = (ROOT / "storage/timescale/schema.sql").read_text()
    hyper = (ROOT / "storage/timescale/hypertables.sql").read_text()
    for t in NEW_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {t}" in schema
        assert f"create_hypertable('{t}', 'ts'" in hyper
        assert f"add_compression_policy('{t}', INTERVAL '180 days'" in hyper


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_backtest_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for t in NEW_TABLES:
            assert await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)", t
            )


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_backtest_tables_are_hypertables(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT hypertable_name FROM timescaledb_information.hypertables")
        names = {r["hypertable_name"] for r in rows}
        for t in NEW_TABLES:
            assert t in names
