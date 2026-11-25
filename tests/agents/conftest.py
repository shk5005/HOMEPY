"""Mock Claude client tracking prompts per agent."""

import json
import re
from types import SimpleNamespace

import pytest


def _resp(verdict, conf=0.7, biases=None):
    return json.dumps({
        "verdict": verdict, "confidence": conf,
        "key_arguments": [f"{verdict} argument"], "data_cited": ["valuation_gap"],
        "identified_biases": biases or [],
    }, ensure_ascii=False)


class MockClaudeClient:
    def __init__(self):
        self.last_prompts: dict[str, str] = {}
        self.all_prompts: dict[str, list[str]] = {}
        self.calls = 0
        self.behavioral_response: str | None = None
        self.final_verdicts = {a: "매수 검토" for a in
                               ("BullAgent", "BearAgent", "BehavioralAgent", "PolicyAgent")}
        self.messages = SimpleNamespace(create=self._create)

    def set_no_consensus(self):
        self.final_verdicts = {"BullAgent": "매수 검토", "BearAgent": "매도 검토",
                               "BehavioralAgent": "관망", "PolicyAgent": "관망"}

    def set_behavioral_response(self, json_str: str):
        self.behavioral_response = json_str

    async def _create(self, *, model, max_tokens, system, messages):
        self.calls += 1
        name = re.match(r"You are (\w+)\.", system).group(1)
        prompt = messages[0]["content"]
        self.last_prompts[name] = prompt
        self.all_prompts.setdefault(name, []).append(prompt)
        phase = re.match(r"\[PHASE:(\w+)\]", prompt).group(1)
        if phase == "bias":
            text = self.behavioral_response or '{"identified_biases": ["anchoring"]}'
        elif phase in ("rebut", "respond", "policy_reeval"):
            text = f"{name} {phase} text"
        elif phase == "final":
            text = _resp(self.final_verdicts[name], 0.8)
        else:
            text = _resp({"BearAgent": "매도 검토", "BullAgent": "매수 검토"}.get(name, "관망"))
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


@pytest.fixture
def mock_claude_api():
    return MockClaudeClient()


@pytest.fixture
def sample_data():
    return {"score": 72, "factors": {"valuation_gap": 0.8}}
