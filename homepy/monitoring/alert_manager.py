"""4-level alert classification, routing, deduplication."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import replace
from typing import Any

from homepy.monitoring.models import ALERT_LEVELS, AlertEvent, AnomalyResult

logger = logging.getLogger(__name__)

ALERT_ROUTING: dict[str, list[str]] = {
    "WATCH": [],
    "ADVISORY": ["slack"],
    "WARNING": ["slack", "kakao"],
    "CRITICAL": ["slack", "kakao", "email"],
}

Z_WARNING_THRESHOLD = 4.0
CRITICAL_SAME_DISTRICT_COUNT = 5


def _is_warning_level(a: AnomalyResult) -> bool:
    return a.severity == "critical" or (
        a.z_score is not None and abs(a.z_score) > Z_WARNING_THRESHOLD
    )


class AlertClassifier:
    def classify(self, anomalies: list[AnomalyResult], active_signals: list[str]) -> str:
        warning_count = sum(1 for a in anomalies if _is_warning_level(a))

        per_district: dict[str, int] = defaultdict(int)
        for a in anomalies:
            per_district[a.district_code] += 1
        if warning_count >= 2 or any(
            n >= CRITICAL_SAME_DISTRICT_COUNT for n in per_district.values()
        ):
            return "CRITICAL"
        if warning_count >= 1:
            return "WARNING"
        if len(anomalies) >= 2 or active_signals:
            return "ADVISORY"
        return "WATCH"


class AlertManager:
    def __init__(
        self,
        channels: dict[str, Any],
        routing: dict[str, list[str]] | None = None,
    ):
        self.channels = channels
        self.routing = routing if routing is not None else ALERT_ROUTING

    async def send_alert(self, event: AlertEvent) -> AlertEvent:
        names = [n for n in self.routing.get(event.level, []) if n in self.channels]

        async def _one(name: str) -> bool:
            try:
                return bool(await self.channels[name].send(event.title, event.description))
            except Exception as exc:
                logger.warning("Channel %s raised: %s", name, exc)
                return False

        results = await asyncio.gather(*(_one(n) for n in names))
        event.channels_sent = [n for n, ok in zip(names, results) if ok]
        event.channels_failed = [n for n, ok in zip(names, results) if not ok]
        return event

    async def deduplicate(
        self, events: list[AlertEvent], window_hours: float = 1.0
    ) -> list[AlertEvent]:
        window = window_hours * 3600.0
        groups: dict[tuple[str | None, str], list[list[AlertEvent]]] = defaultdict(list)
        for ev in sorted(events, key=lambda e: e.created_at):
            clusters = groups[(ev.district_code, ev.level)]
            if clusters and (ev.created_at - clusters[-1][0].created_at).total_seconds() <= window:
                clusters[-1].append(ev)
            else:
                clusters.append([ev])

        merged: list[AlertEvent] = []
        for clusters in groups.values():
            for cluster in clusters:
                if len(cluster) == 1:
                    merged.append(cluster[0])
                    continue
                first = cluster[0]
                ids: list[str] = []
                for e in cluster:
                    for aid in e.anomaly_ids:
                        if aid not in ids:
                            ids.append(aid)
                merged.append(
                    replace(
                        first,
                        anomaly_ids=ids,
                        deduplicated=True,
                        batch_count=sum(e.batch_count for e in cluster),
                    )
                )
        merged.sort(key=lambda e: e.created_at)
        return merged


__all__ = ["ALERT_LEVELS", "ALERT_ROUTING", "AlertClassifier", "AlertManager"]
