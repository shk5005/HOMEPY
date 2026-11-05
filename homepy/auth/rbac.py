"""Role-based access control: endpoint permission map, dependency and middleware."""

from __future__ import annotations

import re
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from homepy.auth.jwt_handler import get_current_user
from homepy.auth.models import TokenPayload

ENDPOINT_PERMISSIONS: dict[str, list[str]] = {
    "/api/v1/ontology/*": ["viewer", "analyst", "admin"],
    "/api/v1/analysis/*": ["analyst", "admin"],
    "/api/v1/simulation/*": ["analyst", "admin"],
    "/api/v1/market/*": ["viewer", "analyst", "admin"],
    "/api/v1/portfolio/*": ["analyst", "admin"],
    "/api/v1/pipeline/*": ["pipeline_operator", "admin"],
    "/api/v1/pipeline/verification/proposals/*/approve": ["admin"],
}

# Probes and docs stay unauthenticated (incl. Plan E pipeline health/HA endpoints).
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/health",
    "/readiness",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
    "/api/v1/pipeline/health",
    "/api/v1/pipeline/ha/status",
})


def _compile(pattern: str) -> re.Pattern[str]:
    # Trailing "/*" matches any depth; inner "*" matches exactly one segment.
    if pattern.endswith("/*"):
        head = re.escape(pattern[:-2]).replace(r"\*", "[^/]+")
        return re.compile(f"^{head}/.+$")
    return re.compile("^" + re.escape(pattern).replace(r"\*", "[^/]+") + "$")


_COMPILED = [(p, _compile(p), roles) for p, roles in ENDPOINT_PERMISSIONS.items()]


def required_roles_for(path: str) -> list[str] | None:
    """Roles allowed for ``path`` via the most specific (longest) matching pattern."""
    best: tuple[int, list[str]] | None = None
    for pattern, regex, roles in _COMPILED:
        if regex.match(path) and (best is None or len(pattern) > best[0]):
            best = (len(pattern), roles)
    return best[1] if best else None


def is_exempt(path: str) -> bool:
    return path.rstrip("/") in EXEMPT_PATHS or path in EXEMPT_PATHS


def check_roles(user: TokenPayload, roles: list[str] | tuple[str, ...]) -> None:
    if not any(r in user.roles for r in roles):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def require_roles(*roles: str) -> Callable[..., TokenPayload]:
    """Return a FastAPI dependency enforcing that the user holds one of ``roles``."""

    async def _dep(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        check_roles(user, roles)
        return user

    return Depends(_dep)  # type: ignore[return-value]


class RBACMiddleware(BaseHTTPMiddleware):
    """Authenticate the bearer token and enforce ``ENDPOINT_PERMISSIONS`` per path."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or is_exempt(path):
            return await call_next(request)
        roles = required_roles_for(path)
        try:
            user = await get_current_user(request)
            if roles is not None:
                check_roles(user, roles)
        except HTTPException as exc:
            return JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )
        request.state.user = user
        return await call_next(request)
