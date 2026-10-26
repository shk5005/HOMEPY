from dataclasses import replace
from datetime import date
from decimal import Decimal
from itertools import count

import pytest

from homepy.config import Settings
from homepy.flags import Flag, assign_flags, excluded_flags
from homepy.trades import Trade

S = Settings(version="t")
AS_OF = date(2026, 12, 31)  # 기본값: 테스트 거래가 미확정 기간에 들지 않게
_ids = count()


def mk(price: int, d: date, **kw) -> Trade:
    t = Trade(
        trade_id=f"t{next(_ids):04d}", group_key="G|85", key_fallback=False,
        apt_name="A", umd_name="U", area_m2=Decimal("84.9"), area_band=85,
        deal_date=d, price_manwon=price, floor=5, dealing_type="중개거래",
        cancelled=False, seller_type="개인", buyer_type="개인",
    )
    return replace(t, **kw)


def comps(*prices: int) -> list[Trade]:
    return [mk(p, date(2026, 5, i + 1)) for i, p in enumerate(prices)]


def result_for(trades, target, settings=S, as_of=AS_OF):
    out = assign_flags(trades + [target], settings, as_of)
    return next(f for f in out if f.trade.trade_id == target.trade_id)


def test_outlier_by_mad():
    r = result_for(comps(100_000, 101_000, 99_000, 100_500), mk(130_000, date(2026, 6, 1)))
    assert Flag.F3 in r.flags
    assert r.comparison_median_manwon == 100_250 and r.comparison_count == 4
    assert r.reasons[r.flags.index(Flag.F3)].startswith("통계적 이상치")


def test_not_outlier_within_band():
    r = result_for(comps(100_000, 101_000, 99_000, 100_500), mk(102_000, date(2026, 6, 1)))
    assert Flag.F3 not in r.flags and r.deviation == 0.0175


def test_mad_zero_uses_flat_pct():
    base = comps(100_000, 100_000, 100_000)
    assert Flag.F3 not in result_for(base, mk(114_000, date(2026, 6, 1))).flags
    assert Flag.F3 in result_for(base, mk(116_000, date(2026, 6, 1))).flags


def test_insufficient_comparison_is_F4_not_F3():
    r = result_for(comps(100_000, 100_000), mk(200_000, date(2026, 6, 1)))
    assert r.flags == (Flag.F4,) and r.comparison_median_manwon is None and r.deviation is None


def test_cancelled_and_direct_excluded_from_comparison():
    others = comps(100_000, 100_000)
    others += [mk(100_000, date(2026, 5, 10), cancelled=True),
               mk(100_000, date(2026, 5, 11), dealing_type="직거래")]
    r = result_for(others, mk(100_000, date(2026, 6, 1)))
    assert r.flags == (Flag.F4,) and r.comparison_count == 2


def test_direct_included_when_setting_off():
    others = comps(100_000, 100_000) + [mk(100_000, date(2026, 5, 11), dealing_type="직거래")]
    r = result_for(others, mk(100_000, date(2026, 6, 1)), settings=replace(S, exclude_direct=False))
    assert Flag.F4 not in r.flags and r.comparison_count == 3


def test_F1_F2_F5_flags():
    trades = comps(100_000, 100_000, 100_000)
    r1 = result_for(trades, mk(100_000, date(2026, 6, 1), cancelled=True))
    r2 = result_for(trades, mk(100_000, date(2026, 6, 1), dealing_type="직거래"))
    r5 = result_for(trades, mk(100_000, date(2026, 6, 1), buyer_type="법인"))
    assert r1.flags == (Flag.F1,) and r2.flags == (Flag.F2,) and r5.flags == (Flag.F5,)
    assert r5.reasons == ("법인 관련 (매도: 개인, 매수: 법인)",)


def test_window_boundary_month_end():
    inside = [mk(100_000, date(2026, 2, 28)) for _ in range(3)]
    outside = [mk(100_000, date(2026, 2, 27)) for _ in range(3)]
    target = mk(100_000, date(2026, 8, 31))
    assert result_for(inside, target).comparison_count == 3
    assert result_for(outside, target).comparison_count == 0


def test_self_excluded_same_day_others_included():
    same_day = [mk(100_000, date(2026, 6, 1)) for _ in range(3)]
    r = result_for(same_day, mk(100_000, date(2026, 6, 1)))
    assert r.comparison_count == 3


def test_later_trades_not_in_comparison():
    later = [mk(100_000, date(2026, 6, 2)) for _ in range(3)]
    assert result_for(later, mk(100_000, date(2026, 6, 1))).comparison_count == 0


def test_other_group_not_in_comparison():
    other = [mk(100_000, date(2026, 5, 1), group_key="H|85") for _ in range(3)]
    assert result_for(other, mk(100_000, date(2026, 6, 1))).comparison_count == 0


@pytest.mark.parametrize("d,flagged", [(date(2026, 8, 26), True), (date(2026, 8, 25), False)])
def test_F6_relative_to_as_of(d, flagged):
    r = result_for([], mk(100_000, d), as_of=date(2026, 10, 26))
    assert (Flag.F6 in r.flags) is flagged


def test_flags_sorted_and_reasons_aligned():
    r = result_for(comps(100_000, 100_000), mk(100_000, date(2026, 10, 1), cancelled=True),
                   as_of=date(2026, 10, 26))
    assert r.flags == (Flag.F1, Flag.F4, Flag.F6) and len(r.reasons) == 3


def test_reason_wording_has_no_forbidden_terms():
    trades = comps(100_000, 101_000, 99_000) + [
        mk(300_000, date(2026, 10, 1), cancelled=True, dealing_type="직거래", seller_type="법인"),
        mk(100_000, date(2026, 1, 1)),
    ]
    reasons = [r for f in assign_flags(trades, S, date(2026, 10, 26)) for r in f.reasons]
    assert reasons
    for r in reasons:
        assert not any(w in r for w in ("불법", "허위", "작전"))


def test_deterministic():
    ts = comps(100_000, 101_000, 99_000, 100_500) + [mk(130_000, date(2026, 6, 1))]
    assert assign_flags(ts, S, AS_OF) == assign_flags(list(reversed(ts)), S, AS_OF)


def test_excluded_flags():
    assert excluded_flags(S) == {Flag.F1, Flag.F2, Flag.F3}
    assert excluded_flags(replace(S, exclude_direct=False)) == {Flag.F1, Flag.F3}
