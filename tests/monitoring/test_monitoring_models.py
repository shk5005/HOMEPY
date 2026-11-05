"""Tests for monitoring data models (AnomalyResult, AlertEvent)."""
from __future__ import annotations

from datetime import datetime, timezone

from homepy.monitoring.models import (
    ALERT_LEVELS,
    ANOMALY_ALGORITHMS,
    ANOMALY_SEVERITIES,
    AlertEvent,
    AnomalyResult,
)


def test_anomaly_result_construction():
    ar = AnomalyResult(
        anomaly_id="A001", detected_at=datetime.now(timezone.utc),
        district_code="11680", metric_name="price_index",
        algorithm="zscore", current_value=150.0, baseline_value=100.0,
        z_score=3.5, severity="high", details={},
    )
    assert ar.anomaly_id == "A001"
    assert ar.algorithm in ANOMALY_ALGORITHMS
    assert ar.severity in ANOMALY_SEVERITIES


def test_anomaly_result_severity_values():
    valid = set(ANOMALY_SEVERITIES)
    for sev in ("low", "medium", "high", "critical"):
        ar = AnomalyResult(
            anomaly_id="X", detected_at=datetime.now(timezone.utc),
            district_code="11680", metric_name="m", algorithm="zscore",
            current_value=0, baseline_value=0, z_score=None,
            severity=sev, details={},
        )
        assert ar.severity in valid


def test_anomaly_result_with_details():
    ar = AnomalyResult(
        anomaly_id="A002", detected_at=datetime.now(timezone.utc),
        district_code="11680", metric_name="volume",
        algorithm="isolation_forest", current_value=800.0,
        baseline_value=500.0, z_score=None, severity="medium",
        details={"contamination": 0.01, "feature_importance": [0.8, 0.2]},
    )
    assert ar.z_score is None
    assert ar.details["contamination"] == 0.01


def test_alert_event_construction():
    ae = AlertEvent(
        alert_id="AL001", created_at=datetime.now(timezone.utc),
        level="WARNING", title="Price spike", description="Z > 3",
        district_code="11680", anomaly_ids=["A001"],
        channels_sent=["slack"], channels_failed=[],
        deduplicated=False, batch_count=1,
    )
    assert ae.level in ALERT_LEVELS
    assert ae.batch_count == 1
    assert ae.deduplicated is False


def test_alert_event_level_values():
    valid = set(ALERT_LEVELS)
    for level in ("WATCH", "ADVISORY", "WARNING", "CRITICAL"):
        ae = AlertEvent(
            alert_id="X", created_at=datetime.now(timezone.utc),
            level=level, title="t", description="d",
            district_code=None,
        )
        assert ae.level in valid


def test_alert_event_deduplicated():
    ae = AlertEvent(
        alert_id="AL002", created_at=datetime.now(timezone.utc),
        level="CRITICAL", title="Batch", description="50 anomalies merged",
        district_code="11680", anomaly_ids=[f"A{i}" for i in range(50)],
        channels_sent=["slack", "kakao", "email"], channels_failed=[],
        deduplicated=True, batch_count=50,
    )
    assert ae.deduplicated is True
    assert ae.batch_count == 50
    assert len(ae.anomaly_ids) == 50


def test_alert_event_defaults():
    ae = AlertEvent(
        alert_id="AL003", created_at=datetime.now(timezone.utc),
        level="WATCH", title="t", description="d", district_code=None,
    )
    assert ae.anomaly_ids == []
    assert ae.channels_sent == []
    assert ae.channels_failed == []
    assert ae.deduplicated is False
    assert ae.batch_count == 1
