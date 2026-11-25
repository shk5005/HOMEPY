"""Safety + schema validation for LLM-generated Cypher (read-only MATCH/RETURN only)."""

from __future__ import annotations

import re

_FORBIDDEN = re.compile(
    r"\b(CREATE|DELETE|DETACH|SET|REMOVE|MERGE|DROP|CALL\s+dbms|CALL\s+db\.)"
    r"\b", re.I)
_STRING = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_COMMENT = re.compile(r"//[^\n]*")
_LABEL_DEF = re.compile(r":\s*([A-Z][A-Za-z0-9_]*)")
_REL_TYPE = re.compile(r"\[[\w]*:([A-Z_]+)")
_PROP_REF = re.compile(r"\.([a-zA-Z]\w*)")


def strip_literals(cypher: str) -> str:
    """Remove comments and string literals so keyword checks ignore data values."""
    return _STRING.sub("''", _COMMENT.sub("", cypher))


class CypherValidator:
    def __init__(self, schema: str):
        text = _COMMENT.sub("", schema)
        self.labels: set[str] = set(_LABEL_DEF.findall(text))
        self.rel_types: set[str] = set(_REL_TYPE.findall(text))

    def is_safe(self, cypher: str) -> bool:
        if not isinstance(cypher, str) or not cypher.strip():
            return False
        body = strip_literals(cypher).strip()
        if not re.match(r"(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|CALL)\b", body, re.I):
            return False
        return not _FORBIDDEN.search(body)

    def validate(self, cypher: str) -> tuple[bool, str]:
        if not self.is_safe(cypher):
            return False, "unsafe query: only read-only MATCH/RETURN queries are allowed"
        body = strip_literals(cypher).strip()
        if not re.search(r"\bRETURN\b", body, re.I):
            return False, "query must contain a 'RETURN' clause"
        for o, c in ("{}", "()", "[]"):
            depth = 0
            for ch in body:
                if ch == o:
                    depth += 1
                elif ch == c:
                    depth -= 1
                    if depth < 0:
                        break
            if depth != 0:
                return False, f"unbalanced '{o}{c}'"
        return True, ""
