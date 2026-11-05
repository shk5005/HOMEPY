"""FastAPI dependency providers. Tests override these via app.dependency_overrides."""

from __future__ import annotations

from fastapi import Request

from homepy.api.services.tax_engine import TaxEngine
from homepy.inference.bias_detector import BiasDetector
from homepy.inference.scorer import InvestmentScorer
from homepy.inference.simulator import ScenarioSimulator
from homepy.inference.verdict import VerdictBuilder
from homepy.simulation.policy_simulator import PolicySimulator


def get_typedb(request: Request):
    return request.app.state.typedb


def get_timescale(request: Request):
    return request.app.state.timescale


def get_scorer(request: Request) -> InvestmentScorer:
    return InvestmentScorer(request.app.state.typedb, request.app.state.timescale)


def get_simulator(request: Request) -> ScenarioSimulator:
    return ScenarioSimulator(get_scorer(request), request.app.state.timescale)


def get_verdict_builder(request: Request) -> VerdictBuilder:
    ts = request.app.state.timescale
    scorer = get_scorer(request)
    return VerdictBuilder(scorer, ScenarioSimulator(scorer, ts), BiasDetector(ts))


def get_tax_engine(request: Request) -> TaxEngine:
    return TaxEngine(request.app.state.typedb)


def get_policy_simulator(request: Request) -> PolicySimulator:
    return PolicySimulator(
        request.app.state.typedb, get_scorer(request), request.app.state.timescale)
