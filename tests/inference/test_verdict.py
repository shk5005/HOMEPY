from types import SimpleNamespace

import pytest

from homepy.inference.bias_detector import BiasDetector
from homepy.inference.simulator import ScenarioSimulator
from homepy.inference.verdict import InvestmentVerdict, VerdictBuilder

from .conftest import MockInvestmentScorer, MockTimescaleService


@pytest.fixture
def mock_deps():
    ts = MockTimescaleService({})
    scorer = MockInvestmentScorer()
    return SimpleNamespace(
        scorer=scorer,
        simulator=ScenarioSimulator(scorer, ts),
        detector=BiasDetector(ts),
    )


async def test_verdict_has_all_red_team_fields(mock_deps):
    builder = VerdictBuilder(mock_deps.scorer, mock_deps.simulator, mock_deps.detector)
    verdict = await builder.build("C001")
    assert isinstance(verdict, InvestmentVerdict)
    assert len(verdict.core_facts) >= 1
    assert verdict.strongest_bull_case
    assert verdict.strongest_bear_case
    assert verdict.verdict in ("매수 검토", "관망", "매도 검토", "판단 유보")
    assert verdict.confidence in ("High", "Medium", "Low")
    assert verdict.kill_switch
    assert len(verdict.watchlist_data) == 5
    assert len(verdict.evidence_chain) >= 1


async def test_verdict_confidence_low_when_data_sparse(mock_deps):
    mock_deps.scorer.set_sparse_data(missing_factors=5)
    builder = VerdictBuilder(mock_deps.scorer, mock_deps.simulator, mock_deps.detector)
    verdict = await builder.build("C001")
    assert verdict.confidence == "Low"
