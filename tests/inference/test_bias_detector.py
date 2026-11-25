from datetime import datetime, timezone

from homepy.inference.bias_detector import BiasDetector
from homepy.inference.scorer import FACTOR_WEIGHTS, FactorScore, InvestmentScore


def make_score(positive_factors: int = 7, negative_factors: int = 7) -> InvestmentScore:
    names = list(FACTOR_WEIGHTS)
    assert positive_factors + negative_factors == len(names)
    factors = []
    for i, name in enumerate(names):
        norm = 70.0 if i < positive_factors else 30.0
        w = FACTOR_WEIGHTS[name]
        factors.append(FactorScore(name, 0.0, norm, w, norm * w, [f"mock {name}"]))
    total = round(sum(f.weighted_score for f in factors), 4)
    return InvestmentScore("C001", total, "C", factors, datetime.now(timezone.utc))


async def test_confirmation_bias_fires_on_skewed_signals(mock_timescale):
    score = make_score(positive_factors=12, negative_factors=2)
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score)
    types = [w.bias_type for w in warnings]
    assert "confirmation_bias" in types


async def test_no_bias_on_balanced_input(mock_timescale):
    score = make_score(positive_factors=7, negative_factors=7)
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score)
    assert len(warnings) == 0


async def test_anchoring_when_reference_price_diverges(mock_timescale):
    score = make_score()
    ctx = {"reference_price": 1_000_000_000}  # user's anchor
    mock_timescale.set_response([{"fair_value": 600_000_000}])
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score, user_context=ctx)
    assert any(w.bias_type == "anchoring" for w in warnings)


async def test_all_nine_biases_have_detectors(mock_timescale):
    detector = BiasDetector(mock_timescale)
    assert len(detector.BIAS_CHECKS) == 9
