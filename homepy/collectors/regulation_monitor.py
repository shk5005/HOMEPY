"""Monitor designation/release of regulated zones (조정대상지역 etc.)."""
from __future__ import annotations

import pandas as pd

from homepy.collectors._feed import JsonFeedCollector

ACTIONS = {"지정": "designate", "해제": "release", "designate": "designate", "release": "release"}


class RegulationMonitor(JsonFeedCollector):
    SOURCE = "regulation_monitor"
    ENV_URL = "REGULATION_API_URL"
    COLUMNS = ["ts", "zone_type", "district_code", "action"]

    def _row(self, item: dict, ts: pd.Timestamp) -> dict:
        action = ACTIONS.get(str(item.get("action", "")).strip())
        if action is None:
            raise ValueError(f"unknown regulation action {item.get('action')!r}")
        return {"ts": ts, "zone_type": item.get("zone_type", ""),
                "district_code": str(item.get("district_code", "")), "action": action}
