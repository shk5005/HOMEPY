"""Patroni REST API health checker."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from homepy.ha.models import HAStatus


class PatroniHealthChecker:
    def __init__(self, patroni_url: str, timeout: float = 5.0) -> None:
        self.patroni_url = patroni_url.rstrip("/")
        self._timeout = timeout

    async def _get_json(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self.patroni_url}{path}")
            # Patroni returns 503 for unhealthy-but-informative responses
            if resp.status_code >= 500 and not resp.content:
                resp.raise_for_status()
            return resp.json()

    async def check(self) -> HAStatus:
        now = datetime.now(timezone.utc)
        try:
            data = await self._get_json("/patroni")
        except (httpx.HTTPError, ValueError):
            return HAStatus(
                component="timescaledb", role="unknown", healthy=False,
                last_heartbeat=now, replica_lag_seconds=None,
            )
        role = str(data.get("role", "unknown"))
        if role == "master":
            role = "primary"
        healthy = data.get("state") == "running"
        lag: float | None = None
        if role != "primary":
            lag = await self._safe_lag()
        return HAStatus(
            component="timescaledb", role=role, healthy=healthy,
            last_heartbeat=now, replica_lag_seconds=lag,
        )

    async def _safe_lag(self) -> float | None:
        try:
            return await self.get_replication_lag()
        except (httpx.HTTPError, ValueError):
            return None

    async def get_replication_lag(self) -> float:
        """Max replication lag across cluster replicas, in seconds.

        Patroni's /cluster reports lag in bytes; when a replica exposes
        `replay_lag` (seconds) it is used, otherwise bytes are mapped to 0.0
        when zero and to a conservative estimate (1s per MiB) otherwise.
        """
        data = await self._get_json("/cluster")
        worst = 0.0
        for member in data.get("members", []):
            if member.get("role") in ("leader", "master", "primary"):
                continue
            if "replay_lag" in member and member["replay_lag"] is not None:
                worst = max(worst, float(member["replay_lag"]))
                continue
            lag_bytes = member.get("lag", 0)
            if isinstance(lag_bytes, (int, float)) and lag_bytes > 0:
                worst = max(worst, float(lag_bytes) / (1024 * 1024))
        return worst
