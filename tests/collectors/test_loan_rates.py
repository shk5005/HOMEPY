import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import respx

from homepy.collectors.loan_rates import LoanRateCollector

FIXTURE = Path(__file__).parent / "fixtures" / "loan_rates_response.json"
URL = re.compile(r".*mortgageLoanProductsSearch.*")
COLS = ["ts", "loan_type", "lender_type", "interest_type", "rate_min", "rate_max"]


async def test_loan_rates_parse(tmp_path):
    c = LoanRateCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect(date(2026, 1, 1), date(2026, 1, 31))
    assert route.call_count == 2  # banks + savings banks
    df = pd.read_parquet(path)
    assert list(df.columns) == COLS
    assert set(df["lender_type"]) == {"bank", "savings_bank"}
    row = df[(df["lender_type"] == "bank") & (df["interest_type"] == "fixed")].iloc[0]
    assert row["loan_type"] == "mortgage"
    assert row["rate_min"] == pytest.approx(3.85)
    assert pd.isna(df["rate_max"]).any()


async def test_loan_rates_empty_skips(tmp_path):
    body = {"result": {"err_cd": "100", "err_msg": "데이터 없음"}}
    c = LoanRateCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=body)
        path = await c.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(path)
    assert len(df) == 0 and list(df.columns) == COLS


async def test_loan_rates_error_raises(tmp_path):
    body = {"result": {"err_cd": "010", "err_msg": "등록되지 않은 인증키"}}
    c = LoanRateCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(json=body)
        with pytest.raises(ValueError, match="인증키"):
            await c.collect(date(2026, 1, 1), date(2026, 1, 31))


async def test_loan_rates_filters_by_date(tmp_path):
    c = LoanRateCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(URL).respond(text=FIXTURE.read_text(encoding="utf-8"))
        path = await c.collect(date(2026, 1, 8), date(2026, 1, 31))  # only B1 (0110)
    df = pd.read_parquet(path)
    assert len(df) == 2  # B1 once per lender group
    assert (df["rate_min"] == 4.0).all()


async def test_loan_rates_paginates(tmp_path):
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))
    body["result"]["max_page_no"] = 2
    c = LoanRateCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        route = respx.get(URL).respond(json=body)
        await c.collect(date(2026, 1, 1), date(2026, 1, 31))
    assert route.call_count == 4  # 2 groups x 2 pages
