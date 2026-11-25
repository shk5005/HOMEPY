"""FSS FINLIFE mortgage loan product rates (banks and savings banks)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector

BASE_URL = "https://finlife.fss.or.kr/finlifeapi"
ENDPOINT = "mortgageLoanProductsSearch.json"
COLUMNS = ["ts", "loan_type", "lender_type", "interest_type", "rate_min", "rate_max"]
OK_CODE = "000"
NO_DATA_CODES = {"100"}  # FINLIFE: no data for the query
LENDER_GROUPS = {"020000": "bank", "030300": "savings_bank"}
INTEREST_TYPES = {"고정금리": "fixed", "변동금리": "floating"}


class LoanRateCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("FSS_API_KEY")
        if not key:
            raise ValueError("FSS api_key missing (pass api_key or set FSS_API_KEY)")
        super().__init__("loan_rates", BASE_URL, data_dir)
        self.api_key = key

    async def _fetch_group(self, group_no: str) -> tuple[list[dict], list[dict]]:
        base: list[dict] = []
        opts: list[dict] = []
        page = 1
        while True:
            payload = await self._fetch(ENDPOINT, {"auth": self.api_key, "topFinGrpNo": group_no,
                                                   "pageNo": page})
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            code = str(result.get("err_cd", ""))
            if code in NO_DATA_CODES or (not result and not payload):
                return base, opts
            if code != OK_CODE:
                raise ValueError(f"FINLIFE error {code}: {result.get('err_msg', 'unexpected response')}")
            base += result.get("baseList") or []
            opts += result.get("optionList") or []
            if page >= int(result.get("max_page_no") or 1):
                return base, opts
            page += 1

    async def collect(self, start_date: date, end_date: date) -> Path:
        """Collect products whose disclosure start date falls in [start_date, end_date]."""
        rows: list[dict] = []
        for group_no, lender in LENDER_GROUPS.items():
            base, opts = await self._fetch_group(group_no)
            starts = {}
            for b in base:
                try:
                    starts[b["fin_prdt_cd"]] = pd.to_datetime(b["dcls_strt_day"], format="%Y%m%d")
                except (KeyError, ValueError, TypeError):
                    continue
            for o in opts:
                ts = starts.get(o.get("fin_prdt_cd"))
                if ts is None or not (pd.Timestamp(start_date) <= ts <= pd.Timestamp(end_date)):
                    continue
                rows.append({
                    "ts": ts, "loan_type": "mortgage", "lender_type": lender,
                    "interest_type": INTEREST_TYPES.get(o.get("lend_rate_type_nm"), o.get("lend_rate_type_nm")),
                    "rate_min": o.get("lend_rate_min"), "rate_max": o.get("lend_rate_max"),
                })
        df = pd.DataFrame(rows, columns=COLUMNS)
        for col in ("rate_min", "rate_max"):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        return self._save_raw(df, end_date)
