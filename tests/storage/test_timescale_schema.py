import re

import asyncpg
import pytest
import pytest_asyncio

DSN = "postgresql://homepy:homepy@localhost:5432/homepy"

EXPECTED_TABLES = [
    "ts_real_trade", "ts_price_index",
    "ts_interest_rate", "ts_exchange_rate", "ts_liquidity", "ts_macro_index",
    "ts_population", "ts_migration", "ts_income",
    "ts_supply", "ts_unsold",
    "ts_sentiment",
    "ts_signals",
]


def _statements(sql: str):
    """Split into statements, run one by one (continuous aggregates cannot
    be created inside a transaction block)."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in re.split(r";[ \t]*\n", sql + "\n") if s.strip()]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        for path in ("storage/timescale/schema.sql", "storage/timescale/hypertables.sql"):
            with open(path) as f:
                for stmt in _statements(f.read()):
                    await conn.execute(stmt)
    yield pool
    await pool.close()


@pytest.mark.asyncio(loop_scope="module")
async def test_all_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for table in EXPECTED_TABLES:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)",
                table,
            )
            assert exists, f"Table '{table}' missing"


@pytest.mark.asyncio(loop_scope="module")
async def test_hypertables_created(db_pool):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT hypertable_name FROM timescaledb_information.hypertables")
        names = {r["hypertable_name"] for r in rows}
        for table in EXPECTED_TABLES:
            assert table in names, f"'{table}' is not a hypertable"


@pytest.mark.asyncio(loop_scope="module")
async def test_ts_column_is_timestamptz_not_null(db_pool):
    async with db_pool.acquire() as conn:
        for table in EXPECTED_TABLES:
            row = await conn.fetchrow(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name=$1 AND column_name='ts'", table)
            assert row and row["data_type"] == "timestamp with time zone"
            assert row["is_nullable"] == "NO"


@pytest.mark.asyncio(loop_scope="module")
async def test_continuous_aggregate_exists(db_pool):
    async with db_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM timescaledb_information.continuous_aggregates "
            "WHERE view_name='ts_real_trade_monthly'")
        assert n == 1
