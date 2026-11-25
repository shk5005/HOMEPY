import re
from pathlib import Path

import httpx
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


async def test_molit_blank_body_is_no_data(tmp_path):
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text="")
        path = await collector.collect("11680", "202601", "202601")
    assert len(pd.read_parquet(path)) == 0


async def test_molit_code_03_is_no_data(tmp_path):
    xml = ("<response><header><resultCode>03</resultCode>"
           "<resultMsg>NODATA_ERROR</resultMsg></header></response>")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await collector.collect("11680", "202601", "202601")
    assert len(pd.read_parquet(path)) == 0


def _page(n, total, start=0):
    items = "".join(
        f"<item><sggCd>11680</sggCd><umdCd>10100</umdCd><aptNm>A{start + i}</aptNm>"
        "<excluUseAr>84.9</excluUseAr><floor>3</floor><dealAmount>100,000</dealAmount>"
        "<dealYear>2026</dealYear><dealMonth>1</dealMonth><dealDay>2</dealDay></item>"
        for i in range(n))
    return (f"<response><header><resultCode>000</resultCode></header><body><items>{items}</items>"
            f"<totalCount>{total}</totalCount></body></response>")


async def test_molit_paginates_when_total_exceeds_page(tmp_path, monkeypatch):
    monkeypatch.setattr("homepy.collectors.molit_trade.NUM_OF_ROWS", 2)
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).mock(side_effect=[
            httpx.Response(200, text=_page(2, 5)),
            httpx.Response(200, text=_page(2, 5, 2)),
            httpx.Response(200, text=_page(1, 5, 4)),
        ])
        path = await collector.collect("11680", "202601", "202601")
    assert route.call_count == 3
    assert len(pd.read_parquet(path)) == 5


async def test_molit_two_districts_do_not_collide(tmp_path):
    xml = FIXTURE.read_text(encoding="utf-8")
    collector = MolitTradeCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        p1 = await collector.collect("11680", "202601", "202601")
        p2 = await collector.collect("11650", "202601", "202601")
    assert p1 != p2 and p1.exists() and p2.exists()
    assert p1.parent.name == "2026-01-31"
