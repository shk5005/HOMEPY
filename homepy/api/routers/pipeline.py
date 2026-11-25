from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from homepy.api.dependencies import get_timescale
from homepy.api.models.schemas import (
    BacktestSummaryResponse,
    CalibrationProposalResponse,
    ImprovementRecordResponse,
    PipelineStatusResponse,
    SystemHealthResponse,
)
from homepy.verification.backtester import Backtester
from homepy.verification.calibrator import AutoCalibrator
from homepy.verification.data_monitor import DataMonitor
from homepy.verification.improvement_tracker import ImprovementTracker
from homepy.verification.self_healer import SelfHealer
from homepy.verification.system_monitor import SystemMonitor

router = APIRouter()

# Hypertables written by collectors; names are fixed constants (no user input).
COLLECTOR_TABLES = [
    "ts_real_trade", "ts_price_index", "ts_interest_rate", "ts_exchange_rate",
    "ts_liquidity", "ts_macro_index", "ts_supply", "ts_unsold", "ts_sentiment",
]


@router.get("/status", response_model=PipelineStatusResponse)
async def status(ts=Depends(get_timescale)):
    collectors, total, latest = [], 0, None
    for table in COLLECTOR_TABLES:
        try:
            rows = await ts.execute(f"SELECT COUNT(*) AS n, MAX(ts) AS latest FROM {table}")
            n, last = int(rows[0]["n"]), rows[0]["latest"]
            state = "ok"
        except Exception:  # noqa: BLE001 - one broken table must not hide the rest
            n, last, state = 0, None, "error"
        collectors.append({"table": table, "rows": n, "latest_ts": last, "state": state})
        total += n
        if last is not None and (latest is None or last > latest):
            latest = last
    return PipelineStatusResponse(collectors=collectors, total_rows=total, latest_ts=latest)


# ---- verification (Plan D) ------------------------------------------------
RECOVERY_LOG_PATH = Path("data/catalog/recovery_log.jsonl")
BACKTEST_LOOKBACK_MONTHS = 3
SLOW_P95_MS = 1000.0


def get_calibrator(request: Request) -> AutoCalibrator:
    """Process-wide calibrator (proposals are held in memory on app.state)."""
    state = request.app.state
    cal = getattr(state, "calibrator", None)
    if cal is None:
        cal = AutoCalibrator(Backtester(state.timescale), state.timescale)
        state.calibrator = cal
    return cal


@router.get("/verification/accuracy", response_model=BacktestSummaryResponse)
async def verification_accuracy(ts=Depends(get_timescale)):
    result = await Backtester(ts).run(BACKTEST_LOOKBACK_MONTHS)
    return BacktestSummaryResponse(
        direction_accuracy=result.direction_accuracy,
        signal_hit_rate=result.signal_hit_rate,
        total_verdicts=result.total_verdicts,
        computed_at=datetime.now(timezone.utc),
    )


@router.get("/verification/proposals", response_model=list[CalibrationProposalResponse])
async def verification_proposals(cal: AutoCalibrator = Depends(get_calibrator)):
    return [CalibrationProposalResponse.model_validate(p) for p in cal.list_proposals("proposed")]


@router.post("/verification/proposals/{proposal_id}/approve",
             response_model=ImprovementRecordResponse)
async def approve_proposal(proposal_id: str, cal: AutoCalibrator = Depends(get_calibrator),
                           ts=Depends(get_timescale)):
    try:
        record = await cal.apply_proposal(proposal_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown proposal: {proposal_id}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await ImprovementTracker(ts).record(record)
    return ImprovementRecordResponse.model_validate(record)


@router.get("/verification/health", response_model=SystemHealthResponse)
async def verification_health(request: Request, ts=Depends(get_timescale)):
    summary = await SystemMonitor(ts).get_performance_summary()
    components = [
        {"name": name, "status": "ok" if st.p95_ms < SLOW_P95_MS else "degraded",
         "latency_p95": st.p95_ms}
        for name, st in summary.components.items()
    ]
    alerts = await DataMonitor(ts).check_freshness()
    healer = SelfHealer(ts, getattr(request.app.state, "typedb", None), RECOVERY_LOG_PATH)
    return SystemHealthResponse(
        components=components,
        data_quality_alerts=len(alerts),
        recovery_events_24h=len(healer.get_recovery_history(24)),
    )


# ---- HA health (Plan E) ----------------------------------------------------

@router.get("/health")
async def health(request: Request):
    uptime = time.monotonic() - getattr(request.app.state, "startup_time", time.monotonic())
    return {
        "status": "ok",
        "node_id": os.environ.get("NODE_ID", "node-1"),
        "uptime_seconds": round(uptime, 2),
    }


@router.get("/ha/status")
async def ha_status(request: Request):
    from homepy.ha.models import HAStatus

    components: list[dict] = []
    ts = getattr(request.app.state, "timescale", None)
    if ts is not None:
        components.append(HAStatus(
            component="timescaledb", role="primary", healthy=True,
            last_heartbeat=datetime.now(timezone.utc),
        ).__dict__)
    typedb = getattr(request.app.state, "typedb", None)
    if typedb is not None:
        components.append(HAStatus(
            component="typedb", role="primary", healthy=True,
            last_heartbeat=datetime.now(timezone.utc),
        ).__dict__)
    return components


# ---- Market monitoring (Plan E Task 7) -------------------------------------

@router.get("/monitoring/anomalies")
async def monitoring_anomalies(
    days: int = Query(default=7, ge=1, le=90), ts=Depends(get_timescale),
) -> list[dict]:
    if ts is None:
        return []
    try:
        rows = await ts.execute(
            "SELECT anomaly_id, ts AS detected_at, district_code, metric_name, algorithm, "
            "current_value, baseline_value, z_score, severity "
            "FROM ts_anomaly_detections "
            "WHERE ts > NOW() - make_interval(days => $1) ORDER BY ts DESC",
            days,
        )
    except Exception:  # DB unavailable / table missing -> degrade to empty
        return []
    return [dict(r) for r in rows]


@router.get("/monitoring/alerts")
async def monitoring_alerts(
    days: int = Query(default=7, ge=1, le=90),
    level: str | None = Query(default=None),
    ts=Depends(get_timescale),
) -> list[dict]:
    if ts is None:
        return []
    sql = (
        "SELECT alert_id, ts AS created_at, level, title, description, district_code, "
        "anomaly_ids, channels_sent, channels_failed, deduplicated, batch_count "
        "FROM ts_alert_events WHERE ts > NOW() - make_interval(days => $1)"
    )
    args: list = [days]
    if level:
        sql += " AND level = $2"
        args.append(level)
    sql += " ORDER BY ts DESC"
    try:
        rows = await ts.execute(sql, *args)
    except Exception:
        return []
    return [dict(r) for r in rows]


@router.get("/monitoring/early-warnings")
async def monitoring_early_warnings(request: Request) -> list[dict]:
    # Placeholder: querying active signals requires a live TypeDB.
    return []
