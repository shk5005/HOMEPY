"""CSV/JSON 출력 (spec FR-5)."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from homepy import __version__
from homepy.baseline import GroupMonth
from homepy.collect import Snapshot
from homepy.config import Settings
from homepy.flags import Flag, FlaggedTrade

TRADE_COLUMNS = ("trade_id", "group_key", "key_fallback", "apt_name", "umd_name", "area_m2", "area_band",
                 "deal_date", "price_manwon", "floor", "dealing_type", "cancelled", "seller_type", "buyer_type",
                 "flags", "reasons", "comparison_count", "comparison_median_manwon", "deviation")
GROUP_COLUMNS = ("group_key", "apt_name", "umd_name", "area_band", "key_fallback", "month",
                 "baseline_median_manwon", "normal_count", "total_count",
                 "F1", "F2", "F3", "F4", "F5", "F6", "unsettled")


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows([_cell(v) for v in row] for row in rows)


def write_trades_csv(path: Path, rows: Sequence[FlaggedTrade]) -> None:
    _write_csv(path, TRADE_COLUMNS, [
        (f.trade.trade_id, f.trade.group_key, f.trade.key_fallback, f.trade.apt_name, f.trade.umd_name,
         f.trade.area_m2, f.trade.area_band, f.trade.deal_date, f.trade.price_manwon, f.trade.floor,
         f.trade.dealing_type, f.trade.cancelled, f.trade.seller_type, f.trade.buyer_type,
         ";".join(flag.value for flag in f.flags), ";".join(f.reasons),
         f.comparison_count, f.comparison_median_manwon, f.deviation)
        for f in rows
    ])


def write_groups_csv(path: Path, rows: Sequence[GroupMonth]) -> None:
    out = []
    for g in rows:
        counts = dict(g.flag_counts)
        out.append((g.group_key, g.apt_name, g.umd_name, g.area_band, g.key_fallback, g.month,
                    g.baseline_median_manwon, g.normal_count, g.total_count,
                    *(counts[flag] for flag in Flag), g.unsettled))
    _write_csv(path, GROUP_COLUMNS, out)


def write_run_json(path: Path, settings: Settings, snapshots: Sequence[Snapshot],
                   as_of: date, run_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "homepy_version": __version__,
        "run_at": run_at.isoformat(),
        "as_of": as_of.isoformat(),
        "settings": settings.as_dict(),
        "snapshots": [
            {"lawd_cd": s.lawd_cd, "month": s.month, "fetched_on": s.fetched_on.isoformat()}
            for s in snapshots
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
