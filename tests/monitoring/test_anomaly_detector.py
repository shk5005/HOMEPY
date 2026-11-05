from __future__ import annotations

from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from homepy.monitoring.anomaly_detector import (
    AnomalyEngine,
    BollingerDetector,
    CUSUMDetector,
    IsolationForestDetector,
    ZScoreDetector,
)


def test_zscore_detects_spike():
    normal = pd.Series([100.0] * 90)
    spiked = pd.concat([normal, pd.Series([200.0])], ignore_index=True)
    results = ZScoreDetector(threshold=3.0, lookback_days=90).detect(spiked)
    assert len(results) >= 1
    assert results[0].algorithm == "zscore"
    assert abs(results[0].z_score) > 3.0
    assert results[0].severity == "critical"


def test_zscore_no_false_positive_on_normal():
    np.random.seed(42)
    normal = pd.Series(np.random.normal(100, 5, 100))
    assert ZScoreDetector(threshold=3.0, lookback_days=90).detect(normal) == []


def test_isolation_forest_detects_multivariate_anomaly():
    np.random.seed(42)
    normal = pd.DataFrame({"price": np.random.normal(100, 5, 100),
                           "volume": np.random.normal(500, 50, 100)})
    anomaly = pd.DataFrame({"price": [300.0], "volume": [50.0]})
    data = pd.concat([normal, anomaly], ignore_index=True)
    results = IsolationForestDetector(contamination=0.01).detect(data)
    assert len(results) >= 1
    assert results[0].algorithm == "isolation_forest"
    assert results[0].z_score is None


def test_cusum_detects_trend_change():
    stable = pd.Series([100.0] * 50)
    drift = pd.Series([100.0 + i * 2 for i in range(50)])
    series = pd.concat([stable, drift], ignore_index=True)
    results = CUSUMDetector(drift_threshold_sigma=5.0).detect(series)
    assert len(results) >= 1
    assert results[0].algorithm == "cusum"


def test_bollinger_detects_overheated():
    np.random.seed(42)
    normal = pd.Series(np.random.normal(100, 2, 50))
    overheated = pd.Series([120.0] * 5)
    series = pd.concat([normal, overheated], ignore_index=True)
    results = BollingerDetector(window=20, num_std=2.0).detect(series)
    assert len(results) >= 1
    assert results[0].algorithm == "bollinger"
    assert any(r.current_value == 120.0 for r in results)


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_anomaly_engine_scan_district():
    svc = AsyncMock()
    svc.execute.return_value = [{"value": 100.0}] * 90 + [{"value": 200.0}]
    engine = AnomalyEngine(svc, [ZScoreDetector()])
    results = await engine.scan_district("11680")
    assert len(results) >= 1
