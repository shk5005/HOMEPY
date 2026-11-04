"""Weekly Mon 07:00 KST: price_index, loan_rate, sentiment, complex_info -> cycle + sentiment."""
from __future__ import annotations

from datetime import date

from homepy.pipelines.flows._common import FlowResult, flow, run_scheduled, window

SOURCE_NAMES = ["price_index", "loan_rate", "sentiment", "complex_info"]
DOMAINS = {"cycle": ["reb_index", "bok_ecos"], "sentiment": ["sentiment"]}
SCHEDULE_CRON = "0 7 * * 1"  # timezone Asia/Seoul


@flow("homepy-weekly")
async def weekly_pipeline(date: date | None = None, collectors=None, timescale_svc=None,
                          typedb_svc=None, data_dir="data") -> FlowResult:
    start, end = window(date, 7)
    return await run_scheduled(SOURCE_NAMES, DOMAINS, start, end, collectors, timescale_svc, typedb_svc, data_dir)
