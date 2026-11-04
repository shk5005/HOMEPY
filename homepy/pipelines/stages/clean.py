"""ETL Stage 1: clean & validate raw Parquet into data/cleaned."""
from __future__ import annotations

from collections import namedtuple
from pathlib import Path

import numpy as np
import pandas as pd

from homepy.pipelines.quality.gates import QualityGate

CleanResult = namedtuple("CleanResult", ["output_path", "quality_report", "passed"])

SOURCE_TIMEZONE = "Asia/Seoul"
IQR_FACTOR = 1.5

# Per-source natural dedup keys and expected schemas (column -> kind).
SOURCE_RULES: dict[str, dict] = {
    "bok_ecos": {"dedup_keys": ["ts"], "schema": {"ts": "datetime"}},
    "molit_trade": {"dedup_keys": None, "schema": {"ts": "datetime", "district_code": "str"}},
    "reb_index": {"dedup_keys": ["ts", "region_code"],
                  "schema": {"ts": "datetime", "region_code": "str", "price_index": "float"}},
    "kosis": {"dedup_keys": ["ts", "region_code", "item_code"],
              "schema": {"ts": "datetime", "region_code": "str", "item_code": "str", "value": "float"}},
    "molit_supply": {"dedup_keys": ["ts", "district_code"],
                     "schema": {"ts": "datetime", "district_code": "str"}},
    "molit_building": {"dedup_keys": None, "schema": {"ts": "datetime", "district_code": "str"}},
    "molit_official_price": {"dedup_keys": ["ts", "district_code", "dong_code", "complex_name", "area_sqm"],
                             "schema": {"ts": "datetime", "district_code": "str", "official_price": "float"}},
    "loan_rates": {"dedup_keys": ["ts", "loan_type", "lender_type", "interest_type"],
                   "schema": {"ts": "datetime", "rate_min": "float", "rate_max": "float"}},
    "regulation_monitor": {"dedup_keys": ["ts", "zone_type", "district_code", "action"],
                   "schema": {"ts": "datetime", "zone_type": "str"}},
    "tax_rule_monitor": {"dedup_keys": ["ts", "law_name", "article", "change_type"],
                 "schema": {"ts": "datetime", "law_name": "str"}},
    "sentiment": {"dedup_keys": ["ts", "district_code"],
                  "schema": {"ts": "datetime", "district_code": "str"}},
}
DEFAULT_RULES: dict = {"dedup_keys": None, "schema": {}}  # None -> all columns


def _rules_for(source_name: str) -> dict:
    return SOURCE_RULES.get(source_name, DEFAULT_RULES)


def _one_ts_to_utc(value) -> pd.Timestamp:
    try:
        t = pd.Timestamp(value)
    except (ValueError, TypeError):
        return pd.NaT
    if pd.isna(t):
        return pd.NaT
    if t.tzinfo is None:
        try:
            t = t.tz_localize(SOURCE_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
        except (ValueError, TypeError):
            return pd.NaT
        if pd.isna(t):
            return pd.NaT
    return t.tz_convert("UTC")


def _ts_to_utc(series: pd.Series) -> pd.Series:
    """Parse to datetime; naive values are KST, tz-aware are converted; result is UTC."""
    try:
        parsed = pd.to_datetime(series, errors="coerce", utc=False)
        if not pd.api.types.is_datetime64_any_dtype(parsed):  # e.g. all-None
            parsed = pd.to_datetime(series, errors="coerce", utc=True)
        if parsed.isna().sum() > series.isna().sum():
            raise ValueError("values coerced to NaT; retry per value")
        if parsed.dt.tz is None:
            parsed = parsed.dt.tz_localize(SOURCE_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
        return parsed.dt.tz_convert("UTC")
    except ValueError:  # mixed naive/offset-bearing values: convert one by one
        converted = [_one_ts_to_utc(v) for v in series]
        return pd.Series(pd.to_datetime(converted, utc=True), index=series.index, name=series.name)


def _standardize_codes(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if col.endswith("_code") and (
            pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])
        ):
            df[col] = df[col].astype("string").str.strip()
    return df


def flag_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Add boolean ``_outlier``: any numeric value beyond 1.5*IQR of Q1/Q3. Never drops rows."""
    flags = pd.Series(False, index=df.index)
    for col in df.select_dtypes(include="number").columns:
        if pd.api.types.is_bool_dtype(df[col]) or col == "_outlier":
            continue
        s = df[col].replace([np.inf, -np.inf], np.nan)
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        if pd.isna(q1) or pd.isna(q3):
            continue
        iqr = q3 - q1
        flags |= (s < q1 - IQR_FACTOR * iqr) | (s > q3 + IQR_FACTOR * iqr)
    df["_outlier"] = flags.fillna(False).astype(bool)
    return df


def clean_source(
    source_name: str,
    raw_path: Path | str,
    data_dir: Path | str | None = None,
    gate: QualityGate | None = None,
) -> CleanResult:
    """Clean one raw Parquet file and write ``{data_dir}/cleaned/{source}/{date}/{file}``.

    The quality gate is evaluated on the raw data (so duplicates and nulls are
    reported before cleaning removes them). ``data_dir`` defaults to the root
    implied by ``{data_dir}/raw/{source}/{date}/file.parquet``.
    """
    raw_path = Path(raw_path)
    rules = _rules_for(source_name)
    gate = gate or QualityGate(null_ratio_max=0.05, duplicate_ratio_max=0.01, schema_match=True)

    df = pd.read_parquet(raw_path)
    if "ts" in df.columns:
        df["ts"] = _ts_to_utc(df["ts"])  # Global constraint #3: KST -> UTC in Stage 1
    df = _standardize_codes(df)

    keys = rules["dedup_keys"]
    subset = [k for k in keys if k in df.columns] if keys else None
    report = gate.check(df, rules["schema"], duplicate_subset=subset)

    cleaned = df.drop_duplicates(subset=subset or None).reset_index(drop=True)
    cleaned = flag_outliers(cleaned)

    if data_dir is None:
        data_dir = raw_path.parents[3] if raw_path.parent.parent.parent.name == "raw" else raw_path.parent
    date_str = raw_path.parent.name
    out_dir = Path(data_dir) / "cleaned" / source_name / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / raw_path.name
    cleaned.to_parquet(output_path, index=False)

    return CleanResult(output_path=output_path, quality_report=report, passed=report.passed)
