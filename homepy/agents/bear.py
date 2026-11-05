from homepy.agents.base import BaseAgent


class BearAgent(BaseAgent):
    agent_name = "BearAgent"
    system_prompt = (
        "Maximize risk signals and cite downside data (leverage, supply glut, rate risk, "
        "liquidity, jeonse-gap). Respond in Korean where natural."
    )

    def perspective(self) -> str:
        return "bearish: downside risks"
