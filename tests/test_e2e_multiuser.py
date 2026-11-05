"""Multi-user / policy simulation E2E and API-contract tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from homepy.api import dependencies as deps
from homepy.api.main import create_app
from homepy.app.api_client import ApiClient
from homepy.app.components.impact_chain import build_impact_chain_html, impact_chain_text
from homepy.inference.scorer import InvestmentScore
from homepy.simulation import PolicySimulator


@pytest.fixture
def client():
    app = create_app(use_lifespan=False)
    scorer = MagicMock()
    scorer.score = AsyncMock(return_value=InvestmentScore(
        "market-baseline", 60.0, "B", [], datetime.now(timezone.utc)))
    ts = MagicMock()
    ts.execute = AsyncMock(return_value=[])
    sim = PolicySimulator(MagicMock(), scorer, ts)
    app.dependency_overrides[deps.get_policy_simulator] = lambda: sim
    with TestClient(app) as c:
        yield c


def test_policy_endpoint_contract(client):
    r = client.post("/api/v1/simulation/policy",
                    json={"policy_type": "tax", "parameters": {"acquisition_tax_rate": 0.04}})
    assert r.status_code == 200
    body = r.json()
    assert {"policy_change", "direct_effects", "score_before", "score_after", "delta",
            "affected_districts", "impact_chain"} <= body.keys()
    assert body["impact_chain"] and "effect" in body["impact_chain"][0]


def test_policy_backtest_contract(client):
    r = client.post("/api/v1/simulation/policy/backtest",
                    json={"policy_name": "test", "policy_date": "2020-12-17", "changes": {}})
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["accuracy_score"] <= 1.0
    assert isinstance(body["missed_factors"], list)


def test_impact_chain_renders_result_without_errors(client):
    body = client.post("/api/v1/simulation/policy", json={
        "policy_type": "supply_shock",
        "parameters": {"district_code": "11680", "units": 3000}}).json()
    html = build_impact_chain_html(body["impact_chain"], policy_label="공급 충격",
                                   delta=body["delta"])
    assert "공급 충격" in html and "점수 변화" in html
    for step in body["impact_chain"]:
        assert step["effect"].split()[0] in html
    assert impact_chain_text(body["impact_chain"]).count("\n") == len(body["impact_chain"]) - 1


def test_impact_chain_escapes_html():
    html = build_impact_chain_html([{"order": 1, "effect": "<script>x</script>", "magnitude": 1}])
    assert "<script>" not in html


def test_api_client_has_policy_methods():
    c = ApiClient()
    assert callable(c.post_policy) and callable(c.post_policy_backtest)


@pytest.mark.skip(reason="requires live services")
async def test_multiuser_policy_roundtrip():
    """Full flow against live Keycloak, TimescaleDB (RLS), Redis and WebSocket.

    1. Create analyst_a, analyst_b, viewer_c in Keycloak; obtain JWTs.
    2. analyst_a adds portfolio item C001; analyst_b adds C002 (tenant-scoped via RLS).
    3. analyst_a queries portfolio -> only C001; analyst_b -> only C002.
    4. analyst_a POST /api/v1/simulation/policy (tax) -> PolicyImpact structure.
    5. analyst_a connects to /ws/signals/11680 with JWT.
    6. Publish a test event to Redis -> analyst_a receives it.
    7. viewer_c GET /api/v1/analysis/* -> 403 (RBAC).
    """
    raise NotImplementedError("run with live services")
