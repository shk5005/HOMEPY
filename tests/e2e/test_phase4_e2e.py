import pytest

pytestmark = pytest.mark.skip(reason="requires live services")


async def test_e2e_nlp_to_report(test_client):
    """End-to-end: NL query -> TypeQL -> analysis -> debate -> report."""
    nlp_resp = await test_client.post("/api/v1/nlp/query", json={"query": "강남구에서 저평가된 단지"})
    assert nlp_resp.status_code == 200
    complexes = nlp_resp.json()["results"]
    assert len(complexes) > 0

    report_resp = await test_client.post("/api/v1/reports/generate", json={
        "complex_id": complexes[0]["id"], "format": "html", "include_debate": True})
    assert report_resp.status_code == 200
    assert "투자 요약" in report_resp.text
