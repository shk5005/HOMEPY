from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from homepy.nlp import NLPQueryResult, TypeQLGenerator, TypeQLValidator
from homepy.nlp.query_generator import RateLimitError, extract_typeql

HOMEPY_SCHEMA = (Path(__file__).resolve().parents[2] / "storage/typedb/schema.tql").read_text(encoding="utf-8")
GOOD = ('match $dist isa district, has district-name "강남구"; $c isa complex; '
        '(parent: $dist, child: $c) isa spatial-hierarchy; get $c;')


def make_gen(text: str) -> TypeQLGenerator:
    gen = TypeQLGenerator("fake-key", HOMEPY_SCHEMA)
    client = MagicMock()
    client.messages.create = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text=text)]))
    gen._client = client
    return gen


async def test_generates_valid_typeql():
    gen = make_gen(GOOD)
    result = await gen.generate("강남구 단지 찾아줘")
    assert TypeQLValidator(HOMEPY_SCHEMA).is_safe(result)
    assert result == GOOD


async def test_strips_explanation_and_fences():
    gen = make_gen(f"Here is the query:\n```typeql\n{GOOD}\n```\nThis finds complexes.")
    assert await gen.generate("강남구 단지") == GOOD


async def test_rejects_malicious_output():
    gen = make_gen("delete $x isa complex;")
    with pytest.raises(ValueError, match="unsafe"):
        await gen.generate("delete all data from the database")


async def test_rejects_schema_violation():
    gen = make_gen("match $x isa spaceship; get $x;")
    with pytest.raises(ValueError, match="invalid"):
        await gen.generate("우주선")


async def test_cache_hit_avoids_second_call():
    gen = make_gen(GOOD)
    await gen.generate("q")
    await gen.generate("q")
    assert gen._client.messages.create.await_count == 1


async def test_cache_expires():
    gen = TypeQLGenerator("k", HOMEPY_SCHEMA, cache_ttl=0.0)
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


def test_extract_typeql_plain():
    assert extract_typeql("blah\nmatch $x isa complex; get $x;") == "match $x isa complex; get $x;"


def test_result_dataclass():
    r = NLPQueryResult("q", "match ...", [{"a": 1}], 1.5)
    assert r.execution_time_ms == 1.5


@pytest.mark.skip(reason="requires live TypeDB")
async def test_live_execution():
    ...
