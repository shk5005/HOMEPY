from __future__ import annotations

from datetime import datetime, timedelta

from homepy.monitoring.alert_manager import ALERT_ROUTING, AlertClassifier, AlertManager
from homepy.monitoring.models import AlertEvent, AnomalyResult


def _anomaly(i=1, z=3.2, severity="high", district="11680"):
    return AnomalyResult(
        anomaly_id=f"A{i}", detected_at=datetime.now(), district_code=district,
        metric_name="price", algorithm="zscore", current_value=150,
        baseline_value=100, z_score=z, severity=severity, details={},
    )


class MockChannel:
    def __init__(self, should_fail=False):
        self.sent = []
        self.should_fail = should_fail

    async def send(self, title, body):
        if self.should_fail:
            return False
        self.sent.append((title, body))
        return True


def test_alert_classify_single_anomaly_is_watch():
    assert AlertClassifier().classify([_anomaly()], []) == "WATCH"


def test_alert_classify_multiple_anomalies_is_advisory():
    assert AlertClassifier().classify([_anomaly(1), _anomaly(2)], []) == "ADVISORY"


def test_alert_classify_extreme_zscore_is_warning():
    assert AlertClassifier().classify([_anomaly(z=4.8)], []) == "WARNING"


def test_alert_classify_critical_signals_present():
    level = AlertClassifier().classify([_anomaly(severity="critical")], ["smart-money-signal"])
    assert level in ("WARNING", "CRITICAL")


def test_alert_classify_five_same_district_is_critical():
    anomalies = [_anomaly(i) for i in range(5)]
    assert AlertClassifier().classify(anomalies, []) == "CRITICAL"


async def test_alert_deduplication_merges_same_district():
    now = datetime.now()
    events = [
        AlertEvent(alert_id=f"E{i}", created_at=now + timedelta(seconds=i), level="WARNING",
                   title="t", description="d", district_code="11680", anomaly_ids=[f"A{i}"])
        for i in range(50)
    ]
    out = await AlertManager({}).deduplicate(events)
    assert len(out) == 1
    assert out[0].batch_count == 50
    assert out[0].deduplicated is True


async def test_slack_failure_does_not_block_kakao():
    slack, kakao = MockChannel(should_fail=True), MockChannel()
    mgr = AlertManager({"slack": slack, "kakao": kakao})
    ev = AlertEvent(alert_id="E1", created_at=datetime.now(), level="WARNING",
                    title="t", description="d", district_code="11680")
    out = await mgr.send_alert(ev)
    assert out.channels_sent == ["kakao"]
    assert out.channels_failed == ["slack"]
    assert kakao.sent == [("t", "d")]


def test_alert_routing_matches_spec():
    assert ALERT_ROUTING == {
        "WATCH": [],
        "ADVISORY": ["slack"],
        "WARNING": ["slack", "kakao"],
        "CRITICAL": ["slack", "kakao", "email"],
    }
