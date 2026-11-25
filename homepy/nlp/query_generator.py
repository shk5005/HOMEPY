"""Natural language (Korean) -> TypeQL generation via the Claude API."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from homepy.nlp.validator import TypeQLValidator

MODEL = "claude-sonnet-4-20250514"
CACHE_TTL_S = 300.0
RATE_CAPACITY = 10
RATE_REFILL_S = 6.0

SCHEMA_SUMMARY = """\
Entities: region, district, dong, complex, unit-type, interest-rate, real-estate-cycle,
cycle-observation, loan-product, loan-regulation, loan-regulation-rule, acquisition-tax-rate,
cgt-rate-rule, crt-rate-rule, gift-tax-rate, policy, zone-designation, price-control,
subscription-regulation, population-data, migration-data, income-data, supply-data,
unsold-inventory, reconstruction-supply, infrastructure, development-project, market-sentiment
Relations: spatial-hierarchy(parent, child), accessibility(location, facility),
regulation-applies(rule-source, rule-detail), tax-applies-to(tax-rule, taxed-area),
zone-applied-to(designation, target-district), cycle-observed-at, development-influence
Key attributes: region-name, district-name, dong-name, complex-id, complex-name, total-units,
built-year, price-per-sqm, safety-grade, regulation-zone-type, loan-name, ltv-limit, dsr-limit,
tax-rate-pct, policy-name, cycle-phase, distance-meter, infra-type"""

FEW_SHOT = """\
Q: 강남구 단지 찾아줘
match $d isa district, has district-name "강남구"; $c isa complex, has complex-name $n; (parent: $d, child: $c) isa spatial-hierarchy; get $c, $n;

Q: 강남구 역세권 단지는?
match $d isa district, has district-name "강남구"; $c isa complex, has complex-name $n; (parent: $d, child: $c) isa spatial-hierarchy; $i isa infrastructure, has infra-type "subway"; (location: $c, facility: $i) isa accessibility, has distance-meter $m; $m < 500.0; get $c, $n, $m;

Q: 투기과열지구 구 목록
match $d isa district, has district-name $n, has regulation-zone-type "투기과열지구"; get $d, $n;"""

SYSTEM_PROMPT = (
    "You translate Korean real-estate questions into TypeQL 2.x read queries for the HOMEPY "
    "knowledge graph. Output ONLY one TypeQL query (match ... get ...;), no explanation, no "
    "markdown. Never emit insert, delete, define or undefine. Use only these schema elements.\n\n"
    f"{SCHEMA_SUMMARY}\n\nExamples:\n{FEW_SHOT}"
)


@dataclass
class NLPQueryResult:
    original_query: str
    generated_typeql: str
    results: list[dict] = field(default_factory=list)
    execution_time_ms: float = 0.0


class RateLimitError(RuntimeError):
    """Raised when the Claude API token bucket is empty."""


class TokenBucket:
    def __init__(self, capacity: int = RATE_CAPACITY, refill_s: float = RATE_REFILL_S):
        self.capacity, self.refill_s = capacity, refill_s
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def try_acquire(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) / self.refill_s)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


def extract_typeql(text: str) -> str:
    """Pull the TypeQL query out of a model response, dropping prose and code fences."""
    fence = re.search(r"```(?:typeql|tql)?\s*(.*?)```", text, re.S | re.I)
    if fence:
        text = fence.group(1)
    m = re.search(r"\b(match|insert|delete|define|undefine)\b", text, re.I)
    if m:
        text = text[m.start():]
    return text.strip()


class TypeQLGenerator:
    def __init__(self, api_key: str, schema_context: str, *, cache_ttl: float = CACHE_TTL_S):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.validator = TypeQLValidator(schema_context)
        self._bucket = TokenBucket()
        self._cache: dict[str, tuple[float, str]] = {}
        self._cache_ttl = cache_ttl

    async def generate(self, natural_language: str) -> str:
        key = natural_language.strip()
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self._cache_ttl:
            return hit[1]
        if not self._bucket.try_acquire():
            raise RateLimitError("Claude API rate limit exceeded (10 requests/min)")
        response = await self._client.messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": key}],
        )
        typeql = extract_typeql(response.content[0].text)
        if not self.validator.is_safe(typeql):
            raise ValueError("unsafe TypeQL generated: only read-only match/get allowed")
        ok, err = self.validator.validate(typeql)
        if not ok:
            raise ValueError(f"invalid TypeQL generated: {err}")
        self._cache[key] = (time.monotonic(), typeql)
        return typeql
