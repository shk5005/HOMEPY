"""BaseAgent: shared Claude API plumbing for debate agents."""

from __future__ import annotations

import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Any

from homepy.agents.models import AgentAnalysis

DEFAULT_MODEL = "claude-sonnet-4-20250514"
JSON_SPEC = (
    'Respond with a single JSON object: {"verdict": str (매수 검토|관망|매도 검토), '
    '"confidence": float 0-1, "key_arguments": [str], "data_cited": [str], '
    '"identified_biases": [str]}.'
)


class RateLimiter:
    """Sliding-window limiter shared across agents (default 10 req/min)."""

    def __init__(self, max_calls: int = 10, period: float = 60.0) -> None:
        self.max_calls, self.period = max_calls, period
        self._calls: deque[float] = deque()
        self._lock: asyncio.Lock | None = None

    async def acquire(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.period:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                await asyncio.sleep(self.period - (now - self._calls[0]))


def parse_analysis(agent_name: str, text: str) -> AgentAnalysis:
    """Parse model output as JSON; fall back to plain-text extraction."""
    data: dict[str, Any] | None = None
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    for candidate in (cleaned, (re.search(r"\{.*\}", cleaned, re.S) or [None])[0]):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                data = parsed
                break
        except (json.JSONDecodeError, TypeError):
            continue
    if data is None:
        return _fallback(agent_name, text)

    def _list(key: str) -> list[str]:
        v = data.get(key) or []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]

    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return AgentAnalysis(
        agent_name=agent_name,
        verdict=str(data.get("verdict") or "관망"),
        confidence=conf,
        key_arguments=_list("key_arguments"),
        data_cited=_list("data_cited"),
        identified_biases=_list("identified_biases"),
    )


def _fallback(agent_name: str, text: str) -> AgentAnalysis:
    verdict = "관망"
    for kw, v in (("매도", "매도 검토"), ("sell", "매도 검토"), ("매수", "매수 검토"), ("buy", "매수 검토")):
        if kw in text.lower():
            verdict = v
            break
    m = re.search(r"confidence\D{0,5}([01](?:\.\d+)?)", text, re.I)
    conf = float(m.group(1)) if m else 0.5
    lines = [ln.strip("-*• \t") for ln in text.splitlines() if ln.strip()]
    return AgentAnalysis(agent_name, verdict, conf, key_arguments=lines[:5])


class BaseAgent(ABC):
    """Abstract debate agent. ``api_key`` may also be a ready client object."""

    agent_name: str = "BaseAgent"
    system_prompt: str = ""

    def __init__(
        self,
        api_key: Any,
        model: str = DEFAULT_MODEL,
        rate_limiter: RateLimiter | None = None,
        max_tokens: int = 2048,
    ) -> None:
        if isinstance(api_key, str):
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        else:  # injected client (tests / shared client)
            self._client = api_key
        self.model = model
        self.rate_limiter = rate_limiter
        self.max_tokens = max_tokens

    @property
    def full_system_prompt(self) -> str:
        return f"You are {self.agent_name}. {self.system_prompt}"

    async def _call(self, prompt: str) -> str:
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.full_system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def analyze(self, data: dict) -> AgentAnalysis:
        prompt = (
            "[PHASE:analyze] Analyze this Korean apartment complex data independently.\n"
            f"DATA:\n{json.dumps(data, ensure_ascii=False, default=str)}\n{JSON_SPEC}"
        )
        return parse_analysis(self.agent_name, await self._call(prompt))

    async def rebut(self, other_analysis: AgentAnalysis) -> str:
        prompt = (
            f"[PHASE:rebut] Rebut this analysis by {other_analysis.agent_name}.\n"
            f"Verdict: {other_analysis.verdict} (confidence {other_analysis.confidence})\n"
            f"Arguments: {other_analysis.key_arguments}\nData cited: {other_analysis.data_cited}\n"
            "Give a concise rebuttal in plain text."
        )
        return await self._call(prompt)

    async def respond_to_rebuttal(self, rebuttal: str) -> str:
        prompt = f"[PHASE:respond] A rebuttal was made against you:\n{rebuttal}\nRespond concisely."
        return await self._call(prompt)

    async def final_position(self, context: str) -> AgentAnalysis:
        prompt = (
            "[PHASE:final] State your final position after the debate. Do not concede merely "
            "to reach consensus; hold your view if the evidence supports it.\n"
            f"DEBATE SO FAR:\n{context}\n{JSON_SPEC}"
        )
        return parse_analysis(self.agent_name, await self._call(prompt))

    @abstractmethod
    def perspective(self) -> str:
        """Short description of this agent's stance."""
