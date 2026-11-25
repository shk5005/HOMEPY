from datetime import date

from homepy.baseline import compute_baselines
from homepy.config import Settings
from homepy.flags import Flag, FlaggedTrade
from tests.test_flags import mk

S = Settings(version="t")
AS_OF = date(2026, 12, 31)


def ft(price: int, d: date, *flags: Flag, **kw) -> FlaggedTrade:
    return FlaggedTrade(mk(price, d, **kw), tuple(flags), tuple("" for _ in flags), None, None, 0)


def row_for(rows, month):
    return next(r for r in rows if r.month == month)


def test_median_excludes_F1_F3_F2():
    trades = [ft(100_000, date(2026, 9, 1)), ft(102_000, date(2026, 9, 2)),
              ft(104_000, date(2026, 9, 3)), ft(150_000, date(2026, 9, 4), Flag.F3),
              ft(90_000, date(2026, 9, 5), Flag.F1), ft(91_000, date(2026, 9, 6), Flag.F2)]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert r.baseline_median_manwon == 102_000 and r.normal_count == 3 and r.total_count == 6


def test_F4_F5_F6_count_as_normal():
    trades = [ft(100_000, date(2026, 9, 1), Flag.F4), ft(102_000, date(2026, 9, 2), Flag.F5),
              ft(104_000, date(2026, 9, 3), Flag.F6)]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert r.normal_count == 3


def test_even_count_half_up():
    trades = [ft(p, date(2026, 9, i + 1)) for i, p in enumerate([100_000, 100_001, 100_002, 100_004])]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert r.baseline_median_manwon == 100_002


def test_below_min_count_is_none():
    trades = [ft(100_000, date(2026, 9, 1)), ft(100_000, date(2026, 9, 2))]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert r.baseline_median_manwon is None and r.normal_count == 2


def test_window_is_calendar_months():
    trades = [ft(100_000, date(2026, 3, 31)), ft(100_000, date(2026, 4, 1))]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert r.total_count == 1


def test_flag_counts_include_zeros():
    trades = [ft(100_000, date(2026, 9, 1), Flag.F3, Flag.F6)]
    r = row_for(compute_baselines(trades, S, ["2026-09"], AS_OF), "2026-09")
    assert [f for f, _ in r.flag_counts] == list(Flag)
    assert dict(r.flag_counts) == {Flag.F1: 0, Flag.F2: 0, Flag.F3: 1, Flag.F4: 0, Flag.F5: 0, Flag.F6: 1}


def test_unsettled_month():
    trades = [ft(100_000, date(2026, 7, 1))]
    rows = compute_baselines(trades, S, ["2026-07", "2026-09"], date(2026, 10, 26))
    assert row_for(rows, "2026-09").unsettled and not row_for(rows, "2026-07").unsettled


def test_rows_only_where_window_has_trades_and_sorted():
    trades = [ft(100_000, date(2026, 9, 1), group_key="B|85"), ft(100_000, date(2026, 1, 1), group_key="A|85")]
    rows = compute_baselines(trades, S, ["2026-01", "2026-09"], AS_OF)
    assert [(r.group_key, r.month) for r in rows] == [("A|85", "2026-01"), ("B|85", "2026-09")]
