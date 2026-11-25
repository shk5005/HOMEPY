from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

POLICY_TYPES = ("tax", "regulation", "interest_rate", "supply_shock")


@dataclass(frozen=True)
class PolicyChange:
    policy_type: str  # one of POLICY_TYPES
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyImpact:
    policy_change: PolicyChange
    direct_effects: list[str]
    score_before: float
    score_after: float
    delta: float
    affected_districts: list[str]
    impact_chain: list[dict]


@dataclass(frozen=True)
class PolicyBacktest:
    policy_date: date
    policy_name: str
    simulated_impact: dict
    actual_market_response: dict
    accuracy_score: float
    missed_factors: list[str]
