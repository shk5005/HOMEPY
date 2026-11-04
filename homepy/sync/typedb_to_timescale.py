"""TypeDB -> TimescaleDB: persist rule-inferred signals into ts_signals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_DB = "homepy"
INFER_CONFIDENCE = 1.0  # rule-derived facts carry no probability


@dataclass(frozen=True)
class SignalSpec:
    signal_type: str   # relation type, also the ts_signals.signal_type
    role: str
    target_type: str   # entity type playing the role
    id_attr: str       # attribute identifying the entity
    rule_name: str


SIGNALS: tuple[SignalSpec, ...] = (
    SignalSpec("undervalued-signal", "subject", "complex", "complex-id", "undervalued-signal"),
    SignalSpec("strong-buy-signal", "buy-candidate", "complex", "complex-id", "strong-buy-signal"),
    SignalSpec("gap-risk-signal", "risky-area", "district", "district-code", "gap-risk-signal"),
    SignalSpec("loan-blocked-signal", "blocked-area", "district", "district-code",
               "loan-blocked-signal"),
    SignalSpec("tax-lockin-signal", "locked-area", "district", "district-code", "tax-lockin-signal"),
)


def build_query(s: SignalSpec) -> str:
    return (f"match ({s.role}: $t) isa {s.signal_type}; $t isa {s.target_type}, "
            f"has {s.id_attr} $id; get $id;")


async def sync_signals_to_timescale(typedb_svc, timescale_svc, db: str = DEFAULT_DB,
                                    signals: tuple[SignalSpec, ...] = SIGNALS,
                                    now: datetime | None = None) -> int:
    """Query inferred signals and insert them into ts_signals; returns rows inserted."""
    ts = now or datetime.now(timezone.utc)
    rows: dict[tuple[str, str], dict] = {}  # dedupe on (signal_type, target_id)
    for s in signals:
        for res in typedb_svc.execute_read(db, build_query(s), infer=True):
            target_id = res.get("id")
            if target_id is None:
                continue
            target_id = str(target_id)
            rows[(s.signal_type, target_id)] = {
                "ts": ts,
                "signal_type": s.signal_type,
                "target_id": target_id,
                "target_type": s.target_type,
                "district_code": target_id if s.target_type == "district" else None,
                "confidence": INFER_CONFIDENCE,
                "rule_name": s.rule_name,
            }
    if not rows:
        return 0
    return await timescale_svc.insert_batch("ts_signals", list(rows.values()))
