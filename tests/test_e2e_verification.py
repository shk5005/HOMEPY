"""E2E: backtest -> calibrate -> API accuracy/proposals -> approve -> ImprovementRecord."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from homepy.api.main import create_app
from homepy.inference.scorer import FACTOR_WEIGHTS
from homepy.verification.backtester import Backtester
from homepy.verification.calibrator import AutoCalibrator

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


class FakeTS:
    """In-memory TimescaleService stand-in that records writes."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args):
        if query.lstrip().upper().startswith(("INSERT", "UPDATE")):
            self.writes.append((query, args))
        return []


class FakeBacktester:
    """Deterministic IC so the calibrator produces a real proposal."""

    async def factor_ic_analysis(self, months: int = 12, skip_recent_months: int = 0):
        return {f: 0.1 * (i + 1) for i, f in enumerate(FACTOR_WEIGHTS)}


@pytest.fixture
def env(tmp_path):
    ts = FakeTS()
    app = create_app(use_lifespan=False)
    app.state.timescale = ts
    app.state.typedb = None
    cal = AutoCalibrator(FakeBacktester(), ts, config_path=tmp_path / "calibration.json")
    app.state.calibrator = cal
    with TestClient(app) as client:
        yield client, ts, cal, tmp_path


async def test_verification_roundtrip(env):
    client, ts, cal, tmp_path = env

    # 1-2. Backtester over empty history returns zeroed metrics
    result = await Backtester(ts, now=lambda: NOW).run(3)
    assert result.total_verdicts == 0 and result.direction_accuracy == 0.0

    # 3. Calibrator proposes new weights
    proposal = await cal.propose_weight_update()
    assert proposal.status == "proposed"
    assert sum(proposal.proposed_values.values()) == pytest.approx(1.0)

    # 4. Accuracy endpoint
    acc = client.get("/api/v1/pipeline/verification/accuracy")
    assert acc.status_code == 200
    body = acc.json()
    assert {"direction_accuracy", "signal_hit_rate", "total_verdicts", "computed_at"} <= body.keys()
    assert body["total_verdicts"] == 0

    # 5. Pending proposal visible
    props = client.get("/api/v1/pipeline/verification/proposals").json()
    assert [p["proposal_id"] for p in props] == [proposal.proposal_id]
    assert props[0]["category"] == "weight"

    # 6. Approve
    resp = client.post(f"/api/v1/pipeline/verification/proposals/{proposal.proposal_id}/approve")
    assert resp.status_code == 200
    rec = resp.json()
    assert rec["category"] == "calibration"
    assert rec["trigger"] == f"proposal {proposal.proposal_id}"

    # 7. ImprovementRecord persisted and config written
    inserts = [a for q, a in ts.writes if "ts_calibration_log" in q]
    assert len(inserts) == 1 and inserts[0][2] == "calibration"
    cfg = json.loads((tmp_path / "calibration.json").read_text())
    assert cfg["weights"] == proposal.proposed_values
    assert client.get("/api/v1/pipeline/verification/proposals").json() == []

    # re-approve -> 409; unknown -> 404
    assert client.post(
        f"/api/v1/pipeline/verification/proposals/{proposal.proposal_id}/approve").status_code == 409
    assert client.post("/api/v1/pipeline/verification/proposals/nope/approve").status_code == 404


async def test_health_endpoint(env):
    client, *_ = env
    resp = client.get("/api/v1/pipeline/verification/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["components"] == [] and body["data_quality_alerts"] == 0
    assert body["recovery_events_24h"] >= 0
