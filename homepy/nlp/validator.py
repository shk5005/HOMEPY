"""Safety + schema validation for LLM-generated TypeQL (read-only match/get only)."""

from __future__ import annotations

import re

_FORBIDDEN = re.compile(r"\b(insert|delete|define|undefine|redefine|rule|put|update)\b", re.I)
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
_COMMENT = re.compile(r"#[^\n]*")
_SUB = re.compile(r"(?<![\w$-])([a-z][\w-]*)\s+sub\s+([a-z][\w-]*)")
_RELATES = re.compile(r"\brelates\s+([a-z][\w-]*)")
_TYPE_REF = re.compile(r"\b(?:isa!?|has)\s+([a-z][\w-]*)")
_ROLE_REF = re.compile(r"[(,]\s*([a-z][\w-]*)\s*:\s*\$")
_VAR = re.compile(r"\$([\w-]*)")
_BUILTIN_TYPES = {"entity", "relation", "attribute", "thing"}


def strip_literals(typeql: str) -> str:
    """Remove comments and string literals so keyword checks ignore data values."""
    return _STRING.sub('""', _COMMENT.sub("", typeql))


class TypeQLValidator:
    def __init__(self, schema: str):
        text = _COMMENT.sub("", schema)
        self.types: set[str] = {m.group(1) for m in _SUB.finditer(text)} | _BUILTIN_TYPES
        self.roles: set[str] = {m.group(1) for m in _RELATES.finditer(text)}

    def is_safe(self, typeql: str) -> bool:
        if not isinstance(typeql, str) or not typeql.strip():
            return False
        body = strip_literals(typeql).strip()
        if not re.match(r"match\b", body, re.I):
            return False
        return not _FORBIDDEN.search(body)

    def validate(self, typeql: str) -> tuple[bool, str]:
        if not self.is_safe(typeql):
            return False, "unsafe query: only read-only match/get queries are allowed"
        body = strip_literals(typeql).strip()
        if not re.search(r"\bget\b", body, re.I):
            return False, "query must contain a 'get' clause"
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
        if not body.endswith(";"):
            return False, "query must end with ';'"
        if any(name == "" for name in _VAR.findall(body)):
            return False, "invalid variable syntax"
        for t in _TYPE_REF.findall(body):
            if t not in self.types:
                return False, f"unknown type '{t}'"
        for r in _ROLE_REF.findall(body):
            if r not in self.roles:
                return False, f"unknown role '{r}'"
        return True, ""
