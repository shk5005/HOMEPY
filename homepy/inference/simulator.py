"""ScenarioSimulator: Bull/Base/Bear scenarios and sensitivity analysis.

The simulator takes the base InvestmentScore from the scorer, then for every
scenario / perturbation works on a deep copy of it: raw factor values are
shifted by multiples of their historical sigma (rolling 36 months), factors
are re-normalized with the same ranges the scorer uses, and the total is
recomputed. The base score object is never mutated.
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from homepy.inference.scorer import (
    FACTOR_RANGES,
    FactorScore,
    InvestmentScore,
    grade_for,
    minmax,
)

_log = logging.getLogger(__name__)

DEFAULT_VARIABLES: list[str] = [
    "supply_demand_gap",
    "valuation_gap",
    "interest_rate_cycle",
    "transport_access",
    "price_momentum",
]

PERTURBATION_SIGMAS: list[float] = [-2.0, -1.0, 0.0, 1.0, 2.0]

# Fallback sigma (in raw units) when TimescaleDB has no history.
DEFAULT_SIGMAS: dict[str, float] = {
    "valuation_gap": 8.0,
    "price_momentum": 5.0,
    "jeonse_ratio_trend": 3.0,
    "interest_rate_cycle": 30.0,
    "liquidity_trend": 15.0,
    "supply_demand_gap": 12.0,
    "unsold_risk": 1.5,
    "migration_momentum": 0.3,
    "transport_access": 200.0,
    "development_upside": 0.5,
    "regulation_impact": 1.0,
    "tax_burden": 2.0,
}

# +1 if an increase in the raw value is favorable, -1 otherwise.
_FAVORABLE_SIGN: dict[str, int] = {
    name: (-1 if inv else 1) for name, (_, _, inv) in FACTOR_RANGES.items()
}

SCENARIO_PROBABILITIES: dict[str, float] = {"bull": 0.25, "base": 0.50, "bear": 0.25}

SIGMA_QUERY = (
    "-- sigma:{var}\nSELECT STDDEV_SAMP(value) AS sigma FROM factor_history "
    "WHERE factor = $1 AND complex_id = $2 "
    "AND time >= NOW() - INTERVAL '36 months'"
)


@dataclass
class Scenario:
    name: str
    conditions: list[str]
    key_variables: dict[str, float]
    expected_outcome: str
    leading_indicators: list[str]
    invalidation_conditions: list[str]
    probability: float


@dataclass
class SensitivityResult:
    variable: str
    base_value: float
    perturbations: list[float]
    score_impacts: list[float]


@dataclass
class ScenarioResult:
    complex_id: str
    scenarios: list[Scenario]
    sensitivity: list[SensitivityResult] = field(default_factory=list)


def _apply_shift(base: InvestmentScore, shifts: dict[str, float]) -> InvestmentScore:
    """Return a deep copy of ``base`` with raw factor values shifted and rescored."""
    scored = copy.deepcopy(base)
    for f in scored.factors:
        delta = shifts.get(f.name)
        if delta is None:
            continue
        f.raw_value = f.raw_value + delta
        lo, hi, inv = FACTOR_RANGES[f.name]
        f.normalized = minmax(f.raw_value, lo, hi, invert=inv)
        f.weighted_score = f.normalized * f.weight
    total = round(sum(f.weighted_score for f in scored.factors), 4)
    scored.total_score = min(100.0, max(0.0, total))
    scored.grade = grade_for(scored.total_score)
    return scored


class ScenarioSimulator:
    def __init__(self, scorer: Any, timescale_svc: Any) -> None:
        self.scorer = scorer
        self.ts = timescale_svc

    async def _sigma(self, variable: str, complex_id: str) -> float:
        """Rolling 36-month standard deviation; falls back to a default."""
        try:
            rows = await self.ts.execute(SIGMA_QUERY.format(var=variable), variable, complex_id)
        except Exception:
            _log.warning(
                "sigma query failed for %s/%s, using default", variable, complex_id, exc_info=True
            )
            rows = []
        sigma = None
        if rows:
            try:
                v = rows[0].get("sigma")
            except AttributeError:
                v = None
            if v is not None and not isinstance(v, bool):
                try:
                    sigma = float(v)
                except (TypeError, ValueError):
                    sigma = None
        if sigma is None or not math.isfinite(sigma) or sigma <= 0:
            sigma = DEFAULT_SIGMAS[variable]
        return sigma

    async def simulate(
        self, complex_id: str, variables: list[str] | None = None
    ) -> ScenarioResult:
        variables = list(variables) if variables is not None else list(DEFAULT_VARIABLES)
        for v in variables:
            if v not in FACTOR_RANGES:
                raise ValueError(f"unsupported simulation variable: {v!r}")

        base = await self.scorer.score(complex_id)
        by_name = {f.name: f for f in base.factors}
        sigmas = {v: await self._sigma(v, complex_id) for v in variables}

        scenarios = [
            self._build_scenario("bull", base, by_name, sigmas, +1.0),
            self._build_scenario("base", base, by_name, sigmas, 0.0),
            self._build_scenario("bear", base, by_name, sigmas, -1.0),
        ]

        sensitivity: list[SensitivityResult] = []
        for v in variables:
            if v not in by_name:
                raise ValueError(f"variable {v!r} not found in base score factors")
            base_raw = by_name[v].raw_value
            impacts: list[float] = []
            perts: list[float] = []
            for k in PERTURBATION_SIGMAS:
                shifted = _apply_shift(base, {v: k * sigmas[v]})
                impacts.append(round(shifted.total_score - base.total_score, 4))
                perts.append(round(base_raw + k * sigmas[v], 4))
            sensitivity.append(SensitivityResult(v, base_raw, perts, impacts))

        return ScenarioResult(complex_id=complex_id, scenarios=scenarios, sensitivity=sensitivity)

    def _build_scenario(
        self,
        name: str,
        base: InvestmentScore,
        by_name: dict[str, FactorScore],
        sigmas: dict[str, float],
        direction: float,
    ) -> Scenario:
        # direction: +1 favorable sigma, -1 unfavorable sigma, 0 current.
        shifts = {v: direction * _FAVORABLE_SIGN[v] * s for v, s in sigmas.items()}
        scored = _apply_shift(base, shifts)  # deep copy; base untouched
        scored_by = {f.name: f for f in scored.factors}
        key_vars = {v: round(scored_by[v].raw_value, 4) for v in sigmas if v in scored_by}
        if not key_vars:
            key_vars = {"total_score": scored.total_score}

        if name == "bull":
            conditions = [f"{v} moves +1 sigma in the favorable direction" for v in sigmas]
            indicators = [f"{v} trending toward {key_vars.get(v)}" for v in sigmas] or ["Score momentum"]
            invalid = ["Any key variable reverts to its base value for two consecutive quarters"]
        elif name == "bear":
            conditions = [f"{v} moves -1 sigma in the unfavorable direction" for v in sigmas]
            indicators = [f"{v} deteriorating toward {key_vars.get(v)}" for v in sigmas] or ["Score momentum"]
            invalid = ["Key variables recover to base values for two consecutive quarters"]
        else:
            conditions = ["All key variables stay at their current values"]
            indicators = ["Key variables remain within +/-0.5 sigma of current values"]
            invalid = ["Any key variable moves more than 1 sigma from its current value"]
        if not conditions:
            conditions = ["No variables perturbed"]

        outcome = (
            f"{name.capitalize()} case: score {scored.total_score:.1f} "
            f"(grade {scored.grade}) vs base {base.total_score:.1f} "
            f"({scored.total_score - base.total_score:+.1f})"
        )
        return Scenario(
            name=name,
            conditions=conditions,
            key_variables=key_vars,
            expected_outcome=outcome,
            leading_indicators=indicators,
            invalidation_conditions=invalid,
            probability=SCENARIO_PROBABILITIES[name],
        )
