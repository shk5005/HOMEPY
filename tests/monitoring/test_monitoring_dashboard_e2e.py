from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from homepy.api.main import create_app


def _get(path: str):
    app = create_app(use_lifespan=False)
    app.state.timescale = None
    app.state.typedb = None
    with TestClient(app) as client:
        return client.get(path)


def test_anomalies_endpoint():
    resp = _get("/api/v1/pipeline/monitoring/anomalies?days=7")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_alerts_endpoint():
    resp = _get("/api/v1/pipeline/monitoring/alerts?days=7")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_alerts_endpoint_with_level_filter():
    resp = _get("/api/v1/pipeline/monitoring/alerts?days=7&level=WARNING")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_early_warnings_endpoint():
    resp = _get("/api/v1/pipeline/monitoring/early-warnings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_components_empty_and_populated():
    pytest.importorskip("plotly")
    from homepy.app.components.alert_timeline import alert_timeline
    from homepy.app.components.anomaly_heatmap import anomaly_heatmap

    assert anomaly_heatmap([]).layout.annotations[0].text == "데이터 없음"
    fig = anomaly_heatmap([{"detected_at": "2026-11-01T00:00:00", "district_code": "11680"}])
    assert fig.data[0].z[0][0] == 1
    assert len(alert_timeline([{"created_at": "2026-11-01", "level": "WARNING"}]).data) == 1


@pytest.mark.skip(reason="requires live TimescaleDB + TypeDB")
async def test_e2e_anomaly_to_alert_pipeline():
    """Full pipeline: inject data → detect → classify → alert → API returns"""
