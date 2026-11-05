"""BiasDetector: nine cognitive-bias checks (spec Section 5.4).

Each check returns ``BiasWarning | None``. Checks that need market data query
TimescaleDB (tolerating failures / empty results); checks about the user's own
position read ``user_context``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from homepy.inference.scorer import InvestmentScore

_log = logging.getLogger(__name__)

# Spec thresholds
CONFIRMATION_RATIO = 3.0
ANCHORING_DIVERGENCE = 0.20
SURVIVORSHIP_DECLINING_PCT = 30.0
AVAILABILITY_PERCENTILE = 90.0
LOSS_AVERSION_DRAWDOWN = -0.15
OVERCONFIDENCE_MIN_EVIDENCE = 3
BASE_RATE_MULTIPLE = 2.0
SUNK_COST_EXPIRED = 2

FAIR_VALUE_QUERY = (
    "-- bias:anchoring\nSELECT fair_value FROM fair_value_estimates "
    "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1"
)
RECENCY_QUERY = (
    "-- bias:recency\nSELECT change_3m_pct, change_36m_pct FROM price_trends "
    "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1"
)
SURVIVORSHIP_QUERY = (
    "-- bias:survivorship\nSELECT declining_ratio_pct FROM comparable_stats "
    "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1"
)
AVAILABILITY_QUERY = (
    "-- bias:availability\nSELECT search_volume_percentile FROM search_volume_rank "
    "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1"
)
BASE_RATE_QUERY = (
    "-- bias:base_rate\nSELECT avg_annual_return_10y_pct FROM historical_returns "
    "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1"
)


@dataclass
class BiasWarning:
    bias_type: str
    description: str
    severity: str  # "low" | "medium" | "high"
    evidence: str
    mitigation: str


def _num(row: Any, key: str) -> float | None:
    try:
        v = row.get(key)
    except AttributeError:
        return None
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class BiasDetector:
    def __init__(self, timescale_svc: Any) -> None:
        self.ts = timescale_svc
        self.BIAS_CHECKS = [
            self._check_confirmation,
            self._check_anchoring,
            self._check_recency,
            self._check_survivorship,
            self._check_availability,
            self._check_loss_aversion,
            self._check_overconfidence,
            self._check_base_rate_neglect,
            self._check_sunk_cost,
        ]

    async def detect(
        self,
        complex_id: str,
        score: InvestmentScore,
        user_context: dict | None = None,
    ) -> list[BiasWarning]:
        ctx = user_context or {}
        results = await asyncio.gather(
            *(check(complex_id, score, ctx) for check in self.BIAS_CHECKS),
            return_exceptions=True,
        )
        warnings: list[BiasWarning] = []
        for check, r in zip(self.BIAS_CHECKS, results):
            if isinstance(r, BaseException):
                _log.warning("bias check %s failed: %r", check.__name__, r)
                continue
            if r is not None:
                warnings.append(r)
        return warnings

    async def _row(self, query: str, complex_id: str) -> Any:
        try:
            rows = await self.ts.execute(query, complex_id)
        except Exception:
            _log.warning("bias query failed", exc_info=True)
            return None
        return rows[0] if rows else None

    # ---- checks -----------------------------------------------------

    async def _check_confirmation(self, complex_id, score, ctx) -> BiasWarning | None:
        pos = sum(1 for f in score.factors if f.normalized > 50)
        neg = sum(1 for f in score.factors if f.normalized < 50)
        if pos < CONFIRMATION_RATIO * neg or pos == 0:
            return None
        return BiasWarning(
            "confirmation_bias",
            "Signals are heavily one-sided; contrary evidence may be under-weighted.",
            "high" if neg == 0 or pos >= 5 * neg else "medium",
            f"{pos} positive vs {neg} negative factors (threshold: positive >= {CONFIRMATION_RATIO:g}x negative)",
            "Actively look for evidence that would contradict the thesis (bear case).",
        )

    async def _check_anchoring(self, complex_id, score, ctx) -> BiasWarning | None:
        ref = ctx.get("reference_price")
        if not ref:
            return None
        fair = _num(await self._row(FAIR_VALUE_QUERY, complex_id), "fair_value")
        if not fair or fair <= 0:
            return None
        div = (float(ref) - fair) / fair
        if abs(div) < ANCHORING_DIVERGENCE:
            return None
        return BiasWarning(
            "anchoring",
            "Your reference price diverges materially from estimated fair value.",
            "high" if abs(div) >= 2 * ANCHORING_DIVERGENCE else "medium",
            f"reference {float(ref):,.0f} vs fair value {fair:,.0f} ({div:+.0%})",
            "Decide against current fair value and comparables, not a past price.",
        )

    async def _check_recency(self, complex_id, score, ctx) -> BiasWarning | None:
        row = await self._row(RECENCY_QUERY, complex_id)
        short, long_ = _num(row, "change_3m_pct"), _num(row, "change_36m_pct")
        if short is None or long_ is None or short == 0 or long_ == 0:
            return None
        if (short > 0) == (long_ > 0):
            return None
        return BiasWarning(
            "recency_bias",
            "Short-term trend contradicts the long-term trend.",
            "medium",
            f"3M change {short:+.1f}% vs 36M change {long_:+.1f}%",
            "Weigh the multi-year trend; avoid extrapolating the last few months.",
        )

    async def _check_survivorship(self, complex_id, score, ctx) -> BiasWarning | None:
        pct = _num(await self._row(SURVIVORSHIP_QUERY, complex_id), "declining_ratio_pct")
        if pct is None or pct >= SURVIVORSHIP_DECLINING_PCT:
            return None
        return BiasWarning(
            "survivorship_bias",
            "Comparable set under-represents declining complexes.",
            "medium",
            f"declining comparables {pct:.0f}% (< {SURVIVORSHIP_DECLINING_PCT:.0f}%)",
            "Include delisted/declining comparables before trusting the benchmark.",
        )

    async def _check_availability(self, complex_id, score, ctx) -> BiasWarning | None:
        pct = _num(await self._row(AVAILABILITY_QUERY, complex_id), "search_volume_percentile")
        if pct is None or pct < AVAILABILITY_PERCENTILE:
            return None
        return BiasWarning(
            "availability_heuristic",
            "This region is in the top 10% of search attention; salience may inflate perceived value.",
            "low",
            f"search volume percentile {pct:.0f}",
            "Compare against less-publicized regions with similar fundamentals.",
        )

    async def _check_loss_aversion(self, complex_id, score, ctx) -> BiasWarning | None:
        peak, cur = ctx.get("peak_price"), ctx.get("current_price")
        if not peak or cur is None or not ctx.get("holding", True):
            return None
        dd = float(cur) / float(peak) - 1.0
        if dd > LOSS_AVERSION_DRAWDOWN:
            return None
        return BiasWarning(
            "loss_aversion",
            "Holding far below peak may be driven by reluctance to realize a loss.",
            "medium",
            f"current {float(cur):,.0f} is {dd:.0%} from peak {float(peak):,.0f}",
            "Ask whether you would buy at today's price with today's information.",
        )

    async def _check_overconfidence(self, complex_id, score, ctx) -> BiasWarning | None:
        conf, n = ctx.get("confidence"), ctx.get("evidence_count")
        if str(conf).lower() != "high" or n is None or n >= OVERCONFIDENCE_MIN_EVIDENCE:
            return None
        return BiasWarning(
            "overconfidence",
            "High confidence is not backed by enough evidence.",
            "high",
            f"confidence High with only {n} evidence item(s) (< {OVERCONFIDENCE_MIN_EVIDENCE})",
            "Gather more independent evidence or lower the stated confidence.",
        )

    async def _check_base_rate_neglect(self, complex_id, score, ctx) -> BiasWarning | None:
        exp = ctx.get("expected_return_pct")
        if exp is None:
            return None
        avg = _num(await self._row(BASE_RATE_QUERY, complex_id), "avg_annual_return_10y_pct")
        if not avg or avg <= 0 or float(exp) <= BASE_RATE_MULTIPLE * avg:
            return None
        return BiasWarning(
            "base_rate_neglect",
            "Expected return far exceeds the long-run historical average.",
            "medium",
            f"expected {float(exp):.1f}% vs 10Y average {avg:.1f}% (> {BASE_RATE_MULTIPLE:g}x)",
            "Anchor expectations on the historical base rate and justify any excess.",
        )

    async def _check_sunk_cost(self, complex_id, score, ctx) -> BiasWarning | None:
        n = ctx.get("expired_signals_held")
        if n is None or n < SUNK_COST_EXPIRED:
            return None
        return BiasWarning(
            "sunk_cost",
            "Position is held although the signals supporting it have expired.",
            "medium",
            f"{n} signals expired (>= {SUNK_COST_EXPIRED}) but position still held",
            "Evaluate the position as if newly entered; past cost is irrelevant.",
        )
