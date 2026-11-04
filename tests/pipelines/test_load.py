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
