"""명령행: python -m homepy run ..."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

from homepy.baseline import compute_baselines
from homepy.collect import IncompleteCollection, ensure_months, requests_getter
from homepy.config import load_settings
from homepy.dates import month_end, month_range, months_before
from homepy.flags import assign_flags
from homepy.parse import ApiError, parse_page
from homepy.report import write_groups_csv, write_run_json, write_trades_csv
from homepy.trades import normalize

KEY_ENV = "DATA_GO_KR_SERVICE_KEY"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="homepy", description="아파트 실거래가 이상거래 탐지")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="수집 → 플래그 → 기준 시세 → CSV")
    run.add_argument("--lawd", required=True, help="시군구 코드 5자리 (예: 11680)")
    run.add_argument("--from", dest="start", required=True, help="시작 계약월 YYYY-MM")
    run.add_argument("--to", dest="end", required=True, help="끝 계약월 YYYY-MM")
    run.add_argument("--config", default="config/anomaly.toml")
    run.add_argument("--raw", default="data/raw", help="원본 스냅샷 폴더")
    run.add_argument("--out", default=None, help="출력 폴더 (기본: out/<lawd>)")
    run.add_argument("--offline", action="store_true", help="수집하지 않고 저장된 스냅샷만 사용")
    return p


def _run(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config))
    key = None if args.offline else os.environ.get(KEY_ENV)
    if not args.offline and not key:
        print(f"환경변수 {KEY_ENV}에 data.go.kr 서비스 키(Decoding 키)를 설정하거나 --offline을 쓰세요.",
              file=sys.stderr)
        return 2

    # 첫 달 거래도 비교 창이 차도록 window_months만큼 앞에서부터 받는다
    first = months_before(month_end(args.start), settings.window_months)
    fetch_months = month_range(f"{first.year:04d}-{first.month:02d}", args.end)
    try:
        snaps = ensure_months(Path(args.raw), args.lawd, fetch_months, key, requests_getter,
                              settings, date.today())
        items = [item for s in snaps for body in s.pages
                 for item in parse_page(body, settings.success_codes).items]
    except (ApiError, IncompleteCollection, RuntimeError, OSError) as e:
        print(f"수집 실패: {e}", file=sys.stderr)
        return 1

    as_of = max(s.fetched_on for s in snaps)
    flagged = assign_flags(normalize(items, settings), settings, as_of)
    out_months = month_range(args.start, args.end)
    lo, hi = date.fromisoformat(f"{args.start}-01"), month_end(args.end)
    in_range = [f for f in flagged if lo <= f.trade.deal_date <= hi]

    out = Path(args.out or f"out/{args.lawd}")
    write_trades_csv(out / "trades.csv", in_range)
    write_groups_csv(out / "groups.csv", compute_baselines(flagged, settings, out_months, as_of))
    write_run_json(out / "run.json", settings, snaps, as_of, datetime.now().replace(microsecond=0))
    print(f"{len(in_range)}건 → {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        return _run(args)
    return 2
