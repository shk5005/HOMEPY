"""Daily 06:00 KST: real_trade, interest_rate, exchange_rate -> price, macro."""
from __future__ import annotations

from datetime import date

from homepy.pipelines.flows._common import FlowResult, flow, run_scheduled, window

SOURCE_NAMES = ["real_trade", "interest_rate", "exchange_rate"]
DOMAINS = {"price": ["molit_trade"], "macro": ["bok_ecos"]}
SCHEDULE_CRON = "0 6 * * *"  # timezone Asia/Seoul


@flow("homepy-daily")
async def daily_pipeline(date: date | None = None, collectors=None, timescale_svc=None,
                         typedb_svc=None, data_dir="data") -> FlowResult:
    start, end = window(date, 1)
    return await run_scheduled(SOURCE_NAMES, DOMAINS, start, end, collectors, timescale_svc, typedb_svc, data_dir)
