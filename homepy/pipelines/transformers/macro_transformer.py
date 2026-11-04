"""Macro transformer: rate direction, real interest rate, liquidity growth."""
from __future__ import annotations

import numpy as np
import pandas as pd

FLAT_EPS = 1e-9


class MacroTransformer:
    def __init__(self, rate_col: str = "base_rate", cpi_col: str = "cpi", m2_col: str = "m2"):
        self.rate_col, self.cpi_col, self.m2_col = rate_col, cpi_col, m2_col

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "ts" in out.columns:
            out = out.sort_values("ts", kind="stable").reset_index(drop=True)
        if self.rate_col in out.columns:
            rate = pd.to_numeric(out[self.rate_col], errors="coerce")
            delta = rate.diff()
            direction = pd.Series("flat", index=out.index, dtype="object")
            direction[delta > FLAT_EPS] = "up"
            direction[delta < -FLAT_EPS] = "down"
            out["rate_direction"] = direction
            if self.cpi_col in out.columns:
                # cpi column is the CPI inflation rate (%, YoY)
                out["real_interest_rate"] = rate - pd.to_numeric(out[self.cpi_col], errors="coerce")
        if self.m2_col in out.columns:
            m2 = pd.to_numeric(out[self.m2_col], errors="coerce")
            prev = m2.shift(1)
            out["liquidity_growth_rate"] = ((m2 - prev) / prev.where(prev != 0) * 100.0).replace(
                [np.inf, -np.inf], np.nan)
        return out
