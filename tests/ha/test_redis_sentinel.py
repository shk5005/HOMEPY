from __future__ import annotations

import pytest

from homepy.ha.redis_sentinel import RedisSentinelManager

pytestmark = pytest.mark.skip(reason="requires live Redis Sentinel")


async def test_redis_sentinel_discovers_master(redis_sentinel_cluster):
    mgr = RedisSentinelManager(redis_sentinel_cluster.sentinels, "homepy-master")
    host, port = await mgr.get_master()
    assert host is not None
    assert port > 0


async def test_redis_sentinel_health(redis_sentinel_cluster):
    mgr = RedisSentinelManager(redis_sentinel_cluster.sentinels, "homepy-master")
    status = await mgr.check_health()
    assert status.healthy is True
    assert status.role == "master"
