import re
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.molit_official_price import MolitOfficialPriceCollector

FIXTURE = Path(__file__).parent / "fixtures" / "molit_official_price_response.xml"
URL = re.compile(r".*getApartHousingPrice.*")
COLS = ["ts", "district_code", "dong_code", "complex_name", "area_sqm", "official_price"]


async def test_official_price_parses(tmp_path):
    c = MolitOfficialPriceCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect("11680", 2025, 2026)
    assert route.call_count == 2  # one per year
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert df["official_price"].iloc[0] == 1_250_000_000
    assert pd.Timestamp(df["ts"].iloc[0]) == pd.Timestamp("2025-01-01")
    assert path.name == "11680_2025_2026.parquet"


async def test_official_price_empty_skips(tmp_path):
    xml = "<response><header><resultCode>003</resultCode><resultMsg>NO DATA</resultMsg></header></response>"
    c = MolitOfficialPriceCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await c.collect("11680", 2025, 2025)
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_official_price_http_error_no_key_leak(tmp_path):
    c = MolitOfficialPriceCollector(api_key="SECRETKEY", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(status_code=503)
        with pytest.raises(RuntimeError) as ei:
            await c.collect("11680", 2025, 2025)
    assert "SECRETKEY" not in str(ei.value)
