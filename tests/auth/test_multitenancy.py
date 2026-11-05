"""Multi-tenancy tests. RLS tests need a live TimescaleDB with schema.sql applied;
the TenantMiddleware test is mock-based."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from homepy.auth.models import TokenPayload
from homepy.auth.tenant import TenantMiddleware, set_tenant_context

live_db = pytest.mark.skip(reason="requires live TimescaleDB")


async def _mk_user(conn, user_id):
    await conn.execute(
        "INSERT INTO ts_users (user_id, email) VALUES ($1, $2)", user_id, f"{user_id}@example.com"
    )


@live_db
async def test_user_a_cannot_see_user_b_portfolio(db_pool):
    user_a, user_b = uuid4(), uuid4()
    async with db_pool.acquire() as conn:
        await _mk_user(conn, user_a)
        await _mk_user(conn, user_b)
        for uid, cid in ((user_a, "C001"), (user_b, "C002")):
            async with conn.transaction():
                await set_tenant_context(conn, str(uid))
                await conn.execute(
                    "INSERT INTO ts_portfolio (ts, user_id, complex_id, action) "
                    "VALUES (NOW(), $1, $2, 'buy')", uid, cid)
    async with db_pool.acquire() as conn, conn.transaction():
        await set_tenant_context(conn, str(user_a))
        ids = {r["complex_id"] for r in await conn.fetch("SELECT * FROM ts_portfolio")}
        assert "C001" in ids and "C002" not in ids


@live_db
async def test_no_tenant_context_returns_zero_rows(db_pool):
    async with db_pool.acquire() as conn:
        assert len(await conn.fetch("SELECT * FROM ts_portfolio")) == 0


@live_db
async def test_rls_on_watchlist(db_pool):
    user_a, user_b = uuid4(), uuid4()
    async with db_pool.acquire() as conn:
        await _mk_user(conn, user_a)
        await _mk_user(conn, user_b)
        async with conn.transaction():
            await set_tenant_context(conn, str(user_a))
            await conn.execute(
                "INSERT INTO ts_watchlist (ts, user_id, complex_id) VALUES (NOW(), $1, 'C001')",
                user_a)
    async with db_pool.acquire() as conn, conn.transaction():
        await set_tenant_context(conn, str(user_b))
        assert len(await conn.fetch("SELECT * FROM ts_watchlist")) == 0


@live_db
async def test_rls_on_verdict_history(db_pool):
    user_a, user_b = uuid4(), uuid4()
    async with db_pool.acquire() as conn:
        await _mk_user(conn, user_a)
        await _mk_user(conn, user_b)
        async with conn.transaction():
            await set_tenant_context(conn, str(user_a))
            await conn.execute(
                "INSERT INTO ts_verdict_history (ts, user_id, complex_id, verdict) "
                "VALUES (NOW(), $1, 'C001', 'buy')", user_a)
    async with db_pool.acquire() as conn, conn.transaction():
        await set_tenant_context(conn, str(user_b))
        assert len(await conn.fetch("SELECT * FROM ts_verdict_history")) == 0


@live_db
async def test_shared_market_data_visible_to_all(db_pool):
    """Market data tables have no RLS: queryable without app.current_user_id."""
    async with db_pool.acquire() as conn:
        await conn.fetch("SELECT * FROM ts_real_trade LIMIT 1")


async def test_set_tenant_context_executes_set_local():
    conn = MagicMock()
    conn.execute = AsyncMock()
    uid = str(uuid4())
    await set_tenant_context(conn, uid)
    conn.execute.assert_awaited_once_with(f"SET LOCAL app.current_user_id = '{uid}'")


async def test_set_tenant_context_rejects_non_uuid():
    conn = MagicMock()
    conn.execute = AsyncMock()
    with pytest.raises(ValueError):
        await set_tenant_context(conn, "x'; DROP TABLE ts_users; --")
    conn.execute.assert_not_awaited()


async def test_tenant_middleware_sets_local_user_id():
    uid = str(uuid4())
    conn = MagicMock()
    conn.execute = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    acq = MagicMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)

    app = FastAPI()
    app.state.timescale = SimpleNamespace(_pool=pool)

    class FakeAuth(BaseHTTPMiddleware):  # stands in for RBACMiddleware
        async def dispatch(self, request, call_next):
            request.state.user = TokenPayload(
                sub=uid, email="u@example.com", roles=["analyst"], exp=2, iat=1, jti="j")
            return await call_next(request)

    app.add_middleware(TenantMiddleware)
    app.add_middleware(FakeAuth)  # last added runs first

    @app.get("/whoami")
    async def whoami(request: Request):
        return {"has_conn": request.state.db_conn is conn}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/whoami")
    assert r.status_code == 200 and r.json() == {"has_conn": True}
    conn.execute.assert_awaited_once_with(f"SET LOCAL app.current_user_id = '{uid}'")


async def test_tenant_middleware_passthrough_without_user():
    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/health")
    async def health():
        return {"ok": True}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/health")).status_code == 200
