from __future__ import annotations

import pytest

SKIP = "requires live TypeDB"


@pytest.mark.skip(reason=SKIP)
async def test_smart_money_signal_fires():
    """price-change-mom < 0 AND sale-to-list-ratio > 1.05 -> smart-money-signal."""


@pytest.mark.skip(reason=SKIP)
async def test_smart_money_signal_not_fires_positive_mom():
    """price-change-mom > 0 -> no smart-money-signal."""
