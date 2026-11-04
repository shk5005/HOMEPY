"""Monitor tax law changes relevant to real estate (양도세, 종부세, 취득세 ...)."""
from __future__ import annotations

import pandas as pd

from homepy.collectors._feed import JsonFeedCollector


class TaxRuleMonitor(JsonFeedCollector):
    SOURCE = "tax_rule_monitor"
    ENV_URL = "TAX_RULE_API_URL"
    COLUMNS = ["ts", "law_name", "article", "change_type", "effective_date", "summary"]

    def _row(self, item: dict, ts: pd.Timestamp) -> dict:
        eff = pd.to_datetime(item.get("effective_date"), errors="coerce")
        return {"ts": ts, "law_name": item.get("law_name", ""), "article": item.get("article", ""),
                "change_type": item.get("change_type", ""), "effective_date": eff,
                "summary": item.get("summary", "")}
