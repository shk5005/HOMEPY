import re
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.molit_building import MolitBuildingCollector

FIXTURE = Path(__file__).parent / "fixtures" / "molit_building_response.xml"
URL = re.compile(r".*getBrTitleInfo.*")
COLS = ["ts", "district_code", "dong_code", "building_name", "main_purpose",
        "total_area_sqm", "floors_above", "floors_below", "households"]


async def test_building_parses(tmp_path):
    c = MolitBuildingCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect("11680", "10300")
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 2
    assert df["building_name"].iloc[1] == "은마"
    assert df["households"].iloc[1] == 4424
    assert pd.Timestamp(df["ts"].iloc[0]) == pd.Timestamp("2015-03-10")
    assert path.name == "11680_10300.parquet"
    assert path.parent.parent.name == "molit_building"


async def test_building_empty_skips(tmp_path):
    xml = "<response><header><resultCode>03</resultCode><resultMsg>NO DATA</resultMsg></header></response>"
    c = MolitBuildingCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        path = await c.collect("11680", "10300")
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_building_error_raises(tmp_path):
    xml = "<response><header><resultCode>30</resultCode><resultMsg>BAD KEY</resultMsg></header></response>"
    c = MolitBuildingCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=xml)
        with pytest.raises(ValueError, match="BAD KEY"):
            await c.collect("11680", "10300")


async def test_building_paginates(tmp_path):
    xml = FIXTURE.read_text(encoding="utf-8").replace("<totalCount>2</totalCount>", "<totalCount>3</totalCount>")
    c = MolitBuildingCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(text=xml)
        await c.collect("11680", "10300")
    assert route.call_count == 2
