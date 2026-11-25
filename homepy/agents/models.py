"""Data models for the multi-agent debate system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentAnalysis:
    agent_name: str
    verdict: str
    confidence: float
    key_arguments: list[str] = field(default_factory=list)
    data_cited: list[str] = field(default_factory=list)
    identified_biases: list[str] = field(default_factory=list)


@dataclass
class DebateRound:
    round_number: int
    agent_outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class DebateResult:
    rounds: list[DebateRound]
    consensus_reached: bool
    final_verdict: str | None
    dissenting_views: list[AgentAnalysis]
    transcript: str
    # Composed InvestmentVerdict when a VerdictBuilder was supplied.
    investment_verdict: Any = None
