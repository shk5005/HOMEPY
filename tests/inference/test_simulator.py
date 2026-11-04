import copy

import pytest

from homepy.inference.simulator import ScenarioSimulator
from tests.inference.conftest import MockInvestmentScorer, MockTimescaleService


@pytest.fixture
def sigma_ts():
    """Timescale mock with hard-coded sigma values."""
    ts = MockTimescaleService({})
    ts.set_response_for("sigma:interest_rate_cycle", [{"sigma": 30.0}])
    ts.set_response_for("sigma:supply_demand_gap", [{"sigma": 10.0}])
    return ts


async def test_simulator_produces_three_scenarios(mock_scorer, sigma_ts):
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate("C001")
    assert len(result.scenarios) == 3
    assert {s.name for s in result.scenarios} == {"bull", "base", "bear"}


async def test_bull_score_higher_than_bear(mock_scorer, sigma_ts):
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate("C001")
    bull = next(s for s in result.scenarios if s.name == "bull")
    bear = next(s for s in result.scenarios if s.name == "bear")
    assert bull.probability + bear.probability <= 1.0

    def score_of(s):
        return float(s.expected_outcome.split("score ")[1].split(" ")[0])

    assert score_of(bull) > score_of(bear)


async def test_sensitivity_varies_with_perturbation(mock_scorer, sigma_ts):
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate(
        "C001", variables=["interest_rate_cycle"]
    )
    assert len(result.sensitivity) >= 1
    sr = result.sensitivity[0]
    assert len(sr.perturbations) >= 3
    assert sr.score_impacts[0] != sr.score_impacts[-1]
    # rate cycle is inverse: -2 sigma (rates falling) is good, +2 sigma is bad
    assert sr.score_impacts[0] > 0 > sr.score_impacts[-1]
    assert sr.score_impacts[2] == 0


async def test_scenarios_have_required_fields(mock_scorer, sigma_ts):
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate("C001")
    for s in result.scenarios:
        assert len(s.conditions) >= 1
        assert len(s.key_variables) >= 1
        assert s.expected_outcome
        assert len(s.leading_indicators) >= 1
        assert len(s.invalidation_conditions) >= 1


async def test_default_variables_and_fallback_sigma(mock_scorer, mock_timescale):
    # mock_timescale has no sigma rows -> default sigmas used
    result = await ScenarioSimulator(mock_scorer, mock_timescale).simulate("C001")
    assert [s.variable for s in result.sensitivity] == [
        "supply_demand_gap", "valuation_gap", "interest_rate_cycle",
        "transport_access", "price_momentum",
    ]


async def test_base_scenario_matches_base_score_and_probabilities_sum(mock_scorer, sigma_ts):
    base = await mock_scorer.score("C001")
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate("C001")
    b = next(s for s in result.scenarios if s.name == "base")
    assert f"{base.total_score:.1f}" in b.expected_outcome
    assert sum(s.probability for s in result.scenarios) == pytest.approx(1.0)


async def test_sigma_used_from_timescale(mock_scorer, sigma_ts):
    result = await ScenarioSimulator(mock_scorer, sigma_ts).simulate(
        "C001", variables=["supply_demand_gap"]
    )
    sr = result.sensitivity[0]
    assert sr.perturbations[3] - sr.base_value == pytest.approx(10.0)


async def test_deep_copy_isolation(sigma_ts):
    """Perturbing must not mutate the scorer's base object or leak between scenarios."""
    scorer = MockInvestmentScorer()
    shared = await scorer.score("C001")
    snapshot = copy.deepcopy(shared)

    class FixedScorer:
        async def score(self, cid):
            return shared  # same object every call

    sim = ScenarioSimulator(FixedScorer(), sigma_ts)
    r1 = await sim.simulate("C001")
    assert shared.total_score == snapshot.total_score
    assert [f.raw_value for f in shared.factors] == [f.raw_value for f in snapshot.factors]
    assert [f.normalized for f in shared.factors] == [f.normalized for f in snapshot.factors]
    r2 = await sim.simulate("C001")  # repeat gives identical results
    assert r1 == r2


async def test_unknown_variable_rejected(mock_scorer, sigma_ts):
    with pytest.raises(ValueError):
        await ScenarioSimulator(mock_scorer, sigma_ts).simulate("C001", variables=["nope"])
