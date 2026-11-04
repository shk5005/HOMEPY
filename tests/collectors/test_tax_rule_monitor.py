import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.tax_rule_monitor import TaxRuleMonitor

FIXTURE = Path(__file__).parent / "fixtures" / "tax_rule_response.json"
URL = re.compile(r".*taxrules.*")
BASE = "https://feeds.example.test/taxrules"
COLS = ["ts", "law_name", "article", "change_type", "effective_date", "summary"]


async def test_tax_rule_parse(tmp_path):
    m = TaxRuleMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await m.collect(date(2026, 1, 1), date(2026, 3, 31))
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert len(df) == 2
    assert df["law_name"].iloc[1] == "종합부동산세법"
    assert pd.Timestamp(df["effective_date"].iloc[0]) == pd.Timestamp("2026-03-01")


async def test_tax_rule_filters_date_range(tmp_path):
    m = TaxRuleMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await m.collect(date(2026, 2, 1), date(2026, 2, 28))
    assert len(pd.read_parquet(path)) == 1


async def test_tax_rule_empty_skips(tmp_path):
    m = TaxRuleMonitor(base_url=BASE, data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json={"items": []})
        path = await m.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


def test_tax_rule_requires_base_url(monkeypatch):
    monkeypatch.delenv("TAX_RULE_API_URL", raising=False)
    with pytest.raises(ValueError):
        TaxRuleMonitor()
