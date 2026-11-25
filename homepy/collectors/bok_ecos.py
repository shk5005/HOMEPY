"""BOK ECOS (Bank of Korea) interest rate collector."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector

ECOS_BASE_URL = "https://ecos.bok.or.kr/api"
FREQUENCY = "M"

# column -> (STAT_CODE, ITEM_CODE1)
SERIES: dict[str, tuple[str, str]] = {
    "base_rate": ("722Y001", "0101000"),
    "cd_rate_91d": ("721Y001", "2010000"),
    "cofix_rate": ("121Y002", "BEABAA2"),
    "treasury_3y": ("721Y001", "5020000"),
    "treasury_10y": ("721Y001", "5050000"),
    "mortgage_rate_avg": ("121Y006", "BECBLA0302"),
}
COLUMNS = ["ts", *SERIES, "rate_direction"]
DIRECTION_THRESHOLD = 0.05  # percentage points over the 3-month window


class BokEcosCollector(BaseCollector):
    def __init__(self, api_key: str | None = None, data_dir: Path | str = "data"):
        key = api_key or os.environ.get("BOK_ECOS_API_KEY")
        if not key:
            raise ValueError("ECOS api_key missing (pass api_key or set BOK_ECOS_API_KEY)")
        super().__init__("bok_ecos", ECOS_BASE_URL, data_dir)
        self.api_key = key

    async def _fetch_series(self, stat_code: str, item_code: str,
                            start: date, end: date) -> pd.Series:
        endpoint = (
            f"StatisticSearch/{self.api_key}/json/kr/1/1000/"
            f"{stat_code}/{FREQUENCY}/{start:%Y%m}/{end:%Y%m}/{item_code}"
        )
        payload = await self._fetch(endpoint, {})
        if "StatisticSearch" not in payload:
            result = payload.get("RESULT", {})
            if result.get("CODE") == "INFO-200":  # no data for this window: skip
                return pd.Series(dtype="float64")
            msg = result.get("MESSAGE", "unexpected ECOS response")
            raise ValueError(f"ECOS error for {stat_code}/{item_code}: {msg}")
        rows = payload["StatisticSearch"].get("row", [])
        data = {
            pd.to_datetime(r["TIME"], format="%Y%m"): float(r["DATA_VALUE"])
            for r in rows
            if r.get("DATA_VALUE") not in (None, "")
        }
        return pd.Series(data, dtype="float64")

    @staticmethod
    def _direction(base_rate: pd.Series) -> pd.Series:
        """'up' / 'down' / 'flat' from the change in base rate over 3 months."""
        delta = base_rate - base_rate.shift(2).fillna(base_rate.iloc[0])
        def label(d: float) -> str | None:
            if pd.isna(d):
                return None
            return "up" if d > DIRECTION_THRESHOLD else "down" if d < -DIRECTION_THRESHOLD else "flat"

        return pd.Series([label(d) for d in delta], index=delta.index, dtype=object)

    async def collect(self, start_date: date, end_date: date) -> Path:
        series = {
            col: await self._fetch_series(code, item, start_date, end_date)
            for col, (code, item) in SERIES.items()
        }
        df = pd.DataFrame(series).sort_index()
        df.index.name = "ts"
        df = df.reset_index()
        if df.empty:
            df["rate_direction"] = pd.Series(dtype="object")
        else:
            df["rate_direction"] = self._direction(df["base_rate"])
        return self._save_raw(df[COLUMNS], end_date)
