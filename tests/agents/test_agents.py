from homepy.agents import (AgentAnalysis, BearAgent, BehavioralAgent, BullAgent,
                           PolicyAgent, RateLimiter)
from homepy.agents.base import parse_analysis


async def test_round1_agents_are_independent(mock_claude_api, sample_data):
    bull, bear = BullAgent(mock_claude_api), BearAgent(mock_claude_api)
    await bull.analyze(sample_data)
    await bear.analyze(sample_data)
    assert "BearAgent" not in mock_claude_api.last_prompts["BullAgent"]
    assert "BullAgent" not in mock_claude_api.last_prompts["BearAgent"]


async def test_behavioral_detects_planted_bias(mock_claude_api):
    mock_claude_api.set_behavioral_response(
        '{"identified_biases": ["confirmation_bias", "recency_bias"]}')
    a = AgentAnalysis("BullAgent", "매수 검토", 0.9, ["최근 3개월 상승"], ["price_momentum"], [])
    result = await BehavioralAgent(mock_claude_api).analyze_bias(a)
    assert "confirmation_bias" in result or "recency_bias" in result


async def test_analyze_parses_json(mock_claude_api, sample_data):
    r = await BullAgent(mock_claude_api).analyze(sample_data)
    assert r.agent_name == "BullAgent" and r.verdict == "매수 검토" and r.confidence == 0.7


async def test_rebut_and_respond(mock_claude_api):
    bear = BearAgent(mock_claude_api)
    other = AgentAnalysis("BullAgent", "매수 검토", 0.8, ["x"], [], [])
    assert "rebut" in await bear.rebut(other)
    assert "BullAgent" in mock_claude_api.last_prompts["BearAgent"]
    assert "respond" in await bear.respond_to_rebuttal("rebuttal")


async def test_policy_reevaluate(mock_claude_api):
    assert "policy_reeval" in await PolicyAgent(mock_claude_api).reevaluate("ctx")


def test_parse_fallbacks():
    assert parse_analysis("X", '```json\n{"verdict": "매도 검토", "confidence": 2}\n```').confidence == 1.0
    p = parse_analysis("X", "I would say sell. confidence: 0.4\n- reason one")
    assert p.verdict == "매도 검토" and p.confidence == 0.4 and p.key_arguments


async def test_rate_limiter_allows_under_limit():
    rl = RateLimiter(max_calls=3, period=60)
    for _ in range(3):
        await rl.acquire()
