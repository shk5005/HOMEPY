"""Multi-tenancy: bind each authenticated request's DB connection to its user (RLS)."""

from __future__ import annotations

import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


async def set_tenant_context(conn: Any, user_id: str) -> None:
    """Run ``SET LOCAL app.current_user_id`` on ``conn`` (must be inside a transaction).

    ``user_id`` is parsed as a UUID first, so the interpolated value cannot inject SQL.
    """
    canonical = str(uuid.UUID(str(user_id)))
    await conn.execute(f"SET LOCAL app.current_user_id = '{canonical}'")


class TenantMiddleware(BaseHTTPMiddleware):
    """Open a transaction scoped to ``request.state.user`` and expose it as ``request.state.db_conn``.

    Must run after ``RBACMiddleware`` (which sets ``request.state.user``). Requests
    without a user (exempt paths) or apps without a DB pool pass through untouched.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user = getattr(request.state, "user", None)
        timescale = getattr(request.app.state, "timescale", None)
        pool = getattr(timescale, "_pool", None)
        if user is None or pool is None:
            return await call_next(request)
        try:
            uuid.UUID(str(user.sub))
        except ValueError:
            return JSONResponse({"detail": "Invalid user identifier"}, status_code=403)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await set_tenant_context(conn, user.sub)
                request.state.db_conn = conn
                return await call_next(request)
