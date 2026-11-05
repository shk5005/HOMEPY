"""Policy simulation engine.

Read-only: hypothetical policy changes are applied as in-memory score deltas on
top of a baseline from InvestmentScorer. Nothing is ever written to TypeDB or
TimescaleDB.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from homepy.simulation.models import PolicyBacktest, PolicyChange, PolicyImpact

BASELINE_ID = "market-baseline"
DEFAULT_ACQ_TAX_RATE = 0.03
DEFAULT_RATE = 3.5
SUPPLY_NEUTRAL_UNITS = 1000

# Sensitivities (score points).
TAX_POINTS_PER_PCT = 3.0       # per 1 percentage point of acquisition tax change
REGULATION_POINTS = {"designate": -6.0, "release": 5.0}
RATE_POINTS_PER_PCT = 4.0      # per 1 percentage point of rate decline
SUPPLY_POINTS_PER_1000 = 1.5   # per 1000 additional units


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


class PolicySimulator:
    def __init__(self, typedb_svc: Any, scorer: Any, timescale_svc: Any) -> None:
        self.typedb = typedb_svc
        self.scorer = scorer
        self.ts = timescale_svc

    async def _baseline(self, scope_id: str = BASELINE_ID) -> float:
        result = await self.scorer.score(scope_id)
        return float(result.total_score)

    def _build(self, change: PolicyChange, before: float, raw_delta: float,
               effects: list[str], districts: list[str], chain: list[dict]) -> PolicyImpact:
        after = _clamp(before + raw_delta)
        return PolicyImpact(
            policy_change=change, direct_effects=effects,
            score_before=round(before, 2), score_after=round(after, 2),
            delta=round(after - before, 2),
            affected_districts=districts, impact_chain=chain)

    async def simulate_tax_change(self, changes: dict) -> PolicyImpact:
        before = await self._baseline()
        new_rate = float(changes.get("acquisition_tax_rate", DEFAULT_ACQ_TAX_RATE))
        pct = (new_rate - DEFAULT_ACQ_TAX_RATE) * 100
        raw = -pct * TAX_POINTS_PER_PCT
        if raw == 0 and changes:
            raw = -0.5  # other tax levers: small generic burden shift
        direction = "increase" if raw < 0 else "decrease"
        chain = [
            {"order": 1, "effect": f"transaction cost {direction}", "magnitude": round(abs(raw), 2)},
            {"order": 2, "effect": "buyer demand shifts", "magnitude": round(abs(raw) * 0.6, 2)},
            {"order": 3, "effect": "price momentum and liquidity adjust", "magnitude": round(abs(raw) * 0.3, 2)},
        ]
        return self._build(PolicyChange("tax", dict(changes)), before, raw,
                           [f"tax_burden factor changes ({', '.join(changes) or 'none'})"],
                           ["ALL"], chain)

    async def simulate_regulation(self, district_code: str, regulation_type: str,
                                  action: str) -> PolicyImpact:
        if action not in REGULATION_POINTS:
            raise ValueError(f"action must be 'designate' or 'release', got {action!r}")
        before = await self._baseline(f"district-{district_code}")
        raw = REGULATION_POINTS[action]
        chain = [
            {"order": 1, "effect": f"{regulation_type} {action}: loan/transaction limits change",
             "magnitude": abs(raw)},
            {"order": 2, "effect": "investment demand and liquidity change", "magnitude": round(abs(raw) * 0.6, 2)},
            {"order": 3, "effect": "spillover to adjacent districts", "magnitude": round(abs(raw) * 0.25, 2)},
        ]
        return self._build(
            PolicyChange("regulation", {"district_code": district_code,
                                        "regulation_type": regulation_type, "action": action}),
            before, raw, [f"regulation_impact factor changes in {district_code}"],
            [district_code], chain)

    async def simulate_interest_rate(self, rate_path: list[float]) -> PolicyImpact:
        if not rate_path:
            raise ValueError("rate_path must not be empty")
        before = await self._baseline()
        decline = DEFAULT_RATE - float(rate_path[-1])
        raw = decline * RATE_POINTS_PER_PCT
        chain = [
            {"order": 1, "effect": "borrowing cost change", "magnitude": round(abs(raw), 2)},
            {"order": 2, "effect": "loan affordability and demand change", "magnitude": round(abs(raw) * 0.6, 2)},
            {"order": 3, "effect": "price expectations adjust", "magnitude": round(abs(raw) * 0.3, 2)},
        ]
        return self._build(PolicyChange("interest_rate", {"rate_path": list(rate_path)}),
                           before, raw, ["interest_rate_cycle factor changes"], ["ALL"], chain)

    async def simulate_supply_shock(self, district_code: str, units: int) -> PolicyImpact:
        before = await self._baseline(f"district-{district_code}")
        raw = -(units / 1000) * SUPPLY_POINTS_PER_1000
        chain = [
            {"order": 1, "effect": f"{units} additional units enter market", "magnitude": abs(round(raw, 2))},
            {"order": 2, "effect": "supply_demand_gap and unsold risk worsen", "magnitude": round(abs(raw) * 0.6, 2)},
            {"order": 3, "effect": "jeonse and sale prices soften", "magnitude": round(abs(raw) * 0.3, 2)},
        ]
        return self._build(
            PolicyChange("supply_shock", {"district_code": district_code, "units": units}),
            before, raw, [f"supply_demand_gap factor worsens in {district_code}"],
            [district_code], chain)

    async def backtest_policy(self, policy_name: str, policy_date: date,
                              changes: dict) -> PolicyBacktest:
        """Placeholder backtest: real historical comparison needs live TimescaleDB.

        Predicts direction per district from the policy's changes and returns
        a structurally valid result with accuracy in [0, 1].
        """
        districts = [d for v in changes.values() if isinstance(v, list) for d in v]
        predicted = {d: "down" for d in districts}  # restrictive policies: down
        simulated = {"predicted_direction": predicted, "horizons_months": [3, 6, 12]}
        actual: dict = {"source": "placeholder (no historical query executed)",
                        "actual_direction": {}}
        return PolicyBacktest(
            policy_date=policy_date, policy_name=policy_name,
            simulated_impact=simulated, actual_market_response=actual,
            accuracy_score=0.0, missed_factors=[])
