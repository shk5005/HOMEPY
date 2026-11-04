import re
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.molit_trade import MolitTradeCollector

FIXTURE = Path(__file__).parent / "fixtures" / "molit_trade_response.xml"
URL = re.compile(r".*getRTMSDataSvcAptTrade.*")
COLS = ["ts", "district_code", "dong_code", "complex_name", "area_sqm", "floor", "price", "trade_type"]


async def test_molit_parses_xml_to_parquet(tmp_path):
    xml = FIXTURE.read_text(encoding="utf-8")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await collector.collect("11680", "202601", "202601")
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 2
    assert df["price"].iloc[0] == 185000
    assert df["area_sqm"].iloc[0] == pytest.approx(84.97)
    assert df["complex_name"].iloc[1] == "은마"
    assert df["district_code"].iloc[0] == "11680"
    assert df["trade_type"].iloc[0] == "sale"
    assert pd.Timestamp(df["ts"].iloc[0]) == pd.Timestamp("2026-01-15")
    assert path.parent.parent.name == "molit_trade"


async def test_molit_queries_each_month(tmp_path):
    xml = FIXTURE.read_text(encoding="utf-8")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(text=xml)
        await collector.collect("11680", "202601", "202603")
    assert route.call_count == 3


async def test_molit_empty_response_skips(tmp_path):
    xml = ("<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>"
           "<body><items/><totalCount>0</totalCount></body></response>")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await collector.collect("11680", "202601", "202601")
    df = pd.read_parquet(path)
    assert len(df) == 0
    assert list(df.columns) == COLS


async def test_molit_error_code_raises(tmp_path):
    xml = ("<response><header><resultCode>30</resultCode>"
           "<resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header></response>")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        with pytest.raises(ValueError):
            await collector.collect("11680", "202601", "202601")


def test_molit_requires_key(monkeypatch):
    monkeypatch.delenv("MOLIT_API_KEY", raising=False)
    with pytest.raises(ValueError):
        MolitTradeCollector()
