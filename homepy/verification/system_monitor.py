"""System performance monitor backed by ``ts_system_metrics``."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService

QUERY_TIME_METRIC = "query_duration_ms"
SUMMARY_PERIOD_HOURS = 24
MAX_QUERY_CHARS = 500


@dataclass
class SlowQuery:
    component: str
    query: str
    duration_ms: float
    ts: datetime


@dataclass
class ComponentStats:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    count: int
    period_hours: int


@dataclass
class PerformanceSummary:
    components: dict[str, ComponentStats] = field(default_factory=dict)


class SystemMonitor:
    def __init__(self, timescale_svc: TimescaleService) -> None:
        self._ts = timescale_svc

    async def record_query_time(self, component: str, query: str, duration_ms: float) -> None:
        await self._ts.execute(
            "INSERT INTO ts_system_metrics (ts, component, metric_name, metric_value, metadata) "
            "VALUES (now(), $1, $2, $3, $4::jsonb)",
            component, QUERY_TIME_METRIC, float(duration_ms),
            json.dumps({"query": query[:MAX_QUERY_CHARS]}),
        )

    async def get_performance_summary(self) -> PerformanceSummary:
        rows = await self._ts.execute(
            "SELECT component, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY metric_value) AS p50_ms, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY metric_value) AS p95_ms, "
            "percentile_cont(0.99) WITHIN GROUP (ORDER BY metric_value) AS p99_ms, "
            "COUNT(*) AS count FROM ts_system_metrics "
            "WHERE metric_name = $1 AND ts >= now() - make_interval(hours => $2) "
            "GROUP BY component",
            QUERY_TIME_METRIC, SUMMARY_PERIOD_HOURS,
        )
        return PerformanceSummary({
            r["component"]: ComponentStats(
                float(r["p50_ms"]), float(r["p95_ms"]), float(r["p99_ms"]),
                int(r["count"]), SUMMARY_PERIOD_HOURS,
            )
            for r in rows
        })

    async def detect_slow_queries(self, threshold_ms: float = 1000) -> list[SlowQuery]:
        rows = await self._ts.execute(
            "SELECT ts, component, metric_value, metadata FROM ts_system_metrics "
            "WHERE metric_name = 'query_duration_ms' AND metric_value > $1 "
            "ORDER BY metric_value DESC",
            threshold_ms,
        )
        out: list[SlowQuery] = []
        for r in rows:
            meta = r.get("metadata") or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            out.append(SlowQuery(r["component"], meta.get("query", ""),
                                 float(r["metric_value"]), r["ts"]))
        return out
