"""MOLIT housing supply statistics (permits, starts, completions, presale, unsold)."""
from __future__ import annotations

import calendar
import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors._molit_paged import fetch_all_items
from homepy.collectors._xml import text, to_int
from homepy.collectors.base import BaseCollector
from homepy.collectors.molit_trade import _months

BASE_URL = "https://apis.data.go.kr/1613000/HousingSupplyService"
ENDPOINT = "getSupply"
COLUMNS = ["ts", "district_code", "permits_issued", "construction_starts", "completions",
           "presale_volume", "unsold_total", "unsold_after_completion"]
FIELDS = {
    "permits_issued": "permits", "construction_starts": "starts", "completions": "completions",
    "presale_volume": "presale", "unsold_total": "unsoldTotal",
    "unsold_after_completion": "unsoldAfterCompletion",
}


class MolitSupplyCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("MOLIT_API_KEY")
        if not key:
            raise ValueError("MOLIT api_key missing (pass api_key or set MOLIT_API_KEY)")
        super().__init__("molit_supply", BASE_URL, data_dir)
        self.api_key = key

    async def collect(self, region_code: str, start_ym: str, end_ym: str) -> Path:  # type: ignore[override]
        rows: list[dict] = []
        for ym in _months(start_ym, end_ym):
            async def fetch(p: dict) -> str:
                return await self._fetch_text(ENDPOINT, p)

            items = await fetch_all_items(
                fetch, {"serviceKey": self.api_key, "LAWD_CD": region_code, "DEAL_YMD": ym},
                "MOLIT supply")
            for it in items:
                try:
                    ts = pd.to_datetime(text(it, "dealYm") or ym, format="%Y%m")
                    vals = {col: to_int(text(it, tag)) for col, tag in FIELDS.items()}
                except ValueError:
                    continue
                rows.append({"ts": ts, "district_code": text(it, "sggCd") or region_code, **vals})
        df = pd.DataFrame(rows, columns=COLUMNS)
        y, m = int(end_ym[:4]), int(end_ym[4:6])
        end = date(y, m, calendar.monthrange(y, m)[1])
        return self._save_raw(df, end, filename=f"{region_code}_{start_ym}_{end_ym}.parquet")
