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
from toss import insights
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
        p.setdefault("currency", currency)
        try:
            candles = client.get_candles(code, interval=interval, count=count)
        except TossAPIError as e:
            print(f"  · {code} 캔들 경고: {e}", file=sys.stderr)
            candles = []
        a = analyze(candles)
        if p.get("last") is None and a.get("last") is not None:
            p["last"] = a["last"]
        # 호가·기업정보(선택) — 실패해도 나머지는 진행
        ob = _try(lambda: client.orderbook_summary(code)) or {}
        info = _try(lambda: client.get_stock_info(code)) or {}
        if not p.get("shares") and info.get("shares"):
            p["shares"] = info["shares"]
        items.append({
            "code": code,
            "name": p.get("name") or info.get("name") or names.get(code, code),
            "currency": currency,
            "price": {k: p.get(k) for k in
                      ("last", "change", "change_rate", "open", "high", "low", "volume",
                       "currency", "market", "upper_limit", "lower_limit", "shares")},
            "info": info,
            "orderbook": ob,
            "analysis": a,
            "candles": _thin(candles),
        })
        print(f"  · {code:<14} {names.get(code,''):<12} 캔들 {len(candles):>3}개 "
              f"신호 {a.get('signal',{}).get('label','-')} "
              f"호가 {'○' if ob.get('imbalance') is not None else '·'}")
    return {"key": title, "title": title, "currency": currency, "items": items}


def _try(fn):
    """API 부가 조회 실패를 조용히 삼킴(필드 누락 시 패널만 비어보임)."""
    try:
        return fn()
    except TossAPIError:
        return None


# --------------------------------------------------------------------------
# DEMO: 네트워크 없이 UI 미리보기 (씨드 고정, 합성 데이터)
# --------------------------------------------------------------------------
DEMO_USDKRW = 1385.0


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
        rd = 2 if currency == "USD" else 0
        # 당일 시/고/저를 종가 주변으로 합성
        last = closes[-1]
        op = round(closes[-2] * (1 + rnd.uniform(-0.01, 0.01)), rd)
        high = round(max(last, op) * (1 + rnd.uniform(0, 0.015)), rd)
        low = round(min(last, op) * (1 - rnd.uniform(0, 0.015)), rd)
        prev = closes[-2]
        chg = last - prev
        volume = rnd.randint(1_000_000, 40_000_000) if currency == "KRW" else rnd.randint(2_000_000, 80_000_000)
        shares = rnd.randint(200_000_000, 6_000_000_000)
        candles = [{"dt": i, "open": c, "high": c, "low": c, "close": c, "volume": 0}
                   for i, c in enumerate(closes)]
        a = analyze(candles)
        price = {"last": last, "change": round(chg, rd), "change_rate": round(chg / prev * 100, 2),
                 "open": op, "high": high, "low": low, "volume": volume,
                 "currency": currency, "market": "KRX" if currency == "KRW" else "NASDAQ",
                 "shares": shares}
        if currency == "KRW":  # 국내 상/하한가 ±30%
            price["upper_limit"] = round(prev * 1.30)
            price["lower_limit"] = round(prev * 0.70)
        bid = rnd.randint(50_000, 900_000)
        ask = rnd.randint(50_000, 900_000)
        total = bid + ask
        items.append({
            "code": code, "name": name, "currency": currency,
            "price": price,
            "info": {"name": name, "shares": shares, "market": price["market"], "currency": currency},
            "orderbook": {"bid_qty": bid, "ask_qty": ask, "imbalance": (bid - ask) / total,
                          "spread_pct": round(rnd.uniform(0.02, 0.25), 3)},
            "analysis": a,
            "candles": [{"dt": c["dt"], "close": c["close"]} for c in candles[-90:]],
        })
    return {"key": title, "title": title, "currency": currency, "items": items}


def build_demo():
    secs = [
        demo_section("국내 (KRX)", "KRW", sym.DOMESTIC, 70000, seed=42),
        demo_section("국외 (US)", "USD", sym.OVERSEAS, 180, seed=7),
    ]
    for s in secs:
        insights.enrich_section(s, DEMO_USDKRW)
    return build_report(secs, mode="demo", usdkrw=DEMO_USDKRW)


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
        usdkrw = _try(lambda: client.get_exchange_rate("USD", "KRW"))
        print(f"환율 USD/KRW: {usdkrw if usdkrw else '조회 불가(국외 원화환산 생략)'}")
        print("국내(KRX) 조회…")
        s_dom = fetch_section(client, "국내 (KRX)", "KRW", dom, args.interval, args.count)
        print("국외(US) 조회…")
        s_ovs = fetch_section(client, "국외 (US)", "USD", ovs, args.interval, args.count)
        insights.enrich_section(s_dom, usdkrw)
        insights.enrich_section(s_ovs, usdkrw)
        report = build_report([s_dom, s_ovs], mode="live", usdkrw=usdkrw)

    out.write_text(build_html(report), encoding="utf-8")
    print(f"\n완료 → {out.resolve()}")
    print("브라우저에서 파일을 열어 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
