"""Sentiment composer: fear/greed index (0 = extreme fear, 100 = extreme greed)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

WEIGHTS = {"buyer_sentiment": 0.35, "jeonse_ratio": 0.25, "volume_change": 0.25, "search_trend": 0.15}
JEONSE_FEAR, JEONSE_GREED = 0.9, 0.4   # ratio (fraction) mapped to score 0 / 100
VOLUME_RANGE = 50.0                    # volume_change % in [-50, +50] -> [0, 100]


def _clip(s: pd.Series) -> pd.Series:
    return s.clip(0.0, 100.0)


def normalize(component: str, s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").astype("float64")
    if component == "jeonse_ratio":
        s = s.where(s <= 3, s / 100.0)  # accept percent as well as fraction
        return _clip((JEONSE_FEAR - s) / (JEONSE_FEAR - JEONSE_GREED) * 100.0)  # inverted
    if component == "volume_change":
        return _clip((s + VOLUME_RANGE) / (2 * VOLUME_RANGE) * 100.0)
    return _clip(s)  # buyer_sentiment, search_trend already 0-100


class SentimentComposer:
    def compose(self, sentiment_df: pd.DataFrame, volume_df: pd.DataFrame | None = None,
                jeonse_df: pd.DataFrame | None = None, search_df: pd.DataFrame | None = None) -> pd.DataFrame:
        out = sentiment_df.copy()
        for other in (volume_df, jeonse_df, search_df):
            if other is None or other.empty:
                continue
            keys = [k for k in ("ts", "district_code") if k in out.columns and k in other.columns]
            new = [c for c in other.columns if c in WEIGHTS and c not in out.columns]
            if not keys:
                logger.warning("sentiment component frame dropped: no shared keys (ts/district_code) "
                               "with sentiment_df; columns=%s", list(other.columns))
            elif new:
                out = out.merge(other[keys + new].drop_duplicates(keys), on=keys, how="left")

        total = pd.Series(0.0, index=out.index)
        weight = pd.Series(0.0, index=out.index)
        for comp, w in WEIGHTS.items():
            if comp not in out.columns:
                continue
            score = normalize(comp, out[comp])
            out[f"{comp}_score"] = score
            total += score.fillna(0.0) * w
            weight += score.notna() * w  # reweight over available components
        out["fear_greed_index"] = (total / weight.where(weight > 0)).replace([np.inf, -np.inf], np.nan)
        return out
