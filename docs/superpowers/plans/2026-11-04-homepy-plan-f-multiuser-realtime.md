# HOMEPY Plan F: Multi-User, Real-Time Data & Policy Simulation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user authentication (Keycloak OAuth2 + JWT), role-based access control with 4 roles, Row-Level Security multi-tenancy for user-owned data, a real-time WebSocket data pipeline via Redis Pub/Sub, and a policy simulation engine with 4 simulation types (tax, regulation, interest rate, supply shock) plus policy backtesting.

**Architecture:** Keycloak serves as the OAuth2/OIDC identity provider, issuing RS256-signed JWTs (15-min access + 7-day refresh). A FastAPI middleware layer verifies Bearer tokens, extracts roles from JWT claims, and sets `app.current_user_id` on each DB connection for RLS enforcement. User-owned tables (portfolio, watchlist, verdict history) use TimescaleDB Row-Level Security; shared data (market, ontology) remains publicly readable. Real-time data flows through WebSocket collectors → Redis Pub/Sub → Event Processor, which fans out to TimescaleDB, TypeDB snapshot updates, and a WebSocket server that pushes to subscribed clients. The policy simulation engine operates on a shadow copy of TypeDB state, applying hypothetical changes and propagating through the existing inference rules to measure impact.

**Tech Stack:** Python 3.11+, Keycloak 24+, python-jose[cryptography], websockets, redis[hiredis], Pyvis, pytest, mypy, ruff

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Section 12)

**Depends on:** Plan E complete (HA infrastructure with Redis Sentinel, load balancer, DB replication all deployed)

## Global Constraints

- Python ≥ 3.11
- JWT algorithm: RS256 only — no HS256, no symmetric secrets in tokens
- Access token lifetime: 15 minutes; refresh token: 7 days
- All user-facing endpoints require a valid JWT; health/readiness probes are exempt
- RBAC roles: `admin`, `analyst`, `viewer`, `pipeline_operator` — no other roles
- RLS enforced at the database layer — application-level filtering is defense-in-depth, not the primary mechanism
- WebSocket collectors are stubs for external APIs (키움/한투/네이버); the transport and pub/sub plumbing must be fully functional
- Policy simulation operates on a TypeDB read transaction with hypothetical overwrites — never mutates production data
- CI quality gates: ruff 0 warnings, mypy strict, tests 100% pass, coverage ≥ 80%

## Review Focus

1. **JWT validation bypass** — every protected endpoint must call the auth dependency. A test must show that a request with no token, an expired token, and a token signed with the wrong key all return 401. The WebSocket handshake must also validate the token before accepting the connection.
2. **RLS leakage** — a query from User A must never return User B's portfolio rows, even if User A crafts a SQL-injected `current_setting` value. Tests must create two users, insert data for both, and assert strict isolation. The test must also verify that RLS still works when the application forgets to set `app.current_user_id` (should return 0 rows, not all rows).
3. **WebSocket backpressure** — a slow consumer must not block the Redis subscriber or other fast consumers. The connection manager must drop messages for a consumer whose send buffer exceeds a threshold, and a test must verify that a blocked consumer is disconnected after timeout.
4. **Policy simulation side effects** — the simulation engine must never write to the production TypeDB database. A test must verify that running a tax-change simulation leaves TypeDB's `tax-rule` entity count unchanged afterward.
5. **RBAC privilege escalation** — a `viewer` role must not access `/api/v1/analysis/*`, and a `pipeline_operator` must not approve calibration proposals. Tests must exercise every role against every permission boundary in `ENDPOINT_PERMISSIONS`.

---

### Task 1: Keycloak Integration + JWT Middleware

**Files:**
- Modify: `docker-compose.yml` (add Keycloak + Keycloak PostgreSQL services)
- Create: `homepy/auth/__init__.py`
- Create: `homepy/auth/jwt_handler.py`
- Create: `homepy/auth/models.py`
- Create: `tests/auth/__init__.py`
- Create: `tests/auth/test_jwt_handler.py`

**Interfaces:**
- Consumes: Keycloak OIDC well-known endpoint for JWKS (public key rotation), Redis from Plan E for token blacklist
- Produces:
  - `TokenPayload(sub: str, email: str, roles: list[str], exp: int, iat: int, jti: str)` — dataclass
  - `JWTHandler(jwks_url: str, audience: str, issuer: str)` with methods:
    - `async verify_token(token: str) -> TokenPayload` — raises `AuthenticationError` on invalid/expired
    - `async blacklist_token(jti: str, exp: int) -> None` — adds to Redis blacklist
    - `async is_blacklisted(jti: str) -> bool`
  - `get_current_user` — FastAPI `Depends` callable returning `TokenPayload`
  - `AuthenticationError(detail: str)` — exception mapped to HTTP 401

- [ ] **Step 1: Write failing tests**

```python
async def test_valid_token_returns_payload(jwt_handler, valid_token):
    payload = await jwt_handler.verify_token(valid_token)
    assert payload.sub == "user-uuid-001"
    assert "analyst" in payload.roles

async def test_expired_token_raises(jwt_handler, expired_token):
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(expired_token)

async def test_wrong_key_token_raises(jwt_handler, wrong_key_token):
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(wrong_key_token)

async def test_blacklisted_token_rejected(jwt_handler, valid_token, token_jti):
    await jwt_handler.blacklist_token(token_jti, exp=9999999999)
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(valid_token)

async def test_no_token_returns_401(test_client):
    resp = await test_client.get("/api/v1/analysis/score/test-complex")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/auth/test_jwt_handler.py -v`
Expected: FAIL with "cannot import name 'JWTHandler'"

- [ ] **Step 3: Add Keycloak services to `docker-compose.yml`**

Add `keycloak` service (image: `quay.io/keycloak/keycloak:24.0`, command: `start-dev`, ports: 8080) and `keycloak-db` service (PostgreSQL 16 for Keycloak's own state). Environment variables: `KC_DB=postgres`, `KC_DB_URL`, `KEYCLOAK_ADMIN`, `KEYCLOAK_ADMIN_PASSWORD` from env.

- [ ] **Step 4: Implement `TokenPayload` in `auth/models.py`**

Frozen dataclass with `sub`, `email`, `roles`, `exp`, `iat`, `jti` fields.

- [ ] **Step 5: Implement `JWTHandler` in `auth/jwt_handler.py`**

Constructor fetches JWKS from Keycloak's `/.well-known/openid-configuration` → `jwks_uri`, caches public keys with 1-hour TTL. `verify_token`: decodes with `python-jose` using RS256, checks `exp`, `iss`, `aud`, checks Redis blacklist. `blacklist_token`: `SET jti:{jti} 1 EX {exp - now}` in Redis. `get_current_user`: FastAPI `Depends` that extracts Bearer token from `Authorization` header, calls `verify_token`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/auth/test_jwt_handler.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml homepy/auth/ tests/auth/
git commit -m "feat: Keycloak integration + JWT verification middleware"
```

---

### Task 2: RBAC + Endpoint Permissions

**Files:**
- Create: `homepy/auth/rbac.py`
- Modify: `homepy/api/main.py` (add auth dependency to all routers)
- Create: `tests/auth/test_rbac.py`

**Interfaces:**
- Consumes: `get_current_user` and `TokenPayload` from Task 1
- Produces:
  - `ENDPOINT_PERMISSIONS: dict[str, list[str]]` — module constant matching spec Section 12.1
  - `require_roles(*roles: str) -> Depends` — FastAPI dependency that checks `TokenPayload.roles` against required roles, raises HTTP 403 if none match
  - `RBACMiddleware` — FastAPI middleware that matches request path against `ENDPOINT_PERMISSIONS` patterns and enforces role check

- [ ] **Step 1: Write failing tests**

```python
async def test_viewer_can_access_market(test_client, viewer_token):
    resp = await test_client.get(
        "/api/v1/market/cycle/11680",
        headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code != 403

async def test_viewer_cannot_access_analysis(test_client, viewer_token):
    resp = await test_client.get(
        "/api/v1/analysis/score/test-complex",
        headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403

async def test_analyst_can_access_analysis(test_client, analyst_token):
    resp = await test_client.get(
        "/api/v1/analysis/score/test-complex",
        headers={"Authorization": f"Bearer {analyst_token}"}
    )
    assert resp.status_code != 403

async def test_pipeline_operator_cannot_approve_proposal(test_client, operator_token):
    resp = await test_client.post(
        "/api/v1/pipeline/verification/proposals/P001/approve",
        headers={"Authorization": f"Bearer {operator_token}"}
    )
    assert resp.status_code == 403

async def test_admin_can_approve_proposal(test_client, admin_token):
    resp = await test_client.post(
        "/api/v1/pipeline/verification/proposals/P001/approve",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code != 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/auth/test_rbac.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ENDPOINT_PERMISSIONS` and `require_roles` in `auth/rbac.py`**

`ENDPOINT_PERMISSIONS` verbatim from spec:
```python
ENDPOINT_PERMISSIONS = {
    "/api/v1/ontology/*": ["viewer", "analyst", "admin"],
    "/api/v1/analysis/*": ["analyst", "admin"],
    "/api/v1/simulation/*": ["analyst", "admin"],
    "/api/v1/market/*": ["viewer", "analyst", "admin"],
    "/api/v1/portfolio/*": ["analyst", "admin"],
    "/api/v1/pipeline/*": ["pipeline_operator", "admin"],
    "/api/v1/pipeline/verification/proposals/*/approve": ["admin"],
}
```

`require_roles`: returns a `Depends` that injects `TokenPayload` via `get_current_user`, checks `any(r in payload.roles for r in roles)`, raises `HTTPException(403)` on failure. `RBACMiddleware`: on each request, finds the most-specific matching pattern in `ENDPOINT_PERMISSIONS` (longer path wins), calls `require_roles` with that pattern's role list. Exempt paths: `/health`, `/readiness`, `/docs`, `/openapi.json`.

- [ ] **Step 4: Wire auth dependency into `api/main.py`**

Add `RBACMiddleware` to the FastAPI app middleware stack, after CORS. Each router's `dependencies` list gets `Depends(get_current_user)`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/auth/test_rbac.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/auth/rbac.py homepy/api/main.py tests/auth/test_rbac.py
git commit -m "feat: RBAC — 4 roles, endpoint permission enforcement, admin-only approval"
```

---

### Task 3: Multi-Tenancy (RLS) + User Data Model

**Files:**
- Modify: `storage/timescale/schema.sql` (add `ts_users` table, add `user_id` columns, RLS policies)
- Create: `homepy/auth/tenant.py`
- Modify: `homepy/api/main.py` (add tenant middleware)
- Create: `tests/auth/test_multitenancy.py`

**Interfaces:**
- Consumes: `TokenPayload` from Task 1, `TimescaleService` from Plan A Task 6
- Produces:
  - `ts_users` table: `user_id UUID PRIMARY KEY, email TEXT UNIQUE, display_name TEXT, role TEXT, created_at TIMESTAMPTZ DEFAULT NOW()`
  - `user_id UUID` column + RLS policies on: `ts_portfolio`, `ts_watchlist`, `ts_verdict_history`
  - `TenantMiddleware` — FastAPI middleware that calls `SET LOCAL app.current_user_id = '{user_id}'` on the DB connection per request
  - `set_tenant_context(conn, user_id: str) -> None` — helper for manual connection contexts

- [ ] **Step 1: Write failing tests**

```python
async def test_user_a_cannot_see_user_b_portfolio(db_pool):
    user_a, user_b = uuid4(), uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ts_portfolio (ts, user_id, complex_id, action) VALUES (NOW(), $1, 'C001', 'buy')",
            user_a
        )
        await conn.execute(
            "INSERT INTO ts_portfolio (ts, user_id, complex_id, action) VALUES (NOW(), $1, 'C002', 'buy')",
            user_b
        )
    async with db_pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.current_user_id = '{user_a}'")
        rows = await conn.fetch("SELECT * FROM ts_portfolio")
        complex_ids = {r["complex_id"] for r in rows}
        assert "C001" in complex_ids
        assert "C002" not in complex_ids

async def test_no_tenant_context_returns_zero_rows(db_pool):
    """If app.current_user_id is not set, RLS should block all rows"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM ts_portfolio")
        assert len(rows) == 0

async def test_rls_on_watchlist(db_pool):
    user_a, user_b = uuid4(), uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO ts_watchlist (ts, user_id, complex_id) VALUES (NOW(), $1, 'C001')", user_a
        )
    async with db_pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.current_user_id = '{user_b}'")
        rows = await conn.fetch("SELECT * FROM ts_watchlist")
        assert len(rows) == 0

async def test_shared_market_data_visible_to_all(db_pool):
    """Market data tables have no RLS — visible regardless of user context"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM ts_real_trade LIMIT 1")
        # Should not fail even without app.current_user_id set
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/auth/test_multitenancy.py -v`
Expected: FAIL

- [ ] **Step 3: Add schema changes to `storage/timescale/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS ts_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE ts_portfolio ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES ts_users(user_id);
ALTER TABLE ts_watchlist ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES ts_users(user_id);
ALTER TABLE ts_verdict_history ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES ts_users(user_id);

ALTER TABLE ts_portfolio ENABLE ROW LEVEL SECURITY;
CREATE POLICY portfolio_isolation ON ts_portfolio
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

ALTER TABLE ts_watchlist ENABLE ROW LEVEL SECURITY;
CREATE POLICY watchlist_isolation ON ts_watchlist
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

ALTER TABLE ts_verdict_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY verdict_isolation ON ts_verdict_history
    USING (user_id = current_setting('app.current_user_id', true)::uuid);
```

`current_setting(..., true)` returns NULL instead of error when unset, so unset context → no rows (not an error).

- [ ] **Step 4: Implement `TenantMiddleware` in `auth/tenant.py`**

Extracts `user_id` from `request.state.user` (set by auth middleware), wraps the DB connection pool's `acquire()` to inject `SET LOCAL app.current_user_id = '{user_id}'` at the start of each transaction. `set_tenant_context` is the low-level helper for use outside HTTP requests (e.g., background jobs).

- [ ] **Step 5: Wire `TenantMiddleware` into `api/main.py`**

Add after `RBACMiddleware`. The middleware ordering is: CORS → Auth (JWT) → RBAC → Tenant.

- [ ] **Step 6: Run tests**

Run: `pytest tests/auth/test_multitenancy.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add storage/timescale/schema.sql homepy/auth/tenant.py homepy/api/main.py tests/auth/test_multitenancy.py
git commit -m "feat: multi-tenancy — RLS on portfolio/watchlist/verdict, tenant middleware"
```

---

### Task 4: WebSocket Collectors + Redis Pub/Sub

**Files:**
- Create: `homepy/realtime/__init__.py`
- Create: `homepy/realtime/base_collector.py`
- Create: `homepy/realtime/event_processor.py`
- Create: `homepy/realtime/collectors/stock_collector.py`
- Create: `homepy/realtime/collectors/listing_collector.py`
- Create: `homepy/realtime/collectors/rate_collector.py`
- Create: `homepy/realtime/collectors/news_collector.py`
- Create: `tests/realtime/__init__.py`
- Create: `tests/realtime/test_collectors.py`
- Create: `tests/realtime/test_event_processor.py`

**Interfaces:**
- Consumes: Redis Sentinel from Plan E, `TimescaleService` from Plan A Task 6, `TypeDBService` from Plan A Task 6
- Produces:
  - `RealTimeEvent(source: str, event_type: str, district_code: str, data: dict, timestamp: datetime)` — dataclass
  - `BaseCollector(redis: Redis, source_name: str)` — abstract base with methods:
    - `async start() -> None` — begins collection loop
    - `async stop() -> None` — graceful shutdown
    - `async publish(event: RealTimeEvent) -> None` — publishes to `events:{source}` Redis channel
  - `StockCollector(BaseCollector)` — WebSocket stub for 증권사 API (키움/한투)
  - `ListingCollector(BaseCollector)` — HTTP polling stub for 네이버 부동산 (5-min interval)
  - `RateCollector(BaseCollector)` — HTTP polling stub for 한국은행 RSS (1-hour interval)
  - `NewsCollector(BaseCollector)` — HTTP polling stub for 정부 보도자료 RSS (30-min interval)
  - `EventProcessor(redis: Redis, timescale_svc, typedb_svc)` with methods:
    - `async start() -> None` — subscribes to all `events:*` channels
    - `async process_event(event: RealTimeEvent) -> None` — fans out to DB writes + signal channel
    - `async stop() -> None`

- [ ] **Step 1: Write failing tests for collectors**

```python
async def test_base_collector_publishes_to_redis(mock_redis):
    collector = StockCollector(mock_redis, "stock_api")
    event = RealTimeEvent(
        source="stock_api", event_type="price_update",
        district_code="11680", data={"price": 950000000},
        timestamp=datetime.now(timezone.utc)
    )
    await collector.publish(event)
    published = mock_redis.published_messages["events:stock_api"]
    assert len(published) == 1
    assert published[0]["district_code"] == "11680"

async def test_listing_collector_polls_at_interval(mock_redis):
    collector = ListingCollector(mock_redis, "naver_listing")
    assert collector.poll_interval_seconds == 300  # 5 minutes

async def test_rate_collector_polls_hourly(mock_redis):
    collector = RateCollector(mock_redis, "bok_rate")
    assert collector.poll_interval_seconds == 3600

async def test_collector_graceful_shutdown(mock_redis):
    collector = StockCollector(mock_redis, "stock_api")
    await collector.start()
    await collector.stop()
    assert collector.running is False
```

- [ ] **Step 2: Write failing tests for EventProcessor**

```python
async def test_event_processor_writes_to_timescale(mock_redis, mock_timescale, mock_typedb):
    processor = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    event = RealTimeEvent(
        source="stock_api", event_type="price_update",
        district_code="11680", data={"price": 950000000},
        timestamp=datetime.now(timezone.utc)
    )
    await processor.process_event(event)
    assert mock_timescale.inserted_count("ts_realtime_events") == 1

async def test_event_processor_publishes_signal(mock_redis, mock_timescale, mock_typedb):
    processor = EventProcessor(mock_redis, mock_timescale, mock_typedb)
    event = RealTimeEvent(
        source="stock_api", event_type="price_update",
        district_code="11680", data={"price": 950000000},
        timestamp=datetime.now(timezone.utc)
    )
    await processor.process_event(event)
    signals = mock_redis.published_messages.get("signals:11680", [])
    assert len(signals) >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/realtime/ -v`
Expected: FAIL

- [ ] **Step 4: Implement `RealTimeEvent` dataclass and `BaseCollector`**

`BaseCollector`: abstract class with `start()`/`stop()` lifecycle, `publish()` serializes `RealTimeEvent` to JSON and calls `redis.publish(f"events:{source_name}", json)`. Includes `poll_interval_seconds` for polling collectors. `start()` runs `_collect_loop()` in an asyncio task; `stop()` cancels the task.

- [ ] **Step 5: Implement 4 collector stubs**

`StockCollector`: `_collect_loop` simulates WebSocket connection to 증권사 API — logs "connecting to stock API" and yields mock events for testing. `ListingCollector`: `poll_interval_seconds = 300`, HTTP GET stub. `RateCollector`: `poll_interval_seconds = 3600`, RSS parse stub. `NewsCollector`: `poll_interval_seconds = 1800`, RSS parse stub. Each stub produces `RealTimeEvent` with the correct `source` and `event_type`.

- [ ] **Step 6: Implement `EventProcessor`**

`start()`: subscribes to `events:*` pattern via Redis Pub/Sub. `process_event`: inserts raw event into `ts_realtime_events` (TimescaleDB), and re-publishes to `signals:{district_code}` channel for WebSocket server consumption. TypeDB snapshot update is async fire-and-forget for non-critical events.

- [ ] **Step 7: Run tests**

Run: `pytest tests/realtime/ -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/realtime/ tests/realtime/
git commit -m "feat: real-time collectors (4 stubs) + Redis Pub/Sub event processor"
```

---

### Task 5: WebSocket Server + Client Push

**Files:**
- Create: `homepy/realtime/ws_server.py`
- Modify: `homepy/api/main.py` (mount WebSocket route)
- Create: `tests/realtime/test_ws_server.py`

**Interfaces:**
- Consumes: `get_current_user` from Task 1 (token validation for WebSocket handshake), Redis Pub/Sub `signals:{district_code}` channel from Task 4
- Produces:
  - `ConnectionManager` with methods:
    - `async connect(ws: WebSocket, district_code: str) -> None`
    - `async disconnect(ws: WebSocket, district_code: str) -> None`
    - `async broadcast(district_code: str, data: dict) -> None`
    - `get_connection_count(district_code: str) -> int`
  - WebSocket endpoint: `GET /ws/signals/{district_code}` — authenticates via query param `token`, subscribes to Redis channel, pushes events to client
  - Backpressure: drops messages for slow consumers, disconnects after 30s of blocked sends

- [ ] **Step 1: Write failing tests**

```python
async def test_ws_connect_and_receive(test_client, analyst_token):
    async with test_client.websocket_connect(
        f"/ws/signals/11680?token={analyst_token}"
    ) as ws:
        # Simulate a Redis publish to signals:11680
        await publish_test_signal("11680", {"price": 950000000})
        data = await asyncio.wait_for(ws.receive_json(), timeout=5)
        assert data["district_code"] == "11680"

async def test_ws_rejects_no_token(test_client):
    with pytest.raises(Exception):
        async with test_client.websocket_connect("/ws/signals/11680") as ws:
            pass

async def test_ws_rejects_expired_token(test_client, expired_token):
    with pytest.raises(Exception):
        async with test_client.websocket_connect(
            f"/ws/signals/11680?token={expired_token}"
        ) as ws:
            pass

async def test_connection_manager_tracks_count(connection_manager):
    mock_ws = MockWebSocket()
    await connection_manager.connect(mock_ws, "11680")
    assert connection_manager.get_connection_count("11680") == 1
    await connection_manager.disconnect(mock_ws, "11680")
    assert connection_manager.get_connection_count("11680") == 0

async def test_slow_consumer_disconnected(connection_manager):
    slow_ws = SlowMockWebSocket(delay=35)  # blocks for 35s
    await connection_manager.connect(slow_ws, "11680")
    await connection_manager.broadcast("11680", {"test": True})
    # After timeout, slow consumer should be removed
    assert connection_manager.get_connection_count("11680") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/realtime/test_ws_server.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ConnectionManager` in `realtime/ws_server.py`**

`_connections: dict[str, set[WebSocket]]` maps district codes to connected clients. `connect`: adds WebSocket to the set. `disconnect`: removes it. `broadcast`: iterates over connections for a district, sends JSON to each. Uses `asyncio.wait_for(ws.send_json(data), timeout=30)` — if send times out, disconnects the slow consumer and logs the event. Thread-safe via asyncio Lock per district.

- [ ] **Step 4: Implement WebSocket endpoint**

```python
@app.websocket("/ws/signals/{district_code}")
async def signal_stream(ws: WebSocket, district_code: str, token: str = Query(...)):
    payload = await jwt_handler.verify_token(token)
    await manager.connect(ws, district_code)
    try:
        async for event in redis_pubsub.listen(f"signals:{district_code}"):
            await manager.broadcast(district_code, event)
    except WebSocketDisconnect:
        await manager.disconnect(ws, district_code)
```

Token is passed as query parameter because WebSocket headers are not reliably settable from browser clients.

- [ ] **Step 5: Mount WebSocket route in `api/main.py`**

Import and register the WebSocket endpoint alongside existing HTTP routers.

- [ ] **Step 6: Run tests**

Run: `pytest tests/realtime/test_ws_server.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/realtime/ws_server.py homepy/api/main.py tests/realtime/test_ws_server.py
git commit -m "feat: WebSocket server — per-district push, backpressure, JWT handshake auth"
```

---

### Task 6: Policy Simulation Engine

**Files:**
- Create: `homepy/simulation/__init__.py`
- Create: `homepy/simulation/policy_simulator.py`
- Create: `homepy/simulation/models.py`
- Modify: `homepy/api/routers/simulation.py` (add policy simulation endpoints)
- Create: `tests/simulation/__init__.py`
- Create: `tests/simulation/test_policy_simulator.py`

**Interfaces:**
- Consumes: `TypeDBService` from Plan A Task 6, `InvestmentScorer` from Plan C Task 1, `ScenarioSimulator` from Plan C Task 2, `TimescaleService` from Plan A Task 6
- Produces:
  - `PolicyChange(policy_type: str, parameters: dict)` — dataclass; `policy_type` is one of `"tax"`, `"regulation"`, `"interest_rate"`, `"supply_shock"`
  - `PolicyImpact(policy_change: PolicyChange, direct_effects: list[str], score_before: float, score_after: float, delta: float, affected_districts: list[str], impact_chain: list[dict])` — dataclass
  - `PolicyBacktest(policy_date: date, policy_name: str, simulated_impact: dict, actual_market_response: dict, accuracy_score: float, missed_factors: list[str])` — dataclass (from spec)
  - `PolicySimulator(typedb_svc, scorer, timescale_svc)` with methods:
    - `async simulate_tax_change(changes: dict) -> PolicyImpact` — e.g., `{"acquisition_tax_rate": 0.04}`
    - `async simulate_regulation(district_code: str, regulation_type: str, action: str) -> PolicyImpact` — action: `"designate"` | `"release"`
    - `async simulate_interest_rate(rate_path: list[float]) -> PolicyImpact` — e.g., `[3.5, 3.25, 3.0]`
    - `async simulate_supply_shock(district_code: str, units: int) -> PolicyImpact` — additional 입주 units
    - `async backtest_policy(policy_name: str, policy_date: date, changes: dict) -> PolicyBacktest`
  - 2 new API endpoints:
    - `POST /api/v1/simulation/policy` → runs policy simulation
    - `POST /api/v1/simulation/policy/backtest` → runs policy backtesting

- [ ] **Step 1: Write failing tests**

```python
async def test_tax_change_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_tax_change({"acquisition_tax_rate": 0.04})
    assert isinstance(impact, PolicyImpact)
    assert impact.policy_change.policy_type == "tax"
    assert impact.score_before != impact.score_after
    assert len(impact.impact_chain) >= 1

async def test_regulation_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_regulation("11680", "speculation_zone", "designate")
    assert impact.policy_change.policy_type == "regulation"
    assert "11680" in impact.affected_districts
    assert impact.delta < 0  # designation should lower scores

async def test_interest_rate_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_interest_rate([3.5, 3.25, 3.0])
    assert impact.policy_change.policy_type == "interest_rate"
    assert impact.delta > 0  # rate cuts should improve scores

async def test_supply_shock_simulation(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    impact = await sim.simulate_supply_shock("11680", units=5000)
    assert impact.policy_change.policy_type == "supply_shock"
    assert impact.delta < 0  # large supply should lower scores

async def test_simulation_does_not_mutate_typedb(mock_typedb, mock_scorer, mock_timescale):
    count_before = mock_typedb.entity_count("tax-rule")
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    await sim.simulate_tax_change({"acquisition_tax_rate": 0.04})
    count_after = mock_typedb.entity_count("tax-rule")
    assert count_before == count_after

async def test_policy_backtest(mock_typedb, mock_scorer, mock_timescale):
    sim = PolicySimulator(mock_typedb, mock_scorer, mock_timescale)
    result = await sim.backtest_policy(
        policy_name="7.10 대책", policy_date=date(2020, 7, 10),
        changes={"speculation_zone": ["강남구", "서초구", "송파구"]}
    )
    assert isinstance(result, PolicyBacktest)
    assert 0.0 <= result.accuracy_score <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/simulation/test_policy_simulator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement dataclasses in `simulation/models.py`**

`PolicyChange`, `PolicyImpact`, `PolicyBacktest` — all frozen dataclasses with fields matching the spec.

- [ ] **Step 4: Implement `PolicySimulator`**

Each `simulate_*` method:
1. Snapshots the current score for affected districts via `InvestmentScorer`
2. Creates a hypothetical modification (does not write to TypeDB — modifies an in-memory overlay or uses a TypeDB read transaction with patched attributes)
3. Re-runs `InvestmentScorer` with the hypothetical state
4. Computes delta and builds the `impact_chain` (list of dictionaries showing 1st→2nd→3rd order effects)
5. Returns `PolicyImpact`

`backtest_policy`: loads historical data at `policy_date`, runs simulation with `changes`, compares `simulated_impact` against actual market data at +3m/+6m/+12m from TimescaleDB. `accuracy_score` = fraction of districts where predicted direction matched actual direction.

- [ ] **Step 5: Add API endpoints to `simulation.py` router**

`POST /api/v1/simulation/policy`: accepts `PolicyChange` as request body, dispatches to the correct `simulate_*` method, returns `PolicyImpact`. `POST /api/v1/simulation/policy/backtest`: accepts policy name + date + changes, returns `PolicyBacktest`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/simulation/test_policy_simulator.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/simulation/ homepy/api/routers/simulation.py tests/simulation/
git commit -m "feat: policy simulation engine — tax/regulation/rate/supply + backtesting"
```

---

### Task 7: Policy Dashboard (Streamlit Page 12) + E2E Integration

**Files:**
- Create: `homepy/app/pages/12_policy_simulation.py`
- Create: `homepy/app/components/impact_chain.py`
- Modify: `homepy/app/components/__init__.py` (export `impact_chain`)
- Create: `tests/test_e2e_multiuser.py`

**Interfaces:**
- Consumes: `PolicySimulator` via API endpoints from Task 6, `ApiClient` from Plan C Task 5, `JWTHandler` from Task 1, `ConnectionManager` from Task 5
- Produces:
  - Streamlit Page 12 (Policy Simulation) with 4 sections:
    1. Simulation input form (select policy type → type-specific parameter form)
    2. Impact summary (score before/after, delta, affected districts table)
    3. Impact chain visualization (Pyvis network graph)
    4. Policy backtest results (historical accuracy table)
  - `impact_chain` component: renders `PolicyImpact.impact_chain` as a Pyvis directed graph (policy → direct effects → indirect effects → score changes)
  - E2E test covering auth → RLS → simulation → WebSocket roundtrip

- [ ] **Step 1: Implement `impact_chain` component**

Takes `impact_chain: list[dict]` from `PolicyImpact`, builds a Pyvis `Network` (directed=True). Nodes: policy change (red), direct effects (orange), indirect effects (yellow), score changes (green/red). Edges: labeled with effect magnitude. Renders as `streamlit.components.v1.html`.

- [ ] **Step 2: Implement Page 12 (Policy Simulation)**

4 sections:
1. `st.selectbox("시뮬레이션 유형", ["세제 변경", "규제 지정/해제", "금리 시나리오", "공급 충격"])` → conditional input form per type. Tax: slider for each tax rate. Regulation: district select + regulation type + designate/release. Interest rate: multi-step rate path input. Supply shock: district + unit count.
2. On submit, calls `POST /api/v1/simulation/policy`, displays `PolicyImpact` as metric cards (score_before, score_after, delta) and affected districts table.
3. Calls `impact_chain` component with the result's `impact_chain`.
4. `st.expander("정책 백테스팅")` — input historical policy name + date, calls backtest endpoint, shows accuracy score and missed factors.

- [ ] **Step 3: Write E2E integration test**

```python
async def test_multiuser_policy_roundtrip():
    """
    1. Create two users (analyst_a, analyst_b) in Keycloak
    2. Analyst_a adds portfolio item for complex C001
    3. Analyst_b adds portfolio item for complex C002
    4. Analyst_a queries portfolio — sees only C001
    5. Analyst_b queries portfolio — sees only C002
    6. Analyst_a runs tax-change simulation → gets PolicyImpact
    7. Analyst_a connects to WebSocket /ws/signals/11680
    8. Publish a test event → Analyst_a receives it
    9. Viewer_c tries to access /api/v1/analysis/* → gets 403
    """
    pass
```

- [ ] **Step 4: Run E2E test**

Run: `pytest tests/test_e2e_multiuser.py -v`
Expected: PASS

- [ ] **Step 5: Verify Page 12 renders**

Run Streamlit, navigate to page 12, test each simulation type with sample inputs, confirm impact chain graph renders.

- [ ] **Step 6: Update project directory structure in spec**

Add `auth/`, `realtime/`, `simulation/` directories and Page 12 to the spec's Section 9 directory tree.

- [ ] **Step 7: Commit**

```bash
git add homepy/app/pages/12_policy_simulation.py homepy/app/components/impact_chain.py tests/test_e2e_multiuser.py
git commit -m "feat: policy simulation dashboard + impact chain visualization + E2E test"
```
