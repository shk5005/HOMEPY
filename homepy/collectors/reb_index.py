"""REB (Korea Real Estate Board) house price / jeonse index collector."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector

REB_BASE_URL = "https://www.reb.or.kr/r-one/openapi"
ENDPOINT = "HousePriceIndex"
COLUMNS = ["ts", "region_code", "price_index", "price_change_mom",
           "price_change_yoy", "jeonse_index"]
OK_CODES = {"00", "000", "INFO-000"}


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class RebIndexCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("REB_API_KEY")
        if not key:
            raise ValueError("REB api_key missing (pass api_key or set REB_API_KEY)")
        super().__init__("reb_index", REB_BASE_URL, data_dir)
        self.api_key = key

    async def collect(self, start_date: date, end_date: date) -> Path:
        payload = await self._fetch(ENDPOINT, {
            "KEY": self.api_key, "Type": "json",
            "START_WRTTIME": f"{start_date:%Y%m}", "END_WRTTIME": f"{end_date:%Y%m}",
        })
        response = (payload or {}).get("response") or {}
        code = str(response.get("header", {}).get("resultCode", ""))
        if code and code not in OK_CODES:
            msg = response.get("header", {}).get("resultMsg", "unexpected REB response")
            raise ValueError(f"REB error {code}: {msg}")
        items = response.get("body", {}).get("items") or []  # empty = skip
        rows = [{
            "ts": pd.to_datetime(str(i["WRTTIME_IDTFR_ID"]), format="%Y%m"),
            "region_code": str(i.get("REGION_CD", "")),
            "price_index": _num(i.get("PRICE_INDEX")),
            "price_change_mom": _num(i.get("MOM")),
            "price_change_yoy": _num(i.get("YOY")),
            "jeonse_index": _num(i.get("JEONSE_INDEX")),
        } for i in items]
        df = pd.DataFrame(rows, columns=COLUMNS)
        return self._save_raw(df, end_date)
