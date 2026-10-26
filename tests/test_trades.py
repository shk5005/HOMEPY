from datetime import date
from decimal import Decimal

import pytest

from homepy.config import Settings
from homepy.trades import area_band, normalize, parse_amount

S = Settings(version="t")


def raw(**kw) -> dict[str, str]:
    base = {
        "aptSeq": "11680-123", "aptNm": "개포주공5단지", "umdNm": "개포동", "jibun": "187",
        "excluUseAr": "84.5", "dealYear": "2026", "dealMonth": "9", "dealDay": "29",
        "dealAmount": "82,500", "floor": "13", "dealingGbn": "중개거래", "cdealType": "",
        "slerGbn": "개인", "buyerGbn": "개인", "aptDong": "",
    }
    base.update(kw)
    return base


def test_parse_amount():
    assert parse_amount("  82,500") == 82500


@pytest.mark.parametrize("a,b", [("84.5", 85), ("83.5", 84), ("84.49", 84), ("59.97", 60)])
def test_area_band_half_up(a, b):
    assert area_band(Decimal(a)) == b


def test_fields_converted():
    t, = normalize([raw()], S)
    assert t.price_manwon == 82500 and t.deal_date == date(2026, 9, 29)
    assert t.area_m2 == Decimal("84.5") and t.area_band == 85 and t.floor == 13
    assert len(t.trade_id) == 12


def test_group_key_uses_aptSeq():
    t, = normalize([raw()], S)
    assert t.group_key == "11680-123|85" and not t.key_fallback


def test_group_key_fallback_when_aptSeq_blank():
    t, = normalize([raw(aptSeq="", excluUseAr="83.17")], S)
    assert t.group_key == "개포동|187|개포주공5단지|83" and t.key_fallback


def test_cancelled_from_code():
    a, = normalize([raw(cdealType="O")], S)
    b, = normalize([raw(cdealType="")], S)
    assert a.cancelled and not b.cancelled


def test_blank_dealing_type_is_unknown():
    t, = normalize([raw(dealingGbn="")], S)
    assert t.dealing_type == "미상"


def test_blank_floor_is_none():
    t, = normalize([raw(floor="")], S)
    assert t.floor is None


def test_exact_duplicates_removed_partial_kept():
    assert len(normalize([raw(), raw()], S)) == 1
    assert len(normalize([raw(), raw(floor="7")], S)) == 2


def test_trade_id_independent_of_key_order():
    r = raw()
    reordered = dict(reversed(list(r.items())))
    assert normalize([r], S)[0].trade_id == normalize([reordered], S)[0].trade_id


def test_output_sorted():
    ts = normalize([
        raw(aptSeq="B", dealDay="2"),
        raw(aptSeq="A", dealDay="5"),
        raw(aptSeq="A", dealDay="1"),
    ], S)
    assert [(t.group_key, t.deal_date.day) for t in ts] == [("A|85", 1), ("A|85", 5), ("B|85", 2)]


@pytest.mark.parametrize("field,value", [("dealAmount", ""), ("excluUseAr", ""), ("dealDay", "")])
def test_malformed_item_raises_bad_item_with_context(field, value):
    from homepy.trades import BadItem
    with pytest.raises(BadItem, match=field):
        normalize([raw(**{field: value})], S)


def test_non_numeric_floor_is_none():
    t, = normalize([raw(floor="B1")], S)
    assert t.floor is None
    assert normalize([raw(floor="-1")], S)[0].floor == -1
