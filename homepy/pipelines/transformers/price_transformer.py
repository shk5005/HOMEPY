"""Price transformer: price per sqm, moving averages, YoY/MoM, district aggregates."""
from __future__ import annotations

import numpy as np
import pandas as pd

MA_WINDOWS = (3, 6, 12)


class PriceTransformer:
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "price" in out.columns and "area_sqm" in out.columns:
            area = pd.to_numeric(out["area_sqm"], errors="coerce").astype("float64")
            price = pd.to_numeric(out["price"], errors="coerce").astype("float64")
            out["price_per_sqm"] = price / area.where(area > 0)  # area 0/neg/NaN -> NaN
        if "price_per_sqm" not in out.columns:
            return out

        if "ts" in out.columns:
            out = out.sort_values("ts", kind="stable").reset_index(drop=True)

        if "district_code" in out.columns:
            grouped = out.groupby("district_code", sort=False)["price_per_sqm"]
        else:
            grouped = None
        series = out["price_per_sqm"]

        for w in MA_WINDOWS:  # NaN until a full window is available
            if grouped is not None:
                out[f"ma_{w}m"] = grouped.transform(lambda s, w=w: s.rolling(w, min_periods=w).mean())
            else:
                out[f"ma_{w}m"] = series.rolling(w, min_periods=w).mean()

        def _pct(s: pd.Series, n: int) -> pd.Series:
            prev = s.shift(n)
            return (s - prev) / prev.where(prev != 0) * 100.0

        if grouped is not None:
            out["mom_change"] = grouped.transform(lambda s: _pct(s, 1))
            out["yoy_change"] = grouped.transform(lambda s: _pct(s, 12))
            keys = ["district_code"] + (["ts"] if "ts" in out.columns else [])
            g = out.groupby(keys, sort=False)["price_per_sqm"]
            out["district_mean_price_per_sqm"] = g.transform("mean")
            out["district_median_price_per_sqm"] = g.transform("median")
        else:
            out["mom_change"] = _pct(series, 1)
            out["yoy_change"] = _pct(series, 12)
        return out.replace([np.inf, -np.inf], np.nan)
