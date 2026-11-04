import pytest

REQUIRED_FIELDS = [
    "core_facts", "strongest_bull_case", "strongest_bear_case", "hidden_variable",
    "primary_risk", "verdict", "confidence", "kill_switch", "watchlist_data",
    "bias_warnings", "scenario_summary", "evidence_chain",
]


@pytest.mark.skip(reason="requires live DBs")
async def test_full_stack_verdict_roundtrip():
    """
    1. Bootstrap DBs (Plan A bootstrap script)
    2. Insert seed data: region->district->dong->complex, interest_rate, supply_data
    3. Run sync (timescale->typedb aggregates)
    4. Call POST /api/v1/analysis/verdict/C001
    5. Assert verdict has all 12 Red Team Protocol fields
    6. Assert evidence_chain traces back to seed data
    """
    import httpx

    from homepy.api.main import create_app

    app = create_app()
    # TODO(live DBs): bootstrap, seed, sync here.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/analysis/verdict/C001")
    assert resp.status_code == 200
    body = resp.json()
    for f in REQUIRED_FIELDS:
        assert f in body
    assert body["evidence_chain"]
