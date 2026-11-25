"""Neo4j -> TimescaleDB: persist rule-inferred signals into ts_signals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

DEFAULT_DB = "homepy"
INFER_CONFIDENCE = 1.0


@dataclass(frozen=True)
class SignalSpec:
    signal_type: str
    rel_type: str
    target_label: str
    id_prop: str
    rule_name: str


SIGNALS: tuple[SignalSpec, ...] = (
    SignalSpec("undervalued-signal", "UNDERVALUED_SIGNAL", "Complex", "complexId",
              "undervalued-signal"),
    SignalSpec("strong-buy-signal", "STRONG_BUY_SIGNAL", "Complex", "complexId",
              "strong-buy-signal"),
    SignalSpec("gap-risk-signal", "GAP_RISK_SIGNAL", "District", "districtCode",
              "gap-risk-signal"),
    SignalSpec("loan-blocked-signal", "LOAN_BLOCKED_SIGNAL", "District", "districtCode",
              "loan-blocked-signal"),
    SignalSpec("tax-lockin-signal", "TAX_LOCKIN_SIGNAL", "District", "districtCode",
              "tax-lockin-signal"),
)


def build_query(s: SignalSpec) -> str:
    return (
        f"MATCH (n:{s.target_label})-[r:{s.rel_type}]->(n) "
        f"RETURN n.{s.id_prop} AS id"
    )


async def sync_signals_to_timescale(neo4j_svc, timescale_svc, db: str = DEFAULT_DB,
                                    signals: tuple[SignalSpec, ...] = SIGNALS,
                                    now: datetime | None = None) -> int:
    """Query materialized signals and insert them into ts_signals; returns rows inserted."""
    ts = now or datetime.now(timezone.utc)
    rows: dict[tuple[str, str], dict] = {}
    for s in signals:
        for res in neo4j_svc.execute_read(db, build_query(s)):
            target_id = res.get("id")
            if target_id is None:
                continue
            target_id = str(target_id)
            rows[(s.signal_type, target_id)] = {
                "ts": ts,
                "signal_type": s.signal_type,
                "target_id": target_id,
                "target_type": s.target_label.lower(),
                "district_code": target_id if s.target_label == "District" else None,
                "confidence": INFER_CONFIDENCE,
                "rule_name": s.rule_name,
            }
    if not rows:
        return 0
    return await timescale_svc.insert_batch("ts_signals", list(rows.values()))
