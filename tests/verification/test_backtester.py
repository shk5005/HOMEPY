from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from homepy.inference.scorer import FACTOR_WEIGHTS
from homepy.verification.backtester import BacktestResult, Backtester

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
V_DATE = datetime(2026, 1, 15, tzinfo=timezone.utc)


class MockTimescale:
    """Records every query; serves verdicts and an as-of price series."""

    def __init__(self) -> None:
        self.executed_queries: list[str] = []
        self.executed_calls: list[tuple[str, tuple]] = []
        self._verdicts: dict[str, dict] = {}
        self.set_verdicts(
            [
                {"verdict": "매수 검토", "score": 70, "actual_3m": 4.0,
                 "factor_scores": {f: 50.0 + i for i, f in enumerate(FACTOR_WEIGHTS)}}
                for _ in range(1)
            ]
        )
        self._verdicts = {"V001": self._verdicts["V1"]}

    def set_verdicts(self, items: list[dict]) -> None:
        self._verdicts = {}
        for i, it in enumerate(items, 1):
            self._verdicts[f"V{i}"] = {
                "ts": it.get("ts", V_DATE),
                "complex_id": f"C{i}",
                **it,
            }

    def set_factor_data(self, ic_signs: dict[str, float]) -> None:
        """Synthetic cohort: factors in ic_signs get the sign given, others positive."""
        items = []
        for i in range(20):
            scores = {
                f: (float(i) if ic_signs.get(f, 1.0) >= 0 else float(-i))
                for f in FACTOR_WEIGHTS
            }
            items.append({"verdict": "매수 검토", "score": 60, "actual_3m": float(i) - 5,
                          "factor_scores": scores})
        self.set_verdicts(items)

    async def execute(self, query: str, *args):
        self.executed_queries.append(query)
        self.executed_calls.append((query, args))
        if "FROM ts_signals" in query and "target_id = $1" in query:
            v = self._verdicts.get(args[0])
            return [self._row(args[0], v)] if v else []
        if "FROM ts_signals" in query:
            return [self._row(k, v) for k, v in self._verdicts.items()]
        if "FROM ts_real_trade" in query:
            cid, as_of = args
            v = next(v for v in self._verdicts.values() if v["complex_id"] == cid)
            delta = (as_of - v["ts"]).days
            key = None if delta < 45 else "actual_3m" if delta < 135 else (
                "actual_6m" if delta < 270 else "actual_12m")
            if key is None:
                return [{"price_per_pyeong": 100.0, "ts": v["ts"]}]
            pct = v.get(key)
            if pct is None:
                return []
            trade_ts = v["ts"] + timedelta(days=delta)
            return [{"price_per_pyeong": 100.0 * (1 + pct / 100), "ts": trade_ts}]
        raise AssertionError(query)

    @staticmethod
    def _row(vid: str, v: dict) -> dict:
        meta = {k: v[k] for k in ("complex_id", "verdict", "score") if k in v}
        meta["factor_scores"] = v.get("factor_scores", {})
        meta["scenarios"] = v.get("scenarios", {})
        meta["bias_warnings"] = v.get("bias_warnings", [])
        return {"ts": v["ts"], "target_id": vid, "metadata": meta}


@pytest.fixture
def mock_timescale() -> MockTimescale:
    return MockTimescale()


def make(mock) -> Backtester:
    return Backtester(mock, now=lambda: NOW)


async def test_backtest_no_lookahead(mock_timescale):
    """Verdict from 2026-01-15 must only use data with ts <= 2026-01-15 (+ horizon)."""
    record = await make(mock_timescale).evaluate_verdict("V001")
    assert mock_timescale.executed_queries
    for query in mock_timescale.executed_queries:
        assert "2026-01-15" in query or "ts <=" in query
    # baseline price lookup is bounded by the verdict date itself
    base_args = [a for q, a in mock_timescale.executed_calls if "ts_real_trade" in q][0]
    assert base_args[1].date() <= V_DATE.date()
    assert record.actual_price_change_3m == pytest.approx(4.0)
    assert record.actual_price_change_12m is None  # horizon not matured at NOW


async def test_direction_accuracy_calculation(mock_timescale):
    mock_timescale.set_verdicts([
        {"verdict": "매수 검토", "score": 75, "actual_3m": 5.0},
        {"verdict": "매수 검토", "score": 70, "actual_3m": -3.0},
        {"verdict": "매도 검토", "score": 30, "actual_3m": -5.0},
    ])
    result = await make(mock_timescale).run(lookback_months=3)
    assert isinstance(result, BacktestResult)
    assert result.total_verdicts == 3
    assert result.direction_accuracy == pytest.approx(66.67, abs=0.1)
    assert result.signal_hit_rate == pytest.approx(66.67, abs=0.1)


async def test_scenario_and_bias_metrics(mock_timescale):
    sc = {"bear": {"price_change": -5}, "bull": {"price_change": 8}}
    mock_timescale.set_verdicts([
        {"verdict": "매수 검토", "score": 75, "actual_3m": 5.0, "scenarios": sc},
        {"verdict": "매수 검토", "score": 70, "actual_3m": -9.0, "scenarios": sc,
         "bias_warnings": [{"type": "anchoring"}]},
    ])
    r = await make(mock_timescale).run(lookback_months=3)
    assert r.scenario_capture_rate == 50.0
    assert r.bias_validity_rate == 100.0


async def test_factor_ic_identifies_weak_factors(mock_timescale):
    mock_timescale.set_factor_data({})
    ic = await make(mock_timescale).factor_ic_analysis(months=12)
    assert all(isinstance(v, float) for v in ic.values())
    assert len(ic) == 14
    assert all(v == pytest.approx(1.0) for v in ic.values())


async def test_underperforming_factors_flagged(mock_timescale):
    """Factors with IC < 0 should appear in underperforming list"""
    mock_timescale.set_factor_data({"tax_burden": -0.05, "unsold_risk": -0.02})
    result = await make(mock_timescale).run(lookback_months=12)
    assert "tax_burden" in result.underperforming_factors
    assert "unsold_risk" in result.underperforming_factors
    assert "valuation_gap" not in result.underperforming_factors


async def test_unknown_verdict_raises(mock_timescale):
    with pytest.raises(KeyError):
        await make(mock_timescale).evaluate_verdict("NOPE")
