import pytest

from homepy.inference.scorer import (
    FACTOR_WEIGHTS, FactorScore, InvestmentScore, InvestmentScorer, grade_for,
)


def test_factor_weights_sum_to_one():
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_factor_weights_has_14_entries():
    assert len(FACTOR_WEIGHTS) == 14


async def test_scorer_returns_investment_score(mock_typedb, mock_timescale):
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    assert isinstance(result, InvestmentScore)
    assert all(isinstance(f, FactorScore) for f in result.factors)
    assert 0 <= result.total_score <= 100
    assert result.grade in ("A", "B", "C", "D", "F")
    assert len(result.factors) == 14
    assert {f.name for f in result.factors} == set(FACTOR_WEIGHTS)


async def test_valuation_gap_positive_when_undervalued(mock_typedb, mock_timescale):
    mock_typedb.set_response([{"price_per_sqm": 15_000_000, "district_avg_price": 20_000_000}])
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    vg = next(f for f in result.factors if f.name == "valuation_gap")
    assert vg.normalized > 50


async def test_valuation_gap_low_when_overvalued(mock_typedb, mock_timescale):
    mock_typedb.set_response([{"price_per_sqm": 25_000_000, "district_avg_price": 20_000_000}])
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    vg = next(f for f in result.factors if f.name == "valuation_gap")
    assert vg.normalized < 50


async def test_tax_burden_high_normalized_low(mock_typedb, mock_timescale):
    mock_typedb.set_response([{"effective_tax_rate": 12.0}])
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    tb = next(f for f in result.factors if f.name == "tax_burden")
    assert tb.normalized < 30


async def test_every_factor_has_evidence(mock_typedb, mock_timescale):
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    for f in result.factors:
        assert len(f.evidence) >= 1, f"{f.name} has no evidence"


async def test_every_factor_has_evidence_when_no_data(mock_typedb, mock_timescale):
    mock_typedb.set_response([])
    mock_timescale.set_response([])
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    assert len(result.factors) == 14
    for f in result.factors:
        assert f.evidence


async def _factor(mock_typedb, mock_timescale, name):
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    return next(f for f in result.factors if f.name == name)


# Normalization direction: (factor, timescale/typedb, key, good value, bad value)
HIGHER_BETTER_TS = [
    ("price_momentum", "price_change_pct_12m", 10.0, -5.0),
    ("jeonse_ratio_trend", "jeonse_ratio_change_pp", 5.0, -5.0),
    ("liquidity_trend", "volume_change_pct", 30.0, -30.0),
    ("migration_momentum", "net_migration_pct", 0.8, -0.8),
]
INVERSE_TS = [
    ("unsold_risk", "unsold_ratio_pct", 0.5, 8.0),
    ("interest_rate_cycle", "rate_change_bp_6m", -50, 50),
]


@pytest.mark.parametrize("name,key,good,bad", HIGHER_BETTER_TS + INVERSE_TS)
async def test_timescale_factor_direction(mock_typedb, mock_timescale, name, key, good, bad):
    mock_timescale.set_response_for(f"factor:{name}", [{key: good}])
    g = await _factor(mock_typedb, mock_timescale, name)
    mock_timescale.set_response_for(f"factor:{name}", [{key: bad}])
    b = await _factor(mock_typedb, mock_timescale, name)
    assert g.normalized > b.normalized
    assert g.normalized > 50 > b.normalized


async def test_supply_demand_surplus_is_good(mock_typedb, mock_timescale):
    mock_timescale.set_response_for("factor:supply_demand_gap",
                                    [{"demand_households": 10000, "supply_units": 5000}])
    g = await _factor(mock_typedb, mock_timescale, "supply_demand_gap")
    mock_timescale.set_response_for("factor:supply_demand_gap",
                                    [{"demand_households": 5000, "supply_units": 10000}])
    b = await _factor(mock_typedb, mock_timescale, "supply_demand_gap")
    assert g.normalized > 50 > b.normalized


async def test_transport_access_closer_is_better(mock_typedb, mock_timescale):
    mock_typedb.set_response_for("factor:transport_access", [{"nearest_station_m": 300}])
    g = await _factor(mock_typedb, mock_timescale, "transport_access")
    mock_typedb.set_response_for("factor:transport_access", [{"nearest_station_m": 1500}])
    b = await _factor(mock_typedb, mock_timescale, "transport_access")
    assert g.normalized > b.normalized


async def test_development_upside_more_is_better(mock_typedb, mock_timescale):
    mock_typedb.set_response_for("factor:development_upside", [{"stage_weight": 1.0}] * 3)
    g = await _factor(mock_typedb, mock_timescale, "development_upside")
    mock_typedb.set_response_for("factor:development_upside", [{"stage_weight": 0.0}])
    b = await _factor(mock_typedb, mock_timescale, "development_upside")
    assert g.normalized > b.normalized


async def test_regulation_impact_is_inverse(mock_typedb, mock_timescale):
    mock_typedb.set_response_for("factor:regulation_impact", [{"severity": 0}])
    g = await _factor(mock_typedb, mock_timescale, "regulation_impact")
    mock_typedb.set_response_for("factor:regulation_impact", [{"severity": 3}, {"severity": 3}])
    b = await _factor(mock_typedb, mock_timescale, "regulation_impact")
    assert g.normalized > b.normalized
    assert b.normalized < 10


async def test_cycle_position_recovery_beats_contraction(mock_typedb, mock_timescale):
    mock_timescale.set_response_for("factor:cycle_position", [{"phase": "recovery"}])
    g = await _factor(mock_typedb, mock_timescale, "cycle_position")
    mock_timescale.set_response_for("factor:cycle_position", [{"phase": "contraction"}])
    b = await _factor(mock_typedb, mock_timescale, "cycle_position")
    assert g.normalized > 50 > b.normalized


async def test_sentiment_composite_bidirectional_with_subevidence(mock_typedb, mock_timescale):
    row = lambda d, f, s: [{"sentiment_divergence": d, "fear_greed_index": f,
                            "search_trend_change_pct": s}]
    mock_timescale.set_response_for("factor:sentiment_composite", row(0.8, 85, 40))
    g = await _factor(mock_typedb, mock_timescale, "sentiment_composite")
    mock_timescale.set_response_for("factor:sentiment_composite", row(-0.8, 15, -40))
    b = await _factor(mock_typedb, mock_timescale, "sentiment_composite")
    assert g.normalized > 50 > b.normalized
    text = " ".join(g.evidence)
    for sub in ("sentiment_divergence", "fear_greed_position", "search_trend_signal"):
        assert sub in text


async def test_weighted_score_and_total(mock_typedb, mock_timescale):
    result = await InvestmentScorer(mock_typedb, mock_timescale).score("C001")
    for f in result.factors:
        assert f.weighted_score == pytest.approx(f.normalized * f.weight)
    assert result.total_score == pytest.approx(sum(f.weighted_score for f in result.factors), abs=1e-3)


@pytest.mark.parametrize("s,g", [(100, "A"), (80, "A"), (79.9, "B"), (65, "B"), (64.9, "C"),
                                 (50, "C"), (49.9, "D"), (35, "D"), (34.9, "F"), (0, "F")])
def test_grade_boundaries(s, g):
    assert grade_for(s) == g


@pytest.mark.parametrize("name", ["regulation_impact", "development_upside"])
async def test_empty_typedb_result_is_neutral(mock_typedb, mock_timescale, name):
    mock_typedb.set_response_for(f"factor:{name}", [])
    f = await _factor(mock_typedb, mock_timescale, name)
    assert f.normalized == 50.0
    assert "no data available" in " ".join(f.evidence).lower()


@pytest.mark.parametrize("bad", ['C1" ; delete $x;', "", "C 1", "C001\n", "a'b"])
async def test_invalid_complex_id_rejected(mock_typedb, mock_timescale, bad):
    with pytest.raises(ValueError):
        await InvestmentScorer(mock_typedb, mock_timescale).score(bad)
    assert mock_typedb.calls == [] and mock_timescale.calls == []


async def test_complex_id_propagates_to_queries(mock_typedb, mock_timescale):
    await InvestmentScorer(mock_typedb, mock_timescale).score("C999")
    assert mock_typedb.calls
    assert all("C999" in q and "C001" not in q for q in mock_typedb.calls)
    assert mock_timescale.call_args
    assert all(a == ("C999",) for q, a in zip(mock_timescale.calls, mock_timescale.call_args)
               if "$1" in q)
    assert any("C999" in a for a in mock_timescale.call_args)
