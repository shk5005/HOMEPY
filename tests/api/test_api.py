import pytest

from homepy.api.services.tax_engine import TaxEngine
from unittest.mock import MagicMock


def test_app_starts(app_client):
    resp = app_client.get("/api/v1/market/macro/summary")
    assert resp.status_code == 200
    assert resp.json()["base_rate"] == 2.5


def test_score_endpoint_returns_factors(app_client):
    resp = app_client.post("/api/v1/analysis/score", json={"complex_ids": ["C001"]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert len(data[0]["factors"]) == 14


def test_score_rejects_empty_list(app_client):
    assert app_client.post("/api/v1/analysis/score", json={"complex_ids": []}).status_code == 422


def test_verdict_endpoint_has_red_team_fields(app_client):
    resp = app_client.post("/api/v1/analysis/verdict/C001")
    assert resp.status_code == 200
    body = resp.json()
    assert "core_facts" in body
    assert "kill_switch" in body
    assert body["verdict"] in ("매수 검토", "관망", "매도 검토", "판단 유보")
    assert body["bias_warnings"][0]["bias_type"] == "anchoring"


def test_scenario_endpoint(app_client):
    resp = app_client.post("/api/v1/simulation/scenario/C001")
    assert resp.status_code == 200
    assert len(resp.json()["scenarios"]) == 3


def test_ontology_graph_endpoint(app_client):
    resp = app_client.get("/api/v1/ontology/graph/C001")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body and "edges" in body
    assert len(body["nodes"]) == 3 and len(body["edges"]) == 2


def test_ontology_graph_rejects_injection(app_client):
    assert app_client.get("/api/v1/ontology/graph/C001%22%3B").status_code == 422


def test_entity_list_and_unknown_type(app_client):
    assert app_client.get("/api/v1/ontology/entity/complex").status_code == 200
    assert app_client.get("/api/v1/ontology/entity/bogus").status_code == 404


def test_cycle_endpoint(app_client):
    resp = app_client.get("/api/v1/market/cycle/11680")
    assert resp.status_code == 200
    assert resp.json()["phase"] == "recovery"


def test_pipeline_status(app_client):
    resp = app_client.get("/api/v1/pipeline/status")
    assert resp.status_code == 200
    assert resp.json()["total_rows"] == 90


def test_portfolio_rank(app_client):
    resp = app_client.post("/api/v1/portfolio/rank", json={"complex_ids": ["A", "B"]})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_tax_endpoint(app_client):
    resp = app_client.post("/api/v1/simulation/tax", json={
        "complex_id": "C001", "price": 1_000_000_000, "buyer_type": "individual",
        "owner_count": 1, "sale_price": 1_300_000_000, "holding_years": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["acquisition_tax"]["acquisition_tax"] == 10_000_000
    assert body["total_tax"] > body["acquisition_tax"]["total"]


def test_loan_endpoint_binding_constraint(app_client):
    resp = app_client.post("/api/v1/simulation/loan", json={
        "price": 1_000_000_000, "income": 50_000_000, "area_type": "non_regulated"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["binding_constraint"] == "DSR"
    assert body["max_borrowable"] == body["dsr_cap_amount"] < body["ltv_cap_amount"]


@pytest.mark.asyncio
async def test_tax_engine_degrades_when_typedb_fails():
    svc = MagicMock()
    svc.execute_read.side_effect = RuntimeError("down")
    eng = TaxEngine(svc)
    r = await eng.calc_acquisition_tax(500_000_000, "individual", 3, "regulated")
    assert r["rate_source"] == "default" and r["rate"] == 0.12
    assert (await eng.calc_capital_gains_tax(5, 4, 3, "x", 1))["total"] == 0
    assert (await eng.calc_comprehensive_tax([500_000_000], 1))["total"] == 0
    assert (await eng.calc_comprehensive_tax([2_000_000_000], 1))["total"] > 0
