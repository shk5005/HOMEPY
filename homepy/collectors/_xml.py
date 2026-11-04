"""Shared parsing for data.go.kr style XML responses."""
from __future__ import annotations

import xml.etree.ElementTree as ET

OK_CODES = {"00", "000"}
NO_DATA_CODES = {"03", "003"}


def text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def to_int(s: str) -> int | None:
    s = s.replace(",", "").strip()
    return int(float(s)) if s else None


def to_float(s: str) -> float | None:
    s = s.replace(",", "").strip()
    return float(s) if s else None


def parse_items(xml_text: str, service: str) -> tuple[list[ET.Element], int]:
    """Return (item elements, totalCount). No-data / empty body -> ([], 0)."""
    if not xml_text.strip():
        return [], 0
    root = ET.fromstring(xml_text)
    code = (root.findtext("header/resultCode") or "").strip()
    if code in NO_DATA_CODES:
        return [], 0
    if code not in OK_CODES:
        msg = (root.findtext("header/resultMsg") or "unexpected response").strip()
        raise ValueError(f"{service} error {code}: {msg}")
    items = root.findall("body/items/item")
    try:
        total = int((root.findtext("body/totalCount") or "").strip() or len(items))
    except ValueError:
        total = len(items)
    return items, total
