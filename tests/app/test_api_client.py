import httpx
import pytest

from homepy.app.api_client import ApiClient, ApiError

BASE = "http://localhost:8000"


async def test_get_macro_summary(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/api/v1/market/macro/summary",
                            json={"base_rate": 3.25, "cycle_phase": "recovery"})
    result = await ApiClient(BASE).get_macro_summary()
    assert result["base_rate"] == 3.25


async def test_get_cycle(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/api/v1/market/cycle/11680",
                            json={"district_code": "11680", "phase": "expansion"})
    assert (await ApiClient(BASE).get_cycle("11680"))["phase"] == "expansion"


async def test_post_score(httpx_mock):
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/v1/analysis/score",
                            json=[{"complex_id": "C001", "total_score": 72.5}])
    result = await ApiClient(BASE).post_score(["C001"])
    assert len(result) == 1
    assert httpx_mock.get_requests()[0].read() == b'{"complex_ids":["C001"]}'


async def test_post_verdict_scenario_graph_status(httpx_mock):
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/v1/analysis/verdict/C001", json={"verdict": "buy"})
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/v1/simulation/scenario/C001", json={"scenarios": []})
    httpx_mock.add_response(url=f"{BASE}/api/v1/ontology/graph/C001", json={"nodes": []})
    httpx_mock.add_response(url=f"{BASE}/api/v1/pipeline/status", json={"total_rows": 3})
    c = ApiClient(BASE + "/")
    assert (await c.post_verdict("C001"))["verdict"] == "buy"
    assert (await c.post_scenario("C001"))["scenarios"] == []
    assert (await c.get_graph("C001"))["nodes"] == []
    assert (await c.get_pipeline_status())["total_rows"] == 3


async def test_tax_and_loan(httpx_mock):
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/v1/simulation/tax", json={"total_tax": 10})
    httpx_mock.add_response(method="POST", url=f"{BASE}/api/v1/simulation/loan", json={"max_borrowable": 5})
    c = ApiClient(BASE)
    assert (await c.post_tax({"price": 1}))["total_tax"] == 10
    assert (await c.post_loan({"price": 1, "income": 1}))["max_borrowable"] == 5


async def test_http_error_raises_api_error(httpx_mock):
    httpx_mock.add_response(status_code=422, json={"detail": "bad"})
    with pytest.raises(ApiError):
        await ApiClient(BASE).get_macro_summary()


async def test_connection_error_retries_then_raises(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("down"), is_reusable=True)
    with pytest.raises(ApiError):
        await ApiClient(BASE, retries=2, backoff=0).get_macro_summary()
    assert len(httpx_mock.get_requests()) == 3


async def test_retry_recovers(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("down"))
    httpx_mock.add_response(json={"base_rate": 1})
    assert (await ApiClient(BASE, retries=1, backoff=0).get_macro_summary())["base_rate"] == 1
