from homepy.agents import (BearAgent, BehavioralAgent, BullAgent, DebateOrchestrator,
                           PolicyAgent)


def _agents(c):
    return [BullAgent(c), BearAgent(c), BehavioralAgent(c), PolicyAgent(c)]


async def test_orchestrator_four_rounds(mock_claude_api, sample_data):
    result = await DebateOrchestrator(_agents(mock_claude_api), None).run_debate("C001", sample_data)
    assert [r.round_number for r in result.rounds] == [1, 2, 3, 4]
    assert result.consensus_reached and result.final_verdict == "매수 검토"
    assert "Round 4" in result.transcript


async def test_round1_prompts_exclude_other_agents(mock_claude_api, sample_data):
    await DebateOrchestrator(_agents(mock_claude_api)).run_debate("C001", sample_data)
    first = {n: p[0] for n, p in mock_claude_api.all_prompts.items()}
    for n, p in first.items():
        assert "[PHASE:analyze]" in p
        assert not any(o in p for o in first if o != n)


async def test_orchestrator_allows_dissent(mock_claude_api, sample_data):
    mock_claude_api.set_no_consensus()
    result = await DebateOrchestrator(_agents(mock_claude_api)).run_debate("C001", sample_data)
    assert not result.consensus_reached
    assert result.final_verdict is None
    assert len(result.dissenting_views) > 0


async def test_verdict_integration_notes_dissent(mock_claude_api, sample_data):
    mock_claude_api.set_no_consensus()
    orch = DebateOrchestrator(_agents(mock_claude_api), verdict_builder=object())
    result = await orch.run_debate("C001", sample_data)
    assert "dissent" in result.investment_verdict.scenario_summary


async def test_round2_biases_attached(mock_claude_api, sample_data):
    mock_claude_api.set_behavioral_response('{"identified_biases": ["herding"]}')
    result = await DebateOrchestrator(_agents(mock_claude_api)).run_debate("C001", sample_data)
    assert "herding" in result.rounds[1].agent_outputs["BehavioralAgent->BullAgent"]
    assert any("BehavioralAgent->" in k for k in result.rounds[1].agent_outputs)
