"""ETL Stage 3: load transformed Parquet into TimescaleDB."""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableSpec:
    """Target hypertable: columns it accepts, primary key, and NOT NULL columns."""

    name: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    required: tuple[str, ...]


def _spec(name: str, columns: str, key: str, required: str | None = None) -> TableSpec:
    k = tuple(key.split())
    return TableSpec(name, tuple(columns.split()), k, tuple(required.split()) if required else k)


# Column lists mirror storage/timescale/schema.sql.
TABLES: dict[str, TableSpec] = {
    s.name: s
    for s in (
        _spec("ts_real_trade",
              "ts trade_id complex_id district_code price_krw area_m2 floor build_year "
              "price_per_pyeong trade_type is_cancelled",
              "ts complex_id trade_id", "ts trade_id complex_id district_code price_krw"),
        _spec("ts_price_index",
              "ts district_code index_type index_value change_wow_pct change_mom_pct "
              "change_yoy_pct trade_volume", "ts district_code index_type",
              "ts district_code"),
        _spec("ts_interest_rate",
              "ts base_rate cd_rate treasury_3y treasury_10y mortgage_rate jeonse_loan_rate cofix",
              "ts"),
        _spec("ts_exchange_rate", "ts usd_krw change_pct jpy_krw_100 eur_krw cny_krw", "ts"),
        _spec("ts_liquidity",
              "ts m2 m2_change_yoy_pct household_credit mortgage_balance jeonse_loan_balance", "ts"),
        _spec("ts_macro_index",
              "ts cpi cpi_change_yoy_pct gdp_growth unemployment leading_index "
              "construction_cost_index", "ts"),
        _spec("ts_population",
              "ts district_code total_pop households pop_change age_20_39_pop age_65_plus_pop "
              "avg_household_size", "ts district_code"),
        _spec("ts_migration", "ts district_code net_migration in_migration out_migration",
              "ts district_code"),
        _spec("ts_income", "ts district_code median_income avg_income pir growth_rate",
              "ts district_code"),
        _spec("ts_supply", "ts district_code permits starts completions planned_supply",
              "ts district_code"),
        _spec("ts_unsold", "ts district_code total_unsold unsold_after_completion unsold_change",
              "ts district_code"),
        _spec("ts_sentiment",
              "ts district_code buyer_sentiment seller_sentiment jeonse_ratio fear_greed "
              "search_trend", "ts district_code"),
    )
}

# INTEGER/BIGINT/SMALLINT columns (pandas upcasts them to float when NaN is present).
INT_COLUMNS: dict[str, tuple[str, ...]] = {
    "ts_real_trade": ("price_krw", "floor", "build_year"),
    "ts_price_index": ("trade_volume",),
    "ts_population": ("total_pop", "households", "pop_change", "age_20_39_pop", "age_65_plus_pop"),
    "ts_migration": ("net_migration", "in_migration", "out_migration"),
    "ts_income": ("median_income", "avg_income"),
    "ts_supply": ("permits", "starts", "completions", "planned_supply"),
    "ts_unsold": ("total_unsold", "unsold_after_completion", "unsold_change"),
}

# Transformed domain -> candidate tables. A frame is split across every table
# for which it carries at least one non-key column.
DOMAIN_TABLES: dict[str, tuple[str, ...]] = {
    "price": ("ts_real_trade",),
    "macro": ("ts_interest_rate", "ts_exchange_rate", "ts_liquidity", "ts_macro_index"),
    "cycle": ("ts_price_index",),
    "supply_demand": ("ts_supply", "ts_population", "ts_migration", "ts_income", "ts_unsold"),
    "sentiment": ("ts_sentiment",),
}


# Collector/transform column name -> DB column name. Applied before matching
# against TableSpec; a rename is skipped if the target column already exists.
COLUMN_RENAMES: dict[str, str] = {
    # molit_trade -> ts_real_trade
    "price": "price_krw",  # value also converted 만원 -> won (see _prepare)
    "area_sqm": "area_m2",
    # bok_ecos -> ts_interest_rate
    "cd_rate_91d": "cd_rate",
    "cofix_rate": "cofix",
    "mortgage_rate_avg": "mortgage_rate",
    # reb_index -> ts_price_index
    "region_code": "district_code",
    "price_index": "index_value",
    "price_change_mom": "change_mom_pct",
    "price_change_yoy": "change_yoy_pct",
    # molit_supply -> ts_supply / ts_unsold
    "permits_issued": "permits",
    "construction_starts": "starts",
    "unsold_total": "total_unsold",
    # sentiment / sentiment_composer -> ts_sentiment
    "search_trend_index": "search_trend",
    "fear_greed_index": "fear_greed",
}

MAN_WON = 10_000  # MOLIT reports prices in 만원


def _hash(*parts, length: int) -> str:
    raw = "|".join("" if p is None or (isinstance(p, float) and math.isnan(p)) else str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:length]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Rename collector columns to DB names and derive synthetic keys."""
    df = df.copy()
    if "price" in df.columns and "price_krw" not in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce") * MAN_WON
    renames = {k: v for k, v in COLUMN_RENAMES.items() if k in df.columns and v not in df.columns}
    df = df.rename(columns=renames)

    if "index_value" in df.columns and "index_type" not in df.columns:
        df["index_type"] = "price"

    if "price_krw" in df.columns and "district_code" in df.columns:
        cols = df.columns
        get = lambda name: df[name] if name in cols else pd.Series([None] * len(df), index=df.index)  # noqa: E731
        if "trade_id" not in cols:
            df["trade_id"] = [
                _hash(*vals, length=32)
                for vals in zip(get("ts"), get("district_code"), get("dong_code"),
                                get("floor"), get("price_krw"))
            ]
        if "complex_id" not in cols and "complex_name" in cols:
            df["complex_id"] = [
                _hash(n, d, length=16) for n, d in zip(df["complex_name"], df["district_code"])
            ]
    return df


def _read(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"no parquet files in {path}")
        return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return pd.read_parquet(path)


def _py(value, as_int: bool = False):
    """Convert pandas/numpy scalars to plain Python values for asyncpg (NaN/NaT -> None)."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer() and as_int:
            return int(value)
    return value


def _records_for(df: pd.DataFrame, spec: TableSpec) -> list[dict]:
    cols = [c for c in spec.columns if c in df.columns]
    missing = [c for c in spec.required if c not in df.columns]
    if missing:
        logger.warning("skip %s: missing required columns %s", spec.name, missing)
        return []
    if not [c for c in cols if c not in spec.key]:
        return []
    sub = df[cols].copy()
    sub["ts"] = pd.to_datetime(sub["ts"], utc=True)
    sub = sub.dropna(subset=list(spec.required))
    sub = sub.drop_duplicates(subset=list(spec.key), keep="last")
    payload = [c for c in cols if c not in spec.key]
    sub = sub.dropna(subset=payload, how="all")
    int_cols = {c for c in cols if c in INT_COLUMNS.get(spec.name, ())}
    return [{c: _py(v, c in int_cols) for c, v in row.items()} for row in sub.to_dict("records")]


async def load_to_timescale(domain: str, transformed_path: Path, timescale_svc) -> int:
    """Bulk-insert a transformed Parquet file (or directory) into TimescaleDB.

    Columns not present in the target table are dropped; returns total rows inserted.
    """
    if domain not in DOMAIN_TABLES:
        raise ValueError(f"unknown domain {domain!r}; expected one of {sorted(DOMAIN_TABLES)}")
    df = _read(transformed_path)
    if "ts" not in df.columns:
        raise ValueError(f"transformed data for {domain!r} has no 'ts' column")
    df = _prepare(df)
    total = 0
    for table in DOMAIN_TABLES[domain]:
        records = _records_for(df, TABLES[table])
        if records:
            total += await timescale_svc.insert_batch(table, records)
    return total
