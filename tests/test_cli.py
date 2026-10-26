import csv
from datetime import date
from pathlib import Path

from homepy.cli import main
from homepy.collect import Snapshot, save_snapshot
from homepy.dates import month_range

ROOT = Path(__file__).resolve().parent.parent
CONFIG = str(ROOT / "config" / "anomaly.toml")


def item(day_month: tuple[int, int], amount: str, seq: str = "11680-1", dealing: str = "중개거래") -> str:
    m, d = day_month
    return (
        f"<item><aptSeq>{seq}</aptSeq><aptNm>테스트</aptNm><umdNm>개포동</umdNm><jibun>1</jibun>"
        f"<excluUseAr>84.97</excluUseAr><dealYear>2026</dealYear><dealMonth>{m}</dealMonth>"
        f"<dealDay>{d}</dealDay><dealAmount>{amount}</dealAmount><floor>5</floor>"
        f"<dealingGbn>{dealing}</dealingGbn><cdealType></cdealType>"
        f"<slerGbn>개인</slerGbn><buyerGbn>개인</buyerGbn></item>"
    )


def page(items: list[str]) -> bytes:
    return (
        "<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>"
        f"<body><items>{''.join(items)}</items><totalCount>{len(items)}</totalCount></body></response>"
    ).encode()


def build_raw(root: Path) -> None:
    by_month = {
        "2026-06": [item((6, 1), "100,000"), item((6, 2), "101,000"), item((6, 3), "99,000")],
        "2026-07": [item((7, 1), "100,500")],
        "2026-09": [item((9, 1), "130,000"), item((9, 2), "100,200"), item((9, 3), "50,000", dealing="직거래")],
    }
    for month in month_range("2026-02", "2026-09"):
        save_snapshot(root, Snapshot("11680", month, date(2026, 10, 26), (page(by_month.get(month, [])),)))


def run(tmp_path: Path, out: str, *extra: str) -> int:
    return main(["run", "--lawd", "11680", "--from", "2026-08", "--to", "2026-09",
                 "--config", CONFIG, "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / out),
                 "--offline", *extra])


def rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_cli_offline_end_to_end(tmp_path):
    build_raw(tmp_path / "raw")
    assert run(tmp_path, "a") == 0
    for f in ("trades.csv", "groups.csv", "run.json"):
        assert (tmp_path / "a" / f).exists()
    trades = {r["price_manwon"]: r for r in rows(tmp_path / "a" / "trades.csv")}
    assert "F3" in trades["130000"]["flags"].split(";")
    assert trades["50000"]["flags"].split(";")[0] == "F2"
    assert "F3" not in trades["100200"]["flags"]


def test_cli_reproducible(tmp_path):
    build_raw(tmp_path / "raw")
    assert run(tmp_path, "a") == 0 and run(tmp_path, "b") == 0
    for f in ("trades.csv", "groups.csv"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_cli_outputs_only_requested_months(tmp_path):
    build_raw(tmp_path / "raw")
    run(tmp_path, "a")
    assert {r["deal_date"][:7] for r in rows(tmp_path / "a" / "trades.csv")} == {"2026-09"}
    assert {r["month"] for r in rows(tmp_path / "a" / "groups.csv")} <= {"2026-08", "2026-09"}


def test_cli_missing_key_exit_2(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)
    code = main(["run", "--lawd", "11680", "--from", "2026-08", "--to", "2026-09",
                 "--config", CONFIG, "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "o")])
    assert code == 2 and "DATA_GO_KR_SERVICE_KEY" in capsys.readouterr().err


def test_cli_offline_missing_snapshot_exit_1(tmp_path, capsys):
    assert run(tmp_path, "a") == 1
    assert "스냅샷" in capsys.readouterr().err


def test_cli_network_error_exit_1(monkeypatch, tmp_path, capsys):
    import requests

    import homepy.cli

    def boom(url, params):
        raise requests.ConnectionError("no route")

    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "K")
    monkeypatch.setattr(homepy.cli, "requests_getter", boom)
    code = main(["run", "--lawd", "11680", "--from", "2026-08", "--to", "2026-09",
                 "--config", CONFIG, "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "o")])
    assert code == 1 and "no route" in capsys.readouterr().err


def test_cli_malformed_row_exit_1(tmp_path, capsys):
    build_raw(tmp_path / "raw")
    save_snapshot(tmp_path / "raw", Snapshot("11680", "2026-09", date(2026, 10, 27), (page([item((9, 1), "")]),)))
    assert run(tmp_path, "a") == 1
    assert "dealAmount" in capsys.readouterr().err


import pytest  # noqa: E402


@pytest.mark.parametrize("start,end", [("2026-09", "2026-01"), ("202601", "2026-09"), ("2026-13", "2026-12")])
def test_cli_bad_month_args_exit_2(tmp_path, capsys, start, end):
    code = main(["run", "--lawd", "11680", "--from", start, "--to", end, "--config", CONFIG,
                 "--raw", str(tmp_path / "raw"), "--out", str(tmp_path / "o"), "--offline"])
    assert code == 2 and "YYYY-MM" in capsys.readouterr().err
