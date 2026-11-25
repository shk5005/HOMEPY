"""Redis Sentinel manager."""
from __future__ import annotations

from datetime import datetime, timezone

from homepy.ha.models import HAStatus


class RedisSentinelManager:
    def __init__(self, sentinel_hosts: list[tuple[str, int]], master_name: str) -> None:
        self.sentinel_hosts = sentinel_hosts
        self.master_name = master_name

    def _sentinel(self):
        from redis.asyncio import Sentinel

        return Sentinel(self.sentinel_hosts, socket_timeout=2.0)

    async def get_master(self) -> tuple[str, int]:
        host, port = await self._sentinel().discover_master(self.master_name)
        return host, int(port)

    async def check_health(self) -> HAStatus:
        now = datetime.now(timezone.utc)
        try:
            sentinel = self._sentinel()
            master = sentinel.master_for(self.master_name, socket_timeout=2.0)
            healthy = bool(await master.ping())
            await master.aclose()
        except Exception:
            return HAStatus(component="redis", role="unknown", healthy=False,
                            last_heartbeat=now)
        return HAStatus(component="redis", role="master", healthy=healthy,
                        last_heartbeat=now)

    async def failover(self) -> tuple[str, int]:
        sentinel = self._sentinel()
        old = await self.get_master()
        await sentinel.sentinels[0].execute_command(
            "SENTINEL", "FAILOVER", self.master_name
        )
        import asyncio

        for _ in range(30):
            await asyncio.sleep(1)
            new = await self.get_master()
            if new != old:
                return new
        return await self.get_master()
