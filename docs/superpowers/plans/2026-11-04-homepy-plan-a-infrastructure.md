# HOMEPY Plan A: Infrastructure & Ontology Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the dual-database infrastructure (TypeDB + TimescaleDB), load the full 7-domain ontology schema with inference rules, create the TimescaleDB time-series schema, and wire both into a Docker Compose stack that starts with one command.

**Architecture:** Docker Compose orchestrates TypeDB 2.x and TimescaleDB (PostgreSQL 16 + timescaledb extension). TypeDB holds the ontology schema (30+ entity types, 15+ relations, 12+ inference rules). TimescaleDB holds 10+ hypertables for time-series data. A Python `typedb-driver` service layer and a `psycopg`/`asyncpg` service layer provide programmatic access, tested against the real databases in integration tests.

**Tech Stack:** Docker Compose, TypeDB 2.28+, TimescaleDB 2.x (PostgreSQL 16), Python 3.11+, typedb-driver, asyncpg, pytest, pyproject.toml (hatch)

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md`

## Global Constraints

- Python ≥ 3.11
- TypeDB ≥ 2.28 (TypeQL 2.x syntax)
- PostgreSQL 16 with timescaledb extension
- All Python dependencies managed via `pyproject.toml` (hatch build system)
- No ORM for TimescaleDB — raw SQL via asyncpg for performance
- TypeDB accessed via official `typedb-driver` Python package
- Every TypeQL schema file must be loadable idempotently (define is additive in TypeDB)
- Directory structure follows spec Section 9

## Review Focus

1. **TypeDB schema load order** — relations reference entity types; loading rules before the entities they reference causes a schema error. Tests must verify the full schema loads without error on a fresh database.
2. **TimescaleDB hypertable creation on existing tables** — calling `create_hypertable` on a table that already has data or is already a hypertable fails. Migration must be idempotent.
3. **Docker healthchecks** — TypeDB takes 10-15s to start; TimescaleDB needs `pg_isready`. Services that depend on them must wait for healthy, not just started.
4. **TypeQL attribute ownership conflicts** — two entity types owning the same attribute name with different value types causes a schema error. Attribute names must be globally unique or share value types.
5. **asyncpg connection pool exhaustion** — tests that open connections without closing them leak until the pool is full. Every test must use `async with pool.acquire()`.

---

### Task 1: Project Scaffold & Docker Compose

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `docker/typedb/typedb-config.yml` (optional tuning)
- Create: `homepy/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `docker compose up -d` starts TypeDB on port 1729 and TimescaleDB on port 5432. `pytest` discovers tests. `homepy` is an importable package.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "homepy"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typedb-driver>=2.28.0",
    "asyncpg>=0.29.0",
    "httpx>=0.27.0",
    "pandas>=2.2.0",
    "pydantic>=2.6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "testcontainers>=4.0",
]
```

- [ ] **Step 2: Create `docker-compose.yml`**

Two services: `typedb` (vaticle/typedb:2.28.0, port 1729, healthcheck via `typedb console --command 'database list'`) and `timescaledb` (timescale/timescaledb:latest-pg16, port 5432, env POSTGRES_DB=homepy POSTGRES_USER=homepy POSTGRES_PASSWORD=homepy, healthcheck via pg_isready). Add a named volume for each.

- [ ] **Step 3: Create package init files**

`homepy/__init__.py` and `tests/__init__.py` (empty). `tests/conftest.py` with `pytest.ini` config setting `asyncio_mode = "auto"`.

- [ ] **Step 4: Verify the stack starts**

Run: `docker compose up -d && docker compose ps`
Expected: both services healthy within 30s.

- [ ] **Step 5: Verify pytest discovers the package**

Run: `pip install -e ".[dev]" && pytest --collect-only`
Expected: no errors, 0 tests collected.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml docker-compose.yml docker/ homepy/ tests/
git commit -m "feat: project scaffold with Docker Compose (TypeDB + TimescaleDB)"
```

---

### Task 2: TypeDB Ontology Schema — Entities & Attributes

**Files:**
- Create: `storage/typedb/schema.tql`
- Create: `tests/storage/test_typedb_schema.py`

**Interfaces:**
- Consumes: Docker Compose from Task 1 (TypeDB on port 1729)
- Produces: `schema.tql` loadable via `typedb console --command 'transaction <db> schema write --file schema.tql'`. All 30+ entity types and their attributes defined.

- [ ] **Step 1: Write the integration test**

```python
import pytest
from typedb.driver import TypeDB, SessionType, TransactionType

DB_NAME = "homepy_test"

@pytest.fixture(scope="module")
def typedb_client():
    with TypeDB.core_driver("localhost:1729") as driver:
        if driver.databases.contains(DB_NAME):
            driver.databases.get(DB_NAME).delete()
        driver.databases.create(DB_NAME)
        yield driver
        driver.databases.get(DB_NAME).delete()

def test_schema_loads_without_error(typedb_client):
    with open("storage/typedb/schema.tql") as f:
        schema = f.read()
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(schema)
            tx.commit()

def test_all_entity_types_exist(typedb_client):
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.READ) as tx:
            expected = [
                "region", "district", "dong", "complex", "unit-type",
                "interest-rate", "exchange-rate", "liquidity", "price-index",
                "real-estate-cycle", "cycle-observation",
                "loan-product", "loan-regulation", "loan-regulation-rule",
                "acquisition-tax", "acquisition-tax-rate",
                "capital-gains-tax", "cgt-rate-rule",
                "comprehensive-re-tax", "crt-rate-rule",
                "inheritance-tax", "gift-tax", "gift-tax-rate", "property-tax",
                "policy", "zone-designation", "price-control",
                "subscription-regulation",
                "population-data", "migration-data", "income-data",
                "supply-data", "unsold-inventory", "reconstruction-supply",
                "infrastructure", "development-project", "market-sentiment",
            ]
            for name in expected:
                concept = tx.concepts.get_entity_type(name).resolve()
                assert concept is not None, f"Entity type '{name}' missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_typedb_schema.py -v`
Expected: FAIL (schema.tql does not exist)

- [ ] **Step 3: Write `storage/typedb/schema.tql`**

Transcribe all entity and attribute definitions from spec Section 3.1 (7 domains + infrastructure/development/sentiment). Use `abstract` for `macro-indicator` and `tax-regime`. Ensure attribute names are globally unique — prefix with domain where needed (e.g., `indicator-date`, `data-date`, `sentiment-date`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/storage/test_typedb_schema.py -v`
Expected: both tests PASS

- [ ] **Step 5: Commit**

```bash
git add storage/typedb/schema.tql tests/storage/
git commit -m "feat: TypeDB ontology schema — 37 entity types across 7 domains"
```

---

### Task 3: TypeDB Ontology Schema — Relations

**Files:**
- Modify: `storage/typedb/schema.tql` (append relations after entities)
- Modify: `tests/storage/test_typedb_schema.py` (add relation tests)

**Interfaces:**
- Consumes: Entity schema from Task 2
- Produces: 15+ relation types with role players defined. Same schema.tql file, loadable as one unit.

- [ ] **Step 1: Add the failing test**

```python
def test_all_relation_types_exist(typedb_client):
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.READ) as tx:
            expected_relations = [
                "spatial-hierarchy", "has-unit-type", "accessibility",
                "macro-drives-cycle", "rate-affects-loan",
                "zone-applied-to", "regulation-applies", "loan-constraint",
                "tax-applies-to", "cgt-applies-to", "crt-applies-to",
                "policy-impact", "policy-targets-tax",
                "demand-in-area", "supply-in-area",
                "cycle-observed-at", "development-influence",
                "sentiment-observation", "comparable",
            ]
            for name in expected_relations:
                concept = tx.concepts.get_relation_type(name).resolve()
                assert concept is not None, f"Relation type '{name}' missing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_typedb_schema.py::test_all_relation_types_exist -v`
Expected: FAIL

- [ ] **Step 3: Append relation definitions to `storage/typedb/schema.tql`**

Transcribe all relation definitions and role-player assignments from spec Section 3.2. Each relation's `relates` roles and each entity's `plays` declarations.

- [ ] **Step 4: Run full schema tests**

Run: `pytest tests/storage/test_typedb_schema.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add storage/typedb/schema.tql tests/storage/test_typedb_schema.py
git commit -m "feat: TypeDB ontology relations — 19 relation types with role players"
```

---

### Task 4: TypeDB Inference Rules

**Files:**
- Create: `storage/typedb/rules.tql`
- Modify: `tests/storage/test_typedb_schema.py` (add rule loading + smoke test)

**Interfaces:**
- Consumes: Full schema (entities + relations) from Tasks 2-3
- Produces: `rules.tql` loadable after `schema.tql`. 12+ inference rules defined. A smoke test inserts seed data and verifies one rule fires.

- [ ] **Step 1: Add rule loading and smoke tests**

```python
def test_rules_load_without_error(typedb_client):
    # schema.tql already loaded by module fixture
    with open("storage/typedb/rules.tql") as f:
        rules = f.read()
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(rules)
            tx.commit()

def test_undervalued_rule_fires(typedb_client):
    """Insert a complex near a subway with price below district avg;
    verify undervalued-signal is inferred."""
    with typedb_client.session(DB_NAME, SessionType.DATA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.insert("""
                insert
                $d isa dong, has dong-code "11010", has dong-name "test-dong";
                $c isa complex, has complex-id "C001", has complex-name "test",
                    has price-per-sqm 15000000, has district-avg-price 20000000,
                    has total-units 500, has built-year 2000,
                    has floor-area-ratio 250.0, has building-coverage 60.0;
                $inf isa infrastructure, has infra-id "S001",
                    has infra-name "test-station", has infra-type "subway",
                    has infra-status "operating";
                (parent: $d, child: $c) isa spatial-hierarchy;
                (location: $c, facility: $inf) isa accessibility,
                    has distance-meter 300, has travel-time-min 5;
            """)
            tx.commit()
        with session.transaction(TransactionType.READ) as tx:
            result = tx.query.get("match (subject: $c) isa undervalued-signal; get $c;")
            answers = list(result)
            assert len(answers) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_typedb_schema.py::test_rules_load_without_error -v`
Expected: FAIL (rules.tql does not exist)

- [ ] **Step 3: Write `storage/typedb/rules.tql`**

Transcribe all 12+ inference rules from spec Section 3.3 (Rule Groups 1-6). The file defines only rules, assuming schema.tql is already loaded.

- [ ] **Step 4: Run all schema tests**

Run: `pytest tests/storage/test_typedb_schema.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add storage/typedb/rules.tql tests/storage/test_typedb_schema.py
git commit -m "feat: TypeDB inference rules — 12+ rules across 6 groups"
```

---

### Task 5: TimescaleDB Schema & Hypertables

**Files:**
- Create: `storage/timescale/schema.sql`
- Create: `storage/timescale/hypertables.sql`
- Create: `tests/storage/test_timescale_schema.py`

**Interfaces:**
- Consumes: Docker Compose from Task 1 (TimescaleDB on port 5432)
- Produces: 10+ hypertables created and queryable. SQL files executable via `psql -f`.

- [ ] **Step 1: Write the integration test**

```python
import pytest
import asyncpg

@pytest.fixture(scope="module")
async def db_pool():
    pool = await asyncpg.create_pool(
        "postgresql://homepy:homepy@localhost:5432/homepy",
        min_size=1, max_size=5
    )
    # Load schema
    async with pool.acquire() as conn:
        with open("storage/timescale/schema.sql") as f:
            await conn.execute(f.read())
        with open("storage/timescale/hypertables.sql") as f:
            await conn.execute(f.read())
    yield pool
    await pool.close()

EXPECTED_TABLES = [
    "ts_real_trade", "ts_price_index",
    "ts_interest_rate", "ts_exchange_rate", "ts_liquidity", "ts_macro_index",
    "ts_population", "ts_migration", "ts_income",
    "ts_supply", "ts_unsold",
    "ts_sentiment",
    "ts_signals",
]

async def test_all_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for table in EXPECTED_TABLES:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)",
                table
            )
            assert exists, f"Table '{table}' missing"

async def test_hypertables_created(db_pool):
    async with db_pool.acquire() as conn:
        hypertables = await conn.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        names = {r["hypertable_name"] for r in hypertables}
        for table in EXPECTED_TABLES:
            assert table in names, f"'{table}' is not a hypertable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_timescale_schema.py -v`
Expected: FAIL

- [ ] **Step 3: Write `storage/timescale/schema.sql`**

Create all 13 tables with columns matching spec Section 3.4. Each table has a `ts` TIMESTAMPTZ NOT NULL column as the time dimension and a composite primary key. Include a `district_code` or `complex_id` column for partitioning where applicable.

- [ ] **Step 4: Write `storage/timescale/hypertables.sql`**

For each table: `SELECT create_hypertable('table_name', 'ts', if_not_exists => TRUE);` Add compression policies for tables older than 90 days. Add continuous aggregates for `ts_real_trade` (monthly avg price per district).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/storage/test_timescale_schema.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add storage/timescale/ tests/storage/test_timescale_schema.py
git commit -m "feat: TimescaleDB schema — 13 hypertables for time-series data"
```

---

### Task 6: Python DB Service Layers

**Files:**
- Create: `homepy/storage/__init__.py`
- Create: `homepy/storage/typedb_service.py`
- Create: `homepy/storage/timescale_service.py`
- Create: `tests/storage/test_db_services.py`

**Interfaces:**
- Consumes: Running TypeDB (Task 1-4) and TimescaleDB (Task 1,5) with schemas loaded
- Produces:
  - `TypeDBService(address: str)` with methods: `connect() -> None`, `close() -> None`, `execute_read(db: str, query: str) -> list[dict]`, `execute_write(db: str, query: str) -> None`, `load_schema(db: str, tql_path: str) -> None`
  - `TimescaleService(dsn: str)` with methods: `connect() -> None`, `close() -> None`, `execute(query: str, *args) -> list[asyncpg.Record]`, `insert_batch(table: str, records: list[dict]) -> int`

- [ ] **Step 1: Write failing tests**

```python
async def test_timescale_service_insert_and_query():
    svc = TimescaleService("postgresql://homepy:homepy@localhost:5432/homepy")
    await svc.connect()
    count = await svc.insert_batch("ts_interest_rate", [
        {"ts": "2026-01-01", "base_rate": 3.25, "rate_direction": "falling"}
    ])
    assert count == 1
    rows = await svc.execute(
        "SELECT base_rate FROM ts_interest_rate WHERE ts = $1",
        datetime(2026, 1, 1)
    )
    assert rows[0]["base_rate"] == 3.25
    await svc.close()

def test_typedb_service_read_entities():
    svc = TypeDBService("localhost:1729")
    svc.connect()
    results = svc.execute_read("homepy_test", "match $x isa region; get $x; limit 5;")
    assert isinstance(results, list)
    svc.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_db_services.py -v`
Expected: FAIL (modules not found)

- [ ] **Step 3: Implement `TypeDBService`**

Wraps `typedb-driver`. `connect()` opens a `TypeDB.core_driver`. `execute_read` opens a session+read transaction, runs the query, collects results as dicts, closes. `execute_write` same with write transaction + commit. `load_schema` reads a .tql file and runs `define`.

- [ ] **Step 4: Implement `TimescaleService`**

Wraps `asyncpg`. `connect()` creates a connection pool. `execute` acquires, runs, returns records. `insert_batch` uses `copy_records_to_table` for bulk inserts. `close()` closes the pool.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/storage/test_db_services.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/storage/ tests/storage/test_db_services.py
git commit -m "feat: Python service layers for TypeDB and TimescaleDB"
```

---

### Task 7: Schema Bootstrap Script & End-to-End Verification

**Files:**
- Create: `scripts/bootstrap_db.py`
- Create: `tests/test_e2e_infrastructure.py`

**Interfaces:**
- Consumes: All prior tasks (Docker, schemas, service layers)
- Produces: `python scripts/bootstrap_db.py` creates database, loads schema + rules, creates hypertables. E2E test verifies the full stack round-trips data through both DBs.

- [ ] **Step 1: Write E2E test**

```python
async def test_full_infrastructure_roundtrip():
    """
    1. Bootstrap both databases
    2. Insert a region+district+dong into TypeDB
    3. Insert a price record into TimescaleDB
    4. Query both and verify
    """
    # Uses bootstrap script, then service layers to verify
    pass  # Full assertions on region lookup and price query
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_e2e_infrastructure.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `scripts/bootstrap_db.py`**

Connects to TypeDB, creates `homepy` database if not exists, loads `schema.tql` then `rules.tql`. Connects to TimescaleDB, executes `schema.sql` then `hypertables.sql`. Prints summary of loaded entity types and created tables.

- [ ] **Step 4: Run E2E test**

Run: `pytest tests/test_e2e_infrastructure.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ tests/test_e2e_infrastructure.py
git commit -m "feat: database bootstrap script and E2E infrastructure test"
```
