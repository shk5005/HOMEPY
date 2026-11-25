import json

from homepy.agents.base import BaseAgent
from homepy.agents.models import AgentAnalysis

BIASES = (
    "confirmation_bias, anchoring, recency_bias, herding, loss_aversion, "
    "overconfidence, sunk_cost, framing, availability_heuristic"
)


class BehavioralAgent(BaseAgent):
    agent_name = "BehavioralAgent"
    system_prompt = (
        "Detect cognitive biases in analyses using the 9-bias framework: " + BIASES + "."
    )

    def perspective(self) -> str:
        return "behavioral: cognitive-bias detection"

    async def analyze_bias(self, analysis: AgentAnalysis) -> str:
        """Identify cognitive biases in another agent's analysis."""
        prompt = (
            f"[PHASE:bias] Identify cognitive biases ({BIASES}) in this analysis by "
            f"{analysis.agent_name}.\nVerdict: {analysis.verdict} (confidence {analysis.confidence})\n"
            f"Arguments: {analysis.key_arguments}\nData cited: {analysis.data_cited}\n"
            'Respond as JSON: {"identified_biases": [str], "explanation": str}.'
        )
        return await self._call(prompt)


def extract_biases(text: str) -> list[str]:
    try:
        return [str(b) for b in json.loads(text).get("identified_biases", [])]
    except (json.JSONDecodeError, AttributeError, TypeError):
        return [b.strip() for b in BIASES.split(",") if b.strip() in text]
