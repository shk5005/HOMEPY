"""ML dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np


@dataclass
class MLFeatureSet:
    complex_id: str
    feature_date: date
    relational_features: dict[str, float]
    timeseries_features: dict[str, float]
    combined: np.ndarray


@dataclass
class MLPrediction:
    complex_id: str
    prediction_date: date
    predicted_change_3m: float
    confidence: float
    shap_values: dict[str, float] = field(default_factory=dict)
    model_version: str = ""


@dataclass
class ModelMetrics:
    mape: float
    direction_accuracy: float
    r_squared: float
    feature_importances: dict[str, float] = field(default_factory=dict)
