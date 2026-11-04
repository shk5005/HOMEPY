"""Tests for the improvement tracker."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from homepy.verification.improvement_tracker import ImprovementTracker
from homepy.verification.models import ImprovementRecord


class MockTimescale:
    """In-memory stand-in dispatching on SQL keywords."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def execute(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = query.strip().upper()
        if q.startswith("INSERT"):
            (rid, ts, category, component, before, after, trigger, evidence,
             impact, approved_by, rollback_possible) = args
            self.rows.append({
                "record_id": rid, "ts": ts, "category": category,
                "component": component, "before_state": before,
                "after_state": after, "trigger": trigger, "evidence": evidence,
                "impact_metrics": impact, "approved_by": approved_by,
                "rollback_possible": rollback_possible,
            })
            return []
        if "GROUP BY" in q:
            counts: dict[str, int] = {}
            for r in self.rows:
                counts[r["category"]] = counts.get(r["category"], 0) + 1
            return [{"category": c, "n": n} for c, n in counts.items()]
        if "WHERE RECORD_ID" in q:
            return [r for r in self.rows if r["record_id"] == args[0]]
        if "WHERE TS" in q:
            return [r for r in self.rows if r["ts"] >= args[0]]
        return list(self.rows)


@pytest.fixture
def mock_timescale() -> MockTimescale:
    return MockTimescale()


def _rec(rid: str = "", **kw: Any) -> ImprovementRecord:
    base: dict[str, Any] = dict(
        record_id=rid, timestamp=datetime.now(timezone.utc), category="calibration",
        component="scorer", before_state={"valuation_gap": 0.10},
        after_state={"valuation_gap": 0.12}, trigger="test", evidence={},
        impact_metrics=None, approved_by="user", rollback_possible=True,
    )
    base.update(kw)
    return ImprovementRecord(**base)


async def test_record_and_retrieve(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    rid = await tracker.record(_rec(trigger="backtest_ic_analysis",
                                    evidence={"ic_before": 0.05, "ic_after": 0.12}))
    assert rid
    recent = await tracker.list_recent(days=1)
    assert len(recent) >= 1
    assert recent[0].record_id == rid
    assert recent[0].after_state == {"valuation_gap": 0.12}


async def test_rollback_restores_before_state(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    await tracker.record(_rec("R001"))
    rollback = await tracker.rollback("R001")
    assert rollback.before_state == {"valuation_gap": 0.12}  # swap
    assert rollback.after_state == {"valuation_gap": 0.10}   # restored
    assert rollback.record_id != "R001"
    assert len(mock_timescale.rows) == 2


async def test_rollback_unknown_or_impossible(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    with pytest.raises(KeyError):
        await tracker.rollback("nope")
    await tracker.record(_rec("R2", rollback_possible=False))
    with pytest.raises(ValueError):
        await tracker.rollback("R2")


async def test_improvement_stats(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    stats = await tracker.get_improvement_stats()
    assert "calibration" in stats.by_category
    assert "bugfix" in stats.by_category
    assert stats.total == 0 and stats.trend == "stable"
    await tracker.record(_rec())
    stats = await tracker.get_improvement_stats()
    assert stats.by_category["calibration"] == 1 and stats.total == 1
    assert stats.trend == "improving"


def test_json_rows_parse():
    from homepy.verification.improvement_tracker import _row_to_record
    row = {"record_id": "x", "ts": datetime.now(timezone.utc) - timedelta(days=1),
           "category": "bugfix", "component": "c", "before_state": json.dumps({"a": 1}),
           "after_state": "{}", "trigger": "t", "evidence": "{}", "impact_metrics": None,
           "approved_by": "", "rollback_possible": True}
    assert _row_to_record(row).before_state == {"a": 1}
