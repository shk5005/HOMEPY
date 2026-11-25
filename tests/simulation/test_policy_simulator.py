from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from homepy.inference.scorer import InvestmentScore
from homepy.simulation import PolicyBacktest, PolicyImpact, PolicySimulator


class MockTypeDB:
    def __init__(self):
        self.entities = {"tax-rule": 5}
        self.execute_write = MagicMock()

    def entity_count(self, name: str) -> int:
        return self.entities[name]


@pytest.fixture
def mock_typedb():
    return MockTypeDB()


@pytest.fixture
def mock_scorer():
    s = MagicMock()
    s.score = AsyncMock(return_value=InvestmentScore(
        "market-baseline", 60.0, "B", [], datetime.now(timezone.utc)))
    return s


@pytest.fixture
def mock_timescale():
    t = MagicMock()
    t.execute = AsyncMock(return_value=[])
    return t


async def test_tax_change_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_tax_change({"acquisition_tax_rate": 0.04})
    assert isinstance(impact, PolicyImpact)
    assert impact.policy_change.policy_type == "tax"
    assert impact.score_before != impact.score_after
    assert len(impact.impact_chain) >= 1


async def test_regulation_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_regulation("11680", "speculation_zone", "designate")
    assert impact.policy_change.policy_type == "regulation"
    assert "11680" in impact.affected_districts
    assert impact.delta < 0


async def test_regulation_release_improves(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    assert (await sim.simulate_regulation("11680", "speculation_zone", "release")).delta > 0
    with pytest.raises(ValueError):
        await sim.simulate_regulation("11680", "speculation_zone", "bogus")


async def test_interest_rate_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_interest_rate([3.5, 3.25, 3.0])
    assert impact.policy_change.policy_type == "interest_rate"
    assert impact.delta > 0


async def test_supply_shock_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_supply_shock("11680", units=5000)
    assert impact.policy_change.policy_type == "supply_shock"
    assert impact.delta < 0


async def test_simulation_does_not_mutate_typedb(mock_typedb, mock_scorer, mock_timescale):
    count_before = mock_typedb.entity_count("tax-rule")
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    await sim.simulate_tax_change({"acquisition_tax_rate": 0.04})
    assert count_before == mock_typedb.entity_count("tax-rule")
    mock_typedb.execute_write.assert_not_called()


async def test_policy_backtest(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    result = await sim.backtest_policy(
        policy_name="7.10 대책", policy_date=date(2020, 7, 10),
        changes={"speculation_zone": ["강남구", "서초구", "송파구"]})
    assert isinstance(result, PolicyBacktest)
    assert 0.0 <= result.accuracy_score <= 1.0


def test_policy_endpoints(mock_typedb, mock_scorer, mock_timescale):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from homepy.api.dependencies import get_policy_simulator
    from homepy.api.routers.simulation import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/simulation")
    app.dependency_overrides[get_policy_simulator] = lambda: PolicySimulator(
        mock_typedb, mock_scorer, mock_timescale)
    c = TestClient(app)
    r = c.post("/api/v1/simulation/policy", json={
        "policy_type": "supply_shock",
        "parameters": {"district_code": "11680", "units": 5000}})
    assert r.status_code == 200 and r.json()["delta"] < 0
    r = c.post("/api/v1/simulation/policy", json={"policy_type": "regulation", "parameters": {}})
    assert r.status_code == 422
    r = c.post("/api/v1/simulation/policy/backtest", json={
        "policy_name": "x", "policy_date": "2020-07-10", "changes": {}})
    assert r.status_code == 200
