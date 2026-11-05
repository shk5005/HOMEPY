"""Price prediction inference with SHAP explanations and health-based fallback."""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Awaitable, Callable

import joblib
import numpy as np

from homepy.ml.features import FeatureCombiner
from homepy.ml.models import MLFeatureSet, MLPrediction, ModelMetrics
from homepy.ml.trainer import DIRECTION_THRESHOLD, FEATURE_NAMES, MAPE_THRESHOLD

logger = logging.getLogger(__name__)

FeatureProvider = Callable[[str], Awaitable[MLFeatureSet]]


class PricePredictor:
    def __init__(self, model_path: str, feature_combiner: FeatureCombiner,
                 feature_provider: FeatureProvider | None = None) -> None:
        self.model_path = model_path
        self.combiner = feature_combiner
        self.feature_provider = feature_provider
        self._model: Any = None
        self._metrics: ModelMetrics | None = None
        self._version: str = ""
        if model_path and os.path.exists(model_path):
            self._load(model_path)

    def _load(self, path: str) -> None:
        blob = joblib.load(path)
        self._model = blob["model"]
        self._metrics = blob.get("metrics")
        self._version = str(blob.get("version", ""))

    def is_healthy(self) -> bool:
        m = self._metrics
        if self._model is None and m is None:
            return False
        if m is None:
            return False
        return m.mape < MAPE_THRESHOLD and m.direction_accuracy >= DIRECTION_THRESHOLD

    async def predict(self, complex_id: str) -> MLPrediction:
        import shap
        if self._model is None:
            raise RuntimeError("no model loaded")
        if self.feature_provider is None:
            raise RuntimeError("no feature_provider configured")
        fs = await self.feature_provider(complex_id)
        X = np.asarray(fs.combined, dtype=float).reshape(1, -1)
        pred = float(self._model.predict(X)[0])
        sv = np.asarray(shap.TreeExplainer(self._model).shap_values(X)).reshape(-1)
        m = self._metrics
        confidence = 0.0 if m is None else float(min(1.0, max(0.0, m.direction_accuracy / 100.0)))
        return MLPrediction(
            complex_id=complex_id, prediction_date=date.today(),
            predicted_change_3m=pred, confidence=confidence,
            shap_values={n: float(v) for n, v in zip(FEATURE_NAMES, sv)},
            model_version=self._version or "unversioned",
        )
