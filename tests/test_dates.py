from datetime import date

import pytest

from homepy.dates import month_end, month_range, months_before


@pytest.mark.parametrize("d,n,expected", [
    (date(2026, 8, 31), 6, date(2026, 2, 28)),
    (date(2024, 8, 31), 6, date(2024, 2, 29)),
    (date(2026, 3, 15), 6, date(2025, 9, 15)),
    (date(2026, 1, 31), 1, date(2025, 12, 31)),
])
def test_months_before(d, n, expected):
    assert months_before(d, n) == expected


def test_month_range():
    assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_month_end():
    assert month_end("2026-02") == date(2026, 2, 28)
    assert month_end("2024-02") == date(2024, 2, 29)
