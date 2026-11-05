from pathlib import Path

import pytest

from homepy.nlp.validator import TypeQLValidator

HOMEPY_SCHEMA = (Path(__file__).resolve().parents[2] / "storage/typedb/schema.tql").read_text(encoding="utf-8")


@pytest.fixture
def v():
    return TypeQLValidator(HOMEPY_SCHEMA)


@pytest.mark.parametrize("q", [
    "match $x isa complex; delete $x;",
    "insert $x isa complex, has complex-name 'hacked';",
    "define malicious-type sub entity;",
    "undefine complex sub entity;",
    "MATCH $x isa complex; DELETE $x;",
    "",
])
def test_rejects_unsafe(v, q):
    assert not v.is_safe(q)


def test_string_literal_with_keyword_is_safe(v):
    assert v.is_safe('match $c isa complex, has complex-name "delete me"; get $c;')


def test_accepts_match_get(v):
    assert v.validate("match $c isa complex, has complex-name $n; get $c, $n;") == (True, "")


def test_accepts_relation(v):
    ok, err = v.validate('match $d isa district; $c isa complex; (parent: $d, child: $c) isa spatial-hierarchy; get $c;')
    assert ok, err


def test_unknown_type(v):
    ok, err = v.validate("match $c isa spaceship; get $c;")
    assert not ok and "spaceship" in err


def test_unknown_attribute(v):
    ok, err = v.validate("match $c isa complex, has bogus-attr $n; get $c;")
    assert not ok and "bogus-attr" in err


def test_unknown_role(v):
    ok, err = v.validate("match $c isa complex; (bogus: $c) isa spatial-hierarchy; get $c;")
    assert not ok and "bogus" in err


def test_unbalanced_and_missing_get(v):
    assert not v.validate("match $c isa complex; (parent: $c isa spatial-hierarchy; get $c;")[0]
    assert not v.validate("match $c isa complex;")[0]
    assert not v.validate("match $c isa complex; get $c")[0]
