from datetime import date, datetime

import numpy as np
import pytest

from homepy.ml.features import (
    FeatureCombiner, RelationalFeatureExtractor, TimeSeriesFeatureExtractor,
)
from homepy.ml.models import MLFeatureSet

REL = {"adjacent_complex_count": 10.0, "development_upside_count": 3.0,
       "regulation_intensity": 0.7, "effective_tax_rate": 0.02,
       "cycle_phase_encoded": 2.0}
TS = {"price_ma_ratio": 1.05, "volume_change_rate": -0.1,
      "interest_rate_cumulative": 0.5, "jeonse_ratio_trend": -0.03,
      "search_zscore": 1.2}


async def test_relational_extractor_returns_five_features(mock_typedb):
    mock_typedb.set_query_result("adjacent_count", [{"count": 12}])
    mock_typedb.set_query_result("development_count", [{"count": 3}])
    features = await RelationalFeatureExtractor(mock_typedb).extract("C001")
    assert set(features) == set(REL)
    assert len(features) == 5
    assert all(isinstance(v, float) for v in features.values())
    assert features["adjacent_complex_count"] == 12.0
    assert features["development_upside_count"] == 3.0


async def test_relational_cycle_phase_and_tax(mock_typedb):
    mock_typedb.set_query_result("cycle_phase", [{"p": {"value": "Peak"}}])
    mock_typedb.set_query_result("effective_tax", [{"r": 2.0}, {"r": 4.0}])
    mock_typedb.set_query_result("regulation_weight", [{"w": 0.5}, {"w": 1.0}])
    f = await RelationalFeatureExtractor(mock_typedb).extract("C001")
    assert f["cycle_phase_encoded"] == 3.0
    assert f["effective_tax_rate"] == pytest.approx(0.03)
    assert f["regulation_intensity"] == pytest.approx(0.75)


async def test_relational_defaults_when_no_data(mock_typedb):
    f = await RelationalFeatureExtractor(mock_typedb).extract("C001")
    assert all(v == 0.0 for v in f.values())


async def test_relational_rejects_injection(mock_typedb):
    with pytest.raises(ValueError):
        await RelationalFeatureExtractor(mock_typedb).extract('C1"; delete')


async def test_timeseries_extractor_returns_five_features(mock_timescale):
    f = await TimeSeriesFeatureExtractor(mock_timescale).extract("C001", date(2026, 10, 1))
    assert set(f) == set(TS)
    assert f["price_ma_ratio"] > 0
    assert f["volume_change_rate"] == pytest.approx(0.2)
    assert f["interest_rate_cumulative"] == pytest.approx(0.75)
    assert f["jeonse_ratio_trend"] == pytest.approx(-1.0)


async def test_timeseries_extractor_respects_as_of_date(mock_timescale):
    await TimeSeriesFeatureExtractor(mock_timescale).extract("C001", date(2026, 6, 15))
    assert len(mock_timescale.executed_queries) == 5
    for query, args in zip(mock_timescale.executed_queries, mock_timescale.executed_args):
        assert "ts <=" in query
        as_of = [a for a in args if isinstance(a, datetime)]
        assert as_of and as_of[0].date() == date(2026, 6, 15)


async def test_timeseries_empty_data_is_neutral(mock_timescale):
    async def empty(q, *a):
        return []
    mock_timescale.execute = empty
    f = await TimeSeriesFeatureExtractor(mock_timescale).extract("C001", date(2026, 6, 15))
    assert f["price_ma_ratio"] == 1.0
    assert all(np.isfinite(v) for v in f.values())


def test_combiner_produces_no_nan():
    result = FeatureCombiner().combine(REL, TS)
    assert isinstance(result, MLFeatureSet)
    assert not np.any(np.isnan(result.combined))
    assert result.combined.shape == (10,)
    assert np.all((result.combined >= 0) & (result.combined <= 1))


def test_combiner_fills_missing_with_history_median():
    hist = {"search_zscore": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
    ts = {**TS, "search_zscore": float("nan")}
    r = FeatureCombiner(hist).combine(REL, ts)
    assert not np.any(np.isnan(r.combined))


def test_combiner_missing_key_without_history():
    ts = {k: v for k, v in TS.items() if k != "price_ma_ratio"}
    r = FeatureCombiner().combine(REL, ts)
    assert r.combined[5] == pytest.approx(0.5)


def test_combiner_uses_rolling_percentiles():
    hist = {"adjacent_complex_count": [float(i) for i in range(100)]}
    r = FeatureCombiner(hist).combine({**REL, "adjacent_complex_count": 50.0}, TS)
    assert r.combined[0] == pytest.approx((50 - 4.95) / (94.05 - 4.95), rel=1e-3)


@pytest.mark.skip(reason="requires live TypeDB and TimescaleDB")
async def test_live_pipeline():
    ...
