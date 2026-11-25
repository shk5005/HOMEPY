from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from homepy.nlp import NLPQueryResult, CypherGenerator, CypherValidator
from homepy.nlp.query_generator import RateLimitError, extract_cypher

HOMEPY_SCHEMA = (Path(__file__).resolve().parents[2] / "storage/neo4j/schema.cypher").read_text(encoding="utf-8")
GOOD = ('MATCH (d:District {districtName: "강남구"})-[:SPATIAL_HIERARCHY]->(c:Complex) '
        'RETURN c.complexName AS name')


def make_gen(text: str) -> CypherGenerator:
    gen = CypherGenerator("fake-key", HOMEPY_SCHEMA)
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text=text)]))
    gen._client = client
    return gen


async def test_generates_valid_cypher():
    gen = make_gen(GOOD)
    result = await gen.generate("강남구 단지 찾아줘")
    assert CypherValidator(HOMEPY_SCHEMA).is_safe(result)
    assert result == GOOD


async def test_strips_explanation_and_fences():
    gen = make_gen(f"Here is the query:\n```cypher\n{GOOD}\n```\nThis finds complexes.")
    assert await gen.generate("강남구 단지") == GOOD


async def test_rejects_malicious_output():
    gen = make_gen("MATCH (x:Complex) DELETE x")
    with pytest.raises(ValueError, match="unsafe"):
        await gen.generate("delete all data from the database")


async def test_rejects_schema_violation():
    gen = make_gen("MATCH (x:Spaceship) RETURN x")
    with pytest.raises(ValueError, match="invalid"):
        await gen.generate("우주선")


async def test_cache_hit_avoids_second_call():
    gen = make_gen(GOOD)
    await gen.generate("q")
    await gen.generate("q")
    assert gen._client.messages.create.await_count == 1


async def test_cache_expires():
    gen = CypherGenerator("k", HOMEPY_SCHEMA, cache_ttl=0.0)
    gen._client = make_gen(GOOD)._client
    await gen.generate("q")
    await gen.generate("q")
    assert gen._client.messages.create.await_count == 2


async def test_rate_limit():
    gen = make_gen(GOOD)
    for i in range(10):
        await gen.generate(f"q{i}")
    with pytest.raises(RateLimitError):
        await gen.generate("q-extra")


def test_extract_cypher_plain():
    assert extract_cypher("blah\nMATCH (x:Complex) RETURN x") == "MATCH (x:Complex) RETURN x"


def test_result_dataclass():
    r = NLPQueryResult("q", "MATCH ...", [{"a": 1}], 1.5)
    assert r.execution_time_ms == 1.5


@pytest.mark.skip(reason="requires live Neo4j")
async def test_live_execution():
    ...
