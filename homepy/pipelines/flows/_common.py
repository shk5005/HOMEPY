"""Shared orchestration machinery for the Prefect flows.

Flows are plain ``async`` functions decorated with Prefect's ``@flow`` when
Prefect is installed; otherwise the decorators are no-ops so the pipelines
remain importable and callable as ordinary coroutines.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from homepy.pipelines.stages.clean import clean_source
from homepy.pipelines.stages.load import load_to_timescale
from homepy.pipelines.stages.transform import transform_domain
from homepy.sync.timescale_to_typedb import SyncReport, sync_aggregates_to_typedb
from homepy.sync.typedb_to_timescale import sync_signals_to_timescale

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

try:  # pragma: no cover - exercised only when prefect is installed
    from prefect import flow as _prefect_flow
    from prefect import task as _prefect_task

    PREFECT_AVAILABLE = True
except ImportError:  # pragma: no cover
    PREFECT_AVAILABLE = False


def flow(name: str):
    """``@flow`` when Prefect is available, identity otherwise."""
    def deco(fn):
        if PREFECT_AVAILABLE:
            # Services / callables are injected objects, not pydantic-validatable.
            return _prefect_flow(name=name, validate_parameters=False)(fn)
        return fn
    return deco


def task(name: str):
    """``@task`` when Prefect is available, identity otherwise."""
    def deco(fn):
        if PREFECT_AVAILABLE:
            return _prefect_task(name=name)(fn)
        return fn
    return deco


@dataclass
class FlowResult:
    collected_sources: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)
    cleaned_count: int = 0
    loaded_rows: int = 0
    sync_report: Optional[SyncReport] = None
    errors: list[str] = field(default_factory=list)


Collector = Callable[[date, date], Awaitable[Path]]


@dataclass(frozen=True)
class SourceSpec:
    """A flow-level source: which clean/transform key its raw data belongs to."""
    clean_key: str                      # key understood by clean_source / transform_domain
    factory: Callable[[], Collector]    # builds the collector call lazily (needs API keys)


def _month(d: date) -> str:
    return d.strftime("%Y%m")


def _default_region() -> str:
    return os.environ.get("HOMEPY_REGION_CODE", "11680")


def _bok(start: date, end: date):
    from homepy.collectors.bok_ecos import BokEcosCollector
    return BokEcosCollector().collect(start, end)


def _trade(start: date, end: date):
    from homepy.collectors.molit_trade import MolitTradeCollector
    return MolitTradeCollector().collect(_default_region(), _month(start), _month(end))


def _reb(start: date, end: date):
    from homepy.collectors.reb_index import RebIndexCollector
    return RebIndexCollector().collect(start, end)


def _loan(start: date, end: date):
    from homepy.collectors.loan_rates import LoanRateCollector
    return LoanRateCollector().collect(start, end)


def _sentiment(start: date, end: date):
    from homepy.collectors.sentiment import SentimentCollector
    return SentimentCollector().collect(start, end)


def _building(start: date, end: date):
    from homepy.collectors.molit_building import MolitBuildingCollector
    code = _default_region()
    return MolitBuildingCollector().collect(code, os.environ.get("HOMEPY_DONG_CODE", "10100"))


def _supply(start: date, end: date):
    from homepy.collectors.molit_supply import MolitSupplyCollector
    return MolitSupplyCollector().collect(_default_region(), _month(start), _month(end))


def _kosis(stat_env: str):
    def run(start: date, end: date):
        from homepy.collectors.kosis import KosisCollector
        return KosisCollector().collect(os.environ.get(stat_env, ""), start, end)
    return run


def _regulation(start: date, end: date):
    from homepy.collectors.regulation_monitor import RegulationMonitor
    return RegulationMonitor().collect(start, end)


def _tax_rule(start: date, end: date):
    from homepy.collectors.tax_rule_monitor import TaxRuleMonitor
    return TaxRuleMonitor().collect(start, end)


def _spec(clean_key: str, fn) -> SourceSpec:
    return SourceSpec(clean_key, lambda: fn)


# flow-level source name -> spec. interest_rate/exchange_rate/liquidity
# are series served by the BOK ECOS collector; macro_index is a KOSIS series.
SOURCES: dict[str, SourceSpec] = {
    "real_trade": _spec("molit_trade", _trade),
    "interest_rate": _spec("bok_ecos", _bok),
    "exchange_rate": _spec("bok_ecos", _bok),
    "price_index": _spec("reb_index", _reb),
    "loan_rate": _spec("loan_rates", _loan),
    "sentiment": _spec("sentiment", _sentiment),
    "complex_info": _spec("molit_building", _building),
    "liquidity": _spec("bok_ecos", _bok),
    "macro_index": _spec("kosis", _kosis("KOSIS_MACRO_INDEX_STAT_ID")),
    "population": _spec("kosis", _kosis("KOSIS_POPULATION_STAT_ID")),
    "migration": _spec("kosis", _kosis("KOSIS_MIGRATION_STAT_ID")),
    "supply": _spec("molit_supply", _supply),
    "unsold": _spec("molit_supply", _supply),
    "regulation": _spec("regulation_monitor", _regulation),
    "tax_rule": _spec("tax_rule_monitor", _tax_rule),
}


# ---------------------------------------------------------------- tasks

@task("collect")
async def collect_task(name: str, collector: Collector, start: date, end: date) -> Path:
    return Path(await collector(start, end))


@task("clean")
async def clean_task(clean_key: str, raw_path: Path):
    return await asyncio.to_thread(clean_source, clean_key, raw_path)


@task("transform")
async def transform_task(domain: str, cleaned_paths: dict[str, Path]) -> Path:
    return await asyncio.to_thread(transform_domain, domain, cleaned_paths)


@task("load")
async def load_task(domain: str, path: Path, timescale_svc) -> int:
    return await load_to_timescale(domain, path, timescale_svc)


@task("sync_aggregates")
async def sync_aggregates_task(timescale_svc, typedb_svc) -> SyncReport:
    return await sync_aggregates_to_typedb(timescale_svc, typedb_svc)


@task("sync_signals")
async def sync_signals_task(typedb_svc, timescale_svc) -> int:
    return await sync_signals_to_timescale(typedb_svc, timescale_svc)


# ---------------------------------------------------------------- helpers

def _latest_cleaned(clean_key: str, data_dir: Path | str = "data") -> Optional[Path]:
    """Most recent cleaned file for a source, used when a domain needs a source
    this flow does not itself collect (e.g. cycle reclassify in the monthly flow)."""
    root = Path(data_dir) / "cleaned" / clean_key
    files = sorted(root.glob("*/*.parquet")) if root.exists() else []
    return files[-1] if files else None


async def collect_sources(names: list[str], start: date, end: date, collectors: dict[str, Collector],
                          result: FlowResult) -> dict[str, Path]:
    """Collect in parallel; one failure never aborts the others."""
    def get(n: str) -> Collector:
        return collectors[n] if n in collectors else SOURCES[n].factory()

    outcomes = await asyncio.gather(
        *(collect_task(n, get(n), start, end) for n in names), return_exceptions=True)
    raw: dict[str, Path] = {}
    for n, out in zip(names, outcomes):
        if isinstance(out, BaseException):
            logger.error("collect %s failed: %s", n, out)
            result.failed_sources.append(n)
            result.errors.append(f"collect:{n}: {type(out).__name__}: {out}")
        else:
            result.collected_sources.append(n)
            raw[n] = out
    return raw


async def clean_sources(raw: dict[str, Path], clean_keys: dict[str, str],
                        result: FlowResult) -> tuple[dict[str, Path], set[str]]:
    """Sequentially clean. Returns ``(cleaned, gate_failed)``, both keyed by flow-level source name.

    Sources sharing a clean key but with different raw files are each cleaned. Sources
    sharing the same raw file are cleaned once and the outcome is reused. ``gate_failed``
    holds sources whose clean step errored or failed the quality gate in this run.
    """
    cleaned: dict[str, Path] = {}
    gate_failed: set[str] = set()
    outcomes: dict[Path, Optional[Path]] = {}  # raw path -> cleaned path (None = failed)
    for name, path in raw.items():
        key = clean_keys[name]
        if path in outcomes:
            out = outcomes[path]
        else:
            out = None
            try:
                res = await clean_task(key, path)
            except Exception as exc:  # noqa: BLE001
                logger.error("clean %s failed: %s", key, exc)
                result.errors.append(f"clean:{key}: {type(exc).__name__}: {exc}")
            else:
                result.cleaned_count += 1
                if res.passed:
                    out = Path(res.output_path)
                else:
                    logger.error("quality gate failed for %s; excluded from load", key)
                    result.errors.append(f"quality_gate:{key}: failed, load stopped for this source")
            outcomes[path] = out
        if out is None:
            gate_failed.add(name)
        else:
            cleaned[name] = out
    return cleaned, gate_failed


async def transform_and_load(domains: dict[str, list[str]], cleaned: dict[str, Path], timescale_svc,
                             result: FlowResult, data_dir: Path | str = "data",
                             gate_failed: Optional[set[str]] = None,
                             clean_keys: Optional[dict[str, str]] = None) -> int:
    """Transform domains in parallel, then load each. ``domains``: domain -> required+optional inputs.

    ``cleaned`` / ``gate_failed`` are keyed by source name. An input is a source name or a
    clean key (matching any source with that clean key). Inputs with no fresh file fall back
    to the latest cleaned file on disk, except that a domain with an input that failed the
    gate in this run is skipped entirely (no stale fallback). A domain with no freshly
    cleaned input is skipped with an error. Returns rows loaded.
    """
    gate_failed = gate_failed or set()
    if clean_keys is None:
        clean_keys = {n: s.clean_key for n, s in SOURCES.items()}

    def matches(k: str, names) -> list[str]:
        return [n for n in names if n == k or clean_keys.get(n) == k]

    inputs: dict[str, dict[str, Path]] = {}
    for domain, keys in domains.items():
        paths: dict[str, Path] = {}
        fresh = False
        blocked: list[str] = []
        for k in keys:
            if matches(k, gate_failed):
                blocked.append(k)
                continue
            hit = matches(k, cleaned)
            if hit:
                paths[k] = cleaned[hit[0]]
                fresh = True
            else:
                p = _latest_cleaned(clean_keys.get(k, k), data_dir)
                if p is not None:
                    paths[k] = p
        if blocked:
            result.errors.append(f"transform:{domain}: input failed quality gate ({', '.join(blocked)}), skipped")
            continue
        if not fresh:
            result.errors.append(f"transform:{domain}: no freshly cleaned input, skipped")
            continue
        inputs[domain] = paths

    names = list(inputs)
    outs = await asyncio.gather(*(transform_task(d, inputs[d]) for d in names), return_exceptions=True)
    loaded = 0
    for domain, out in zip(names, outs):
        if isinstance(out, BaseException):
            logger.error("transform %s failed: %s", domain, out)
            result.errors.append(f"transform:{domain}: {type(out).__name__}: {out}")
            continue
        try:
            loaded += await load_task(domain, out, timescale_svc)
        except Exception as exc:  # noqa: BLE001
            logger.error("load %s failed: %s", domain, exc)
            result.errors.append(f"load:{domain}: {type(exc).__name__}: {exc}")
    result.loaded_rows += loaded
    return loaded


async def run_syncs(timescale_svc, typedb_svc, result: FlowResult) -> None:
    """sync_aggregates then sync_signals (inference trigger); failures are recorded, not raised."""
    try:
        result.sync_report = await sync_aggregates_task(timescale_svc, typedb_svc)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"sync_aggregates: {type(exc).__name__}: {exc}")
        return
    try:
        await sync_signals_task(typedb_svc, timescale_svc)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"sync_signals: {type(exc).__name__}: {exc}")


class _Services:
    """Use injected services, or build real ones from env and close them afterwards."""

    def __init__(self, timescale_svc, typedb_svc):
        self.timescale_svc, self.typedb_svc = timescale_svc, typedb_svc
        self._own: list[Any] = []

    async def __aenter__(self):
        if self.timescale_svc is None:
            from homepy.storage.timescale_service import TimescaleService
            self.timescale_svc = TimescaleService(os.environ["HOMEPY_TIMESCALE_DSN"])
            await self.timescale_svc.connect()
            self._own.append(self.timescale_svc)
        if self.typedb_svc is None:
            from homepy.storage.typedb_service import TypeDBService
            self.typedb_svc = TypeDBService(os.environ.get("HOMEPY_TYPEDB_ADDRESS", "localhost:1729"))
            self.typedb_svc.connect()
            self._own.append(self.typedb_svc)
        return self

    async def __aexit__(self, *exc):
        for svc in self._own:
            try:
                r = svc.close()
                if asyncio.iscoroutine(r):
                    await r
            except Exception:  # noqa: BLE001
                logger.exception("closing service failed")


async def run_scheduled(source_names: list[str], domains: dict[str, list[str]], start: date, end: date,
                        collectors: Optional[dict[str, Collector]], timescale_svc, typedb_svc,
                        data_dir: Path | str = "data") -> FlowResult:
    result = FlowResult()
    collectors = collectors or {}
    raw = await collect_sources(source_names, start, end, collectors, result)
    clean_keys = {n: SOURCES[n].clean_key for n in raw}
    cleaned, gate_failed = await clean_sources(raw, clean_keys, result)
    async with _Services(timescale_svc, typedb_svc) as svc:
        await transform_and_load(domains, cleaned, svc.timescale_svc, result, data_dir,
                                 gate_failed=gate_failed, clean_keys=clean_keys)
        await run_syncs(svc.timescale_svc, svc.typedb_svc, result)
    return result


def window(end: date | None, days: int) -> tuple[date, date]:
    end = end or datetime.now(KST).date()
    return end - timedelta(days=days), end
