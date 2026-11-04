import pandas as pd

from homepy.pipelines.quality.gates import QualityGate
from homepy.pipelines.stages.clean import clean_source


def _write(tmp_path, df, source="test", date="2026-01-02"):
    d = tmp_path / "raw" / source / date
    d.mkdir(parents=True)
    p = d / "data.parquet"
    df.to_parquet(p, index=False)
    return p


def test_clean_removes_duplicates(tmp_path):
    p = _write(tmp_path, pd.DataFrame({"ts": ["2026-01-01"] * 3, "base_rate": [3.25] * 3}))
    result = clean_source("test", p)
    df = pd.read_parquet(result.output_path)
    assert len(df) == 1
    assert not result.passed  # duplicate ratio > 1%
    assert result.output_path == tmp_path / "cleaned" / "test" / "2026-01-02" / "data.parquet"


def test_clean_flags_high_null_ratio(tmp_path):
    p = _write(tmp_path, pd.DataFrame({"ts": [None] * 10, "base_rate": [3.25] * 10}))
    result = clean_source("test", p)
    assert not result.passed
    assert result.quality_report.null_ratio > 0.05


def test_clean_passes_good_data_and_converts_kst_to_utc(tmp_path):
    p = _write(tmp_path, pd.DataFrame({"ts": ["2026-01-01", "2026-01-02"], "v": [1.0, 2.0]}))
    result = clean_source("test", p)
    assert result.passed
    df = pd.read_parquet(result.output_path)
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["ts"].iloc[0] == pd.Timestamp("2025-12-31 15:00", tz="UTC")


def test_tz_aware_ts_converted_to_utc(tmp_path):
    ts = pd.to_datetime(["2026-01-01 09:00"]).tz_localize("Asia/Seoul")
    p = _write(tmp_path, pd.DataFrame({"ts": ts, "v": [1.0]}))
    df = pd.read_parquet(clean_source("test", p).output_path)
    assert df["ts"].iloc[0] == pd.Timestamp("2026-01-01 00:00", tz="UTC")


def test_outliers_flagged_not_removed(tmp_path):
    vals = [10.0, 11.0, 10.5, 9.5, 10.2, 10.1, 9.9, 10.3, 10.0, 500.0]
    p = _write(tmp_path, pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=10).astype(str), "v": vals}))
    df = pd.read_parquet(clean_source("test", p).output_path)
    assert len(df) == 10
    assert df["_outlier"].sum() == 1
    assert bool(df.loc[df["v"] == 500.0, "_outlier"].iloc[0])


def test_registry_dedup_keys_and_schema_mismatch(tmp_path):
    raw = pd.DataFrame({
        "ts": ["2026-01-01", "2026-01-01"], "region_code": [" 11000 ", "11000"], "price_index": [100.0, 101.0],
    })
    p = _write(tmp_path, raw, source="reb_index")
    result = clean_source("reb_index", p)
    assert len(pd.read_parquet(result.output_path)) == 1  # deduped on (ts, region_code) after trim

    p2 = _write(tmp_path, pd.DataFrame({"ts": ["2026-01-01"], "v": [1.0]}), source="kosis")
    bad = clean_source("kosis", p2)
    assert not bad.passed and not bad.quality_report.schema_ok


def test_quality_gate_thresholds():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
    assert QualityGate(0.05, 0.01, True).check(df, {"a": "float"}).passed
    assert not QualityGate(0.05, 0.01, True).check(df, {"b": "float"}).passed
    assert QualityGate(0.05, 0.01, False).check(df, {"b": "float"}).passed


def test_mixed_naive_and_offset_timestamps_do_not_crash(tmp_path):
    p = _write(tmp_path, pd.DataFrame({
        "ts": ["2026-01-01 09:00:00", "2026-01-01 09:00:00+09:00", "2026-01-01 00:00:00+00:00"],
        "v": [1.0, 2.0, 3.0],
    }))
    df = pd.read_parquet(clean_source("test", p).output_path)
    assert str(df["ts"].dt.tz) == "UTC"
    assert (df["ts"] == pd.Timestamp("2026-01-01 00:00", tz="UTC")).all()


def test_registry_uses_collector_source_names():
    from homepy.pipelines.stages.clean import SOURCE_RULES
    assert "regulation_monitor" in SOURCE_RULES and "tax_rule_monitor" in SOURCE_RULES
    assert "regulation" not in SOURCE_RULES and "tax_rule" not in SOURCE_RULES


def test_null_ratio_is_overall_not_per_column():
    cols = {f"c{i}": [float(j) for j in range(10)] for i in range(25)}
    cols["optional"] = [None] * 10  # 100% null column, overall 1/26 ~ 3.8%
    assert QualityGate().check(pd.DataFrame(cols), {}).passed


def test_reb_index_region_code_renamed_to_district_code(tmp_path):
    df = pd.DataFrame({"ts": ["2026-01-01"], "region_code": ["11680"], "price_index": [100.5]})
    out = pd.read_parquet(clean_source("reb_index", _write(tmp_path, df, "reb_index")).output_path)
    assert "district_code" in out.columns and "region_code" not in out.columns


def test_kosis_long_to_wide_pivot(tmp_path):
    df = pd.DataFrame({
        "ts": ["2026-01-01"] * 4,
        "region_code": ["11680", "11680", "11650", "11650"],
        "region_name": ["a", "a", "b", "b"],
        "item_code": ["T1", "T2", "T1", "T2"],
        "item_name": ["Total Pop", "Households", "Total Pop", "Households"],
        "value": [100.0, 40.0, 200.0, 80.0],
        "unit": ["p", "h", "p", "h"],
    })
    out = pd.read_parquet(clean_source("kosis", _write(tmp_path, df, "kosis")).output_path)
    assert {"ts", "district_code", "total_pop", "households"} <= set(out.columns)
    assert not {"region_code", "region_name", "unit", "item_code", "value"} & set(out.columns)
    assert len(out) == 2
    row = out[out.district_code == "11680"].iloc[0]
    assert row.total_pop == 100.0 and row.households == 40.0
