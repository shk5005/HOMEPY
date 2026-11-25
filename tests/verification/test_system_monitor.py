"""Tests for SystemMonitor."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from homepy.verification.system_monitor import SystemMonitor


class MockTimescale:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def execute(self, query: str, *args: Any) -> list[dict]:
        if query.lstrip().upper().startswith("INSERT"):
            component, name, value, metadata = args
            self.rows.append({
                "ts": datetime.now(timezone.utc), "component": component,
                "metric_name": name, "metric_value": value, "metadata": metadata,
            })
            return []
        if "percentile_cont" in query:
            return [{"component": "typedb", "p50_ms": 20.0, "p95_ms": 120.0,
                     "p99_ms": 300.0, "count": 42}]
        if "metric_value >" in query:
            threshold = args[0]
            return [r for r in self.rows if r["metric_value"] > threshold]
        return []


@pytest.fixture
def mock_timescale() -> MockTimescale:
    return MockTimescale()


async def test_record_and_retrieve_metrics(mock_timescale):
    sm = SystemMonitor(mock_timescale)
    await sm.record_query_time("typedb", "match $x isa region;", 1500.0)
    slow = await sm.detect_slow_queries(threshold_ms=1000)
    assert len(slow) == 1
    assert slow[0].duration_ms == 1500.0
    assert slow[0].component == "typedb"


async def test_performance_summary(mock_timescale):
    sm = SystemMonitor(mock_timescale)
    summary = await sm.get_performance_summary()
    assert "typedb" in summary.components
    assert summary.components["typedb"].p95_ms >= 0
    assert summary.components["typedb"].period_hours == 24
