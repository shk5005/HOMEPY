"""ML feature engineering: 5 relational (TypeDB) + 5 time-series (TimescaleDB).

All time-series queries are point-in-time: every one filters ``ts <= $as_of``.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import date, datetime, time, timezone
from typing import Any

import numpy as np

from homepy.ml.models import MLFeatureSet

TYPEDB_DB = "homepy"
_ID_RE = re.compile(r"[A-Za-z0-9_\-]{1,40}")

RELATIONAL_FEATURES = (
    "adjacent_complex_count", "development_upside_count", "regulation_intensity",
    "effective_tax_rate", "cycle_phase_encoded",
)
TIMESERIES_FEATURES = (
    "price_ma_ratio", "volume_change_rate", "interest_rate_cumulative",
    "jeonse_ratio_trend", "search_zscore",
)
FEATURE_NAMES = RELATIONAL_FEATURES + TIMESERIES_FEATURES

CYCLE_PHASE_ENCODING = {"recovery": 1.0, "expansion": 2.0, "peak": 3.0, "contraction": 4.0}

# Fallback (lo, hi) bounds used when no rolling history is supplied.
DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "adjacent_complex_count": (0.0, 30.0),
    "development_upside_count": (0.0, 10.0),
    "regulation_intensity": (0.0, 1.0),
    "effective_tax_rate": (0.0, 0.15),
    "cycle_phase_encoded": (1.0, 4.0),
    "price_ma_ratio": (0.9, 1.1),
    "volume_change_rate": (-0.5, 0.5),
    "interest_rate_cumulative": (-1.0, 1.0),
    "jeonse_ratio_trend": (-0.1, 0.1),
    "search_zscore": (-2.0, 2.0),
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _val(row: Any, key: str) -> Any:
    """Read a key from a dict / asyncpg.Record / TypeDB-style {'v': {'value': x}} row."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(v, dict) and "value" in v:
        v = v["value"]
    return v


def _check_id(complex_id: str) -> str:
    if not isinstance(complex_id, str) or not _ID_RE.fullmatch(complex_id):
        raise ValueError(f"invalid complex_id: {complex_id!r}")
    return complex_id


class RelationalFeatureExtractor:
    def __init__(self, typedb_svc: Any) -> None:
        self.typedb = typedb_svc

    async def _tql(self, query: str) -> list[dict]:
        # TypeDBService is synchronous.
        return await asyncio.to_thread(self.typedb.execute_read, TYPEDB_DB, query)

    async def extract(self, complex_id: str) -> dict[str, float]:
        cid = _check_id(complex_id)
        head = f'match $c isa complex, has complex_id "{cid}"; '

        adj = await self._tql(
            f"# feature:adjacent_count\n{head}"
            "(location: $c, facility: $o) isa accessibility, has distance-meter $d; "
            "$d <= 500.0; get $o; count;"
        )
        dev = await self._tql(
            f"# feature:development_count\n{head}"
            "(beneficiary: $c, project: $p) isa development-influence; get $p; count;"
        )
        reg = await self._tql(
            f"# feature:regulation_weight\n{head}"
            "(designation: $z, target-district: $c) isa zone-applied-to; "
            "$z has regulation-weight $w; get $w;"
        )
        tax = await self._tql(
            f"# feature:effective_tax\n{head}"
            "(tax-rule: $t, taxed-area: $c) isa tax-applies-to, has effective-rate-pct $r; get $r;"
        )
        cyc = await self._tql(
            f"# feature:cycle_phase\n{head}"
            "(observation: $o, observed-district: $c) isa cycle-observed-at; "
            "$o has local-cycle-phase $p; get $p;"
        )

        weights = [_to_float(_val(r, "w")) for r in reg if _val(r, "w") is not None]
        rates = [_to_float(_val(r, "r")) for r in tax if _val(r, "r") is not None]
        phase = str(_val(cyc[0], "p") or "").lower() if cyc else ""
        return {
            "adjacent_complex_count": _to_float(_val(adj[0], "count")) if adj else 0.0,
            "development_upside_count": _to_float(_val(dev[0], "count")) if dev else 0.0,
            "regulation_intensity": float(np.mean(weights)) if weights else 0.0,
            # effective-rate-pct is stored in percent; feature is a fraction.
            "effective_tax_rate": float(np.mean(rates)) / 100.0 if rates else 0.0,
            "cycle_phase_encoded": CYCLE_PHASE_ENCODING.get(phase, 0.0),
        }


class TimeSeriesFeatureExtractor:
    def __init__(self, timescale_svc: Any) -> None:
        self.ts = timescale_svc

    async def extract(self, complex_id: str, as_of: date) -> dict[str, float]:
        cid = _check_id(complex_id)
        as_of_dt = datetime.combine(as_of, time.max, tzinfo=timezone.utc)

        # 1. price_ma_ratio: 3M MA / 12M MA of monthly average price.
        rows = await self.ts.execute(
            "SELECT date_trunc('month', ts) AS month, AVG(price_krw)::float AS avg_price "
            "FROM ts_real_trade WHERE complex_id = $1 AND ts <= $2 "
            "AND ts > $2 - INTERVAL '12 months' GROUP BY 1 ORDER BY 1 DESC",
            cid, as_of_dt)
        prices = [_to_float(_val(r, "avg_price")) for r in rows]
        ma12 = float(np.mean(prices)) if prices else 0.0
        ma3 = float(np.mean(prices[:3])) if prices else 0.0
        price_ma_ratio = ma3 / ma12 if ma12 > 0 else 1.0

        # 2. volume_change_rate: (cur month - prev month) / prev month.
        rows = await self.ts.execute(
            "SELECT date_trunc('month', ts) AS month, COUNT(*)::float AS volume "
            "FROM ts_real_trade WHERE complex_id = $1 AND ts <= $2 "
            "AND ts > $2 - INTERVAL '2 months' GROUP BY 1 ORDER BY 1 DESC",
            cid, as_of_dt)
        vols = [_to_float(_val(r, "volume")) for r in rows]
        volume_change = (vols[0] - vols[1]) / vols[1] if len(vols) >= 2 and vols[1] > 0 else 0.0

        # 3. interest_rate_cumulative: sum of base-rate changes over 6 months.
        rows = await self.ts.execute(
            "SELECT ts, base_rate::float AS base_rate FROM ts_interest_rate "
            "WHERE ts <= $1 AND ts > $1 - INTERVAL '6 months' ORDER BY ts ASC",
            as_of_dt)
        rates = [_to_float(_val(r, "base_rate")) for r in rows]
        rate_cum = float(np.sum(np.diff(rates))) if len(rates) >= 2 else 0.0

        # 4. jeonse_ratio_trend: slope of linear regression over 6 months.
        rows = await self.ts.execute(
            "SELECT ts, AVG(jeonse_ratio)::float AS jeonse_ratio FROM ts_sentiment "
            "WHERE district_code = (SELECT district_code FROM ts_real_trade "
            "WHERE complex_id = $1 AND ts <= $2 ORDER BY ts DESC LIMIT 1) "
            "AND ts <= $2 AND ts > $2 - INTERVAL '6 months' GROUP BY ts ORDER BY ts ASC",
            cid, as_of_dt)
        ratios = [_to_float(_val(r, "jeonse_ratio")) for r in rows]
        jeonse_trend = (
            float(np.polyfit(np.arange(len(ratios)), ratios, 1)[0]) if len(ratios) >= 2 else 0.0
        )

        # 5. search_zscore: (current - 90d mean) / 90d std.
        rows = await self.ts.execute(
            "SELECT ts, AVG(search_trend)::float AS search_trend FROM ts_sentiment "
            "WHERE district_code = (SELECT district_code FROM ts_real_trade "
            "WHERE complex_id = $1 AND ts <= $2 ORDER BY ts DESC LIMIT 1) "
            "AND ts <= $2 AND ts > $2 - INTERVAL '90 days' GROUP BY ts ORDER BY ts DESC",
            cid, as_of_dt)
        trends = [_to_float(_val(r, "search_trend")) for r in rows]
        std = float(np.std(trends)) if len(trends) >= 2 else 0.0
        zscore = (trends[0] - float(np.mean(trends))) / std if std > 0 else 0.0

        return {
            "price_ma_ratio": float(price_ma_ratio),
            "volume_change_rate": float(volume_change),
            "interest_rate_cumulative": rate_cum,
            "jeonse_ratio_trend": jeonse_trend,
            "search_zscore": float(zscore),
        }


class FeatureCombiner:
    """Min-max normalize with rolling 5th/95th percentile bounds, then concatenate.

    ``history`` maps feature name -> trailing 36-month values. Where it is missing
    or too short, ``DEFAULT_BOUNDS`` are used. Missing/NaN values are filled with
    the history median (or the bounds midpoint when there is no history).
    """

    MIN_HISTORY = 6

    def __init__(self, history: dict[str, list[float]] | None = None) -> None:
        self.history = history or {}

    def _bounds(self, name: str) -> tuple[float, float]:
        h = np.array([x for x in self.history.get(name, []) if x is not None and math.isfinite(x)])
        if len(h) >= self.MIN_HISTORY:
            lo, hi = float(np.percentile(h, 5)), float(np.percentile(h, 95))
            if hi > lo:
                return lo, hi
        return DEFAULT_BOUNDS[name]

    def _fill(self, name: str, lo: float, hi: float) -> float:
        h = [x for x in self.history.get(name, []) if x is not None and math.isfinite(x)]
        return float(np.median(h)) if h else (lo + hi) / 2.0

    def combine(
        self, relational: dict[str, float], timeseries: dict[str, float],
        complex_id: str = "", feature_date: date | None = None,
    ) -> MLFeatureSet:
        merged = {**relational, **timeseries}
        out = []
        for name in FEATURE_NAMES:
            lo, hi = self._bounds(name)
            v = merged.get(name)
            v = float(v) if v is not None and math.isfinite(_to_float(v, float("nan"))) else self._fill(name, lo, hi)
            out.append(min(1.0, max(0.0, (v - lo) / (hi - lo))))
        return MLFeatureSet(
            complex_id=complex_id,
            feature_date=feature_date or date.today(),
            relational_features=dict(relational),
            timeseries_features=dict(timeseries),
            combined=np.array(out, dtype=float),
        )
