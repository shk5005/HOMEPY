import re
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.molit_supply import MolitSupplyCollector

FIXTURE = Path(__file__).parent / "fixtures" / "molit_supply_response.xml"
URL = re.compile(r".*getSupply.*")
COLS = ["ts", "district_code", "permits_issued", "construction_starts", "completions",
        "presale_volume", "unsold_total", "unsold_after_completion"]


async def test_supply_parses(tmp_path):
    c = MolitSupplyCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect("11680", "202601", "202601")
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 2
    assert df["unsold_total"].iloc[0] == 1200
    assert pd.Timestamp(df["ts"].iloc[1]) == pd.Timestamp("2026-02-01")
    assert path.name == "11680_202601_202601.parquet"
    assert path.parent.parent.name == "molit_supply"


async def test_supply_empty_skips(tmp_path):
    xml = "<response><header><resultCode>003</resultCode><resultMsg>NO DATA</resultMsg></header></response>"
    c = MolitSupplyCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await c.collect("11680", "202601", "202601")
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_supply_error_does_not_leak_key(tmp_path):
    c = MolitSupplyCollector(api_key="SECRETKEY", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(status_code=500)
        with pytest.raises(RuntimeError) as ei:
            await c.collect("11680", "202601", "202601")
    assert "SECRETKEY" not in str(ei.value)


async def test_supply_paginates(tmp_path):
    xml = FIXTURE.read_text(encoding="utf-8").replace("<totalCount>2</totalCount>", "<totalCount>3</totalCount>")
    c = MolitSupplyCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(text=xml)
        await c.collect("11680", "202601", "202601")
    assert route.call_count == 2


def test_supply_requires_key(monkeypatch):
    monkeypatch.delenv("MOLIT_API_KEY", raising=False)
    with pytest.raises(ValueError):
        MolitSupplyCollector()
