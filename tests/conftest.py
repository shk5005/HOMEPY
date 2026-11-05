"""Shared pytest fixtures.

asyncio_mode = "auto" is configured in pyproject.toml ([tool.pytest.ini_options]).
"""

import pytest


@pytest.fixture(autouse=True)
def _disable_rbac_outside_auth_tests(request, monkeypatch):
    """Pre-RBAC API tests send no tokens; auth behaviour is covered in tests/auth/."""
    if "auth" in request.node.path.parts:
        return
    from starlette.middleware.base import BaseHTTPMiddleware

    class _PassThrough(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            return await call_next(request)

    monkeypatch.setattr("homepy.api.main.RBACMiddleware", _PassThrough)
