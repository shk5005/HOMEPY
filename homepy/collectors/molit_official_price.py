"""MOLIT apartment official assessed price (공동주택가격) collector."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors._molit_paged import fetch_all_items
from homepy.collectors._xml import text, to_float, to_int
from homepy.collectors.base import BaseCollector

BASE_URL = "https://apis.data.go.kr/1613000/ApartHousingPriceService"
ENDPOINT = "getApartHousingPrice"
COLUMNS = ["ts", "district_code", "dong_code", "complex_name", "area_sqm", "official_price"]


class MolitOfficialPriceCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("MOLIT_API_KEY")
        if not key:
            raise ValueError("MOLIT api_key missing (pass api_key or set MOLIT_API_KEY)")
        super().__init__("molit_official_price", BASE_URL, data_dir)
        self.api_key = key

    async def collect(self, region_code: str, start_year: int, end_year: int) -> Path:  # type: ignore[override]
        rows: list[dict] = []
        for year in range(start_year, end_year + 1):
            async def fetch(p: dict) -> str:
                return await self._fetch_text(ENDPOINT, p)

            items = await fetch_all_items(
                fetch, {"serviceKey": self.api_key, "LAWD_CD": region_code, "stdrYear": year},
                "MOLIT official price")
            for it in items:
                try:
                    ts = pd.Timestamp(year=int(text(it, "stdrYear") or year), month=1, day=1)
                    area = to_float(text(it, "prvuseAr"))
                    price = to_int(text(it, "pblntfPc"))
                except ValueError:
                    continue
                rows.append({
                    "ts": ts, "district_code": text(it, "sggCd") or region_code,
                    "dong_code": text(it, "umdCd"), "complex_name": text(it, "aptNm"),
                    "area_sqm": area, "official_price": price,
                })
        df = pd.DataFrame(rows, columns=COLUMNS)
        return self._save_raw(df, date(end_year, 12, 31),
                              filename=f"{region_code}_{start_year}_{end_year}.parquet")
