"""Monthly 15th 08:00 KST: liquidity, population, migration, supply, unsold, macro_index
-> macro + supply_demand + cycle reclassify."""
from __future__ import annotations

from datetime import date

from homepy.pipelines.flows._common import FlowResult, flow, run_scheduled, window

SOURCE_NAMES = ["liquidity", "population", "migration", "supply", "unsold", "macro_index"]
# cycle reclassify also needs reb_index, taken from the latest cleaned file on disk.
DOMAINS = {
    "macro": ["bok_ecos"],
    "supply_demand": ["molit_supply", "kosis"],
    "cycle": ["reb_index", "bok_ecos"],
}
SCHEDULE_CRON = "0 8 15 * *"  # timezone Asia/Seoul


@flow("homepy-monthly")
async def monthly_pipeline(date: date | None = None, collectors=None, timescale_svc=None,
                           typedb_svc=None, data_dir="data") -> FlowResult:
    start, end = window(date, 31)
    return await run_scheduled(SOURCE_NAMES, DOMAINS, start, end, collectors, timescale_svc, typedb_svc, data_dir)
