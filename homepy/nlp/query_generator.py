"""Natural language (Korean) -> Cypher generation via the Claude API."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

from homepy.nlp.validator import CypherValidator

MODEL = "claude-sonnet-4-20250514"
CACHE_TTL_S = 300.0
RATE_CAPACITY = 10
RATE_REFILL_S = 6.0

SCHEMA_SUMMARY = """\
Node labels: Region, District, Dong, Complex, UnitType, InterestRate, RealEstateCycle,
CycleObservation, LoanProduct, LoanRegulation, LoanRegulationRule, AcquisitionTaxRate,
CgtRateRule, CrtRateRule, GiftTaxRate, Policy, ZoneDesignation, PriceControl,
SubscriptionRegulation, PopulationData, MigrationData, IncomeData, SupplyData,
UnsoldInventory, ReconstructionSupply, Infrastructure, DevelopmentProject, MarketSentiment
Relationships: SPATIAL_HIERARCHY, ACCESSIBILITY, REGULATION_APPLIES, TAX_APPLIES_TO,
ZONE_APPLIED_TO, CYCLE_OBSERVED_AT, DEVELOPMENT_INFLUENCE
Key properties: regionName, districtName, dongName, complexId, complexName, totalUnits,
builtYear, pricePerSqm, safetyGrade, regulationZoneType, loanName, ltvLimit, dsrLimit,
taxRatePct, policyName, cyclePhase, distanceMeter, infraType"""

FEW_SHOT = """\
Q: 강남구 단지 찾아줘
MATCH (d:District {districtName: '강남구'})-[:SPATIAL_HIERARCHY]->(c:Complex) RETURN c.complexName AS name

Q: 강남구 역세권 단지는?
MATCH (d:District {districtName: '강남구'})-[:SPATIAL_HIERARCHY]->(c:Complex)<-[a:ACCESSIBILITY]-(i:Infrastructure {infraType: 'subway'}) WHERE a.distanceMeter < 500.0 RETURN c.complexName AS name, a.distanceMeter AS distance

Q: 투기과열지구 구 목록
MATCH (d:District) WHERE d.regulationZoneType = '투기과열지구' RETURN d.districtName AS name"""

SYSTEM_PROMPT = (
    "You translate Korean real-estate questions into Cypher read queries for the HOMEPY Neo4j "
    "knowledge graph. Output ONLY one Cypher query (MATCH ... RETURN ...), no explanation, no "
    "markdown. Never emit CREATE, DELETE, SET, MERGE, DROP or REMOVE. Use only these schema "
    "elements.\n\n"
    f"{SCHEMA_SUMMARY}\n\nExamples:\n{FEW_SHOT}"
)


@dataclass
class NLPQueryResult:
    original_query: str
    generated_cypher: str
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


def extract_cypher(text: str) -> str:
    """Pull the Cypher query out of a model response, dropping prose and code fences."""
    fence = re.search(r"```(?:cypher)?\s*(.*?)```", text, re.S | re.I)
    if fence:
        text = fence.group(1)
    m = re.search(r"\b(MATCH|RETURN|WITH|UNWIND|CALL|OPTIONAL)\b", text, re.I)
    if m:
        text = text[m.start():]
    return text.strip()


class CypherGenerator:
    def __init__(self, api_key: str, schema_context: str, *, cache_ttl: float = CACHE_TTL_S):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self.validator = CypherValidator(schema_context)
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
        cypher = extract_cypher(response.content[0].text)
        if not self.validator.is_safe(cypher):
            raise ValueError("unsafe Cypher generated: only read-only MATCH/RETURN allowed")
        ok, err = self.validator.validate(cypher)
        if not ok:
            raise ValueError(f"invalid Cypher generated: {err}")
        self._cache[key] = (time.monotonic(), cypher)
        return cypher
