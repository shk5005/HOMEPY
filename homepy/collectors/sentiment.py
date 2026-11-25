"""Market sentiment (buyer/seller index) and search trend collector."""
from __future__ import annotations

import pandas as pd

from homepy.collectors._feed import JsonFeedCollector


class SentimentCollector(JsonFeedCollector):
    SOURCE = "sentiment"
    ENV_URL = "SENTIMENT_API_URL"
    ENV_KEY = "SENTIMENT_API_KEY"
    COLUMNS = ["ts", "district_code", "buyer_sentiment", "seller_sentiment", "search_trend_index"]

    def _row(self, item: dict, ts: pd.Timestamp) -> dict:
        return {"ts": ts, "district_code": str(item.get("district_code", "")),
                "buyer_sentiment": item.get("buyer_sentiment"),
                "seller_sentiment": item.get("seller_sentiment"),
                "search_trend_index": item.get("search_trend_index")}

    def _finalize(self, df: pd.DataFrame) -> pd.DataFrame:
        for c in ("buyer_sentiment", "seller_sentiment", "search_trend_index"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        return df
