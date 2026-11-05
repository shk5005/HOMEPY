"""Anomaly detection and alert event models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

ANOMALY_ALGORITHMS = ("zscore", "isolation_forest", "cusum", "bollinger")
ANOMALY_SEVERITIES = ("low", "medium", "high", "critical")
ALERT_LEVELS = ("WATCH", "ADVISORY", "WARNING", "CRITICAL")


@dataclass
class AnomalyResult:
    anomaly_id: str
    detected_at: datetime
    district_code: str
    metric_name: str
    algorithm: str
    current_value: float
    baseline_value: float
    z_score: float | None
    severity: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertEvent:
    alert_id: str
    created_at: datetime
    level: str
    title: str
    description: str
    district_code: str | None
    anomaly_ids: list[str] = field(default_factory=list)
    channels_sent: list[str] = field(default_factory=list)
    channels_failed: list[str] = field(default_factory=list)
    deduplicated: bool = False
    batch_count: int = 1
