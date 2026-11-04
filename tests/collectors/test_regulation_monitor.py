import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.regulation_monitor import RegulationMonitor

FIXTURE = Path(__file__).parent / "fixtures" / "regulation_response.json"
URL = re.compile(r".*regulation.*")
BASE = "https://feeds.example.test/regulation"
COLS = ["ts", "zone_type", "district_code", "action"]


async def test_regulation_parse_and_normalize(tmp_path):
    m = RegulationMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await m.collect(date(2026, 1, 1), date(2026, 3, 31))
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert list(df["action"]) == ["designate", "release", "designate"]
    assert df["zone_type"].iloc[0] == "조정대상지역"


async def test_regulation_filters_date_range(tmp_path):
    m = RegulationMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await m.collect(date(2026, 2, 1), date(2026, 2, 28))
    df = pd.read_parquet(path)
    assert len(df) == 1 and df["district_code"].iloc[0] == "11710"


async def test_regulation_empty_skips(tmp_path):
    m = RegulationMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text="")
        path = await m.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_regulation_unknown_action_raises(tmp_path):
    m = RegulationMonitor(base_url=BASE, data_dir=tmp_path)
    body = {"items": [{"date": "2026-01-10", "zone_type": "x", "district_code": "1", "action": "???"}]}
    with respx.mock:
        respx.get(URL).respond(json=body)
        with pytest.raises(ValueError):
            await m.collect(date(2026, 1, 1), date(2026, 1, 31))


def test_regulation_requires_base_url(monkeypatch):
    monkeypatch.delenv("REGULATION_API_URL", raising=False)
    with pytest.raises(ValueError):
        RegulationMonitor()
