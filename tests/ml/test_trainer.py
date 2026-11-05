from datetime import date

import lightgbm as lgb
import numpy as np
import pytest

from homepy.ml.features import FeatureCombiner
from homepy.ml.trainer import FEATURE_NAMES, ModelTrainer, compute_metrics


def _dataset():
    rng = np.random.default_rng(0)
    dates = [date(2025 + (m // 12), m % 12 + 1, 1) for m in range(15) for _ in range(10)]
    X = rng.random((len(dates), 10))
    y = X[:, 0] * 10 - 5 + rng.normal(0, 0.1, len(dates))
    return {"date": np.array(dates, dtype=object),
            "complex_id": np.array(["C001"] * len(dates), dtype=object), "X": X, "y": y}


def _trained(mock_timescale):
    t = ModelTrainer(mock_timescale, FeatureCombiner())
    ds = _dataset()
    t._model = lgb.LGBMRegressor(n_estimators=30, verbose=-1).fit(ds["X"], ds["y"])
    t._last_X["C001"] = ds["X"][0]
    return t, ds


def test_training_data_no_leakage(mock_timescale):
    t = ModelTrainer(mock_timescale, FeatureCombiner())
    t._dataset = _dataset()
    train_set, val_set = t._split_data(start=date(2025, 1, 1), train_months=12, val_months=3)
    assert len(train_set["y"]) > 0 and len(val_set["y"]) > 0
    assert train_set["date"].max() < val_set["date"].min()


def test_shap_values_sum_to_prediction(mock_timescale):
    t, ds = _trained(mock_timescale)
    x = ds["X"][:1]
    shap_vals = t._compute_shap(x)
    assert set(shap_vals) == set(FEATURE_NAMES)
    raw = t._model.predict(x, raw_score=True)[0]
    import shap
    base = float(np.ravel(shap.TreeExplainer(t._model).expected_value)[0])
    assert abs(sum(shap_vals.values()) - (raw - base)) < 0.01


async def test_get_shap_values(mock_timescale):
    t, _ = _trained(mock_timescale)
    assert len(await t.get_shap_values("C001")) == 10
    with pytest.raises(KeyError):
        await t.get_shap_values("nope")


def test_compute_metrics():
    y = np.array([1.0, -2.0, 3.0])
    m = compute_metrics(y, y.copy(), {})
    assert m.mape == 0 and m.direction_accuracy == 100 and m.r_squared == 1.0


async def test_train_insufficient_data_raises(mock_timescale):
    t = ModelTrainer(mock_timescale, FeatureCombiner())
    with pytest.raises(ValueError):
        await t.train()


@pytest.mark.skip(reason="requires live TimescaleDB")
async def test_train_live():
    ...
