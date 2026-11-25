"""Price transformer: price per sqm, moving averages, YoY/MoM, district aggregates."""
from __future__ import annotations

import numpy as np
import pandas as pd

MA_WINDOWS = (3, 6, 12)


SUM_HINTS = ("count", "volume", "units")


class PriceTransformer:
    @staticmethod
    def _aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
        """Collapse transaction-level rows to one row per (district, calendar month).

        No-op when ts is absent or each (district, month) already has one row.
        Numeric columns are averaged (count/volume/units columns summed); others take the first value.
        """
        if "ts" not in df.columns or df.empty:
            return df
        ts = pd.to_datetime(df["ts"])
        tz = ts.dt.tz
        month = (ts.dt.tz_localize(None) if tz is not None else ts).dt.to_period("M")
        keys = ["district_code"] if "district_code" in df.columns else []
        work = df.drop(columns=["ts"]).assign(_month=month.to_numpy())
        group_cols = keys + ["_month"]
        if not work.duplicated(group_cols).any():
            return df
        agg: dict[str, str] = {}
        for c in work.columns:
            if c in group_cols:
                continue
            if pd.api.types.is_bool_dtype(work[c]):
                agg[c] = "max"  # e.g. _outlier: any flagged trade flags the month
            elif pd.api.types.is_numeric_dtype(work[c]):
                agg[c] = "sum" if any(h in c.lower() for h in SUM_HINTS) else "mean"
            else:
                agg[c] = "first"
        g = work.groupby(group_cols, sort=False)
        res = g.agg(agg)
        res["n_trades"] = g.size()
        res = res.reset_index()
        new_ts = pd.PeriodIndex(res.pop("_month"), freq="M").to_timestamp()
        if tz is not None:
            new_ts = new_ts.tz_localize(tz)
        res.insert(0, "ts", new_ts)
        return res

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "price" in out.columns and "area_sqm" in out.columns:
            area = pd.to_numeric(out["area_sqm"], errors="coerce").astype("float64")
            price = pd.to_numeric(out["price"], errors="coerce").astype("float64")
            out["price_per_sqm"] = price / area.where(area > 0)  # area 0/neg/NaN -> NaN
        if "price_per_sqm" not in out.columns:
            return out

        out = self._aggregate_monthly(out)
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
