import json
import re
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from homepy.collectors.bok_ecos import BokEcosCollector

FIXTURE = Path(__file__).parent / "fixtures" / "ecos_interest_rate_response.json"


@pytest.fixture
def mock_ecos_response():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


async def test_bok_ecos_collects_interest_rates(mock_ecos_response, tmp_path):
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(re.compile(r".*/StatisticSearch/.*")).respond(json=mock_ecos_response)
        result_path = await collector.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(result_path)
    assert "base_rate" in df.columns
    assert len(df) > 0
    for col in ["ts", "cd_rate_91d", "cofix_rate", "treasury_3y", "treasury_10y",
                "mortgage_rate_avg", "rate_direction"]:
        assert col in df.columns
    assert len(df) == 3
    assert df["base_rate"].iloc[-1] == 2.75
    assert result_path.parent.parent.name == "bok_ecos"
    assert result_path.name == "data.parquet"


async def test_rate_direction_from_three_month_trend(mock_ecos_response, tmp_path):
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(re.compile(r".*/StatisticSearch/.*")).respond(json=mock_ecos_response)
        df = pd.read_parquet(await collector.collect(date(2026, 1, 1), date(2026, 1, 31)))
    # 2.50 -> 2.75 over 3 rows: rising
    assert df["rate_direction"].iloc[-1] == "up"


async def test_fetch_retries_then_succeeds(tmp_path, monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr("homepy.collectors.base.asyncio.sleep", no_sleep)
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(re.compile(r".*/StatisticSearch/.*")).mock(
            side_effect=[httpx.Response(500), httpx.Response(500), httpx.Response(200, json={"ok": 1})]
        )
        data = await collector._fetch("StatisticSearch/x", {})
    assert data == {"ok": 1}
    assert route.call_count == 3


async def test_fetch_raises_after_three_attempts(tmp_path, monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr("homepy.collectors.base.asyncio.sleep", no_sleep)
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(re.compile(r".*/StatisticSearch/.*")).respond(500)
        with pytest.raises(httpx.HTTPStatusError):
            await collector._fetch("StatisticSearch/x", {})
    assert route.call_count == 3


async def test_api_error_payload_raises(tmp_path):
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(re.compile(r".*/StatisticSearch/.*")).respond(
            json={"RESULT": {"CODE": "INFO-200", "MESSAGE": "no data"}}
        )
        with pytest.raises(ValueError):
            await collector.collect(date(2026, 1, 1), date(2026, 1, 31))
