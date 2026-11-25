"""HA component status models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class HAStatus:
    component: str
    role: str
    healthy: bool
    last_heartbeat: datetime
    replica_lag_seconds: float | None = None
