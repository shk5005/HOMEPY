from homepy.agents.base import BaseAgent


class BullAgent(BaseAgent):
    agent_name = "BullAgent"
    system_prompt = (
        "Maximize positive signals and cite upside data (valuation gap, momentum, "
        "supply shortage, rate relief). Respond in Korean where natural."
    )

    def perspective(self) -> str:
        return "bullish: upside signals"
