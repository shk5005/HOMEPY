"""토스 Open API 원자료(현재가·호가·기업정보·환율)로부터 교차 분석용
인사이트 지표를 파생합니다.

각 지표 옆에 어떤 API 데이터에서 나오는지 주석으로 표기했습니다.
"""
from __future__ import annotations


def derive(item: dict, fx_usdkrw: float | None) -> dict:
    """item 에 derived 필드를 추가해 반환. item 은 다음을 포함할 수 있음:
    price(현재가), info(기업정보), orderbook(호가요약), analysis(기술적).
    """
    p = item.get("price", {}) or {}
    info = item.get("info", {}) or {}
    ob = item.get("orderbook", {}) or {}
    a = item.get("analysis", {}) or {}
    cur = p.get("currency") or item.get("currency")

    last = p.get("last")
    high, low, op = p.get("high"), p.get("low"), p.get("open")
    vol = p.get("volume")
    shares = p.get("shares") or info.get("shares")

    d: dict = {}

    # 거래대금 = 현재가 × 거래량   (prices)
    turnover = last * vol if (last is not None and vol is not None) else None
    d["turnover"] = turnover
    d["turnover_krw"] = _to_krw(turnover, cur, fx_usdkrw)

    # 시가총액 = 현재가 × 발행주식수  (prices × stock-info)
    mktcap = last * shares if (last is not None and shares) else None
    d["market_cap"] = mktcap
    d["market_cap_krw"] = _to_krw(mktcap, cur, fx_usdkrw)

    # 일중 위치 = (현재가−저가)/(고가−저가)  (prices)
    if last is not None and high is not None and low is not None and high > low:
        d["intraday_pos"] = (last - low) / (high - low) * 100
    else:
        d["intraday_pos"] = None
    # 시가 대비  (prices)
    d["vs_open"] = ((last / op - 1) * 100) if (last and op) else None

    # 상한/하한 근접도  (prices, 국내)
    up, lo = p.get("upper_limit"), p.get("lower_limit")
    d["dist_upper"] = ((up / last - 1) * 100) if (up and last) else None
    d["dist_lower"] = ((last / lo - 1) * 100) if (lo and last) else None

    # 호가 불균형·스프레드  (orderbook)
    d["imbalance"] = ob.get("imbalance")
    d["spread_pct"] = ob.get("spread_pct")

    # 환효과: 국외 종목의 원화 환산 수익률과 달러 수익률 차이  (prices × 환율)
    # 20일 수익률 기준. 환율 시계열이 없으면 당일 환율로 근사 → 환효과=0 근사.
    d["ret_20d"] = a.get("ret_20d")
    if cur and cur != "KRW":
        d["krw_return_20d"] = a.get("ret_20d")  # 환율 시계열 없으면 동일(근사)
        d["fx_effect_20d"] = 0.0 if a.get("ret_20d") is not None else None
    else:
        d["krw_return_20d"] = a.get("ret_20d")
        d["fx_effect_20d"] = None

    return d


def _to_krw(v, cur, fx_usdkrw):
    if v is None:
        return None
    if cur in (None, "KRW"):
        return v
    if cur == "USD" and fx_usdkrw:
        return v * fx_usdkrw
    return None


def enrich_section(section: dict, fx_usdkrw: float | None) -> dict:
    """섹션 내 모든 종목에 derived 를 채우고, 섹션 요약(랭킹 원천)을 계산."""
    for it in section.get("items", []):
        it["derived"] = derive(it, fx_usdkrw)
    section["fx_usdkrw"] = fx_usdkrw
    return section
