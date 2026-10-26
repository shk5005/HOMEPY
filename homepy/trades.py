"""원본 거래 항목 → Trade 정제 (spec FR-2)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from homepy.config import Settings

UNKNOWN = "미상"


@dataclass(frozen=True)
class Trade:
    trade_id: str
    group_key: str
    key_fallback: bool
    apt_name: str
    umd_name: str
    area_m2: Decimal
    area_band: int
    deal_date: date
    price_manwon: int
    floor: int | None
    dealing_type: str
    cancelled: bool
    seller_type: str
    buyer_type: str


def parse_amount(s: str) -> int:
    return int(s.replace(",", "").strip())


def area_band(area: Decimal) -> int:
    return int(area.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _trade_id(item: dict[str, str]) -> str:
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def _to_trade(item: dict[str, str], settings: Settings) -> Trade:
    get = lambda k: item.get(k, "").strip()  # noqa: E731
    area = Decimal(get("excluUseAr"))
    band = area_band(area)
    apt_seq = get("aptSeq")
    if apt_seq:
        group_key, fallback = f"{apt_seq}|{band}", False
    else:
        group_key, fallback = f"{get('umdNm')}|{get('jibun')}|{get('aptNm')}|{band}", True
    floor = get("floor")
    return Trade(
        trade_id=_trade_id(item),
        group_key=group_key,
        key_fallback=fallback,
        apt_name=get("aptNm"),
        umd_name=get("umdNm"),
        area_m2=area,
        area_band=band,
        deal_date=date(int(get("dealYear")), int(get("dealMonth")), int(get("dealDay"))),
        price_manwon=parse_amount(get("dealAmount")),
        floor=int(floor) if floor else None,
        dealing_type=get("dealingGbn") or UNKNOWN,
        cancelled=get("cdealType") in settings.cancelled_codes,
        seller_type=get("slerGbn") or UNKNOWN,
        buyer_type=get("buyerGbn") or UNKNOWN,
    )


def normalize(items: Iterable[dict[str, str]], settings: Settings) -> list[Trade]:
    """정제한다. 모든 원본 필드가 같은 행(같은 trade_id)만 중복으로 제거한다."""
    by_id: dict[str, Trade] = {}
    for item in items:
        t = _to_trade(item, settings)
        by_id.setdefault(t.trade_id, t)
    return sorted(by_id.values(), key=lambda t: (t.group_key, t.deal_date, t.trade_id))
