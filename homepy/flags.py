"""거래별 이상거래 플래그 F1–F6 (spec FR-3, §5)."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from homepy.config import Settings
from homepy.dates import months_before
from homepy.trades import Trade

MAD_SCALE = 1.4826  # 정규분포에서 MAD를 표준편차로 환산하는 상수


class Flag(str, Enum):
    F1 = "F1"  # 해제
    F2 = "F2"  # 직거래
    F3 = "F3"  # 통계적 이상치
    F4 = "F4"  # 판정 보류
    F5 = "F5"  # 법인 관련
    F6 = "F6"  # 미확정


@dataclass(frozen=True)
class FlaggedTrade:
    trade: Trade
    flags: tuple[Flag, ...]
    reasons: tuple[str, ...]
    comparison_median_manwon: int | None
    deviation: float | None
    comparison_count: int


def excluded_flags(settings: Settings) -> frozenset[Flag]:
    """기준 시세 산출에서 빼는 플래그."""
    base = {Flag.F1, Flag.F3}
    if settings.exclude_direct:
        base.add(Flag.F2)
    return frozenset(base)


def _is_direct(t: Trade, settings: Settings) -> bool:
    return t.dealing_type in settings.direct_codes


def _comparable(t: Trade, settings: Settings) -> bool:
    return not t.cancelled and not (settings.exclude_direct and _is_direct(t, settings))


def _flag_one(t: Trade, group: Sequence[Trade], settings: Settings, cutoff_f6: date) -> FlaggedTrade:
    found: dict[Flag, str] = {}
    if t.cancelled:
        found[Flag.F1] = "해제 신고된 거래"
    if _is_direct(t, settings):
        found[Flag.F2] = "직거래"
    if t.seller_type in settings.corporate_codes or t.buyer_type in settings.corporate_codes:
        found[Flag.F5] = f"법인 관련 (매도: {t.seller_type}, 매수: {t.buyer_type})"
    if t.deal_date >= cutoff_f6:
        found[Flag.F6] = "미확정 기간 거래 (신고·해제 반영 전일 수 있음)"

    start = months_before(t.deal_date, settings.window_months)
    prices = [
        o.price_manwon for o in group
        if o.trade_id != t.trade_id and start <= o.deal_date <= t.deal_date and _comparable(o, settings)
    ]

    median_manwon = None
    deviation = None
    if len(prices) < settings.min_count:
        found[Flag.F4] = f"비교 거래 {len(prices)}건 < 최소 {settings.min_count}건, 판정 보류"
    else:
        logs = [math.log(p) for p in prices]
        m = statistics.median(logs)
        mad = statistics.median(abs(x - m) for x in logs)
        ratio = t.price_manwon / math.exp(m) - 1
        if mad == 0:
            outlier = abs(ratio) > settings.flat_pct
        else:
            outlier = abs(math.log(t.price_manwon) - m) > settings.mad_k * MAD_SCALE * mad
        median_manwon = int(Decimal(math.exp(m)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        deviation = round(ratio, 4)
        if outlier:
            found[Flag.F3] = f"통계적 이상치 (기준 대비 {ratio:+.1%})"

    flags = tuple(sorted(found, key=lambda f: f.value))
    return FlaggedTrade(
        trade=t,
        flags=flags,
        reasons=tuple(found[f] for f in flags),
        comparison_median_manwon=median_manwon,
        deviation=deviation,
        comparison_count=len(prices),
    )


def assign_flags(trades: Sequence[Trade], settings: Settings, as_of: date) -> list[FlaggedTrade]:
    groups: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        groups[t.group_key].append(t)
    cutoff_f6 = months_before(as_of, settings.unsettled_months)
    ordered = sorted(trades, key=lambda t: (t.group_key, t.deal_date, t.trade_id))
    return [_flag_one(t, groups[t.group_key], settings, cutoff_f6) for t in ordered]
