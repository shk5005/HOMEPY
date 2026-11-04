"""Cycle classifier: HP-filter trend + phase classification."""
from __future__ import annotations

import numpy as np
import pandas as pd

HP_LAMBDA_MONTHLY = 14400
TOLERANCE = 1e-6  # relative tolerance for "actual == trend"


def hp_filter(values: np.ndarray, lamb: float = HP_LAMBDA_MONTHLY) -> np.ndarray:
    """Return the HP trend. Uses scipy sparse solver if installed, else numpy dense.

    Falls back to a centered moving average if n < 4 (HP undefined/degenerate).
    """
    y = np.asarray(values, dtype="float64")
    n = len(y)
    if n < 4:
        return pd.Series(y).rolling(3, min_periods=1, center=True).mean().to_numpy()
    try:
        from scipy import sparse
        from scipy.sparse.linalg import spsolve

        d = sparse.diags([1, -2, 1], [0, 1, 2], shape=(n - 2, n), format="csc")
        a = sparse.eye(n, format="csc") + lamb * (d.T @ d)
        return np.asarray(spsolve(a, y))
    except ImportError:
        d = np.zeros((n - 2, n))
        for i in range(n - 2):
            d[i, i:i + 3] = (1, -2, 1)
        return np.linalg.solve(np.eye(n) + lamb * d.T @ d, y)


class CycleClassifier:
    def __init__(self, value_col: str = "price_index", lamb: float = HP_LAMBDA_MONTHLY):
        self.value_col, self.lamb = value_col, lamb

    def classify(self, price_index_df: pd.DataFrame, macro_df: pd.DataFrame | None = None) -> pd.DataFrame:
        out = price_index_df.copy()
        if "ts" in out.columns:
            out = out.sort_values("ts", kind="stable").reset_index(drop=True)
        if self.value_col not in out.columns or out.empty:
            out["trend"], out["cycle"], out["cycle_phase"] = np.nan, np.nan, None
            return out
        actual = pd.to_numeric(out[self.value_col], errors="coerce").astype("float64")
        valid = actual.notna()
        trend = pd.Series(np.nan, index=out.index)
        if valid.sum() > 0:
            trend[valid] = hp_filter(actual[valid].to_numpy(), self.lamb)
        out["trend"] = trend
        out["cycle"] = actual - trend

        delta = actual.diff()
        tol = TOLERANCE * actual.abs().clip(lower=1.0)
        above = out["cycle"] >= -tol  # on-trend counts as above
        rising = delta >= 0
        phase = np.select(
            [above & rising, above & ~rising, ~above & ~rising, ~above & rising],
            ["expansion", "peak", "contraction", "recovery"], default="")
        phase = pd.Series(phase, index=out.index, dtype="object")
        phase[(~valid) | delta.isna() | (phase == "")] = None  # first row has no direction
        out["cycle_phase"] = phase

        out["coincident_index"] = actual / actual[valid].iloc[0] * 100.0 if valid.any() else np.nan
        out["leading_index"] = self._leading_index(out, macro_df)
        return out

    @staticmethod
    def _leading_index(out: pd.DataFrame, macro_df: pd.DataFrame | None) -> pd.Series:
        """Leading index = 100 + liquidity growth - real rate (z-free, base 100); NaN w/o macro data."""
        nan = pd.Series(np.nan, index=out.index)
        if macro_df is None or macro_df.empty or "ts" not in macro_df.columns or "ts" not in out.columns:
            return nan
        m = macro_df.copy()
        if "liquidity_growth_rate" not in m.columns and "m2" in m.columns:
            m = m.sort_values("ts")
            m["liquidity_growth_rate"] = pd.to_numeric(m["m2"], errors="coerce").pct_change() * 100.0
        if "real_interest_rate" not in m.columns and {"base_rate", "cpi"} <= set(m.columns):
            m["real_interest_rate"] = m["base_rate"] - m["cpi"]
        cols = [c for c in ("liquidity_growth_rate", "real_interest_rate") if c in m.columns]
        if len(cols) < 2:
            return nan
        m = m.drop_duplicates("ts").set_index("ts")[cols]
        aligned = m.reindex(out["ts"]).reset_index(drop=True)
        aligned.index = out.index
        if len(cols) < 2:  # any missing component -> NaN, never substitute zero
            return nan
        return 100.0 + aligned["liquidity_growth_rate"] - aligned["real_interest_rate"]
