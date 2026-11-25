import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.sentiment import SentimentCollector

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment_response.json"
URL = re.compile(r".*sentiment.*")
BASE = "https://feeds.example.test/sentiment"
COLS = ["ts", "district_code", "buyer_sentiment", "seller_sentiment", "search_trend_index"]


async def test_sentiment_parse(tmp_path):
    c = SentimentCollector(api_key="test", base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect(date(2026, 1, 1), date(2026, 2, 28))
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 3
    assert df["buyer_sentiment"].iloc[0] == pytest.approx(112.5)
    assert pd.isna(df["search_trend_index"].iloc[2])


async def test_sentiment_filters_date_range(tmp_path):
    c = SentimentCollector(api_key="test", base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect(date(2026, 2, 1), date(2026, 2, 28))
    assert len(pd.read_parquet(path)) == 2


async def test_sentiment_empty_skips(tmp_path):
    c = SentimentCollector(api_key="test", base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text="")
        path = await c.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_sentiment_http_error_no_key_leak(tmp_path):
    c = SentimentCollector(api_key="SECRETKEY", base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(status_code=500)
        with pytest.raises(RuntimeError) as ei:
            await c.collect(date(2026, 1, 1), date(2026, 1, 31))
    assert "SECRETKEY" not in str(ei.value)


def test_sentiment_requires_key(monkeypatch):
    monkeypatch.delenv("SENTIMENT_API_KEY", raising=False)
    with pytest.raises(ValueError):
        SentimentCollector(base_url=BASE)
