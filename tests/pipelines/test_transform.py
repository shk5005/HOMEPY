import numpy as np
import pandas as pd
import pytest

from homepy.pipelines.stages.transform import transform_domain
from homepy.pipelines.transformers import (
    CycleClassifier,
    MacroTransformer,
    PriceTransformer,
    SentimentComposer,
    SupplyDemandTransformer,
)
from homepy.pipelines.transformers.cycle_classifier import hp_filter


def test_price_transformer_calculates_per_sqm():
    df = pd.DataFrame({"price": [500000000], "area_sqm": [84.0]})
    result = PriceTransformer().transform(df)
    assert "price_per_sqm" in result.columns
    assert result.iloc[0]["price_per_sqm"] == pytest.approx(500000000 / 84.0)


def test_price_transformer_zero_area_is_null():
    df = pd.DataFrame({"price": [100.0, 200.0], "area_sqm": [0.0, 50.0]})
    result = PriceTransformer().transform(df)
    assert pd.isna(result.iloc[0]["price_per_sqm"])
    assert result.iloc[1]["price_per_sqm"] == pytest.approx(4.0)


def test_price_transformer_moving_averages_and_changes():
    df = pd.DataFrame({
        "ts": pd.date_range("2025-01", periods=14, freq="MS"),
        "district_code": ["A"] * 14,
        "price": [100.0 * (i + 1) for i in range(14)],
        "area_sqm": [1.0] * 14,
    })
    r = PriceTransformer().transform(df)
    assert pd.isna(r.loc[1, "ma_3m"])  # insufficient data -> NaN
    assert r.loc[2, "ma_3m"] == pytest.approx(200.0)
    assert r.loc[5, "ma_6m"] == pytest.approx(350.0)
    assert pd.isna(r.loc[10, "ma_12m"]) and r.loc[11, "ma_12m"] == pytest.approx(650.0)
    assert r.loc[1, "mom_change"] == pytest.approx(100.0)
    assert pd.isna(r.loc[11, "yoy_change"]) and r.loc[12, "yoy_change"] == pytest.approx(1200.0)
    assert r.loc[0, "district_mean_price_per_sqm"] == pytest.approx(100.0)


def test_price_transformer_missing_columns_noop():
    df = pd.DataFrame({"x": [1, 2]})
    assert list(PriceTransformer().transform(df).columns) == ["x"]


def test_macro_transformer():
    df = pd.DataFrame({
        "ts": pd.date_range("2025-01", periods=4, freq="MS"),
        "base_rate": [3.0, 3.25, 3.25, 3.0],
        "cpi": [2.0, 2.0, 2.5, 2.0],
        "m2": [1000.0, 1010.0, 1010.0, 1000.0],
    })
    r = MacroTransformer().transform(df)
    assert list(r["rate_direction"]) == [None, "up", "flat", "down"]
    assert list(r["real_interest_rate"]) == pytest.approx([1.0, 1.25, 0.75, 1.0])
    assert pd.isna(r.loc[0, "liquidity_growth_rate"])
    assert r.loc[1, "liquidity_growth_rate"] == pytest.approx(1.0)


def test_hp_filter_linear_series_is_its_own_trend():
    y = np.arange(100.0, 112.0)
    assert hp_filter(y) == pytest.approx(y, abs=1e-6)


def test_cycle_classifier_detects_expansion():
    df = pd.DataFrame({
        "ts": pd.date_range("2025-01", periods=12, freq="MS"),
        "price_index": range(100, 112),
    })
    result = CycleClassifier().classify(df, macro_df=None)
    assert result.iloc[-1]["cycle_phase"] == "expansion"
    assert result.iloc[-1]["coincident_index"] == pytest.approx(111.0)


def test_cycle_classifier_all_phases():
    # Sine wave: all four phases must appear.
    n = 48
    vals = 100 + 10 * np.sin(np.linspace(0, 4 * np.pi, n))
    df = pd.DataFrame({"ts": pd.date_range("2020-01", periods=n, freq="MS"), "price_index": vals})
    phases = set(CycleClassifier(lamb=14400).classify(df, None)["cycle_phase"].dropna())
    assert phases == {"expansion", "peak", "contraction", "recovery"}


def test_cycle_classifier_leading_index_with_macro():
    df = pd.DataFrame({"ts": pd.date_range("2025-01", periods=6, freq="MS"),
                       "price_index": range(100, 106)})
    macro = pd.DataFrame({"ts": df["ts"], "liquidity_growth_rate": [1.0] * 6,
                          "real_interest_rate": [0.5] * 6})
    r = CycleClassifier().classify(df, macro)
    assert r["leading_index"].tolist() == pytest.approx([100.5] * 6)


def test_cycle_classifier_short_or_empty_data():
    short = pd.DataFrame({"ts": pd.date_range("2025-01", periods=2, freq="MS"), "price_index": [100, 101]})
    assert len(CycleClassifier().classify(short, None)) == 2
    empty = pd.DataFrame({"ts": [], "price_index": []})
    assert len(CycleClassifier().classify(empty, None)) == 0


def test_supply_demand_transformer():
    supply = pd.DataFrame({
        "ts": ["2025-01"] * 2, "district_code": ["A", "B"],
        "supply_units": [100, 50], "unsold_units": [60, 10], "absorption_units": [20, 0],
        "median_price": [900.0, 500.0], "median_income": [100.0, 0.0],
    })
    pop = pd.DataFrame({"ts": ["2025-01"] * 2, "district_code": ["A", "B"], "new_households": [80, 70]})
    mig = pd.DataFrame({"ts": ["2025-01"] * 2, "district_code": ["A", "B"], "net_migration": [30, -10]})
    r = SupplyDemandTransformer().transform(supply, pop, mig)
    assert r["supply_demand_gap"].tolist() == [10, 10]  # (80+30-100), (70-10-50)
    assert r.loc[0, "pir"] == pytest.approx(9.0)
    assert pd.isna(r.loc[1, "pir"])  # zero income
    assert r.loc[0, "months_of_inventory"] == pytest.approx(3.0)
    assert pd.isna(r.loc[1, "months_of_inventory"])  # zero absorption


def test_sentiment_composer_fear_greed():
    df = pd.DataFrame({
        "buyer_sentiment": [25],
        "jeonse_ratio": [0.80],
        "volume_change": [-15.0],
        "search_trend": [30],
    })
    result = SentimentComposer().compose(df)
    assert result.iloc[0]["fear_greed_index"] < 30
    assert result.iloc[0]["fear_greed_index"] == pytest.approx(25 * .35 + 20 * .25 + 35 * .25 + 30 * .15)


def test_sentiment_composer_greed_and_bounds():
    df = pd.DataFrame({"buyer_sentiment": [100], "jeonse_ratio": [0.3],
                       "volume_change": [80.0], "search_trend": [100]})
    assert SentimentComposer().compose(df).iloc[0]["fear_greed_index"] == pytest.approx(100.0)


def test_sentiment_composer_merges_other_frames_and_missing_component():
    s = pd.DataFrame({"ts": ["2025-01"], "buyer_sentiment": [50]})
    v = pd.DataFrame({"ts": ["2025-01"], "volume_change": [0.0]})
    r = SentimentComposer().compose(s, volume_df=v)
    assert r.iloc[0]["fear_greed_index"] == pytest.approx((50 * .35 + 50 * .25) / .6)


def _cleaned(tmp_path, source, df, date="2026-01-02"):
    d = tmp_path / "cleaned" / source / date
    d.mkdir(parents=True)
    p = d / "data.parquet"
    df.to_parquet(p, index=False)
    return p


def test_transform_domain_price_and_cycle(tmp_path):
    p = _cleaned(tmp_path, "molit_trade", pd.DataFrame({"price": [840.0], "area_sqm": [84.0]}))
    out = transform_domain("price", {"molit_trade": p})
    assert out == tmp_path / "transformed" / "price" / "2026-01-02" / "price.parquet"
    assert pd.read_parquet(out).loc[0, "price_per_sqm"] == pytest.approx(10.0)

    idx = _cleaned(tmp_path, "reb_index", pd.DataFrame({
        "ts": pd.date_range("2025-01", periods=12, freq="MS"), "price_index": range(100, 112)}))
    out = transform_domain("cycle", {"reb_index": idx})
    assert pd.read_parquet(out).iloc[-1]["cycle_phase"] == "expansion"


def test_transform_domain_errors(tmp_path):
    with pytest.raises(ValueError):
        transform_domain("bogus", {"x": tmp_path})
    p = _cleaned(tmp_path, "other", pd.DataFrame({"a": [1]}))
    with pytest.raises(ValueError):
        transform_domain("macro", {"other": p})


def _sd_supply():
    return pd.DataFrame({"ts": ["2025-01"], "district_code": ["A"],
                         "supply_units": [100], "unsold_units": [10]})


def test_supply_demand_partial_inputs():
    pop = pd.DataFrame({"ts": ["2025-01"], "district_code": ["A"], "new_households": [80]})
    mig = pd.DataFrame({"ts": ["2025-01"], "district_code": ["A"], "net_migration": [30]})
    t = SupplyDemandTransformer()
    assert "supply_demand_gap" not in t.transform(_sd_supply()).columns
    assert t.transform(_sd_supply(), pop).iloc[0]["supply_demand_gap"] == -20
    assert t.transform(_sd_supply(), None, mig).iloc[0]["supply_demand_gap"] == -70


def test_price_transformer_aggregates_transactions_to_months():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-05", "2025-01-20", "2025-02-10", "2025-03-01"], utc=True),
        "district_code": ["A"] * 4,
        "price": [100.0, 300.0, 400.0, 600.0],
        "area_sqm": [1.0] * 4,
    })
    r = PriceTransformer().transform(df)
    assert len(r) == 3
    assert r["price_per_sqm"].tolist() == pytest.approx([200.0, 400.0, 600.0])
    assert r.loc[2, "ma_3m"] == pytest.approx(400.0)  # 3 months, not 3 trades
    assert r["n_trades"].tolist() == [2, 1, 1]
    assert r.loc[1, "mom_change"] == pytest.approx(100.0)


def test_macro_first_row_direction_none():
    df = pd.DataFrame({"base_rate": [3.0, 3.25]})
    assert MacroTransformer().transform(df)["rate_direction"].tolist() == [None, "up"]


def test_leading_index_nan_when_component_missing():
    df = pd.DataFrame({"ts": pd.date_range("2025-01", periods=4, freq="MS"), "price_index": range(100, 104)})
    macro = pd.DataFrame({"ts": df["ts"], "liquidity_growth_rate": [1.0] * 4})
    assert CycleClassifier().classify(df, macro)["leading_index"].isna().all()


def test_sentiment_unalignable_component_warns(caplog):
    s = pd.DataFrame({"ts": ["2025-01"], "buyer_sentiment": [50]})
    v = pd.DataFrame({"volume_change": [0.0]})
    with caplog.at_level("WARNING"):
        SentimentComposer().compose(s, volume_df=v)
    assert "dropped" in caplog.text


def test_transform_domain_output_date_is_max(tmp_path):
    a = _cleaned(tmp_path, "bok_ecos", pd.DataFrame({"base_rate": [3.0]}), date="2026-01-01")
    b = _cleaned(tmp_path, "other", pd.DataFrame({"x": [1]}), date="2026-01-09")
    out = transform_domain("macro", {"other": b, "bok_ecos": a})
    assert out.parent.name == "2026-01-09"
