"""InvestmentScorer: 14-factor weighted scoring engine.

Each factor is normalized to 0-100 where HIGHER ALWAYS MEANS BETTER FOR AN
INVESTOR. "Inverse" factors (unsold_risk, regulation_impact, tax_burden, rising
interest rates) are flipped during normalization.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

TYPEDB_DB = "homepy"

FACTOR_WEIGHTS: dict[str, float] = {
    "valuation_gap": 0.10,
    "price_momentum": 0.08,
    "jeonse_ratio_trend": 0.07,
    "interest_rate_cycle": 0.08,
    "liquidity_trend": 0.07,
    "supply_demand_gap": 0.10,
    "unsold_risk": 0.05,
    "migration_momentum": 0.05,
    "transport_access": 0.08,
    "development_upside": 0.07,
    "regulation_impact": 0.05,
    "tax_burden": 0.05,
    "cycle_position": 0.05,
    # sentiment_divergence 0.05 + fear_greed_position 0.03 + search_trend_signal 0.02
    "sentiment_composite": 0.10,
}

# (lo, hi, invert) normalization ranges, shared with the simulator.
FACTOR_RANGES: dict[str, tuple[float, float, bool]] = {
    "valuation_gap": (-30, 30, False),
    "price_momentum": (-10, 15, False),
    "jeonse_ratio_trend": (-10, 10, False),
    "interest_rate_cycle": (-100, 100, True),
    "liquidity_trend": (-50, 50, False),
    "supply_demand_gap": (-50, 50, False),
    "unsold_risk": (0, 10, True),
    "migration_momentum": (-1, 1, False),
    "transport_access": (300, 1500, True),
    "development_upside": (0, 3, False),
    "regulation_impact": (0, 6, True),
    "tax_burden": (0, 15, True),
}

GRADE_BOUNDARIES: list[tuple[float, str]] = [(80, "A"), (65, "B"), (50, "C"), (35, "D")]

NEUTRAL = 50.0

CYCLE_PHASE_SCORES: dict[str, float] = {
    "recovery": 85.0,
    "expansion": 70.0,
    "peak": 35.0,
    "slowdown": 25.0,
    "contraction": 10.0,
    "trough": 55.0,
}


@dataclass
class FactorScore:
    name: str
    raw_value: float
    normalized: float
    weight: float
    weighted_score: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class InvestmentScore:
    complex_id: str
    total_score: float
    grade: str
    factors: list[FactorScore]
    computed_at: datetime


_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_id(complex_id: str) -> str:
    """Reject IDs that could alter a TypeQL query when interpolated."""
    if not isinstance(complex_id, str) or not _ID_RE.fullmatch(complex_id):
        raise ValueError(f"invalid complex_id: {complex_id!r}")
    return complex_id


def minmax(value: float, lo: float, hi: float, invert: bool = False) -> float:
    """Min-max normalize to 0-100, clamped. ``invert`` flips direction."""
    if hi == lo:
        return NEUTRAL
    x = (value - lo) / (hi - lo)
    x = min(1.0, max(0.0, x))
    if invert:
        x = 1.0 - x
    return x * 100.0


def grade_for(score: float) -> str:
    for bound, grade in GRADE_BOUNDARIES:
        if score >= bound:
            return grade
    return "F"


def _num(row: Any, key: str) -> float | None:
    """Read a numeric field from a dict/Record; None when absent or non-numeric."""
    if row is None:
        return None
    try:
        v = row.get(key)
    except AttributeError:
        try:
            v = row[key]
        except (KeyError, IndexError, TypeError):
            return None
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _make(name: str, raw: float, normalized: float, evidence: list[str]) -> FactorScore:
    w = FACTOR_WEIGHTS[name]
    normalized = min(100.0, max(0.0, normalized))
    return FactorScore(name, raw, normalized, w, normalized * w, evidence)


def _no_data(name: str, what: str) -> FactorScore:
    return _make(name, 0.0, NEUTRAL, [f"No data available for {what}; neutral score {NEUTRAL:.0f} applied"])


class InvestmentScorer:
    def __init__(self, typedb_svc: Any, timescale_svc: Any) -> None:
        self.typedb = typedb_svc
        self.ts = timescale_svc

    # ---- data access helpers -------------------------------------------
    async def _tql(self, query: str) -> list[dict]:
        # TypeDBService is synchronous; keep the event loop free.
        return await asyncio.to_thread(self.typedb.execute_read, TYPEDB_DB, query)

    async def _sql(self, query: str, *args: Any) -> list[Any]:
        return await self.ts.execute(query, *args)

    # ---- public API ------------------------------------------------------
    async def score(self, complex_id: str) -> InvestmentScore:
        complex_id = _validate_id(complex_id)
        calcs: list[Callable[[str], Awaitable[FactorScore]]] = [
            getattr(self, f"_calc_{name}") for name in FACTOR_WEIGHTS
        ]
        factors = list(await asyncio.gather(*(c(complex_id) for c in calcs)))
        total = round(sum(f.weighted_score for f in factors), 4)
        total = min(100.0, max(0.0, total))
        return InvestmentScore(
            complex_id=complex_id,
            total_score=total,
            grade=grade_for(total),
            factors=factors,
            computed_at=datetime.now(timezone.utc),
        )

    # ---- TypeDB-backed factors -------------------------------------------
    async def _calc_valuation_gap(self, cid: str) -> FactorScore:
        rows = await self._tql(
            f'# factor:valuation_gap\nmatch $c isa complex, has complex_id "{cid}"; '
            "get $price_per_sqm, $district_avg_price;"
        )
        price = _num(rows[0], "price_per_sqm") if rows else None
        avg = _num(rows[0], "district_avg_price") if rows else None
        if not price or not avg:
            return _no_data("valuation_gap", "price vs district average")
        gap = (avg - price) / avg * 100.0  # positive = undervalued = good
        return _make(
            "valuation_gap", gap, minmax(gap, -30, 30),
            [
                f"Price {price:,.0f}/sqm vs district average {avg:,.0f}/sqm",
                f"Valuation gap {gap:+.1f}% ({'undervalued' if gap > 0 else 'overvalued'})",
            ],
        )

    async def _calc_transport_access(self, cid: str) -> FactorScore:
        rows = await self._tql(
            f'# factor:transport_access\nmatch $c isa complex, has complex_id "{cid}"; '
            "get $nearest_station_m;"
        )
        d = _num(rows[0], "nearest_station_m") if rows else None
        if d is None:
            return _no_data("transport_access", "station distance")
        lines = _num(rows[0], "line_count")
        ev = [f"Nearest station {d:.0f} m away"]
        if lines is not None:
            ev.append(f"{lines:.0f} subway line(s) within reach")
        return _make("transport_access", d, minmax(d, 300, 1500, invert=True), ev)

    async def _calc_development_upside(self, cid: str) -> FactorScore:
        rows = await self._tql(
            f'# factor:development_upside\nmatch $c isa complex, has complex_id "{cid}"; '
            "(complex: $c, project: $p) isa near_development; get $stage_weight;"
        )
        if not rows:
            return _no_data("development_upside", "development projects")
        weights = [w for w in (_num(r, "stage_weight") for r in rows) if w is not None]
        if not weights:
            return _no_data("development_upside", "development project stages")
        raw = sum(weights)
        return _make(
            "development_upside", raw, minmax(raw, 0, 3),
            [f"{len(weights)} nearby development project(s), stage-weighted sum {raw:.2f}"],
        )

    async def _calc_regulation_impact(self, cid: str) -> FactorScore:
        rows = await self._tql(
            f'# factor:regulation_impact\nmatch $c isa complex, has complex_id "{cid}"; '
            "(complex: $c, regulation: $r) isa regulated_by; get $severity;"
        )
        if not rows:
            return _no_data("regulation_impact", "regulations")
        sev = [s for s in (_num(r, "severity") for r in rows) if s is not None]
        if not sev:
            return _no_data("regulation_impact", "regulation severity")
        raw = sum(sev)
        return _make(
            "regulation_impact", raw, minmax(raw, 0, 6, invert=True),
            [f"{len(sev)} active regulation(s), total severity {raw:.0f} (more = worse)"],
        )

    async def _calc_tax_burden(self, cid: str) -> FactorScore:
        rows = await self._tql(
            f'# factor:tax_burden\nmatch $c isa complex, has complex_id "{cid}"; '
            "get $effective_tax_rate;"
        )
        rate = _num(rows[0], "effective_tax_rate") if rows else None
        if rate is None:
            return _no_data("tax_burden", "effective tax rate")
        return _make(
            "tax_burden", rate, minmax(rate, 0, 15, invert=True),
            [f"Effective tax rate {rate:.1f}% (higher burden = lower score)"],
        )

    # ---- TimescaleDB-backed factors --------------------------------------
    async def _calc_price_momentum(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:price_momentum\nSELECT price_change_pct_12m FROM complex_price_momentum "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        v = _num(rows[0], "price_change_pct_12m") if rows else None
        if v is None:
            return _no_data("price_momentum", "12m price change")
        return _make("price_momentum", v, minmax(v, -10, 15),
                     [f"12-month price change {v:+.1f}%"])

    async def _calc_jeonse_ratio_trend(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:jeonse_ratio_trend\nSELECT jeonse_ratio_change_pp FROM complex_jeonse_ratio "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        v = _num(rows[0], "jeonse_ratio_change_pp") if rows else None
        if v is None:
            return _no_data("jeonse_ratio_trend", "jeonse ratio change")
        ratio = _num(rows[0], "jeonse_ratio")
        ev = [f"Jeonse ratio change {v:+.1f}pp over 12m (rising = stronger floor under price)"]
        if ratio is not None:
            ev.append(f"Current jeonse ratio {ratio:.1f}%")
        return _make("jeonse_ratio_trend", v, minmax(v, -10, 10), ev)

    async def _calc_interest_rate_cycle(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:interest_rate_cycle\nSELECT rate_change_bp_6m FROM mortgage_rate_trend "
            "ORDER BY time DESC LIMIT 1")
        v = _num(rows[0], "rate_change_bp_6m") if rows else None
        if v is None:
            return _no_data("interest_rate_cycle", "mortgage rate change")
        return _make("interest_rate_cycle", v, minmax(v, -100, 100, invert=True),
                     [f"Mortgage rate change {v:+.0f}bp over 6m (rising = worse)"])

    async def _calc_liquidity_trend(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:liquidity_trend\nSELECT volume_change_pct FROM complex_trade_volume "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        v = _num(rows[0], "volume_change_pct") if rows else None
        if v is None:
            return _no_data("liquidity_trend", "trade volume change")
        return _make("liquidity_trend", v, minmax(v, -50, 50),
                     [f"Trade volume change {v:+.1f}% vs prior period"])

    async def _calc_supply_demand_gap(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:supply_demand_gap\nSELECT demand_households, supply_units FROM district_supply_demand "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        dem = _num(rows[0], "demand_households") if rows else None
        sup = _num(rows[0], "supply_units") if rows else None
        if dem is None or sup is None or dem <= 0:
            return _no_data("supply_demand_gap", "supply/demand")
        gap = (dem - sup) / dem * 100.0  # positive = demand surplus = good
        return _make("supply_demand_gap", gap, minmax(gap, -50, 50),
                     [f"Demand {dem:,.0f} households vs supply {sup:,.0f} units",
                      f"Demand surplus {gap:+.1f}%"])

    async def _calc_unsold_risk(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:unsold_risk\nSELECT unsold_ratio_pct FROM district_unsold "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        v = _num(rows[0], "unsold_ratio_pct") if rows else None
        if v is None:
            return _no_data("unsold_risk", "unsold ratio")
        return _make("unsold_risk", v, minmax(v, 0, 10, invert=True),
                     [f"Unsold inventory ratio {v:.1f}% (higher = worse)"])

    async def _calc_migration_momentum(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:migration_momentum\nSELECT net_migration_pct FROM district_migration "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        v = _num(rows[0], "net_migration_pct") if rows else None
        if v is None:
            return _no_data("migration_momentum", "net migration")
        return _make("migration_momentum", v, minmax(v, -1, 1),
                     [f"Net migration {v:+.2f}% of population (inflow = better)"])

    async def _calc_cycle_position(self, cid: str) -> FactorScore:
        rows = await self._sql(
            "-- factor:cycle_position\nSELECT phase FROM market_cycle_phase "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        phase = None
        if rows:
            try:
                phase = rows[0].get("phase")
            except AttributeError:
                phase = None
        score = CYCLE_PHASE_SCORES.get(str(phase).lower()) if phase else None
        if score is None:
            return _no_data("cycle_position", "market cycle phase")
        return _make("cycle_position", score, score,
                     [f"Market cycle phase: {phase} (recovery/expansion favoured)"])

    async def _calc_sentiment_composite(self, cid: str) -> FactorScore:
        """Composite of sentiment_divergence (0.5), fear_greed_position (0.3),
        search_trend_signal (0.2). All bidirectional: higher = more positive."""
        rows = await self._sql(
            "-- factor:sentiment_composite\nSELECT sentiment_divergence, fear_greed_index, "
            "search_trend_change_pct FROM complex_sentiment "
            "WHERE complex_id = $1 ORDER BY time DESC LIMIT 1", cid)
        r = rows[0] if rows else None
        div = _num(r, "sentiment_divergence")      # -1..1 (news/community vs price)
        fg = _num(r, "fear_greed_index")           # 0..100
        st = _num(r, "search_trend_change_pct")    # % change in search interest
        parts: list[tuple[float, float, float, str]] = []  # (weight, normalized, raw, evidence)
        if div is not None:
            parts.append((0.5, minmax(div, -1, 1), div,
                          f"sentiment_divergence {div:+.2f} (weight 0.05)"))
        if fg is not None:
            parts.append((0.3, minmax(fg, 0, 100), fg,
                          f"fear_greed_position {fg:.0f}/100 (weight 0.03)"))
        if st is not None:
            parts.append((0.2, minmax(st, -50, 50), st,
                          f"search_trend_signal {st:+.1f}% (weight 0.02)"))
        if not parts:
            return _no_data("sentiment_composite", "sentiment signals")
        tw = sum(p[0] for p in parts)
        norm = sum(p[0] * p[1] for p in parts) / tw
        raw = sum(p[0] * p[2] for p in parts) / tw
        ev = [p[3] for p in parts]
        ev.append(f"Composite from {len(parts)}/3 sub-signals")
        return _make("sentiment_composite", raw, norm, ev)
