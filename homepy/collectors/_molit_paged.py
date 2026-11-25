"""Shared month/page loop helpers for MOLIT data.go.kr collectors."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable

from homepy.collectors._xml import parse_items

NUM_OF_ROWS = 1000


async def fetch_all_items(fetch_text: Callable[[dict], Awaitable[str]], params: dict,
                          service: str) -> list[ET.Element]:
    """Fetch every page for ``params``; stop on empty page or once totalCount is reached."""
    out: list[ET.Element] = []
    page, seen = 1, 0
    while True:
        text = await fetch_text({**params, "numOfRows": NUM_OF_ROWS, "pageNo": page})
        items, total = parse_items(text, service)
        out.extend(items)
        seen += len(items)
        if not items or seen >= total:
            return out
        page += 1
