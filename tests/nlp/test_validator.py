from pathlib import Path

import pytest

from homepy.nlp.validator import CypherValidator

HOMEPY_SCHEMA = (Path(__file__).resolve().parents[2] / "storage/neo4j/schema.cypher").read_text(encoding="utf-8")


@pytest.fixture
def v():
    return CypherValidator(HOMEPY_SCHEMA)


@pytest.mark.parametrize("q", [
    "MATCH (x:Complex) DELETE x",
    "MATCH (x:Complex) SET x.name = 'hacked'",
    "CREATE (x:Complex {name: 'evil'})",
    "MATCH (x:Complex) REMOVE x.name",
    "MATCH (x:Complex) MERGE (y:Complex)",
    "DROP CONSTRAINT ON (c:Complex)",
    "",
])
def test_rejects_unsafe(v, q):
    assert not v.is_safe(q)


def test_string_literal_with_keyword_is_safe(v):
    assert v.is_safe('MATCH (c:Complex {complexName: "delete me"}) RETURN c')


def test_accepts_match_return(v):
    assert v.validate("MATCH (c:Complex) RETURN c.complexName AS name") == (True, "")


def test_accepts_relation(v):
    ok, err = v.validate('MATCH (d:District)-[:SPATIAL_HIERARCHY]->(c:Complex) RETURN c')
    assert ok, err


def test_unknown_type(v):
    ok, err = v.validate("MATCH (c:Spaceship) RETURN c")
    assert not ok and "Spaceship" in err


def test_unknown_attribute(v):
    ok, err = v.validate("MATCH (c:Complex {bogusAttr: 'x'}) RETURN c")
    assert not ok and "bogusAttr" in err


def test_missing_return(v):
    assert not v.validate("MATCH (c:Complex)")[0]
