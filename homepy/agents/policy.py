from homepy.agents.base import BaseAgent


class PolicyAgent(BaseAgent):
    agent_name = "PolicyAgent"
    system_prompt = (
        "Analyze regulation and policy (LTV/DSR, tax, supply policy, redevelopment rules) "
        "including 2nd and 3rd order effects. Evaluate regulation scenarios when asked."
    )

    def perspective(self) -> str:
        return "policy: regulatory second/third-order effects"

    async def reevaluate(self, context: str, scenarios: list[str] | None = None) -> str:
        scenarios = scenarios or ["규제 강화", "현행 유지", "규제 완화"]
        prompt = (
            "[PHASE:policy_reeval] Re-evaluate the debate under these regulation scenarios: "
            f"{scenarios}.\nDEBATE SO FAR:\n{context}\nSummarize impact per scenario."
        )
        return await self._call(prompt)
