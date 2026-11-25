"""Self-healing engine: retry policies, cooldown, escalation and a JSONL recovery log."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from homepy.verification.models import RecoveryEvent

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService
    from homepy.storage.typedb_service import TypeDBService

logger = logging.getLogger(__name__)

RetryFn = Callable[[str], Awaitable[bool]]
SleepFn = Callable[[float], Awaitable[None]]


@dataclass
class RecoveryPolicy:
    failure_type: str
    max_retries: int
    backoff_base_seconds: float
    cooldown_seconds: float
    escalate_after: int


DEFAULT_POLICIES: dict[str, RecoveryPolicy] = {
    "api_error": RecoveryPolicy("api_error", 3, 2.0, 300.0, 3),
    "db_disconnect": RecoveryPolicy("db_disconnect", 5, 1.0, 60.0, 5),
    # Escalate immediately, no automatic retries.
    "quality_gate_fail": RecoveryPolicy("quality_gate_fail", 0, 0.0, 0.0, 0),
    # One retry with a reduced batch size.
    "inference_timeout": RecoveryPolicy("inference_timeout", 1, 1.0, 120.0, 1),
    # Action is archival rather than retry.
    "disk_space": RecoveryPolicy("disk_space", 0, 0.0, 3600.0, 1),
}

_AUTO_ACTIONS = {
    "inference_timeout": "retry_reduced_batch",
    "disk_space": "archive",
}


class SelfHealer:
    def __init__(
        self,
        timescale_svc: TimescaleService,
        typedb_svc: TypeDBService,
        recovery_log_path: Path,
        policies: dict[str, RecoveryPolicy] | None = None,
        retry_fn: RetryFn | None = None,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self._timescale = timescale_svc
        self._typedb = typedb_svc
        self._log_path = Path(recovery_log_path)
        self._policies = policies or DEFAULT_POLICIES
        self._retry_fn = retry_fn or self._default_retry
        self._sleep = sleep_fn
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_recovery: dict[str, float] = {}

    async def handle_failure(
        self, failure_type: str, component: str, error: Exception
    ) -> RecoveryEvent:
        async with self._locks.setdefault(component, asyncio.Lock()):
            started = time.monotonic()
            policy = self._policies.get(failure_type)
            if policy is None:
                return self._record(
                    failure_type, component, "escalate", False, True, started
                )

            last = self._last_recovery.get(component)
            if last is not None and started - last < policy.cooldown_seconds:
                return self._record(
                    failure_type, component, "cooldown_active", False, False, started
                )

            logger.warning("Failure %s on %s: %r", failure_type, component, error)
            action = _AUTO_ACTIONS.get(failure_type, "retry")
            success = False

            if failure_type == "disk_space":
                try:
                    await self.archive_old_data()
                    success = True
                except OSError:
                    logger.exception("Archive failed")
            else:
                for attempt in range(policy.max_retries):
                    await self._sleep(policy.backoff_base_seconds * (2**attempt))
                    if await self._safe_retry(component):
                        success = True
                        break

            escalated = not success
            self._last_recovery[component] = time.monotonic()
            return self._record(
                failure_type, component, action, success, escalated, started
            )

    async def reconnect_db(self, db_type: str) -> bool:
        """Placeholder reconnect probe."""
        if db_type == "timescale":
            try:
                await self._timescale.execute("SELECT 1")
            except (ConnectionError, OSError):
                return False
            return True
        if db_type == "typedb":
            return self._typedb is not None
        return False

    async def archive_old_data(self, days_threshold: int = 90) -> int:
        """Placeholder archival; returns bytes freed."""
        return 0

    def get_recovery_history(self, hours: int = 24) -> list[RecoveryEvent]:
        if not self._log_path.exists():
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        events: list[RecoveryEvent] = []
        with self._log_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    raw["timestamp"] = datetime.fromisoformat(raw["timestamp"])
                    event = RecoveryEvent(**raw)
                except (ValueError, KeyError, TypeError):
                    logger.warning("Skipping malformed recovery log line")
                    continue
                if event.timestamp >= cutoff:
                    events.append(event)
        return events

    async def _default_retry(self, component: str) -> bool:
        if component in ("timescale", "typedb"):
            return await self.reconnect_db(component)
        return True  # placeholder: component-specific retry wired in later

    async def _safe_retry(self, component: str) -> bool:
        try:
            return await self._retry_fn(component)
        except (ConnectionError, TimeoutError, OSError):
            return False

    def _record(
        self,
        failure_type: str,
        component: str,
        action: str,
        success: bool,
        escalated: bool,
        started: float,
    ) -> RecoveryEvent:
        event = RecoveryEvent(
            event_id=uuid.uuid4().hex,
            timestamp=datetime.now(timezone.utc),
            failure_type=failure_type,
            component=component,
            auto_action=action,
            success=success,
            human_escalated=escalated,
            resolution_time_seconds=time.monotonic() - started,
        )
        self._append(event)
        return event

    def _append(self, event: RecoveryEvent) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(event)
        data["timestamp"] = event.timestamp.isoformat()
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data) + "\n")
