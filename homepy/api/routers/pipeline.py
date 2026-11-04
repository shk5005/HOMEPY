from __future__ import annotations

from fastapi import APIRouter, Depends

from homepy.api.dependencies import get_timescale
from homepy.api.models.schemas import PipelineStatusResponse

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
