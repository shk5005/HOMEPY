"""Backtesting engine: evaluates past investment verdicts against realized prices.

No-lookahead rule: every query is bounded by ``ts <= <date>``.  The verdict
and its inputs are read as of the verdict date; realized outcomes are read as
the latest trade ``ts <= verdict_date + horizon`` (an as-of lookup), and a
horizon that has not yet matured at ``now`` yields no outcome rather than a
partial one.
"""
from __future__ import annotations

import calendar
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from scipy.stats import spearmanr

from homepy.inference.scorer import FACTOR_WEIGHTS

from homepy.verification.models import BacktestRecord

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService

BUY_VERDICTS = {"매수 검토", "적극 매수", "buy"}
SELL_VERDICTS = {"매도 검토", "적극 매도", "sell"}
HOLD_BAND_PCT = 3.0  # |change| within this band counts as a correct "hold"
MIN_IC_SAMPLES = 5

_VERDICT_BY_ID = (
    "SELECT ts, target_id, metadata FROM ts_signals "
    "WHERE signal_type = 'verdict' AND target_id = $1 AND ts <= $2 "
    "ORDER BY ts DESC LIMIT 1"
)
_VERDICTS_IN_WINDOW = (
    "SELECT ts, target_id, metadata FROM ts_signals "
    "WHERE signal_type = 'verdict' AND ts >= $1 AND ts <= $2 ORDER BY ts"
)
_PRICE_AS_OF = (
    "SELECT price_per_pyeong FROM ts_real_trade "
    "WHERE complex_id = $1 AND is_cancelled = FALSE AND ts <= $2 "
    "ORDER BY ts DESC LIMIT 1"
)


@dataclass
class BacktestResult:
    period_start: date
    period_end: date
    total_verdicts: int
    direction_accuracy: float  # percent
    signal_hit_rate: float  # percent, buy/sell verdicts only
    scenario_capture_rate: float  # percent
    bias_validity_rate: float  # percent
    factor_ic: dict[str, float] = field(default_factory=dict)
    underperforming_factors: list[str] = field(default_factory=list)


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _as_date(v: date | datetime) -> date:
    return v.date() if isinstance(v, datetime) else v


def _as_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def _meta(row: Any) -> dict[str, Any]:
    m = row["metadata"]
    if isinstance(m, str):
        m = json.loads(m)
    return m or {}


def _pct(num: int, den: int) -> float:
    return round(100.0 * num / den, 2) if den else 0.0


class Backtester:
    def __init__(
        self,
        timescale_svc: TimescaleService,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ts = timescale_svc
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def _price_as_of(
        self, complex_id: str, as_of: date,
    ) -> tuple[float | None, datetime | None]:
        """Return (price, trade_ts) as-of *as_of*, or (None, None)."""
        if as_of > self._now().date():
            return None, None  # horizon not matured yet
        rows = await self._ts.execute(_PRICE_AS_OF, complex_id, _as_dt(as_of))
        if not rows or rows[0]["price_per_pyeong"] is None:
            return None, None
        return float(rows[0]["price_per_pyeong"]), rows[0].get("ts")

    async def _record_from_row(self, row: Any) -> BacktestRecord:
        meta = _meta(row)
        vdate = row["ts"]
        vday = _as_date(vdate)
        complex_id = str(meta.get("complex_id", ""))
        record = BacktestRecord(
            verdict_id=str(row["target_id"]),
            complex_id=complex_id,
            verdict_date=vdate,
            predicted_verdict=str(meta.get("verdict", "")),
            predicted_score=float(meta.get("score", 0.0)),
            predicted_scenarios=meta.get("scenarios") or {},
            factor_contributions={
                k: float(v) for k, v in (meta.get("factor_scores") or {}).items()
            },
            bias_warnings_issued=len(meta.get("bias_warnings") or []),
        )

        base, base_ts = await self._price_as_of(complex_id, vday)
        changes: dict[int, float | None] = {}
        for h in (3, 6, 12):
            later, later_ts = await self._price_as_of(complex_id, _add_months(vday, h))
            if base and later is not None and later_ts is not None and later_ts != base_ts:
                changes[h] = round((later / base - 1.0) * 100.0, 4)
            else:
                changes[h] = None
        record.actual_price_change_3m = changes[3]
        record.actual_price_change_6m = changes[6]
        record.actual_price_change_12m = changes[12]

        actual = changes[3]
        if actual is not None:
            record.direction_correct = self._direction_correct(
                record.predicted_verdict, actual
            )
            record.scenario_hit = self._scenario_hit(record.predicted_scenarios, actual)
            if record.bias_warnings_issued:
                # a bias warning is "valid" when the warned-about risk materialised,
                # i.e. the verdict's direction turned out wrong
                record.bias_warnings_valid = (
                    record.bias_warnings_issued if not record.direction_correct else 0
                )
        return record

    @staticmethod
    def _direction_correct(verdict: str, actual: float) -> bool:
        if verdict in BUY_VERDICTS:
            return actual > 0
        if verdict in SELL_VERDICTS:
            return actual < 0
        return abs(actual) <= HOLD_BAND_PCT

    @staticmethod
    def _scenario_hit(scenarios: dict[str, Any], actual: float) -> bool | None:
        vals = []
        for s in scenarios.values():
            v = s.get("price_change") if isinstance(s, dict) else s
            if isinstance(v, (int, float)):
                vals.append(float(v))
        if len(vals) < 2:
            return None
        return min(vals) <= actual <= max(vals)

    async def evaluate_verdict(self, verdict_id: str) -> BacktestRecord:
        rows = await self._ts.execute(_VERDICT_BY_ID, verdict_id, self._now())
        if not rows:
            raise KeyError(f"verdict not found: {verdict_id}")
        return await self._record_from_row(rows[0])

    async def _evaluate_window(
        self, months: int, skip_recent_months: int = 0,
    ) -> tuple[date, date, list[BacktestRecord]]:
        end_date = _add_months(self._now().date(), -skip_recent_months) if skip_recent_months else self._now().date()
        start = _add_months(self._now().date(), -months)
        end_dt = _as_dt(end_date)
        rows = await self._ts.execute(
            _VERDICTS_IN_WINDOW, _as_dt(start).replace(hour=0, minute=0, second=0), end_dt
        )
        return start, end_date, [await self._record_from_row(r) for r in rows]

    @staticmethod
    def _ic_from_records(records: list[BacktestRecord]) -> dict[str, float]:
        ic: dict[str, float] = {}
        matured = [r for r in records if r.actual_price_change_3m is not None]
        for factor in FACTOR_WEIGHTS:
            pairs = [
                (r.factor_contributions[factor], r.actual_price_change_3m)
                for r in matured
                if factor in r.factor_contributions
            ]
            xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
            if len(pairs) < MIN_IC_SAMPLES or len(set(xs)) < 2 or len(set(ys)) < 2:
                ic[factor] = 0.0
                continue
            rho = float(spearmanr(xs, ys).statistic)
            ic[factor] = 0.0 if math.isnan(rho) else rho
        return ic

    async def factor_ic_analysis(
        self, months: int = 12, skip_recent_months: int = 0,
    ) -> dict[str, float]:
        _, _, records = await self._evaluate_window(months, skip_recent_months)
        return self._ic_from_records(records)

    async def run(self, lookback_months: int = 3) -> BacktestResult:
        start, end, records = await self._evaluate_window(lookback_months)
        judged = [r for r in records if r.direction_correct is not None]
        signals = [
            r for r in judged
            if r.predicted_verdict in BUY_VERDICTS | SELL_VERDICTS
        ]
        scen = [r for r in judged if r.scenario_hit is not None]
        issued = sum(r.bias_warnings_issued for r in judged)

        # IC needs a larger sample than the headline window
        ic = self._ic_from_records(
            records
            if lookback_months >= 12
            else (await self._evaluate_window(12))[2]
        )
        return BacktestResult(
            period_start=start,
            period_end=end,
            total_verdicts=len(records),
            direction_accuracy=_pct(sum(bool(r.direction_correct) for r in judged), len(judged)),
            signal_hit_rate=_pct(sum(bool(r.direction_correct) for r in signals), len(signals)),
            scenario_capture_rate=_pct(sum(bool(r.scenario_hit) for r in scen), len(scen)),
            bias_validity_rate=_pct(sum(r.bias_warnings_valid for r in judged), issued),
            factor_ic=ic,
            underperforming_factors=sorted(f for f, v in ic.items() if v < 0),
        )
