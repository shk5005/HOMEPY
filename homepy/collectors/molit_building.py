"""MOLIT building registry (건축물대장 표제부) collector."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors._molit_paged import fetch_all_items
from homepy.collectors._xml import text, to_float, to_int
from homepy.collectors.base import BaseCollector

BASE_URL = "https://apis.data.go.kr/1613000/BldRgstService_v2"
ENDPOINT = "getBrTitleInfo"
COLUMNS = ["ts", "district_code", "dong_code", "building_name", "main_purpose",
           "total_area_sqm", "floors_above", "floors_below", "households"]


class MolitBuildingCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("MOLIT_API_KEY")
        if not key:
            raise ValueError("MOLIT api_key missing (pass api_key or set MOLIT_API_KEY)")
        super().__init__("molit_building", BASE_URL, data_dir)
        self.api_key = key

    async def collect(self, sigungu_code: str, dong_code: str) -> Path:  # type: ignore[override]
        """Collect building titles for a sigungu + bjdong code. ``ts`` is the use-approval date."""
        async def fetch(p: dict) -> str:
            return await self._fetch_text(ENDPOINT, p)

        items = await fetch_all_items(
            fetch, {"serviceKey": self.api_key, "sigunguCd": sigungu_code, "bjdongCd": dong_code},
            "MOLIT building")
        rows = []
        for it in items:
            try:
                ts = pd.to_datetime(text(it, "useAprDay"), format="%Y%m%d")
                area = to_float(text(it, "totArea"))
                above, below = to_int(text(it, "grndFlrCnt")), to_int(text(it, "ugrndFlrCnt"))
                hh = to_int(text(it, "hhldCnt"))
            except ValueError:
                continue  # malformed record (incl. missing approval date): skip
            rows.append({
                "ts": ts, "district_code": text(it, "sigunguCd") or sigungu_code,
                "dong_code": text(it, "bjdongCd") or dong_code,
                "building_name": text(it, "bldNm"), "main_purpose": text(it, "mainPurpsCdNm"),
                "total_area_sqm": area, "floors_above": above, "floors_below": below,
                "households": hh,
            })
        df = pd.DataFrame(rows, columns=COLUMNS)
        return self._save_raw(df, date.today(), filename=f"{sigungu_code}_{dong_code}.parquet")
