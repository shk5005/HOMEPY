from __future__ import annotations

import asyncio

import pytest

from homepy.ha.patroni_config import PatroniHealthChecker

pytestmark = pytest.mark.skip(reason="requires live Patroni cluster")


async def test_patroni_primary_accepts_writes(patroni_cluster):
    async with patroni_cluster.primary_pool.acquire() as conn:
        await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 100.0)")
        row = await conn.fetchrow("SELECT val FROM ts_prices ORDER BY ts DESC LIMIT 1")
        assert row["val"] == 100.0


async def test_replica_replicates_writes(patroni_cluster):
    async with patroni_cluster.primary_pool.acquire() as conn:
        await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 200.0)")
    await asyncio.sleep(1)
    async with patroni_cluster.replica_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT val FROM ts_prices ORDER BY ts DESC LIMIT 1")
        assert row["val"] == 200.0


async def test_replica_rejects_writes(patroni_cluster):
    import asyncpg

    async with patroni_cluster.replica_pool.acquire() as conn:
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 300.0)")


async def test_replication_lag_within_threshold(patroni_cluster):
    checker = PatroniHealthChecker(patroni_cluster.patroni_url)
    assert await checker.get_replication_lag() < 5.0
