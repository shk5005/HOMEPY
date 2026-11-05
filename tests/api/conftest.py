from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from homepy.api import dependencies as deps
from homepy.api.main import create_app
from homepy.inference.bias_detector import BiasWarning
from homepy.inference.scorer import FACTOR_WEIGHTS, FactorScore, InvestmentScore
from homepy.inference.simulator import Scenario, ScenarioResult, SensitivityResult
from homepy.inference.verdict import InvestmentVerdict

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


def _score(cid: str, total: float = 62.0) -> InvestmentScore:
    factors = [FactorScore(n, 1.0, 0.5, w, 0.5 * w, [f"{n} evidence"])
               for n, w in FACTOR_WEIGHTS.items()]
    return InvestmentScore(cid, total, "B", factors, NOW)


def _scenario(name: str, p: float) -> Scenario:
    return Scenario(name, ["cond"], {"rate": 3.0}, f"{name} outcome", ["indicator"], ["invalid"], p)


class FakeTimescale:
    async def execute(self, query: str, *args):
        if "COUNT(*)" in query:
            return [{"n": 10, "latest": NOW}]
        if "ts_interest_rate" in query:
            return [{"ts": NOW, "base_rate": 2.5, "mortgage_rate": 4.1}]
        if "ts_exchange_rate" in query:
            return [{"usd_krw": 1350.0}]
        if "ts_liquidity" in query:
            return [{"m2_change_yoy_pct": 5.2}]
        if "ts_macro_index" in query:
            return [{"cpi_change_yoy_pct": 2.1, "gdp_growth": 1.8, "unemployment": 3.0}]
        if "market_cycle_phase" in query:
            return [{"phase": "recovery", "price_change_3m": 1.2,
                     "volume_change_3m": 8.0, "unsold_ratio": 0.5}]
        return []


@pytest.fixture
def app_client():
    app = create_app(use_lifespan=False)

    typedb = MagicMock()
    typedb.execute_read.return_value = [
        {"o_id": "D001", "rel": "located-in", "ot": "district"},
        {"o_id": "S001", "rel": "near", "ot": "infrastructure"},
    ]
    app.state.typedb = typedb
    app.state.timescale = FakeTimescale()

    scorer = MagicMock()
    scorer.score = AsyncMock(side_effect=lambda cid: _score(cid))
    simulator = MagicMock()
    simulator.simulate = AsyncMock(side_effect=lambda cid, variables=None: ScenarioResult(
        cid, [_scenario("bull", 0.25), _scenario("base", 0.5), _scenario("bear", 0.25)],
        [SensitivityResult("interest_rate", 3.0, [-1.0, 0.0, 1.0], [2.0, 0.0, -2.0])]))
    builder = MagicMock()
    builder.build = AsyncMock(side_effect=lambda cid, user_context=None: InvestmentVerdict(
        core_facts=["fact"], strongest_bull_case="bull", strongest_bear_case="bear",
        hidden_variable="hidden", primary_risk="risk", verdict="관망", confidence="Medium",
        kill_switch="kill", watchlist_data=["w"],
        bias_warnings=[BiasWarning("anchoring", "d", "low", "e", "m")],
        scenario_summary="s", evidence_chain=["c"]))

    app.dependency_overrides[deps.get_scorer] = lambda: scorer
    app.dependency_overrides[deps.get_simulator] = lambda: simulator
    app.dependency_overrides[deps.get_verdict_builder] = lambda: builder
    with TestClient(app) as client:
        yield client
