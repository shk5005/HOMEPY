"""Supply-demand transformer: gap, PIR, months of inventory."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _keys(*dfs: pd.DataFrame) -> list[str]:
    cols = set.intersection(*[set(d.columns) for d in dfs])
    return [k for k in ("ts", "district_code") if k in cols]


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    b = pd.to_numeric(b, errors="coerce").astype("float64")
    return (pd.to_numeric(a, errors="coerce") / b.where(b > 0)).replace([np.inf, -np.inf], np.nan)


class SupplyDemandTransformer:
    """supply_df: supply_units, unsold_units, [absorption_units], [median_price, median_income]
    population_df: [new_households | households]; migration_df: net_migration."""

    def transform(self, supply_df: pd.DataFrame, population_df: pd.DataFrame | None = None,
                  migration_df: pd.DataFrame | None = None) -> pd.DataFrame:
        out = supply_df.copy()
        for other in (population_df, migration_df):
            if other is None or other.empty:
                continue
            keys = _keys(out, other)
            if not keys:
                continue
            extra = [c for c in other.columns if c not in out.columns or c in keys]
            out = out.merge(other[extra].drop_duplicates(keys), on=keys, how="left")

        if "new_households" not in out.columns and "households" in out.columns:
            sort_cols = [c for c in ("district_code", "ts") if c in out.columns]
            out = out.sort_values(sort_cols, kind="stable").reset_index(drop=True)
            hh = pd.to_numeric(out["households"], errors="coerce")
            out["new_households"] = (hh.groupby(out["district_code"]).diff()
                                     if "district_code" in out.columns else hh.diff())

        if "supply_units" in out.columns and ("new_households" in out.columns or "net_migration" in out.columns):
            demand = (pd.to_numeric(out.get("new_households", 0), errors="coerce").fillna(0)
                      + pd.to_numeric(out.get("net_migration", 0), errors="coerce").fillna(0))
            out["demand"] = demand
            out["supply_demand_gap"] = demand - pd.to_numeric(out["supply_units"], errors="coerce")
        if {"median_price", "median_income"} <= set(out.columns):
            out["pir"] = _div(out["median_price"], out["median_income"])
        if "unsold_units" in out.columns:
            absorb = out["absorption_units"] if "absorption_units" in out.columns else None
            if absorb is not None:
                out["months_of_inventory"] = _div(out["unsold_units"], absorb)
        return out
