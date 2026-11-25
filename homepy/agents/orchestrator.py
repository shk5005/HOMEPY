"""DebateOrchestrator: 4-round protocol that preserves dissent."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from homepy.agents.base import BaseAgent
from homepy.agents.behavioral import BehavioralAgent, extract_biases
from homepy.agents.bear import BearAgent
from homepy.agents.bull import BullAgent
from homepy.agents.models import AgentAnalysis, DebateResult, DebateRound
from homepy.agents.policy import PolicyAgent

CONSENSUS_THRESHOLD = 3


def direction(verdict: str) -> str:
    v = verdict.lower()
    if "매도" in v or "sell" in v or "bear" in v:
        return "sell"
    if "매수" in v or "buy" in v or "bull" in v:
        return "buy"
    return "hold"


def _find(agents: list[BaseAgent], cls: type) -> Any:
    return next((a for a in agents if isinstance(a, cls)), None)


class DebateOrchestrator:
    def __init__(self, agents: list[BaseAgent], verdict_builder: Any | None = None) -> None:
        self.agents = agents
        self.verdict_builder = verdict_builder

    async def run_debate(self, complex_id: str, data: dict) -> DebateResult:
        log: list[str] = [f"# Debate for {complex_id}"]
        rounds: list[DebateRound] = []

        # Round 1: independent analyses (each agent sees only the raw data).
        analyses = await asyncio.gather(*(a.analyze(data) for a in self.agents))
        by_name = {a.agent_name: an for a, an in zip(self.agents, analyses)}
        r1 = DebateRound(1, {n: self._fmt(an) for n, an in by_name.items()})
        rounds.append(r1)

        # Round 2: Bull<->Bear rebuttals; Behavioral flags biases.
        bull, bear = _find(self.agents, BullAgent), _find(self.agents, BearAgent)
        beh, pol = _find(self.agents, BehavioralAgent), _find(self.agents, PolicyAgent)
        tasks: dict[str, Any] = {}
        if bull and bear:
            tasks[bull.agent_name] = bull.rebut(by_name[bear.agent_name])
            tasks[bear.agent_name] = bear.rebut(by_name[bull.agent_name])
        if beh:
            for target in (bull, bear):
                if target:
                    tasks[f"{beh.agent_name}->{target.agent_name}"] = beh.analyze_bias(
                        by_name[target.agent_name]
                    )
        results = await asyncio.gather(*tasks.values())
        r2 = DebateRound(2, dict(zip(tasks.keys(), results)))
        rounds.append(r2)
        for key, text in r2.agent_outputs.items():
            if "->" in key:
                target = key.split("->")[1]
                found = extract_biases(text)
                by_name[target].identified_biases = sorted(
                    set(by_name[target].identified_biases) | set(found)
                )

        # Round 3: Policy re-evaluation under regulation scenarios.
        context = self._context(rounds)
        r3 = DebateRound(3, {})
        if pol:
            r3.agent_outputs[pol.agent_name] = await pol.reevaluate(context)
        rounds.append(r3)

        # Round 4: final positions (independent given the shared transcript).
        context = self._context(rounds)
        finals = await asyncio.gather(*(a.final_position(context) for a in self.agents))
        r4 = DebateRound(4, {f.agent_name: self._fmt(f) for f in finals})
        rounds.append(r4)

        consensus, final_verdict, dissent = self._tally(list(finals))
        for r in rounds:
            log.append(f"\n## Round {r.round_number}")
            log.extend(f"### {k}\n{v}" for k, v in r.agent_outputs.items())
        log.append(f"\nConsensus: {consensus}; final: {final_verdict}")
        if dissent:
            log.append("Dissent: " + ", ".join(f"{d.agent_name}({d.verdict})" for d in dissent))

        result = DebateResult(rounds, consensus, final_verdict, dissent, "\n".join(log))
        if self.verdict_builder is not None:
            result.investment_verdict = self._compose_verdict(
                list(finals), consensus, final_verdict, dissent, rounds
            )
        return result

    @staticmethod
    def _fmt(a: AgentAnalysis) -> str:
        return (
            f"verdict={a.verdict} confidence={a.confidence:.2f} "
            f"args={a.key_arguments} data={a.data_cited} biases={a.identified_biases}"
        )

    @staticmethod
    def _context(rounds: list[DebateRound]) -> str:
        return "\n".join(
            f"[R{r.round_number}] {k}: {v}" for r in rounds for k, v in r.agent_outputs.items()
        )

    @staticmethod
    def _tally(finals: list[AgentAnalysis]):
        counts = Counter(direction(f.verdict) for f in finals)
        top, n = counts.most_common(1)[0]
        consensus = n >= CONSENSUS_THRESHOLD
        # Minority views are always preserved; with no majority, every
        # agent outside the plurality direction is recorded as dissent.
        dissent = [f for f in finals if direction(f.verdict) != top]
        if consensus:
            verdict = next(f.verdict for f in finals if direction(f.verdict) == top)
            return True, verdict, dissent
        return False, None, dissent

    def _compose_verdict(self, finals, consensus, final_verdict, dissent, rounds):
        from homepy.inference.verdict import InvestmentVerdict

        by = {f.agent_name: f for f in finals}
        bull, bear = by.get("BullAgent"), by.get("BearAgent")
        avg = sum(f.confidence for f in finals) / max(len(finals), 1)
        conf = "High" if avg >= 0.75 and consensus else "Medium" if avg >= 0.5 else "Low"
        scenario = (
            "Consensus reached" if consensus else "No consensus (dissent preserved)"
        ) + (
            "; dissent: " + "; ".join(f"{d.agent_name}: {d.verdict}" for d in dissent)
            if dissent
            else ""
        )
        biases = sorted({b for f in finals for b in f.identified_biases})
        policy = by.get("PolicyAgent")
        return InvestmentVerdict(
            core_facts=sorted({d for f in finals for d in f.data_cited}),
            strongest_bull_case="; ".join(bull.key_arguments) if bull else "",
            strongest_bear_case="; ".join(bear.key_arguments) if bear else "",
            hidden_variable="; ".join(policy.key_arguments) if policy else "",
            primary_risk=(bear.key_arguments[0] if bear and bear.key_arguments else ""),
            verdict=final_verdict or "판단 유보",
            confidence=conf,
            kill_switch="",
            watchlist_data=[],
            bias_warnings=[],
            scenario_summary=scenario + (f"; biases: {biases}" if biases else ""),
            evidence_chain=[f"R{r.round_number}" for r in rounds],
        )
