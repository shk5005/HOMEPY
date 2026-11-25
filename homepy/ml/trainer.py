"""LightGBM training for the 3-month price change model (local joblib persistence)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import joblib
import numpy as np

from homepy.ml.features import RELATIONAL_FEATURES, TIMESERIES_FEATURES, FeatureCombiner
from homepy.ml.models import ModelMetrics

logger = logging.getLogger(__name__)

FEATURE_NAMES: list[str] = list(RELATIONAL_FEATURES) + list(TIMESERIES_FEATURES)
TARGET_NAME = "target_change_3m"
MAPE_THRESHOLD = 15.0
DIRECTION_THRESHOLD = 60.0
FALLBACK_ENABLED = True  # InvestmentScorer uses rule-based score when model unhealthy

_QUERY = (
    "SELECT ts, complex_id, feature_name, feature_value FROM ts_ml_features "
    "WHERE ts >= $1 AND ts < $2 ORDER BY ts"
)


def _add_months(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) + months
    y, m = divmod(idx, 12)
    return date(y, m + 1, 1).replace(day=min(d.day, 28))


def _as_date(ts: Any) -> date:
    return ts.date() if isinstance(ts, datetime) else ts


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, importances: dict[str, float]) -> ModelMetrics:
    """MAPE and direction accuracy in percent; R2 as a fraction."""
    denom = np.maximum(np.abs(y_true), 1e-2)  # target is a % change; avoid /0
    mape = float(np.mean(np.abs(y_true - y_pred) / denom) * 100.0)
    direction = float(np.mean(np.sign(y_true) == np.sign(y_pred)) * 100.0)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return ModelMetrics(mape=mape, direction_accuracy=direction, r_squared=r2,
                        feature_importances=importances)


class ModelTrainer:
    def __init__(self, timescale_svc: Any, feature_combiner: FeatureCombiner,
                 model_path: str = "models/price_model.joblib") -> None:
        self.timescale = timescale_svc
        self.combiner = feature_combiner
        self.model_path = model_path
        self._model: Any = None
        self._metrics: ModelMetrics | None = None
        # dataset: {"date": ndarray[object], "X": (n,10), "y": (n,), "complex_id": ndarray}
        self._dataset: dict[str, np.ndarray] | None = None
        self._last_X: dict[str, np.ndarray] = {}

    async def _load_dataset(self, start: date, end: date) -> dict[str, np.ndarray]:
        rows = await self.timescale.execute(_QUERY, start, end)
        grouped: dict[tuple[date, str], dict[str, float]] = {}
        for r in rows:
            key = (_as_date(r["ts"]), r["complex_id"])
            grouped.setdefault(key, {})[r["feature_name"]] = float(r["feature_value"])
        dates, ids, X, y = [], [], [], []
        for (d, cid), feats in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if TARGET_NAME not in feats:
                continue
            fs = self.combiner.combine(
                {k: feats[k] for k in RELATIONAL_FEATURES if k in feats},
                {k: feats[k] for k in TIMESERIES_FEATURES if k in feats},
                complex_id=cid, feature_date=d,
            )
            dates.append(d); ids.append(cid); X.append(fs.combined); y.append(feats[TARGET_NAME])
        return {
            "date": np.array(dates, dtype=object), "complex_id": np.array(ids, dtype=object),
            "X": np.array(X, dtype=float).reshape(-1, len(FEATURE_NAMES)),
            "y": np.array(y, dtype=float),
        }

    def _split_data(self, start: date, train_months: int, val_months: int,
                    dataset: dict[str, np.ndarray] | None = None):
        """Chronological split: train in [start, start+train), validation in the next val_months."""
        ds = dataset if dataset is not None else self._dataset
        if ds is None:
            raise ValueError("no dataset loaded")
        train_end = _add_months(start, train_months)
        val_end = _add_months(train_end, val_months)
        dates = ds["date"]
        tr = np.array([start <= d < train_end for d in dates], dtype=bool)
        va = np.array([train_end <= d < val_end for d in dates], dtype=bool)
        pick = lambda m: {k: v[m] for k, v in ds.items()}  # noqa: E731
        return pick(tr), pick(va)

    async def train(self, training_months: int = 12, validation_months: int = 3) -> ModelMetrics:
        import lightgbm as lgb

        today = date.today()
        start = _add_months(today, -(training_months + validation_months))
        self._dataset = await self._load_dataset(start, today)
        train_set, val_set = self._split_data(start, training_months, validation_months)
        if len(train_set["y"]) == 0 or len(val_set["y"]) == 0:
            raise ValueError("insufficient training/validation data in ts_ml_features")
        model = lgb.LGBMRegressor(objective="regression", n_estimators=500, learning_rate=0.05,
                                  num_leaves=31, verbose=-1)
        model.fit(train_set["X"], train_set["y"])
        pred = model.predict(val_set["X"])
        imps = dict(zip(FEATURE_NAMES, (float(x) for x in model.feature_importances_)))
        self._model = model
        self._metrics = compute_metrics(val_set["y"], pred, imps)
        # latest feature row per complex, for get_shap_values
        for cid, x in zip(self._dataset["complex_id"], self._dataset["X"]):
            self._last_X[cid] = x
        # ML never auto-deploys: persist only; promotion needs ImprovementRecord + user approval.
        self.save()
        return self._metrics

    def save(self, path: str | None = None) -> str:
        import os
        path = path or self.model_path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        version = datetime.now().strftime("%Y%m%d%H%M%S")
        joblib.dump({"model": self._model, "metrics": self._metrics, "version": version,
                     "feature_names": FEATURE_NAMES}, path)
        return path

    def _compute_shap(self, features: np.ndarray) -> dict[str, float]:
        import shap
        X = np.asarray(features, dtype=float).reshape(1, -1)
        vals = shap.TreeExplainer(self._model).shap_values(X)
        vals = np.asarray(vals).reshape(-1)
        return {n: float(v) for n, v in zip(FEATURE_NAMES, vals)}

    async def get_shap_values(self, complex_id: str) -> dict[str, float]:
        if self._model is None:
            raise ValueError("model not trained")
        x = self._last_X.get(complex_id)
        if x is None:
            raise KeyError(f"no features for complex {complex_id}")
        return self._compute_shap(x)
