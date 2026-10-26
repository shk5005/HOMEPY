import csv
import json
from datetime import date, datetime

from homepy.baseline import compute_baselines
from homepy.collect import Snapshot
from homepy.config import Settings
from homepy.flags import Flag, FlaggedTrade
from homepy.report import (
    GROUP_COLUMNS,
    TRADE_COLUMNS,
    write_groups_csv,
    write_run_json,
    write_trades_csv,
)
from tests.test_flags import mk

S = Settings(version="t")


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def test_trades_csv_header_and_bom(tmp_path):
    p = tmp_path / "trades.csv"
    write_trades_csv(p, [FlaggedTrade(mk(100_000, date(2026, 9, 1)), (), (), None, None, 0)])
    assert p.read_bytes()[:3] == b"\xef\xbb\xbf"
    assert tuple(read_rows(p)[0]) == TRADE_COLUMNS
    assert b"\r\n" not in p.read_bytes()


def test_none_and_bool_and_multi_formatting(tmp_path):
    p = tmp_path / "trades.csv"
    t = mk(100_000, date(2026, 9, 1), floor=None, cancelled=True)
    write_trades_csv(p, [FlaggedTrade(t, (Flag.F1, Flag.F4), ("a", "b"), None, None, 2)])
    row = dict(zip(TRADE_COLUMNS, read_rows(p)[1]))
    assert row["floor"] == "" and row["cancelled"] == "true" and row["key_fallback"] == "false"
    assert row["flags"] == "F1;F4" and row["reasons"] == "a;b"
    assert row["comparison_median_manwon"] == "" and row["deviation"] == ""
    assert row["deal_date"] == "2026-09-01" and row["area_m2"] == "84.9"


def test_groups_csv(tmp_path):
    p = tmp_path / "groups.csv"
    flagged = [FlaggedTrade(mk(100_000, date(2026, 9, 1)), (Flag.F3,), ("x",), None, None, 0)]
    write_groups_csv(p, compute_baselines(flagged, S, ["2026-09"], date(2026, 10, 26)))
    rows = read_rows(p)
    row = dict(zip(GROUP_COLUMNS, rows[1]))
    assert tuple(rows[0]) == GROUP_COLUMNS
    assert row["F3"] == "1" and row["F1"] == "0" and row["baseline_median_manwon"] == ""
    assert row["unsettled"] == "true" and row["month"] == "2026-09"


def test_run_json(tmp_path):
    p = tmp_path / "run.json"
    snaps = [Snapshot("11680", "2026-09", date(2026, 10, 26), ())]
    write_run_json(p, S, snaps, date(2026, 10, 26), datetime(2026, 10, 26, 18, 0))
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["settings"]["version"] == "t" and d["as_of"] == "2026-10-26"
    assert d["snapshots"] == [{"lawd_cd": "11680", "month": "2026-09", "fetched_on": "2026-10-26"}]
    assert d["run_at"] == "2026-10-26T18:00:00" and "homepy_version" in d
