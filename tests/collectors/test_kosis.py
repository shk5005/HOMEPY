import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.kosis import STATS, KosisCollector

FIXTURE = Path(__file__).parent / "fixtures" / "kosis_response.json"
URL = re.compile(r".*statisticsParameterData.*")
COLS = ["ts", "region_code", "region_name", "item_code", "item_name", "value", "unit"]


async def test_kosis_collects_population(tmp_path):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    collector = KosisCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=payload)
        path = await collector.collect("population", date(2025, 11, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 3
    assert df["value"].iloc[0] == 9331828
    assert df["region_name"].iloc[0] == "서울특별시"
    assert pd.Timestamp(df["ts"].iloc[-1]) == pd.Timestamp("2026-01-01")
    assert path.parent.parent.name == "kosis"
    assert path.name == "population.parquet"


@pytest.mark.parametrize("stat_id", ["population", "migration", "income", "cpi", "gdp"])
def test_known_stat_ids(stat_id):
    assert stat_id in STATS


async def test_kosis_unknown_stat_raises(tmp_path):
    collector = KosisCollector(api_key="test", data_dir=tmp_path)
    with pytest.raises(ValueError):
        await collector.collect("nope", date(2026, 1, 1), date(2026, 1, 31))


async def test_kosis_no_data_skips(tmp_path):
    collector = KosisCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json={"err": "30", "errMsg": "no data"})
        path = await collector.collect("cpi", date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0
    assert list(df.columns) == COLS


async def test_kosis_error_raises(tmp_path):
    collector = KosisCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json={"err": "10", "errMsg": "bad key"})
        with pytest.raises(ValueError):
            await collector.collect("cpi", date(2026, 1, 1), date(2026, 1, 31))


def test_kosis_requires_key(monkeypatch):
    monkeypatch.delenv("KOSIS_API_KEY", raising=False)
    with pytest.raises(ValueError):
        KosisCollector()
