from datetime import datetime, timezone

import pytest

from homepy.agents.models import AgentAnalysis, DebateResult, DebateRound
from homepy.inference.bias_detector import BiasWarning
from homepy.inference.scorer import FactorScore, InvestmentScore
from homepy.inference.simulator import Scenario, ScenarioResult, SensitivityResult
from homepy.inference.verdict import InvestmentVerdict
from homepy.reports import ReportGenerator

TEMPLATES = "homepy/reports/templates"


@pytest.fixture
def verdict():
    return InvestmentVerdict(
        core_facts=["Total score 72.0 (grade B)"], strongest_bull_case="bull <b>x</b>",
        strongest_bear_case="bear", hidden_variable="hv", primary_risk="risk1",
        verdict="매수 검토", confidence="High", kill_switch="rate +2sigma",
        watchlist_data=["w1", "w2"],
        bias_warnings=[BiasWarning("anchoring", "desc", "high", "ev", "mit")],
        scenario_summary="s", evidence_chain=["verdict <- score"])


@pytest.fixture
def score():
    fs = [FactorScore(f"f{i}", 1.0, 40.0 + i * 3, 1 / 14, 0.5, [f"ev{i}"]) for i in range(14)]
    return InvestmentScore("C001", 72.0, "B", fs, datetime(2026, 11, 4, tzinfo=timezone.utc))


@pytest.fixture
def scenarios():
    sc = [Scenario(n, ["cond"], {"rate": 3.0}, f"{n} outcome", ["ind"], ["inv"], p)
          for n, p in (("Bull", 0.25), ("Base", 0.5), ("Bear", 0.25))]
    return ScenarioResult("C001", sc, [SensitivityResult("rate", 3.0, [-2, 2], [-4.0, 3.0])])


@pytest.fixture
def debate():
    return DebateResult(
        rounds=[DebateRound(1, {"Bull": "good", "Bear": "bad"})], consensus_reached=False,
        final_verdict=None,
        dissenting_views=[AgentAnalysis("Bear", "매도 검토", 0.6, ["arg"])], transcript="t")


def test_report_has_five_sections(verdict, score, scenarios, debate):
    html = ReportGenerator(TEMPLATES).generate_html(verdict, debate, score=score, scenarios=scenarios)
    for title in ("투자 요약", "14팩터 상세 분석", "시나리오 분석", "편향 경고 및 리스크", "근거 데이터 부록"):
        assert title in html
    assert "<svg" in html and "멀티에이전트 토론" in html and "소수 의견" in html
    assert "&lt;b&gt;x" in html  # autoescaped


def test_report_without_debate_or_score(verdict):
    html = ReportGenerator(TEMPLATES).generate_html(verdict, None)
    assert "투자 요약" in html and "멀티에이전트 토론" not in html


def test_report_pdf_is_valid(verdict, score, scenarios, debate):
    pdf = ReportGenerator(TEMPLATES).generate_pdf(verdict, debate, score=score, scenarios=scenarios)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000
