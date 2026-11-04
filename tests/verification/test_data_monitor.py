"""Tests for DataMonitor (freshness, drift, anomaly, consistency)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from homepy.verification.data_monitor import DataMonitor


class MockTimescale:
    def __init__(self) -> None:
        self.last_collection: dict[str, datetime] = {}
        self.latest: dict[str, float] = {}
        self.stats: dict[str, tuple[float, float]] = {}

    def set_last_collection(self, source: str, ts: datetime) -> None:
        self.last_collection[source] = ts

    def set_latest_value(self, metric: str, value: float) -> None:
        self.latest[metric] = value

    def set_90d_stats(self, metric: str, mean: float, std: float) -> None:
        self.stats[metric] = (mean, std)

    async def execute(self, query: str, *args: Any) -> list[dict]:
        if "MAX(ts)" in query:
            return [{"source": s, "last_ts": t} for s, t in self.last_collection.items()]
        if "latest_value" in query:
            metric = args[0]
            if metric in self.latest and metric in self.stats:
                mean, std = self.stats[metric]
                return [{"value": self.latest[metric], "mean": mean, "std": std}]
            return []
        if "trend_delta" in query:
            return []
        if "metric_series" in query:  # drift windows: identical distributions
            return [{"value": 3.0 + (i % 5) * 0.1} for i in range(60)]
        return []


@pytest.fixture
def mock_timescale() -> MockTimescale:
    return MockTimescale()


async def test_freshness_alert_when_stale(mock_timescale):
    mock_timescale.set_last_collection("interest_rate", datetime(2026, 11, 1))
    dm = DataMonitor(mock_timescale)
    alerts = await dm.check_freshness()
    stale = [a for a in alerts if a.source == "interest_rate"]
    assert len(stale) == 1
    assert stale[0].severity in ("WARNING", "ADVISORY")


async def test_no_freshness_alert_when_current(mock_timescale):
    mock_timescale.set_last_collection("interest_rate", datetime.now(timezone.utc))
    dm = DataMonitor(mock_timescale)
    alerts = await dm.check_freshness()
    assert not any(a.source == "interest_rate" for a in alerts)


async def test_drift_detection_kl_divergence(mock_timescale):
    dm = DataMonitor(mock_timescale)
    result = await dm.check_distribution_drift("interest_rate")
    assert isinstance(result.kl_divergence, float)
    assert result.drifted == (result.kl_divergence > 0.1)


async def test_anomaly_z_score(mock_timescale):
    mock_timescale.set_latest_value("base_rate", 8.0)  # normal ~3.0
    mock_timescale.set_90d_stats("base_rate", mean=3.25, std=0.5)
    dm = DataMonitor(mock_timescale)
    anomalies = await dm.check_anomalies("interest_rate")
    assert len(anomalies) >= 1
    assert anomalies[0].metric == "base_rate"
    assert abs(anomalies[0].z_score) > 3.0


async def test_invalid_source_rejected(mock_timescale):
    dm = DataMonitor(mock_timescale)
    with pytest.raises(ValueError):
        await dm.check_anomalies("bad source;")
