"""Improvement tracker: records, lists and rolls back system improvements."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from homepy.verification.models import ImprovementRecord

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService

KNOWN_CATEGORIES = ("calibration", "bugfix", "feature", "data_source", "performance")
TREND_WINDOW_DAYS = 30

_INSERT_SQL = (
    "INSERT INTO ts_calibration_log (record_id, ts, category, component, before_state, "
    "after_state, trigger, evidence, impact_metrics, approved_by, rollback_possible) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
)
_SELECT_SINCE_SQL = "SELECT * FROM ts_calibration_log WHERE ts >= $1 ORDER BY ts DESC"
_SELECT_ONE_SQL = "SELECT * FROM ts_calibration_log WHERE record_id = $1"
_COUNT_SQL = "SELECT category, COUNT(*) AS n FROM ts_calibration_log GROUP BY category"


@dataclass
class ImprovementStats:
    by_category: dict[str, int] = field(default_factory=dict)
    total: int = 0
    trend: str = "stable"  # improving | stable | declining


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = json.loads(value) if value else {}
        return loaded if isinstance(loaded, dict) else {}
    return dict(value)


def _row_to_record(row: dict[str, Any]) -> ImprovementRecord:
    impact = row.get("impact_metrics")
    return ImprovementRecord(
        record_id=row["record_id"],
        timestamp=row["ts"],
        category=row["category"],
        component=row["component"],
        before_state=_as_dict(row.get("before_state")),
        after_state=_as_dict(row.get("after_state")),
        trigger=row.get("trigger") or "",
        evidence=_as_dict(row.get("evidence")),
        impact_metrics=_as_dict(impact) if impact is not None else None,
        approved_by=row.get("approved_by") or "",
        rollback_possible=bool(row.get("rollback_possible", True)),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


class ImprovementTracker:
    def __init__(self, timescale_svc: TimescaleService) -> None:
        self._db = timescale_svc

    async def record(self, record: ImprovementRecord) -> str:
        rid = record.record_id or uuid.uuid4().hex
        await self._db.execute(
            _INSERT_SQL, rid, record.timestamp, record.category, record.component,
            json.dumps(record.before_state), json.dumps(record.after_state),
            record.trigger, json.dumps(record.evidence),
            json.dumps(record.impact_metrics) if record.impact_metrics is not None else None,
            record.approved_by, record.rollback_possible,
        )
        return rid

    async def list_recent(self, days: int = 30) -> list[ImprovementRecord]:
        since = _now() - timedelta(days=days)
        rows = await self._db.execute(_SELECT_SINCE_SQL, since)
        return [_row_to_record(r) for r in rows]

    async def get_improvement_stats(self) -> ImprovementStats:
        rows = await self._db.execute(_COUNT_SQL)
        by_category = {c: 0 for c in KNOWN_CATEGORIES}
        for r in rows:
            by_category[r["category"]] = by_category.get(r["category"], 0) + int(r["n"])
        total = sum(by_category.values())

        # Trend: records in the last window vs. the window before it.
        records = await self.list_recent(days=2 * TREND_WINDOW_DAYS)
        cutoff = _now() - timedelta(days=TREND_WINDOW_DAYS)
        recent = sum(1 for r in records if _aware(r.timestamp) >= cutoff)
        older = len(records) - recent
        trend = "improving" if recent > older else "declining" if recent < older else "stable"
        return ImprovementStats(by_category=by_category, total=total, trend=trend)

    async def rollback(self, record_id: str) -> ImprovementRecord:
        rows = await self._db.execute(_SELECT_ONE_SQL, record_id)
        if not rows:
            raise KeyError(f"improvement record not found: {record_id}")
        original = _row_to_record(rows[0])
        if not original.rollback_possible:
            raise ValueError(f"record {record_id} is not rollback-capable")
        reverse = replace(
            original,
            record_id=uuid.uuid4().hex,
            timestamp=_now(),
            before_state=original.after_state,
            after_state=original.before_state,
            trigger=f"rollback:{record_id}",
            evidence={"rolled_back_record": record_id},
            impact_metrics=None,
            rollback_possible=False,
        )
        reverse.record_id = await self.record(reverse)
        return reverse
