#!/usr/bin/env python3
"""토스증권 국내·국외 주식 분석 → HTML 대시보드 생성.

사용법:
  1) 환경변수 설정 (또는 .env)
       export TOSSINVEST_CLIENT_ID=...       # tsck_live_...
       export TOSSINVEST_CLIENT_SECRET=...   # tssk_live_...
       # (선택) export TOSSINVEST_ACCOUNT=... TOSSINVEST_API_BASE_URL=...
  2) 실행
       python main.py                                   # 기본 관심종목
       python main.py --domestic A005930,A000660 \
                      --overseas NVDA,AAPL --out out/report.html
       python main.py --demo                            # 네트워크 없이 샘플 미리보기

주의: 자격증명은 코드/저장소에 넣지 말고 환경변수로만 주입하세요.
"""
from __future__ import annotations

import argparse
import os
import sys
import math
import random
from pathlib import Path

from toss import TossClient, TossAPIError, analyze
from toss import symbols as sym
from toss.report import build_html, build_report


def _load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _thin(candles: list[dict], keep: int = 90) -> list[dict]:
    """리포트 용량 절약: 종가·날짜만, 최근 keep 개."""
    return [{"dt": c["dt"], "close": c["close"]} for c in candles[-keep:]]


def fetch_section(client: TossClient, title: str, currency: str,
                  pairs, interval: str, count: int) -> dict:
    codes = [c for c, _ in pairs]
    names = {c: n for c, n in pairs}
    try:
        prices = {p["code"]: p for p in client.get_prices(codes)}
    except TossAPIError as e:
        print(f"  · 시세 조회 경고: {e}", file=sys.stderr)
        if e.body:
            print(f"    응답본문: {e.body[:400]}", file=sys.stderr)
        prices = {}
    items = []
    for code in codes:
        p = prices.get(code) or {"code": code}
        try:
            candles = client.get_candles(code, interval=interval, count=count)
        except TossAPIError as e:
            print(f"  · {code} 캔들 경고: {e}", file=sys.stderr)
            candles = []
        a = analyze(candles)
        # 현재가가 비면 마지막 종가로 보완
        if p.get("last") is None and a.get("last") is not None:
            p["last"] = a["last"]
        items.append({
            "code": code,
            "name": p.get("name") or names.get(code, code),
            "price": {k: p.get(k) for k in
                      ("last", "change", "change_rate", "open", "high", "low", "volume", "currency", "market")},
            "analysis": a,
            "candles": _thin(candles),
        })
        print(f"  · {code:<14} {names.get(code,''):<12} 캔들 {len(candles):>3}개 "
              f"신호 {a.get('signal',{}).get('label','-')}")
    return {"key": title, "title": title, "currency": currency, "items": items}


# --------------------------------------------------------------------------
# DEMO: 네트워크 없이 UI 미리보기 (씨드 고정, 합성 데이터)
# --------------------------------------------------------------------------
def demo_section(title, currency, pairs, base_price, seed):
    rnd = random.Random(seed)
    items = []
    for code, name in pairs:
        drift = rnd.uniform(-0.0012, 0.0022)
        vol = rnd.uniform(0.012, 0.035)
        price = base_price * rnd.uniform(0.4, 2.4)
        closes = []
        for _ in range(130):
            price *= math.exp(drift + rnd.gauss(0, vol))
            closes.append(round(price, 2 if currency == "USD" else 0))
        candles = [{"dt": i, "open": c, "high": c, "low": c, "close": c, "volume": 0}
                   for i, c in enumerate(closes)]
        a = analyze(candles)
        prev = closes[-2]
        last = closes[-1]
        chg = last - prev
        items.append({
            "code": code, "name": name,
            "price": {"last": last, "change": round(chg, 2), "change_rate": round(chg / prev * 100, 2),
                      "open": closes[-2], "high": max(closes[-2:]), "low": min(closes[-2:]),
                      "volume": rnd.randint(1_000_000, 40_000_000),
                      "currency": currency, "market": "KRX" if currency == "KRW" else "NASDAQ"},
            "analysis": a,
            "candles": [{"dt": c["dt"], "close": c["close"]} for c in candles[-90:]],
        })
    return {"key": title, "title": title, "currency": currency, "items": items}


def build_demo():
    return build_report([
        demo_section("국내 (KRX)", "KRW", sym.DOMESTIC, 70000, seed=42),
        demo_section("국외 (US)", "USD", sym.OVERSEAS, 180, seed=7),
    ], mode="demo")


def main():
    ap = argparse.ArgumentParser(description="토스증권 국내·국외 주식 분석 대시보드 생성")
    ap.add_argument("--domestic", help="국내 종목코드 CSV (예: A005930,A000660)")
    ap.add_argument("--overseas", help="국외 티커 CSV (예: NVDA,AAPL)")
    ap.add_argument("--interval", default="day", help="캔들 주기 (day/week/month/min)")
    ap.add_argument("--count", type=int, default=130, help="캔들 개수")
    ap.add_argument("--out", default="out/report.html", help="출력 HTML 경로")
    ap.add_argument("--demo", action="store_true", help="네트워크 없이 샘플 데이터로 생성")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.demo:
        print("샘플(오프라인) 리포트 생성 중…")
        report = build_demo()
    else:
        _load_dotenv()
        cid = os.environ.get("TOSSINVEST_CLIENT_ID")
        csec = os.environ.get("TOSSINVEST_CLIENT_SECRET")
        if not cid or not csec:
            print("오류: TOSSINVEST_CLIENT_ID / TOSSINVEST_CLIENT_SECRET 환경변수가 필요합니다.\n"
                  "      미리보기는 python main.py --demo 로 확인하세요.", file=sys.stderr)
            return 2
        client = TossClient(
            cid, csec,
            base_url=os.environ.get("TOSSINVEST_API_BASE_URL", "https://openapi.tossinvest.com"),
            account=os.environ.get("TOSSINVEST_ACCOUNT"),
        )
        print("토큰 발급 중…")
        try:
            client.authenticate()
        except TossAPIError as e:
            print(f"인증 실패: {e}", file=sys.stderr)
            if e.body:
                print(f"응답본문: {e.body[:400]}", file=sys.stderr)
            return 1
        print("인증 성공.")

        dom = [(c, "") for c in args.domestic.split(",")] if args.domestic else sym.DOMESTIC
        ovs = [(c, "") for c in args.overseas.split(",")] if args.overseas else sym.OVERSEAS
        print("국내(KRX) 조회…")
        s_dom = fetch_section(client, "국내 (KRX)", "KRW", dom, args.interval, args.count)
        print("국외(US) 조회…")
        s_ovs = fetch_section(client, "국외 (US)", "USD", ovs, args.interval, args.count)
        report = build_report([s_dom, s_ovs], mode="live")

    out.write_text(build_html(report), encoding="utf-8")
    print(f"\n완료 → {out.resolve()}")
    print("브라우저에서 파일을 열어 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
