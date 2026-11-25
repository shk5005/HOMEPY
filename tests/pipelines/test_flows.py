from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from homepy.pipelines.flows import (
    FlowResult, daily_pipeline, event_pipeline, monthly_pipeline, weekly_pipeline)
from homepy.sync.timescale_to_typedb import SyncReport

D = date(2026, 1, 15)
TS = [datetime(2026, 1, 14, tzinfo=timezone.utc), datetime(2026, 1, 15, tzinfo=timezone.utc)]


def raw_file(tmp_path, source, df):
    p = tmp_path / "raw" / source / "2026-01-15" / "data.parquet"
    p.parent.mkdir(parents=True)
    df.to_parquet(p, index=False)
    return p


@pytest.fixture
def raws(tmp_path):
    return {
        "trade": raw_file(tmp_path, "molit_trade", pd.DataFrame({
            "ts": TS, "district_code": ["11680", "11680"], "trade_id": ["a", "b"],
            "complex_id": ["c", "c"], "price_krw": [100, 110], "area_m2": [84.0, 84.0]})),
        "bok": raw_file(tmp_path, "bok_ecos", pd.DataFrame({
            "ts": TS, "base_rate": [3.25, 3.25], "rate_direction": ["flat", "flat"]})),
    }


@pytest.fixture
def services(monkeypatch):
    ts, tdb = AsyncMock(), MagicMock()
    ts.insert_batch = AsyncMock(side_effect=lambda t, recs: len(recs))
    report = SyncReport()
    monkeypatch.setattr("homepy.pipelines.flows._common.sync_aggregates_to_typedb", AsyncMock(return_value=report))
    monkeypatch.setattr("homepy.pipelines.flows._common.sync_signals_to_timescale", AsyncMock(return_value=3))
    return ts, tdb, report


def collectors(raws, **overrides):
    c = {
        "real_trade": AsyncMock(return_value=raws["trade"]),
        "interest_rate": AsyncMock(return_value=raws["bok"]),
        "exchange_rate": AsyncMock(return_value=raws["bok"]),
    }
    c.update(overrides)
    return c


async def test_daily_flow_runs_end_to_end(raws, services, tmp_path):
    ts, tdb, report = services
    result = await daily_pipeline(date=D, collectors=collectors(raws), timescale_svc=ts, typedb_svc=tdb,
                                  data_dir=tmp_path)
    assert isinstance(result, FlowResult)
    assert result.collected_sources == ["real_trade", "interest_rate", "exchange_rate"]
    assert result.failed_sources == []
    assert result.cleaned_count == 2  # molit_trade + bok_ecos (shared raw file cleaned once)
    assert result.loaded_rows > 0
    assert result.sync_report is report
    assert result.errors == []


async def test_daily_flow_continues_when_collector_fails(raws, services, tmp_path):
    ts, tdb, _ = services
    c = collectors(raws, real_trade=AsyncMock(side_effect=RuntimeError("API down")))
    result = await daily_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert result.failed_sources == ["real_trade"]
    assert result.collected_sources == ["interest_rate", "exchange_rate"]
    assert result.loaded_rows > 0  # macro still loaded
    assert any(e.startswith("collect:real_trade") for e in result.errors)
    assert {call.args[0] for call in ts.insert_batch.await_args_list} <= {"ts_interest_rate", "ts_exchange_rate"}


async def test_quality_gate_failure_stops_load(raws, services, tmp_path):
    ts, tdb, _ = services
    bad = raw_file(tmp_path / "bad", "molit_trade", pd.DataFrame({
        "ts": TS, "district_code": [None, None], "trade_id": [None, None], "price_krw": [None, None]}))
    c = collectors(raws, real_trade=AsyncMock(return_value=bad))
    result = await daily_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert any(e.startswith("quality_gate:molit_trade") for e in result.errors)
    tables = {call.args[0] for call in ts.insert_batch.await_args_list}
    assert "ts_real_trade" not in tables
    assert "ts_interest_rate" in tables


async def test_all_collectors_fail_does_not_crash(services, tmp_path):
    ts, tdb, _ = services
    boom = {n: AsyncMock(side_effect=RuntimeError("x")) for n in ("real_trade", "interest_rate", "exchange_rate")}
    result = await daily_pipeline(date=D, collectors=boom, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert result.collected_sources == [] and result.loaded_rows == 0
    assert len(result.failed_sources) == 3


async def test_sync_failure_is_recorded(raws, services, tmp_path, monkeypatch):
    ts, tdb, _ = services
    monkeypatch.setattr("homepy.pipelines.flows._common.sync_aggregates_to_typedb",
                        AsyncMock(side_effect=RuntimeError("typedb down")))
    result = await daily_pipeline(date=D, collectors=collectors(raws), timescale_svc=ts, typedb_svc=tdb,
                                  data_dir=tmp_path)
    assert result.sync_report is None
    assert any(e.startswith("sync_aggregates") for e in result.errors)


async def test_weekly_flow(tmp_path, services):
    ts, tdb, _ = services
    sent = raw_file(tmp_path, "sentiment", pd.DataFrame({
        "ts": TS, "district_code": ["11680", "11680"], "buyer_sentiment": [60.0, 62.0],
        "seller_sentiment": [50.0, 51.0]}))
    c = {n: AsyncMock(side_effect=RuntimeError("n/a")) for n in ("price_index", "loan_rate", "complex_info")}
    c["sentiment"] = AsyncMock(return_value=sent)
    result = await weekly_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert result.collected_sources == ["sentiment"]
    assert sorted(result.failed_sources) == ["complex_info", "loan_rate", "price_index"]


async def test_monthly_flow_all_fail_is_graceful(services, tmp_path):
    ts, tdb, _ = services
    names = ["liquidity", "population", "migration", "supply", "unsold", "macro_index"]
    c = {n: AsyncMock(side_effect=RuntimeError("x")) for n in names}
    result = await monthly_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert result.failed_sources == names


async def test_event_flow_holds_without_approval(tmp_path):
    reg = raw_file(tmp_path, "regulation_monitor", pd.DataFrame({
        "ts": TS, "zone_type": ["adjust", "adjust"], "district_code": ["11680", "11650"], "action": ["add", "add"]}))
    c = {"regulation": AsyncMock(return_value=reg)}
    result = await event_pipeline("regulation", date=D, collectors=c)
    assert result.collected_sources == ["regulation"]
    assert result.loaded_rows == 0
    assert any("pending manual review" in e for e in result.errors)


async def test_event_flow_loads_when_approved(tmp_path, services):
    ts, tdb, report = services
    reg = raw_file(tmp_path, "regulation_monitor", pd.DataFrame({
        "ts": TS, "zone_type": ["adjust", "adjust"], "district_code": ["11680", "11650"], "action": ["add", "add"]}))
    loader = AsyncMock(return_value=2)
    result = await event_pipeline("regulation", date=D, collectors={"regulation": AsyncMock(return_value=reg)},
                                  approve=lambda t, p: True, loader=loader, timescale_svc=ts, typedb_svc=tdb)
    assert result.loaded_rows == 2 and result.sync_report is report
    loader.assert_awaited_once()


async def test_event_flow_rejects_unknown_type():
    with pytest.raises(ValueError):
        await event_pipeline("bogus")


# --- regression: shared clean key / gate-failure leakage -------------------

KOSIS_DF = pd.DataFrame({"ts": TS, "region_code": ["11680", "11680"], "item_code": ["a", "a"],
                         "value": [1.0, 2.0]})


def named_raw(tmp_path, source, filename, df):
    p = tmp_path / "raw" / source / "2026-01-15" / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p


@pytest.fixture
def spy_transform(monkeypatch, tmp_path):
    """Record transform inputs per domain; stub transform output and load."""
    calls = {}

    def fake(domain, paths, *a, **k):
        calls[domain] = dict(paths)
        return tmp_path / f"{domain}.parquet"

    monkeypatch.setattr("homepy.pipelines.flows._common.transform_domain", fake)
    monkeypatch.setattr("homepy.pipelines.flows._common.load_to_timescale", AsyncMock(return_value=1))
    return calls


async def test_monthly_cleans_both_population_and_migration(services, tmp_path, spy_transform):
    ts, tdb, _ = services
    supply = named_raw(tmp_path, "molit_supply", "supply.parquet", pd.DataFrame({
        "ts": TS, "district_code": ["11680", "11680"], "supply": [1, 2]}))
    pop = named_raw(tmp_path, "kosis", "pop.parquet", KOSIS_DF)
    mig = named_raw(tmp_path, "kosis", "mig.parquet", KOSIS_DF)
    c = {n: AsyncMock(side_effect=RuntimeError("x")) for n in ("liquidity", "macro_index")}
    c.update(supply=AsyncMock(return_value=supply), unsold=AsyncMock(return_value=supply),
             population=AsyncMock(return_value=pop), migration=AsyncMock(return_value=mig))
    result = await monthly_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert result.cleaned_count == 3  # supply (shared by unsold) + population + migration
    got = spy_transform["supply_demand"]
    assert got["population"].name == "pop.parquet"
    assert got["migration"].name == "mig.parquet"
    assert got["molit_supply"].name == "supply.parquet"


async def test_gate_failed_input_does_not_load_stale_data(services, tmp_path, spy_transform):
    ts, tdb, _ = services
    # Stale cleaned reb_index exists on disk; bok_ecos (liquidity) fails the gate this run.
    stale = tmp_path / "cleaned" / "reb_index" / "2025-12-15" / "old.parquet"
    stale.parent.mkdir(parents=True)
    pd.DataFrame({"ts": TS}).to_parquet(stale, index=False)
    bad_bok = named_raw(tmp_path, "bok_ecos", "bad.parquet", pd.DataFrame({"ts": [None, None]}))
    c = {n: AsyncMock(side_effect=RuntimeError("x"))
         for n in ("population", "migration", "supply", "unsold", "macro_index")}
    c["liquidity"] = AsyncMock(return_value=bad_bok)
    result = await monthly_pipeline(date=D, collectors=c, timescale_svc=ts, typedb_svc=tdb, data_dir=tmp_path)
    assert any(e.startswith("quality_gate:bok_ecos") for e in result.errors)
    assert "cycle" not in spy_transform and "macro" not in spy_transform
    assert any(e.startswith("transform:cycle") and "quality gate" in e for e in result.errors)
