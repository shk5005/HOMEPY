"""국토부 실거래가 API 응답 페이지 파싱."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    total_count: int
    items: tuple[dict[str, str], ...]


class ApiError(Exception):
    """API가 정상 데이터 대신 오류를 돌려줬다 (HTTP 200이어도)."""


def parse_page(xml: bytes, success_codes: tuple[str, ...]) -> Page:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ApiError(f"XML 파싱 실패: {e}; 응답 앞부분={xml[:200]!r}") from e

    if root.tag == "OpenAPI_ServiceResponse":
        msg = " / ".join(
            (root.findtext(f"cmmMsgHeader/{t}") or "").strip()
            for t in ("errMsg", "returnAuthMsg", "returnReasonCode")
        )
        raise ApiError(f"서비스 오류: {msg}")
    if root.tag != "response":
        raise ApiError(f"알 수 없는 응답 루트: {root.tag}")

    code = (root.findtext("header/resultCode") or "").strip()
    if code not in success_codes:
        msg = (root.findtext("header/resultMsg") or "").strip()
        raise ApiError(f"resultCode={code!r}: {msg}")

    total_text = (root.findtext("body/totalCount") or "").strip()
    try:
        total = int(total_text)
    except ValueError as e:
        raise ApiError(f"totalCount가 숫자가 아니다: {total_text!r}") from e

    items = tuple(
        {child.tag: (child.text or "").strip() for child in item}
        for item in root.iterfind("body/items/item")
    )
    return Page(total_count=total, items=items)
