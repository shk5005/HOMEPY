"""VerdictBuilder: assembles the 12-field Red Team Protocol verdict."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from homepy.inference.bias_detector import BiasWarning
from homepy.inference.scorer import FactorScore, InvestmentScore

BUY, HOLD, SELL, DEFER = "매수 검토", "관망", "매도 검토", "판단 유보"
_MISSING_MARKERS = ("no data", "데이터 없음")


@dataclass
class InvestmentVerdict:
    core_facts: list[str]
    strongest_bull_case: str
    strongest_bear_case: str
    hidden_variable: str
    primary_risk: str
    verdict: str
    confidence: str
    kill_switch: str
    watchlist_data: list[str]
    bias_warnings: list[BiasWarning] = field(default_factory=list)
    scenario_summary: str = ""
    evidence_chain: list[str] = field(default_factory=list)


def _is_missing(f: FactorScore) -> bool:
    return any(m in e.lower() for e in f.evidence for m in _MISSING_MARKERS)


def _contribution(f: FactorScore) -> float:
    return (f.normalized - 50.0) * f.weight


class VerdictBuilder:
    def __init__(self, scorer: Any, simulator: Any, bias_detector: Any) -> None:
        self.scorer = scorer
        self.simulator = simulator
        self.bias_detector = bias_detector

    async def build(self, complex_id: str, user_context: dict | None = None) -> InvestmentVerdict:
        # Score and scenarios are independent; bias detection needs the score.
        score, scenarios = await asyncio.gather(
            self.scorer.score(complex_id), self.simulator.simulate(complex_id)
        )
        biases = await self.bias_detector.detect(complex_id, score, user_context)

        factors = score.factors
        missing = [f for f in factors if _is_missing(f)]
        confidence = "Low" if len(missing) >= 5 else "Medium" if len(missing) >= 2 else "High"

        high_bias = any(b.severity == "high" for b in biases)
        total = score.total_score
        if total >= 65 and not high_bias and confidence != "Low":
            verdict = BUY
        elif total < 35:
            verdict = SELL
        elif high_bias or confidence == "Low":
            verdict = DEFER
        else:
            verdict = HOLD

        known = [f for f in factors if not _is_missing(f)] or factors
        ranked = sorted(known, key=_contribution, reverse=True)
        best = ranked[0] if ranked else None
        worst = ranked[-1] if ranked else None

        def fmt(f: FactorScore | None) -> str:
            if f is None:
                return "n/a"
            ev = f"; {f.evidence[0]}" if f.evidence else ""
            return f"{f.name} (normalized {f.normalized:.0f}, weight {f.weight:.2f}){ev}"

        core_facts = [f"Total score {total:.1f} (grade {score.grade}) across {len(factors)} factors"]
        core_facts += [fmt(f) for f in ranked[:2]]
        core_facts.append(f"Data coverage: {len(factors) - len(missing)}/{len(factors)} factors")

        bull = f"Strongest support: {fmt(best)}"
        bear_label = "Strongest drag" if worst and _contribution(worst) < 0 else "Weakest support"
        bear = f"{bear_label}: {fmt(worst)}"
        primary_risk = (
            f"{worst.name} is the weakest contributor" if worst else "Insufficient factor data"
        )

        if missing:
            hv = max(missing, key=lambda f: f.weight)
            hidden = f"{hv.name}: no data available, market may be pricing something unobserved"
        else:
            neutral = min(factors, key=lambda f: abs(f.normalized - 50), default=None)
            hidden = (
                f"{neutral.name} is near neutral and could swing the thesis"
                if neutral
                else "None identified"
            )

        sens = scenarios.sensitivity
        impact = lambda s: max((abs(x) for x in s.score_impacts), default=0.0)  # noqa: E731
        by_impact = sorted(sens, key=impact, reverse=True)
        if by_impact:
            ks = by_impact[0]
            kill_switch = f"{ks.variable}: +/-2 sigma moves the score by up to {impact(ks):.1f} points"
        else:
            kill_switch = "No sensitivity data; monitor the largest-weight factor"

        watch = [f"{s.variable} (base {s.base_value:g})" for s in by_impact[:5]]
        for f in sorted(factors, key=lambda f: f.weight, reverse=True):
            if len(watch) >= 5:
                break
            label = f"{f.name} (raw {f.raw_value:g})"
            if not any(w.startswith(f.name + " ") for w in watch):
                watch.append(label)
        watch = watch[:5]

        scenario_summary = " | ".join(s.expected_outcome for s in scenarios.scenarios)

        evidence_chain = [
            f"verdict={verdict} <- total_score {total:.1f}, confidence {confidence}, "
            f"{len(biases)} bias warning(s)",
            f"confidence={confidence} <- {len(missing)} factor(s) with missing data",
            f"bull_case <- {best.name}" if best else "bull_case <- n/a",
            f"bear_case <- {worst.name}" if worst else "bear_case <- n/a",
            f"kill_switch <- sensitivity:{by_impact[0].variable}" if by_impact else "kill_switch <- n/a",
        ]
        evidence_chain += [f"bias:{b.bias_type} <- {b.evidence}" for b in biases]

        return InvestmentVerdict(
            core_facts=core_facts,
            strongest_bull_case=bull,
            strongest_bear_case=bear,
            hidden_variable=hidden,
            primary_risk=primary_risk,
            verdict=verdict,
            confidence=confidence,
            kill_switch=kill_switch,
            watchlist_data=watch,
            bias_warnings=biases,
            scenario_summary=scenario_summary,
            evidence_chain=evidence_chain,
        )
