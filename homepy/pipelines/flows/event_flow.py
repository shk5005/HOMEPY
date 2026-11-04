"""Event-driven: regulation / tax_rule change -> validate -> manual review gate -> load."""
from __future__ import annotations

import inspect
from datetime import date
from typing import Awaitable, Callable, Optional, Union

from homepy.pipelines.flows._common import (
    FlowResult, clean_sources, collect_sources, flow, run_syncs, window, SOURCES, _Services)

EVENT_TYPES = ("regulation", "tax_rule")
Approver = Callable[[str, "object"], Union[bool, Awaitable[bool]]]
Loader = Callable[[str, "object"], Awaitable[int]]


@flow("homepy-event")
async def event_pipeline(event_type: str, date: date | None = None, collectors=None,
                         approve: Optional[Approver] = None, loader: Optional[Loader] = None,
                         timescale_svc=None, typedb_svc=None) -> FlowResult:
    """Collect and validate; load only if the manual review gate ``approve(event_type, cleaned_path)``
    returns True. With no approver the data is held (cleaned, not loaded) pending review.
    ``loader(event_type, cleaned_path) -> rows`` performs the load for approved data
    (no TimescaleDB table exists for regulation/tax data yet), then aggregates are synced."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}; expected one of {EVENT_TYPES}")
    result = FlowResult()
    start, end = window(date, 1)
    raw = await collect_sources([event_type], start, end, collectors or {}, result)
    cleaned = await clean_sources(raw, {event_type: SOURCES[event_type].clean_key}, result)
    if not cleaned:
        return result
    path = cleaned[SOURCES[event_type].clean_key]

    approved = False
    if approve is not None:
        verdict = approve(event_type, path)
        approved = bool(await verdict if inspect.isawaitable(verdict) else verdict)
    if not approved:
        result.errors.append(f"review:{event_type}: held pending manual review")
        return result
    if loader is not None:
        try:
            result.loaded_rows += await loader(event_type, path)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"load:{event_type}: {type(exc).__name__}: {exc}")
            return result
    async with _Services(timescale_svc, typedb_svc) as svc:
        await run_syncs(svc.timescale_svc, svc.typedb_svc, result)
    return result
