import httpx
import pytest
import respx

from homepy.app.api_client import ApiClient, ApiError

BASE = "http://localhost:8000"


async def test_get_macro_summary(respx_mock):
    respx_mock.get(f"{BASE}/api/v1/market/macro/summary").respond(
        json={"base_rate": 3.25, "cycle_phase": "recovery"})
    result = await ApiClient(BASE).get_macro_summary()
    assert result["base_rate"] == 3.25


async def test_get_cycle(respx_mock):
    respx_mock.get(f"{BASE}/api/v1/market/cycle/11680").respond(
        json={"district_code": "11680", "phase": "expansion"})
    assert (await ApiClient(BASE).get_cycle("11680"))["phase"] == "expansion"


async def test_post_score(respx_mock):
    route = respx_mock.post(f"{BASE}/api/v1/analysis/score").respond(
        json=[{"complex_id": "C001", "total_score": 72.5}])
    result = await ApiClient(BASE).post_score(["C001"])
    assert len(result) == 1
    assert route.calls[0].request.content == b'{"complex_ids":["C001"]}'


async def test_post_verdict_scenario_graph_status(respx_mock):
    respx_mock.post(f"{BASE}/api/v1/analysis/verdict/C001").respond(json={"verdict": "buy"})
    respx_mock.post(f"{BASE}/api/v1/simulation/scenario/C001").respond(json={"scenarios": []})
    respx_mock.get(f"{BASE}/api/v1/ontology/graph/C001").respond(json={"nodes": []})
    respx_mock.get(f"{BASE}/api/v1/pipeline/status").respond(json={"total_rows": 3})
    c = ApiClient(BASE + "/")
    assert (await c.post_verdict("C001"))["verdict"] == "buy"
    assert (await c.post_scenario("C001"))["scenarios"] == []
    assert (await c.get_graph("C001"))["nodes"] == []
    assert (await c.get_pipeline_status())["total_rows"] == 3


async def test_tax_and_loan(respx_mock):
    respx_mock.post(f"{BASE}/api/v1/simulation/tax").respond(json={"total_tax": 10})
    respx_mock.post(f"{BASE}/api/v1/simulation/loan").respond(json={"max_borrowable": 5})
    c = ApiClient(BASE)
    assert (await c.post_tax({"price": 1}))["total_tax"] == 10
    assert (await c.post_loan({"price": 1, "income": 1}))["max_borrowable"] == 5


async def test_http_error_raises_api_error(respx_mock):
    respx_mock.get(f"{BASE}/api/v1/market/macro/summary").respond(status_code=422, json={"detail": "bad"})
    with pytest.raises(ApiError):
        await ApiClient(BASE).get_macro_summary()


async def test_connection_error_retries_then_raises(respx_mock):
    route = respx_mock.get(f"{BASE}/api/v1/market/macro/summary").mock(
        side_effect=httpx.ConnectError("down"))
    with pytest.raises(ApiError):
        await ApiClient(BASE, retries=2, backoff=0).get_macro_summary()
    assert route.call_count == 3


async def test_retry_recovers(respx_mock):
    route = respx_mock.get(f"{BASE}/api/v1/market/macro/summary")
    route.side_effect = [httpx.ConnectError("down"), httpx.Response(200, json={"base_rate": 1})]
    assert (await ApiClient(BASE, retries=1, backoff=0).get_macro_summary())["base_rate"] == 1
