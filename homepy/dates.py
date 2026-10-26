"""월 단위 날짜 계산."""

from __future__ import annotations

import calendar
from datetime import date


def months_before(d: date, n: int) -> date:
    """n개월 전 같은 날. 그 달에 그날이 없으면 말일로 맞춘다."""
    total = d.year * 12 + (d.month - 1) - n
    year, month0 = divmod(total, 12)
    last = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last))


def month_end(ym: str) -> date:
    year, month = (int(x) for x in ym.split("-"))
    return date(year, month, calendar.monthrange(year, month)[1])


def month_range(start: str, end: str) -> list[str]:
    """양 끝을 포함한 "YYYY-MM" 목록."""
    y, m = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
