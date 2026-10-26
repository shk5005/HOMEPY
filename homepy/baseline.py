"""단지·면적 그룹별 월 기준 시세 (spec FR-4)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from homepy.config import Settings
from homepy.dates import month_end, month_range, months_before
from homepy.flags import Flag, FlaggedTrade, excluded_flags


@dataclass(frozen=True)
class GroupMonth:
    group_key: str
    apt_name: str
    umd_name: str
    area_band: int
    key_fallback: bool
    month: str
    baseline_median_manwon: int | None
    normal_count: int
    total_count: int
    flag_counts: tuple[tuple[Flag, int], ...]
    unsettled: bool


def _window_months(month: str, n: int) -> list[str]:
    """month를 포함한 직전 n개 달력 월."""
    start = months_before(month_end(month), n - 1)
    return month_range(f"{start.year:04d}-{start.month:02d}", month)


def compute_baselines(flagged: Sequence[FlaggedTrade], settings: Settings,
                      months: Sequence[str], as_of: date) -> list[GroupMonth]:
    by_group_month: dict[str, dict[str, list[FlaggedTrade]]] = defaultdict(lambda: defaultdict(list))
    for f in flagged:
        d = f.trade.deal_date
        by_group_month[f.trade.group_key][f"{d.year:04d}-{d.month:02d}"].append(f)

    excluded = excluded_flags(settings)
    cutoff = months_before(as_of, settings.unsettled_months)
    rows = []
    for group_key in sorted(by_group_month):
        per_month = by_group_month[group_key]
        for month in sorted(months):
            window = [f for m in _window_months(month, settings.window_months) for f in per_month.get(m, [])]
            if not window:
                continue
            normal = [f.trade.price_manwon for f in window if not excluded.intersection(f.flags)]
            median = None
            if len(normal) >= settings.min_count:
                median = int(Decimal(statistics.median(normal)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            first = window[0].trade
            rows.append(GroupMonth(
                group_key=group_key,
                apt_name=first.apt_name,
                umd_name=first.umd_name,
                area_band=first.area_band,
                key_fallback=first.key_fallback,
                month=month,
                baseline_median_manwon=median,
                normal_count=len(normal),
                total_count=len(window),
                flag_counts=tuple((flag, sum(flag in f.flags for f in window)) for flag in Flag),
                unsettled=month_end(month) >= cutoff,
            ))
    return rows
