from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from homepy.pipelines.stages.load import load_to_timescale


class FakeTimescale:
    def __init__(self):
        self.calls: list[tuple[str, list[dict]]] = []

    async def insert_batch(self, table, records):
        self.calls.append((table, records))
        return len(records)


def save(df, tmp_path, name="macro.parquet"):
    p = tmp_path / name
    df.to_parquet(p, index=False)
    return p


async def test_load_to_timescale_inserts_rows(tmp_path):
    df = pd.DataFrame({
        "ts": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
        "base_rate": [3.25], "rate_direction": ["falling"],
    })
    svc = FakeTimescale()
    assert await load_to_timescale("macro", save(df, tmp_path), svc) == 1
    table, recs = svc.calls[0]
    assert table == "ts_interest_rate"
    assert set(recs[0]) == {"ts", "base_rate"}  # rate_direction not a column -> dropped
    assert recs[0]["base_rate"] == 3.25
    assert recs[0]["ts"].tzinfo is not None


async def test_macro_split_across_tables_and_nan_to_none(tmp_path):
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-01", "2026-02-01"], utc=True),
        "base_rate": [3.25, np.nan], "usd_krw": [1300.5, 1310.0],
    })
    svc = FakeTimescale()
    total = await load_to_timescale("macro", save(df, tmp_path), svc)
    by = {t: r for t, r in svc.calls}
    assert set(by) == {"ts_interest_rate", "ts_exchange_rate"}
    assert len(by["ts_interest_rate"]) == 1  # all-null payload row dropped
    assert len(by["ts_exchange_rate"]) == 2
    assert total == 3


async def test_directory_and_dedupe(tmp_path):
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01"] * 2, utc=True),
                       "district_code": ["11680"] * 2, "buyer_sentiment": [50.0, 60.0]})
    df.to_parquet(tmp_path / "sentiment.parquet", index=False)
    svc = FakeTimescale()
    assert await load_to_timescale("sentiment", tmp_path, svc) == 1
    assert svc.calls[0][1][0]["buyer_sentiment"] == 60.0


async def test_skips_table_missing_required_columns(tmp_path):
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01"], utc=True), "price_krw": [1]})
    svc = FakeTimescale()
    assert await load_to_timescale("price", save(df, tmp_path), svc) == 0
    assert svc.calls == []


async def test_unknown_domain_and_missing_ts(tmp_path):
    p = save(pd.DataFrame({"x": [1]}), tmp_path)
    with pytest.raises(ValueError):
        await load_to_timescale("bogus", p, FakeTimescale())
    with pytest.raises(ValueError):
        await load_to_timescale("macro", p, FakeTimescale())


async def test_integer_columns_cast_and_index_type_key(tmp_path):
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-01"] * 3, utc=True),
        "district_code": ["11680"] * 3,
        "index_type": ["sale", "lease", "sale"],
        "index_value": [1.0, 2.0, 3.0],
        "trade_volume": [1000.0, np.nan, 5.0],
    })
    svc = FakeTimescale()
    await load_to_timescale("cycle", save(df, tmp_path), svc)
    recs = svc.calls[0][1]
    assert len(recs) == 2  # sale (deduped, last) + lease
    vols = {r["index_type"]: r["trade_volume"] for r in recs}
    assert vols == {"sale": 5, "lease": None}
    assert isinstance(vols["sale"], int)


async def test_trade_renames_price_units_and_synthetic_keys(tmp_path):
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-01"], utc=True), "district_code": ["11680"],
        "dong_code": ["10100"], "complex_name": ["A"], "floor": [5], "price": [85000],
        "area_sqm": [84.9],
    })
    svc = FakeTimescale()
    await load_to_timescale("price", save(df, tmp_path), svc)
    table, recs = svc.calls[0]
    assert table == "ts_real_trade"
    r = recs[0]
    assert r["price_krw"] == 850_000_000 and r["area_m2"] == 84.9
    assert len(r["trade_id"]) <= 40 and len(r["complex_id"]) <= 20


async def test_interest_rate_and_cycle_renames(tmp_path):
    macro = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01"], utc=True), "cd_rate_91d": [3.1],
                          "cofix_rate": [3.5], "mortgage_rate_avg": [4.2]})
    svc = FakeTimescale()
    await load_to_timescale("macro", save(macro, tmp_path), svc)
    assert {"cd_rate", "cofix", "mortgage_rate"} <= set(svc.calls[0][1][0])

    reb = pd.DataFrame({"ts": pd.to_datetime(["2026-01-01"], utc=True), "region_code": ["11680"],
                        "price_index": [100.0], "price_change_mom": [0.5], "price_change_yoy": [2.0]})
    svc = FakeTimescale()
    await load_to_timescale("cycle", save(reb, tmp_path, "reb.parquet"), svc)
    rec = svc.calls[0][1][0]
    assert rec["district_code"] == "11680" and rec["index_type"] == "price"
    assert rec["index_value"] == 100.0 and rec["change_mom_pct"] == 0.5 and rec["change_yoy_pct"] == 2.0


async def test_supply_unsold_sentiment_renames(tmp_path):
    base = {"ts": pd.to_datetime(["2026-01-01"], utc=True), "district_code": ["11680"]}
    sd = pd.DataFrame({**base, "permits_issued": [10.0], "construction_starts": [5.0], "unsold_total": [7.0]})
    svc = FakeTimescale()
    await load_to_timescale("supply_demand", save(sd, tmp_path), svc)
    by = {t: r[0] for t, r in svc.calls}
    assert by["ts_supply"]["permits"] == 10 and by["ts_supply"]["starts"] == 5
    assert by["ts_unsold"]["total_unsold"] == 7

    se = pd.DataFrame({**base, "search_trend_index": [60.0], "fear_greed_index": [40.0]})
    svc = FakeTimescale()
    await load_to_timescale("sentiment", save(se, tmp_path, "s.parquet"), svc)
    assert svc.calls[0][1][0]["search_trend"] == 60.0 and svc.calls[0][1][0]["fear_greed"] == 40.0
