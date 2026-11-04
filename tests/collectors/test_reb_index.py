import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.reb_index import RebIndexCollector

FIXTURE = Path(__file__).parent / "fixtures" / "reb_index_response.json"
URL = re.compile(r".*reb.*|.*PriceIndex.*", re.I)
COLS = ["ts", "region_code", "price_index", "price_change_mom", "price_change_yoy", "jeonse_index"]


async def test_reb_collects_index(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    collector = RebIndexCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=payload)
        path = await collector.collect(date(2025, 11, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 3
    assert df["price_index"].iloc[-1] == pytest.approx(102.1)
    assert df["jeonse_index"].iloc[0] == pytest.approx(99.8)
    assert df["region_code"].iloc[0] == "11000"
    assert pd.Timestamp(df["ts"].iloc[0]) == pd.Timestamp("2025-11-01")
    assert path.parent.parent.name == "reb_index"


async def test_reb_empty_response_skips(tmp_path):
    payload = {"response": {"header": {"resultCode": "00"}, "body": {"items": []}}}
    collector = RebIndexCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=payload)
        path = await collector.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0
    assert list(df.columns) == COLS


async def test_reb_error_code_raises(tmp_path):
    payload = {"response": {"header": {"resultCode": "30", "resultMsg": "bad key"}}}
    collector = RebIndexCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=payload)
        with pytest.raises(ValueError):
            await collector.collect(date(2026, 1, 1), date(2026, 1, 31))


def test_reb_requires_key(monkeypatch):
    monkeypatch.delenv("REB_API_KEY", raising=False)
    with pytest.raises(ValueError):
        RebIndexCollector()
