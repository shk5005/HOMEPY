"""Korean real-estate tax calculations (simplified; rates looked up in TypeDB)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

TYPEDB_DB = "homepy"

# Fallback statutory defaults used when TypeDB has no matching rule.
DEFAULT_ACQ_RATE = {1: 0.01, 2: 0.08, 3: 0.12}  # 1 house / 2nd (regulated) / 3rd+
SURTAX_RATE = 0.002  # education tax (0.1%) + special rural tax (0.1%), simplified
LONG_TERM_DEDUCTION_PER_YEAR = 0.02
LONG_TERM_DEDUCTION_CAP = 0.30
BASIC_DEDUCTION = 2_500_000
CGT_BRACKETS = [  # (upper bound, rate, progressive deduction)
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"), 0.45, 65_940_000),
]
COMP_EXEMPTION = 900_000_000  # per-person exemption (1 owner)
COMP_FAIR_MARKET_RATIO = 0.60
COMP_BRACKETS = [
    (300_000_000, 0.005, 0),
    (600_000_000, 0.007, 600_000),
    (1_200_000_000, 0.010, 2_400_000),
    (2_500_000_000, 0.013, 6_000_000),
    (5_000_000_000, 0.020, 23_500_000),
    (9_400_000_000, 0.027, 58_500_000),
    (float("inf"), 0.030, 86_700_000),
]


def _bracket(amount: float, table: list[tuple]) -> tuple[float, float]:
    for upper, rate, deduction in table:
        if amount <= upper:
            return rate, deduction
    return table[-1][1], table[-1][2]


class TaxEngine:
    def __init__(self, typedb_svc: Any) -> None:
        self.typedb = typedb_svc

    async def _rate_lookup(self, query: str) -> float | None:
        """Run a placeholder TypeQL rate query; None if nothing usable returned."""
        try:
            rows = await asyncio.to_thread(self.typedb.execute_read, TYPEDB_DB, query)
        except Exception:  # noqa: BLE001 - tax calc must degrade to statutory defaults
            log.warning("TypeDB tax-rate lookup failed; using defaults", exc_info=True)
            return None
        for row in rows or []:
            try:
                val = row.get("rate")
                if val is not None:
                    return float(val)
            except (AttributeError, TypeError, ValueError):
                continue
        return None

    async def calc_acquisition_tax(
        self, price: int, buyer_type: str, owner_count: int, area_type: str
    ) -> dict:
        regulated = area_type == "regulated"
        if buyer_type == "corporate":
            key = 3
        elif owner_count <= 1:
            key = 1
        elif owner_count == 2 and regulated:
            key = 2
        elif owner_count == 2:
            key = 1
        else:
            key = 3 if regulated or owner_count >= 4 else 2
        query = (
            "match $r isa acquisition-tax-rate, has buyer-type "
            f'"{buyer_type}", has owner-count {key}, has rate $rate; get $rate;'
        )
        rate = await self._rate_lookup(query)
        source = "typedb"
        if rate is None:
            rate = DEFAULT_ACQ_RATE[key]
            source = "default"
        tax = round(price * rate)
        surtax = round(price * SURTAX_RATE)
        return {"base_price": price, "rate": rate, "acquisition_tax": tax,
                "surtax": surtax, "total": tax + surtax, "rate_source": source}

    async def calc_capital_gains_tax(
        self, purchase_price: int, sale_price: int, holding_years: float,
        area_type: str, owner_count: int,
    ) -> dict:
        gain = sale_price - purchase_price
        if gain <= 0:
            return {"gain": gain, "taxable_income": 0, "rate": 0.0, "tax": 0, "total": 0}
        deduction_rate = 0.0
        if owner_count <= 1 and holding_years >= 3:
            deduction_rate = min(LONG_TERM_DEDUCTION_CAP, int(holding_years) * LONG_TERM_DEDUCTION_PER_YEAR)
        taxable = max(0.0, gain * (1 - deduction_rate) - BASIC_DEDUCTION)
        surcharge = 0.0
        if area_type == "regulated" and owner_count >= 2:
            surcharge = 0.20 if owner_count == 2 else 0.30
        if holding_years < 1:
            rate, prog, label = 0.70, 0, "short_term_lt1y"
        elif holding_years < 2:
            rate, prog, label = 0.60, 0, "short_term_lt2y"
        else:
            rate, prog = _bracket(taxable, CGT_BRACKETS)
            label = "progressive"
        query = (
            "match $r isa cgt-rate-rule, has holding-period "
            f"{int(holding_years)}, has rate $rate; get $rate;"
        )
        db_rate = await self._rate_lookup(query)
        if db_rate is not None and label != "progressive":
            rate = db_rate
        eff = rate + surcharge
        tax = max(0, round(taxable * eff - prog))
        local = round(tax * 0.1)
        return {"gain": gain, "long_term_deduction_rate": deduction_rate,
                "taxable_income": round(taxable), "rate_type": label, "rate": rate,
                "heavy_surcharge": surcharge, "tax": tax, "local_income_tax": local,
                "total": tax + local}

    async def calc_comprehensive_tax(self, assessed_values: list[int], owner_count: int) -> dict:
        total_assessed = sum(assessed_values)
        base = max(0.0, (total_assessed - COMP_EXEMPTION) * COMP_FAIR_MARKET_RATIO)
        if base <= 0:
            return {"total_assessed": total_assessed, "tax_base": 0, "rate": 0.0, "tax": 0,
                    "total": 0}
        rate, prog = _bracket(base, COMP_BRACKETS)
        tax = max(0, round(base * rate - prog))
        rural = round(tax * 0.2)
        return {"total_assessed": total_assessed, "tax_base": round(base), "rate": rate,
                "tax": tax, "rural_special_tax": rural, "owner_count": owner_count,
                "total": tax + rural}
