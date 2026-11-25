"""Base for collectors reading a JSON ``{"items": [...]}`` feed filtered by date."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd

from homepy.collectors.base import BaseCollector


class JsonFeedCollector(BaseCollector):
    COLUMNS: list[str] = []
    ENV_URL = ""
    ENV_KEY: str | None = None
    SOURCE = ""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 data_dir: Path | str = "data"):
        url = base_url or os.environ.get(self.ENV_URL)
        if not url:
            raise ValueError(f"{self.SOURCE} base_url missing (pass base_url or set {self.ENV_URL})")
        self.api_key = None
        if self.ENV_KEY:
            self.api_key = api_key or os.environ.get(self.ENV_KEY)
            if not self.api_key:
                raise ValueError(f"{self.SOURCE} api_key missing (pass api_key or set {self.ENV_KEY})")
        super().__init__(self.SOURCE, url, data_dir)

    def _row(self, item: dict, ts: pd.Timestamp) -> dict:
        raise NotImplementedError

    async def collect(self, start_date: date, end_date: date) -> Path:
        params = {"start": start_date.isoformat(), "end": end_date.isoformat()}
        if self.api_key:
            params["apiKey"] = self.api_key
        payload = await self._fetch("", params)
        items = payload.get("items") or [] if isinstance(payload, dict) else []
        lo, hi = pd.Timestamp(start_date), pd.Timestamp(end_date)
        rows = []
        for it in items:
            try:
                ts = pd.Timestamp(it["date"])
            except (KeyError, ValueError, TypeError):
                continue
            if lo <= ts <= hi:
                rows.append(self._row(it, ts))
        df = pd.DataFrame(rows, columns=self.COLUMNS)
        return self._save_raw(self._finalize(df), end_date)

    def _finalize(self, df: pd.DataFrame) -> pd.DataFrame:
        return df
