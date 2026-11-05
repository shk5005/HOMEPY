"""Data quality monitor: freshness, distribution drift, anomalies, consistency.

All SQL is placeholder-style (accepted project pattern).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import numpy as np
from scipy.special import kl_div

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService

COMPLEX_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
_SOURCE_RE = re.compile(COMPLEX_ID_PATTERN)

DRIFT_THRESHOLD = 0.1
Z_THRESHOLD = 3.0
HISTOGRAM_BINS = 10
_EPS = 1e-9

# source -> (schedule, expected interval, grace period)
SCHEDULES: dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}
GRACE: dict[str, timedelta] = {
    "daily": timedelta(hours=2),
    "weekly": timedelta(days=1),
    "monthly": timedelta(days=2),
}
SOURCE_SCHEDULE: dict[str, str] = {
    "interest_rate": "daily",
    "real_trade": "daily",
    "listing": "daily",
    "population": "monthly",
    "macro_index": "weekly",
}
# metrics monitored per source for anomalies
SOURCE_METRICS: dict[str, list[str]] = {
    "interest_rate": ["base_rate", "cd_rate"],
    "real_trade": ["avg_price_per_m2"],
    "listing": ["listing_count"],
    "population": ["net_migration"],
    "macro_index": ["cpi_yoy"],
}
# (metric_a, metric_b, expected directional relation) for cross-source checks
CONSISTENCY_PAIRS: list[tuple[str, str]] = [("base_rate", "cd_rate")]


@dataclass
class FreshnessAlert:
    source: str
    last_seen: datetime
    expected_interval: timedelta
    severity: str


@dataclass
class DriftResult:
    source: str
    kl_divergence: float
    drifted: bool
    window_days: int


@dataclass
class AnomalyAlert:
    source: str
    metric: str
    value: float
    z_score: float
    severity: str


@dataclass
class ConsistencyAlert:
    sources: list[str]
    metric: str
    discrepancy: float
    severity: str


def _validate(source: str) -> None:
    if not _SOURCE_RE.match(source):
        raise ValueError(f"invalid source identifier: {source!r}")


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


class DataMonitor:
    def __init__(self, timescale_svc: TimescaleService) -> None:
        self._ts = timescale_svc

    async def check_freshness(self) -> list[FreshnessAlert]:
        rows = await self._ts.execute(
            "SELECT source, MAX(ts) AS last_ts FROM ts_collection_log GROUP BY source"
        )
        now = datetime.now(timezone.utc)
        alerts: list[FreshnessAlert] = []
        for row in rows:
            source = row["source"]
            schedule = SOURCE_SCHEDULE.get(source)
            if schedule is None or row["last_ts"] is None:
                continue
            interval = SCHEDULES[schedule]
            last = _aware(row["last_ts"])
            overdue = now - last - interval - GRACE[schedule]
            if overdue <= timedelta(0):
                continue
            severity = "WARNING" if overdue > 2 * interval else "ADVISORY"
            alerts.append(FreshnessAlert(source, last, interval, severity))
        return alerts

    async def _window(self, source: str, start_days: int, end_days: int) -> np.ndarray:
        rows = await self._ts.execute(
            "SELECT value FROM metric_series WHERE source = $1 "
            "AND ts >= now() - make_interval(days => $2) "
            "AND ts < now() - make_interval(days => $3)",
            source, start_days, end_days,
        )
        return np.array([float(r["value"]) for r in rows], dtype=float)

    async def check_distribution_drift(
        self, source: str, window_days: int = 30
    ) -> DriftResult:
        _validate(source)
        current = await self._window(source, window_days, 0)
        previous = await self._window(source, 2 * window_days, window_days)
        if current.size == 0 or previous.size == 0:
            return DriftResult(source, 0.0, False, window_days)
        lo = float(min(current.min(), previous.min()))
        hi = float(max(current.max(), previous.max()))
        if hi == lo:
            return DriftResult(source, 0.0, False, window_days)
        bins = np.linspace(lo, hi, HISTOGRAM_BINS + 1)
        p = np.histogram(current, bins=bins)[0].astype(float) + _EPS
        q = np.histogram(previous, bins=bins)[0].astype(float) + _EPS
        p /= p.sum()
        q /= q.sum()
        kl = float(np.sum(kl_div(p, q)))
        return DriftResult(source, kl, kl > DRIFT_THRESHOLD, window_days)

    async def check_anomalies(self, source: str) -> list[AnomalyAlert]:
        _validate(source)
        alerts: list[AnomalyAlert] = []
        for metric in SOURCE_METRICS.get(source, [source]):
            rows = await self._ts.execute(
                "SELECT latest_value AS value, AVG(value) AS mean, STDDEV(value) AS std "
                "FROM metric_series WHERE metric = $1 AND ts >= now() - interval '90 days'",
                metric,
            )
            if not rows:
                continue
            row = rows[0]
            std = float(row["std"] or 0.0)
            if std <= 0:
                continue
            z = (float(row["value"]) - float(row["mean"])) / std
            if abs(z) > Z_THRESHOLD:
                alerts.append(AnomalyAlert(
                    source, metric, float(row["value"]), z,
                    "CRITICAL" if abs(z) > 2 * Z_THRESHOLD else "WARNING",
                ))
        return alerts

    async def check_cross_source_consistency(self) -> list[ConsistencyAlert]:
        alerts: list[ConsistencyAlert] = []
        for a, b in CONSISTENCY_PAIRS:
            deltas: dict[str, float] = {}
            for metric in (a, b):
                rows = await self._ts.execute(
                    "SELECT last(value, ts) - first(value, ts) AS trend_delta "
                    "FROM metric_series WHERE metric = $1 "
                    "AND ts >= now() - interval '90 days'",
                    metric,
                )
                if rows and rows[0].get("trend_delta") is not None:
                    deltas[metric] = float(rows[0]["trend_delta"])
            if len(deltas) < 2:
                continue
            da, db = deltas[a], deltas[b]
            if da * db < 0:  # opposite directions
                alerts.append(ConsistencyAlert([a, b], f"{a}_vs_{b}", abs(da - db), "WARNING"))
        return alerts
