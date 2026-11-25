from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from homepy.api.dependencies import get_timescale
from homepy.api.models.schemas import CycleStatusResponse, MacroSummaryResponse

router = APIRouter()
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _val(row, key):
    try:
        v = row.get(key)
    except AttributeError:
        return None
    return float(v) if v is not None and not hasattr(v, "isoformat") else v


@router.get("/macro/summary", response_model=MacroSummaryResponse)
async def macro_summary(ts=Depends(get_timescale)):
    rates = await ts.execute(
        "SELECT ts, base_rate, mortgage_rate FROM ts_interest_rate ORDER BY ts DESC LIMIT 1")
    fx = await ts.execute("SELECT usd_krw FROM ts_exchange_rate ORDER BY ts DESC LIMIT 1")
    liq = await ts.execute(
        "SELECT m2_change_yoy_pct FROM ts_liquidity ORDER BY ts DESC LIMIT 1")
    macro = await ts.execute(
        "SELECT cpi_change_yoy_pct, gdp_growth, unemployment FROM ts_macro_index "
        "ORDER BY ts DESC LIMIT 1")
    out: dict = {}
    for rows, keys in ((rates, ["ts", "base_rate", "mortgage_rate"]), (fx, ["usd_krw"]),
                       (liq, ["m2_change_yoy_pct"]),
                       (macro, ["cpi_change_yoy_pct", "gdp_growth", "unemployment"])):
        if rows:
            for k in keys:
                out["as_of" if k == "ts" else k] = _val(rows[0], k)
    return MacroSummaryResponse(**out)


@router.get("/cycle/{district_code}", response_model=CycleStatusResponse)
async def cycle(district_code: str, ts=Depends(get_timescale)):
    if not _CODE_RE.fullmatch(district_code):
        raise HTTPException(status_code=422, detail="invalid district_code")
    rows = await ts.execute(
        "SELECT phase, price_change_3m, volume_change_3m, unsold_ratio FROM "
        "market_cycle_phase WHERE district_code = $1 ORDER BY time DESC LIMIT 1",
        district_code)
    if not rows:
        return CycleStatusResponse(district_code=district_code)
    row = rows[0]
    return CycleStatusResponse(
        district_code=district_code, phase=row.get("phase"),
        indicators={k: _val(row, k) for k in ("price_change_3m", "volume_change_3m", "unsold_ratio")})
