from __future__ import annotations

import json

import pytest

from homepy.inference.scorer import FACTOR_WEIGHTS
from homepy.verification.calibrator import AutoCalibrator
from homepy.verification.models import ImprovementRecord

FACTORS = list(FACTOR_WEIGHTS)


class MockBacktester:
    """factor_ic_analysis(months): >6 months -> in-sample, otherwise out-of-sample."""

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.in_sample = {f: 0.05 * (i % 4) for i, f in enumerate(FACTORS)}
        self.out_of_sample = dict(self.in_sample)

    def set_ic_split(self, in_sample: dict, out_of_sample: dict) -> None:
        self.in_sample, self.out_of_sample = in_sample, out_of_sample

    async def factor_ic_analysis(
        self, months: int = 12, skip_recent_months: int = 0,
    ) -> dict[str, float]:
        self.calls.append((months, skip_recent_months))
        if skip_recent_months > 0:
            return dict(self.in_sample)
        return dict(self.out_of_sample if months <= 6 else self.in_sample)


class MockTimescale:
    def __init__(self) -> None:
        self.bias_rows: list[dict] = []
        self.queries: list[str] = []

    async def execute(self, query: str, *args):
        self.queries.append(query)
        if "bias_outcome" in query:
            return self.bias_rows
        return [{"factor": f, "p05": 10.0 + i, "p95": 90.0 + i} for i, f in enumerate(FACTORS)]


@pytest.fixture
def mock_backtester():
    return MockBacktester()


@pytest.fixture
def mock_timescale():
    return MockTimescale()


@pytest.fixture
def cal(mock_backtester, mock_timescale, tmp_path):
    return AutoCalibrator(mock_backtester, mock_timescale, config_path=tmp_path / "calibration.json")


async def test_weight_proposal_uses_rolling_window(cal, mock_backtester):
    proposal = await cal.propose_weight_update()
    assert proposal.category == "weight"
    assert proposal.status == "proposed"
    assert "36" in proposal.rationale or "rolling" in proposal.rationale.lower()
    assert (36, 6) in mock_backtester.calls and (6, 0) in mock_backtester.calls


async def test_weight_proposal_flags_overfit(cal, mock_backtester):
    fs = FACTORS[:5]
    mock_backtester.set_ic_split(
        in_sample={f: 0.3 for f in fs}, out_of_sample={f: -0.1 for f in fs}
    )
    proposal = await cal.propose_weight_update()
    assert "overfit" in proposal.risk_assessment.lower()
    assert proposal.backtest_evidence["overfit"] is True


async def test_three_degraded_factors_is_not_overfit(cal, mock_backtester):
    fs = FACTORS[:3]
    mock_backtester.set_ic_split(
        in_sample={f: 0.3 for f in fs}, out_of_sample={f: -0.1 for f in fs}
    )
    proposal = await cal.propose_weight_update()
    assert proposal.backtest_evidence["overfit"] is False


async def test_weights_still_sum_to_one(cal):
    proposal = await cal.propose_weight_update()
    assert set(proposal.proposed_values) == set(FACTOR_WEIGHTS)
    assert abs(sum(proposal.proposed_values.values()) - 1.0) < 1e-9


async def test_weights_proportional_to_positive_ic(cal, mock_backtester):
    mock_backtester.set_ic_split(
        in_sample={"valuation_gap": 0.3, "price_momentum": 0.1, "supply_demand_gap": -0.2},
        out_of_sample={"valuation_gap": 0.3, "price_momentum": 0.1, "supply_demand_gap": -0.2},
    )
    w = (await cal.propose_weight_update()).proposed_values
    assert w["valuation_gap"] == pytest.approx(0.75)
    assert w["price_momentum"] == pytest.approx(0.25)
    assert w["supply_demand_gap"] == 0.0


async def test_all_nonpositive_ic_keeps_current_weights(cal, mock_backtester):
    mock_backtester.set_ic_split(in_sample={f: -0.1 for f in FACTORS}, out_of_sample={})
    p = await cal.propose_weight_update()
    assert p.proposed_values == p.current_values
    assert abs(sum(p.proposed_values.values()) - 1.0) < 1e-9


async def test_normalization_refresh_auto_applies(cal):
    ranges = await cal.refresh_normalization_ranges()
    assert isinstance(ranges, dict) and ranges
    for factor, (lo, hi) in ranges.items():
        assert lo < hi
    assert cal.normalization_ranges == ranges


async def test_apply_creates_improvement_record(cal, tmp_path):
    proposal = await cal.propose_weight_update()
    record = await cal.apply_proposal(proposal.proposal_id)
    assert isinstance(record, ImprovementRecord)
    assert record.category == "calibration"
    assert record.rollback_possible is True
    assert record.before_state == proposal.current_values
    assert proposal.status == "applied"
    saved = json.loads((tmp_path / "calibration.json").read_text())
    assert saved["weights"] == proposal.proposed_values
    with pytest.raises(ValueError):
        await cal.apply_proposal(proposal.proposal_id)


async def test_reject_proposal(cal, tmp_path):
    proposal = await cal.propose_weight_update()
    await cal.reject_proposal(proposal.proposal_id, "too aggressive")
    assert proposal.status == "rejected"
    assert proposal.backtest_evidence["rejection_reason"] == "too aggressive"
    assert not (tmp_path / "calibration.json").exists()
    with pytest.raises(ValueError):
        await cal.apply_proposal(proposal.proposal_id)


async def test_unknown_proposal_raises(cal):
    with pytest.raises(KeyError):
        await cal.apply_proposal("nope")


async def test_threshold_proposal_maximizes_f1(cal, mock_timescale):
    # warnings valid only when ratio >= 5 -> best threshold is 5, not the current 3.0
    mock_timescale.bias_rows = [
        {"metadata": {"bias": "confirmation", "value": v, "valid": v >= 5}}
        for v in (1, 2, 3, 4, 5, 6, 7, 8)
    ]
    p = await cal.propose_threshold_update()
    assert p.category == "threshold"
    assert p.proposed_values["CONFIRMATION_RATIO"] == 5
    assert p.current_values["CONFIRMATION_RATIO"] == 3.0
    # no data for other biases -> unchanged
    assert p.proposed_values["ANCHORING_DIVERGENCE"] == p.current_values["ANCHORING_DIVERGENCE"]
    rec = await cal.apply_proposal(p.proposal_id)
    assert rec.component == "thresholds"
