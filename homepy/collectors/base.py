"""Abstract base class for all HOMEPY data collectors."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0


class BaseCollector(ABC):
    """Fetches from an HTTP API and stores raw data as Parquet.

    Raw files land in ``{data_dir}/raw/{source_name}/{YYYY-MM-DD}/data.parquet``.
    """

    def __init__(self, source_name: str, api_base_url: str, data_dir: Path | str = "data"):
        self.source_name = source_name
        self.api_base_url = api_base_url.rstrip("/")
        self.data_dir = Path(data_dir)

    async def _fetch(self, endpoint: str, params: dict | None = None) -> dict:
        """GET ``api_base_url/endpoint`` with 3 attempts and exponential backoff."""
        url = f"{self.api_base_url}/{endpoint.lstrip('/')}"
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    resp = await client.get(url, params=params or {})
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    last_exc = exc
                    if attempt < MAX_ATTEMPTS - 1:
                        await asyncio.sleep(BACKOFF_BASE_SECONDS * 2**attempt)
        assert last_exc is not None
        raise last_exc

    def _save_raw(self, df: pd.DataFrame, date: date) -> Path:  # noqa: A002
        out_dir = self.data_dir / "raw" / self.source_name / date.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "data.parquet"
        df.to_parquet(path, index=False)
        return path

    @abstractmethod
    async def collect(self, start_date: date, end_date: date) -> Path:
        """Collect data for the range and return the saved Parquet path."""
