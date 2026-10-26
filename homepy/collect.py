"""실거래가 수집과 원본 스냅샷 보관 (spec FR-1)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from homepy.config import Settings
from homepy.dates import month_end, months_before
from homepy.parse import parse_page

# plan Task 0에서 data.go.kr 기술문서로 확인할 것
ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

Getter = Callable[[str, dict[str, str]], bytes]


class IncompleteCollection(Exception):
    def __init__(self, expected: int, received: int):
        super().__init__(f"totalCount={expected}인데 {received}건만 받았다")
        self.expected = expected
        self.received = received


@dataclass(frozen=True)
class Snapshot:
    lawd_cd: str
    month: str  # "YYYY-MM"
    fetched_on: date
    pages: tuple[bytes, ...]


def fetch_month(lawd_cd: str, month: str, service_key: str, get: Getter,
                settings: Settings) -> tuple[bytes, ...]:
    pages: list[bytes] = []
    received = 0
    page_no = 1
    while True:
        params = {
            "serviceKey": service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": month.replace("-", ""),
            "pageNo": str(page_no),
            "numOfRows": str(settings.page_size),
        }
        body = get(ENDPOINT, params)
        page = parse_page(body, settings.success_codes)
        pages.append(body)
        received += len(page.items)
        if received >= page.total_count:
            if received > page.total_count:
                raise IncompleteCollection(page.total_count, received)
            return tuple(pages)
        if not page.items:
            raise IncompleteCollection(page.total_count, received)
        page_no += 1


def _month_dir(root: Path, lawd_cd: str, month: str) -> Path:
    return Path(root) / lawd_cd / month


def _counts(pages: tuple[bytes, ...]) -> tuple[int | None, int]:
    total = None
    received = 0
    for body in pages:
        root = ET.fromstring(body)
        text = root.findtext("body/totalCount")
        if total is None and text is not None:
            total = int(text.strip())
        received += len(root.findall("body/items/item"))
    return total, received


def save_snapshot(root: Path, snap: Snapshot) -> Path:
    month_dir = _month_dir(root, snap.lawd_cd, snap.month)
    month_dir.mkdir(parents=True, exist_ok=True)
    final = month_dir / snap.fetched_on.strftime("%Y%m%d")
    tmp = Path(tempfile.mkdtemp(dir=month_dir, prefix=".tmp-"))
    try:
        for i, body in enumerate(snap.pages, start=1):
            (tmp / f"page_{i:03d}.xml").write_bytes(body)
        total, received = _counts(snap.pages)
        (tmp / "manifest.json").write_text(json.dumps({
            "lawd_cd": snap.lawd_cd,
            "month": snap.month,
            "fetched_on": snap.fetched_on.isoformat(),
            "pages": len(snap.pages),
            "total_count": total,
            "received": received,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def load_latest(root: Path, lawd_cd: str, month: str) -> Snapshot | None:
    month_dir = _month_dir(root, lawd_cd, month)
    if not month_dir.is_dir():
        return None
    dated = sorted(p for p in month_dir.iterdir()
                   if p.is_dir() and p.name.isdigit() and len(p.name) == 8)
    if not dated:
        return None
    latest = dated[-1]
    pages = tuple(p.read_bytes() for p in sorted(latest.glob("page_*.xml")))
    fetched = datetime.strptime(latest.name, "%Y%m%d").date()
    return Snapshot(lawd_cd, month, fetched, pages)


def ensure_months(root: Path, lawd_cd: str, months: list[str], service_key: str | None,
                  get: Getter, settings: Settings, today: date) -> list[Snapshot]:
    """스냅샷이 없거나 미확정 기간에 든 월은 다시 받는다. 오프라인이면 있는 스냅샷만 쓴다."""
    cutoff = months_before(today, settings.unsettled_months)
    out = []
    for month in months:
        existing = load_latest(root, lawd_cd, month)
        needs_fetch = existing is None or month_end(month) >= cutoff
        if needs_fetch and service_key is not None:
            pages = fetch_month(lawd_cd, month, service_key, get, settings)
            snap = Snapshot(lawd_cd, month, today, pages)
            save_snapshot(root, snap)
            out.append(snap)
        elif existing is not None:
            out.append(existing)
        else:
            raise RuntimeError(f"{lawd_cd} {month}: 스냅샷이 없고 오프라인 모드라 수집할 수 없다")
    return out


def requests_getter(url: str, params: dict[str, str]) -> bytes:
    import requests

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.content
