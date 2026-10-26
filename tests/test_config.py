from pathlib import Path

import pytest

from homepy.config import load_settings

ROOT = Path(__file__).resolve().parent.parent


def test_load_default_config_matches_spec():
    s = load_settings(ROOT / "config" / "anomaly.toml")
    assert (s.window_months, s.min_count, s.mad_k, s.flat_pct) == (6, 3, 3.0, 0.15)
    assert s.exclude_direct is True and s.unsettled_months == 2
    assert s.version == "2026-10-26-draft"


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('version = "x"\n[thresholds]\nmad_kk = 2\n')
    with pytest.raises(ValueError, match="mad_kk"):
        load_settings(p)


def test_as_dict_round_trips_values():
    s = load_settings(ROOT / "config" / "anomaly.toml")
    d = s.as_dict()
    assert d["version"] == "2026-10-26-draft"
    assert d["cancelled_codes"] == ["O"]
