from datetime import date

import pytest

from homepy.collect import (
    IncompleteCollection,
    Snapshot,
    ensure_months,
    fetch_month,
    load_latest,
    save_snapshot,
)
from homepy.config import Settings

SETTINGS = Settings(version="t", page_size=2)


def page_xml(total: int, n_items: int, tag: str = "x") -> bytes:
    items = "".join(f"<item><aptNm>{tag}{i}</aptNm></item>" for i in range(n_items))
    return (
        "<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>"
        f"<body><items>{items}</items><totalCount>{total}</totalCount></body></response>"
    ).encode()


class FakeGetter:
    def __init__(self, pages: dict[int, bytes]):
        self.pages = pages
        self.calls: list[dict[str, str]] = []

    def __call__(self, url: str, params: dict[str, str]) -> bytes:
        self.calls.append(params)
        return self.pages[int(params["pageNo"])]


def test_paginates_until_total():
    get = FakeGetter({1: page_xml(3, 2), 2: page_xml(3, 1)})
    pages = fetch_month("11680", "2026-09", "KEY", get, SETTINGS)
    assert len(pages) == 2 and len(get.calls) == 2
    assert get.calls[0]["DEAL_YMD"] == "202609" and get.calls[0]["numOfRows"] == "2"
    assert get.calls[0]["LAWD_CD"] == "11680" and get.calls[0]["serviceKey"] == "KEY"


def test_short_collection_raises():
    get = FakeGetter({1: page_xml(3, 2), 2: page_xml(3, 0)})
    with pytest.raises(IncompleteCollection) as e:
        fetch_month("11680", "2026-09", "KEY", get, SETTINGS)
    assert (e.value.expected, e.value.received) == (3, 2)


def test_empty_month_single_call():
    get = FakeGetter({1: page_xml(0, 0)})
    assert len(fetch_month("11680", "2026-09", "KEY", get, SETTINGS)) == 1
    assert len(get.calls) == 1


def snap(month: str, fetched: date, tag: str = "x") -> Snapshot:
    return Snapshot("11680", month, fetched, (page_xml(1, 1, tag),))


def test_save_and_load_round_trip(tmp_path):
    s = snap("2026-01", date(2026, 2, 5))
    save_snapshot(tmp_path, s)
    assert load_latest(tmp_path, "11680", "2026-01") == s


def test_load_latest_picks_newest_date(tmp_path):
    save_snapshot(tmp_path, snap("2026-09", date(2026, 10, 1), "old"))
    save_snapshot(tmp_path, snap("2026-09", date(2026, 10, 20), "new"))
    latest = load_latest(tmp_path, "11680", "2026-09")
    assert latest.fetched_on == date(2026, 10, 20) and b"new0" in latest.pages[0]


def test_load_latest_missing_is_none(tmp_path):
    assert load_latest(tmp_path, "11680", "2026-09") is None


def test_settled_month_not_refetched(tmp_path):
    save_snapshot(tmp_path, snap("2026-01", date(2026, 2, 5)))
    get = FakeGetter({})
    out = ensure_months(tmp_path, "11680", ["2026-01"], "KEY", get, SETTINGS, date(2026, 10, 26))
    assert get.calls == [] and out[0].fetched_on == date(2026, 2, 5)


def test_unsettled_month_refetched(tmp_path):
    save_snapshot(tmp_path, snap("2026-09", date(2026, 10, 1)))
    get = FakeGetter({1: page_xml(1, 1)})
    out = ensure_months(tmp_path, "11680", ["2026-09"], "KEY", get, SETTINGS, date(2026, 10, 26))
    assert len(get.calls) == 1 and out[0].fetched_on == date(2026, 10, 26)
    assert (tmp_path / "11680" / "2026-09" / "20261026" / "page_001.xml").exists()


def test_offline_missing_month_raises(tmp_path):
    with pytest.raises(RuntimeError):
        ensure_months(tmp_path, "11680", ["2026-01"], None, FakeGetter({}), SETTINGS, date(2026, 10, 26))


def test_offline_unsettled_month_uses_existing_snapshot(tmp_path):
    save_snapshot(tmp_path, snap("2026-09", date(2026, 10, 1)))
    out = ensure_months(tmp_path, "11680", ["2026-09"], None, FakeGetter({}), SETTINGS, date(2026, 10, 26))
    assert out[0].fetched_on == date(2026, 10, 1)


def test_manifest_records_counts(tmp_path):
    import json
    s = Snapshot("11680", "2026-09", date(2026, 10, 26), (page_xml(3, 2), page_xml(3, 1)))
    path = save_snapshot(tmp_path, s)
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert (m["total_count"], m["received"], m["pages"]) == (3, 3, 2)
