"""ETL Stage 2: transform & enrich cleaned Parquet into data/transformed."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.pipelines.transformers import (
    CycleClassifier,
    MacroTransformer,
    PriceTransformer,
    SentimentComposer,
    SupplyDemandTransformer,
)

logger = logging.getLogger(__name__)

OUTLIER_RATIO_MAX = 0.02  # spec 4.6: cleaned -> transformed gate

# Source-name aliases accepted per role; first match wins.
PRICE_SOURCES = ("molit_trade", "price")
MACRO_SOURCES = ("bok_ecos", "macro")
PRICE_INDEX_SOURCES = ("reb_index", "price_index")
SUPPLY_SOURCES = ("molit_supply", "supply")
POPULATION_SOURCES = ("population", "kosis_population", "kosis")
MIGRATION_SOURCES = ("migration", "kosis_migration")
SENTIMENT_SOURCES = ("sentiment",)
VOLUME_SOURCES = ("volume", "trade_volume")
JEONSE_SOURCES = ("jeonse", "jeonse_ratio")
SEARCH_SOURCES = ("search", "search_trend")

DOMAINS = ("price", "macro", "cycle", "supply_demand", "sentiment")


def _pick(paths: dict[str, Path], names: tuple[str, ...], required: bool = False) -> pd.DataFrame | None:
    for n in names:
        if n in paths:
            return pd.read_parquet(paths[n])
    if required:
        raise ValueError(f"missing required cleaned source (one of {names}); got {sorted(paths)}")
    return None


def _check_gate(df: pd.DataFrame, label: str) -> None:
    """Outlier-ratio gate. Warn only; _outlier flags stay in the data for downstream use."""
    if "_outlier" in df.columns and len(df):
        ratio = float(df["_outlier"].mean())
        if ratio > OUTLIER_RATIO_MAX:
            logger.warning("%s outlier ratio %.3f exceeds %.2f", label, ratio, OUTLIER_RATIO_MAX)
    if "ts" in df.columns and df["ts"].is_monotonic_increasing is False and "district_code" not in df.columns:
        logger.info("%s: ts not sorted; transformers sort before computing", label)


def _output_dir(domain: str, cleaned_paths: dict[str, Path], data_dir: Path | str | None) -> Path:
    first = Path(next(iter(cleaned_paths.values())))
    if data_dir is None:
        data_dir = first.parents[3] if first.parent.parent.parent.name == "cleaned" else first.parent
    date_str = first.parent.name
    try:
        date.fromisoformat(date_str)
    except ValueError:
        date_str = date.today().isoformat()
    out = Path(data_dir) / "transformed" / domain / date_str
    out.mkdir(parents=True, exist_ok=True)
    return out


def transform_domain(domain: str, cleaned_paths: dict[str, Path],
                     data_dir: Path | str | None = None) -> Path:
    """Run the transformer pipeline for ``domain`` and write ``{data_dir}/transformed/{domain}/{date}/{domain}.parquet``."""
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}; expected one of {DOMAINS}")
    if not cleaned_paths:
        raise ValueError("cleaned_paths is empty")
    cleaned_paths = {k: Path(v) for k, v in cleaned_paths.items()}

    if domain == "price":
        df = _pick(cleaned_paths, PRICE_SOURCES, required=True)
        _check_gate(df, domain)
        result = PriceTransformer().transform(df)
    elif domain == "macro":
        df = _pick(cleaned_paths, MACRO_SOURCES, required=True)
        _check_gate(df, domain)
        result = MacroTransformer().transform(df)
    elif domain == "cycle":
        price_index = _pick(cleaned_paths, PRICE_INDEX_SOURCES, required=True)
        macro = _pick(cleaned_paths, MACRO_SOURCES)
        _check_gate(price_index, domain)
        if macro is not None:
            macro = MacroTransformer().transform(macro)
        result = CycleClassifier().classify(price_index, macro)
    elif domain == "supply_demand":
        supply = _pick(cleaned_paths, SUPPLY_SOURCES, required=True)
        _check_gate(supply, domain)
        result = SupplyDemandTransformer().transform(
            supply, _pick(cleaned_paths, POPULATION_SOURCES), _pick(cleaned_paths, MIGRATION_SOURCES))
    else:  # sentiment
        sentiment = _pick(cleaned_paths, SENTIMENT_SOURCES, required=True)
        _check_gate(sentiment, domain)
        result = SentimentComposer().compose(
            sentiment, _pick(cleaned_paths, VOLUME_SOURCES),
            _pick(cleaned_paths, JEONSE_SOURCES), _pick(cleaned_paths, SEARCH_SOURCES))

    out_path = _output_dir(domain, cleaned_paths, data_dir) / f"{domain}.parquet"
    result.to_parquet(out_path, index=False)
    return out_path
