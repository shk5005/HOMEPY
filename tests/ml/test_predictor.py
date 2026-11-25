from datetime import date

import joblib
import lightgbm as lgb
import numpy as np
import pytest

from homepy.ml.features import FeatureCombiner
from homepy.ml.models import MLFeatureSet, MLPrediction, ModelMetrics
from homepy.ml.predictor import PricePredictor


@pytest.fixture
def mock_model(tmp_path):
    rng = np.random.default_rng(1)
    X = rng.random((200, 10))
    model = lgb.LGBMRegressor(n_estimators=20, verbose=-1).fit(X, X[:, 0] * 4 - 2)
    path = str(tmp_path / "m.joblib")
    joblib.dump({"model": model, "version": "v-test", "feature_names": [],
                 "metrics": ModelMetrics(5.0, 70.0, 0.5, {})}, path)
    return path


async def _provider(cid):
    return MLFeatureSet(cid, date.today(), {}, {}, np.full(10, 0.5))


async def test_predictor_fallback_on_low_accuracy():
    p = PricePredictor("dummy_path", FeatureCombiner())
    p._metrics = ModelMetrics(mape=20.0, direction_accuracy=55.0, r_squared=0.1, feature_importances={})
    assert not p.is_healthy()


async def test_predictor_healthy(mock_model):
    p = PricePredictor(mock_model, FeatureCombiner())
    assert p.is_healthy()
    p._metrics = ModelMetrics(15.0, 80.0, 0.5, {})
    assert not p.is_healthy()
    p._metrics = ModelMetrics(5.0, 59.9, 0.5, {})
    assert not p.is_healthy()


async def test_predictor_returns_prediction_with_shap(mock_model):
    p = PricePredictor(mock_model, FeatureCombiner(), feature_provider=_provider)
    r = await p.predict("C001")
    assert isinstance(r, MLPrediction)
    assert len(r.shap_values) == 10
    assert r.model_version == "v-test"


async def test_predict_without_model_raises():
    p = PricePredictor("dummy_path", FeatureCombiner())
    assert not p.is_healthy()
    with pytest.raises(RuntimeError):
        await p.predict("C001")
