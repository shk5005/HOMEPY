"""MOLIT (Ministry of Land) apartment real-trade collector. The API returns XML."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector

MOLIT_BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"
ENDPOINT = "getRTMSDataSvcAptTrade"
COLUMNS = ["ts", "district_code", "dong_code", "complex_name",
           "area_sqm", "floor", "price", "trade_type"]
OK_CODES = {"00", "000"}


def _months(start_ym: str, end_ym: str) -> list[str]:
    y, m = int(start_ym[:4]), int(start_ym[4:6])
    ey, em = int(end_ym[:4]), int(end_ym[4:6])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


class MolitTradeCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("MOLIT_API_KEY")
        if not key:
            raise ValueError("MOLIT api_key missing (pass api_key or set MOLIT_API_KEY)")
        super().__init__("molit_trade", MOLIT_BASE_URL, data_dir)
        self.api_key = key

    @staticmethod
    def _parse(xml_text: str, region_code: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        code = (root.findtext("header/resultCode") or "").strip()
        if code not in OK_CODES:
            msg = (root.findtext("header/resultMsg") or "unexpected MOLIT response").strip()
            raise ValueError(f"MOLIT error {code}: {msg}")
        rows = []
        for item in root.findall("body/items/item"):
            try:
                ts = pd.Timestamp(year=int(_text(item, "dealYear")),
                                  month=int(_text(item, "dealMonth")),
                                  day=int(_text(item, "dealDay")))
                price = int(_text(item, "dealAmount").replace(",", ""))
                area = float(_text(item, "excluUseAr"))
                floor = int(_text(item, "floor"))
            except ValueError:
                continue  # malformed record: skip
            rows.append({
                "ts": ts,
                "district_code": _text(item, "sggCd") or region_code,
                "dong_code": _text(item, "umdCd"),
                "complex_name": _text(item, "aptNm"),
                "area_sqm": area,
                "floor": floor,
                "price": price,
                "trade_type": "sale",
            })
        return rows

    async def collect(self, region_code: str, start_ym: str, end_ym: str) -> Path:  # type: ignore[override]
        """Collect apartment trades for ``region_code`` (LAWD_CD) from start_ym to end_ym (YYYYMM)."""
        rows: list[dict] = []
        for ym in _months(start_ym, end_ym):
            text = await self._fetch_text(ENDPOINT, {
                "serviceKey": self.api_key, "LAWD_CD": region_code,
                "DEAL_YMD": ym, "numOfRows": 1000, "pageNo": 1,
            })
            rows.extend(self._parse(text, region_code))
        df = pd.DataFrame(rows, columns=COLUMNS)
        return self._save_raw(df, date.today())
