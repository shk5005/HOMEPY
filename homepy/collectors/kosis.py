"""KOSIS (Statistics Korea) generic statistics collector."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector

KOSIS_BASE_URL = "https://kosis.kr/openapi"
ENDPOINT = "Param/statisticsParameterData.do"
COLUMNS = ["ts", "region_code", "region_name", "item_code", "item_name", "value", "unit"]
NO_DATA_ERRS = {"30", "31"}  # KOSIS: no data / no result

# stat_id -> (orgId, tblId, period type, objL1)
STATS: dict[str, dict[str, str]] = {
    "population": {"orgId": "101", "tblId": "DT_1B040A3", "prdSe": "M", "objL1": "ALL", "itmId": "ALL"},
    "migration": {"orgId": "101", "tblId": "DT_1B26001", "prdSe": "M", "objL1": "ALL", "itmId": "ALL"},
    "income": {"orgId": "101", "tblId": "DT_1L6E001", "prdSe": "Y", "objL1": "ALL", "itmId": "ALL"},
    "cpi": {"orgId": "101", "tblId": "DT_1J22003", "prdSe": "M", "objL1": "ALL", "itmId": "ALL"},
    "gdp": {"orgId": "301", "tblId": "DT_200Y001", "prdSe": "Q", "objL1": "ALL", "itmId": "ALL"},
}


def _parse_period(prd: str) -> pd.Timestamp:
    prd = str(prd)
    if len(prd) == 4:
        return pd.Timestamp(year=int(prd), month=1, day=1)
    if "Q" in prd:  # e.g. 2026Q1
        return pd.Timestamp(year=int(prd[:4]), month=(int(prd[-1]) - 1) * 3 + 1, day=1)
    return pd.to_datetime(prd, format="%Y%m")


class KosisCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("KOSIS_API_KEY")
        if not key:
            raise ValueError("KOSIS api_key missing (pass api_key or set KOSIS_API_KEY)")
        super().__init__("kosis", KOSIS_BASE_URL, data_dir)
        self.api_key = key

    async def collect(self, stat_id: str, start_date: date, end_date: date) -> Path:  # type: ignore[override]
        if stat_id not in STATS:
            raise ValueError(f"unknown KOSIS stat_id {stat_id!r}; known: {sorted(STATS)}")
        spec = STATS[stat_id]
        fmt = "%Y" if spec["prdSe"] == "Y" else "%Y%m"
        payload = await self._fetch(ENDPOINT, {
            "method": "getList", "apiKey": self.api_key, "format": "json", "jsonVD": "Y",
            **spec, "startPrdDe": start_date.strftime(fmt), "endPrdDe": end_date.strftime(fmt),
        })
        if isinstance(payload, dict):
            err = str(payload.get("err", ""))
            if err in NO_DATA_ERRS:
                payload = []
            else:
                raise ValueError(f"KOSIS error {err}: {payload.get('errMsg', 'unexpected response')}")
        rows = []
        for r in payload:
            try:
                value = float(str(r["DT"]).replace(",", ""))
            except (KeyError, ValueError):
                continue  # suppressed ('-') or missing value
            rows.append({
                "ts": _parse_period(r["PRD_DE"]),
                "region_code": str(r.get("C1", "")),
                "region_name": r.get("C1_NM", ""),
                "item_code": str(r.get("ITM_ID", "")),
                "item_name": r.get("ITM_NM", ""),
                "value": value,
                "unit": r.get("UNIT_NM", ""),
            })
        df = pd.DataFrame(rows, columns=COLUMNS)
        return self._save_raw(df, end_date, filename=f"{stat_id}.parquet")
