"""Auth data models."""

from __future__ import annotations

from dataclasses import dataclass, field

RBAC_ROLES = ("admin", "analyst", "viewer", "pipeline_operator")


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    email: str
    roles: list[str] = field(default_factory=list)
    exp: int = 0
    iat: int = 0
    jti: str = ""
