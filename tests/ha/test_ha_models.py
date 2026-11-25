"""Tests for HA data models and health endpoint."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from homepy.ha.models import HAStatus


def test_ha_status_primary():
    s = HAStatus(component="timescaledb", role="primary", healthy=True,
                 last_heartbeat=datetime.now(timezone.utc), replica_lag_seconds=None)
    assert s.healthy is True
    assert s.role == "primary"
    assert s.replica_lag_seconds is None


def test_ha_status_replica_with_lag():
    s = HAStatus(component="timescaledb", role="replica", healthy=True,
                 last_heartbeat=datetime.now(timezone.utc), replica_lag_seconds=0.5)
    assert s.role == "replica"
    assert s.replica_lag_seconds == 0.5


def test_ha_status_unhealthy():
    s = HAStatus(component="redis", role="master", healthy=False,
                 last_heartbeat=datetime.now(timezone.utc))
    assert s.healthy is False


def test_health_endpoint():
    from fastapi.testclient import TestClient
    from homepy.api.main import create_app

    app = create_app(use_lifespan=False)
    app.state.timescale = None
    app.state.typedb = None
    with TestClient(app) as client:
        resp = client.get("/api/v1/pipeline/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "node_id" in body
        assert "uptime_seconds" in body
        assert body["uptime_seconds"] >= 0


def test_ha_status_endpoint():
    from fastapi.testclient import TestClient
    from homepy.api.main import create_app

    app = create_app(use_lifespan=False)
    app.state.timescale = None
    app.state.typedb = None
    with TestClient(app) as client:
        resp = client.get("/api/v1/pipeline/ha/status")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_alert_event_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for table in ["ts_alert_events", "ts_anomaly_detections"]:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)",
                table,
            )
            assert exists, f"Table '{table}' missing"


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_new_tables_are_hypertables(db_pool):
    async with db_pool.acquire() as conn:
        hypertables = await conn.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        names = {r["hypertable_name"] for r in hypertables}
        for table in ["ts_alert_events", "ts_anomaly_detections"]:
            assert table in names
