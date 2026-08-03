"""기술적 분석 지표 (표준 라이브러리만 사용).

입력: 캔들 리스트 [{dt, open, high, low, close, volume}, ...]  (오래된→최근)
출력: 지표 딕셔너리. 데이터가 부족하면 해당 지표는 None.
"""
from __future__ import annotations

from typing import Sequence


def _sma(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _rsi(closes: Sequence[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: Sequence[float]) -> tuple[float | None, float | None]:
    if len(closes) < 26:
        return None, None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd_line = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    signal = _ema_series(macd_line, 9)
    if not macd_line or not signal:
        return None, None
    return macd_line[-1], macd_line[-1] - signal[-1]


def _stdev(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def analyze(candles: list[dict]) -> dict:
    """캔들 리스트로부터 지표 세트를 계산."""
    closes = [c["close"] for c in candles if c["close"] is not None]
    highs = [c["high"] for c in candles if c["high"] is not None]
    lows = [c["low"] for c in candles if c["low"] is not None]
    n = len(closes)
    result: dict = {"points": n}
    if n == 0:
        return result

    last = closes[-1]
    result["last"] = last
    result["sma20"] = _sma(closes, 20)
    result["sma60"] = _sma(closes, 60)
    result["sma120"] = _sma(closes, 120)
    result["rsi14"] = _rsi(closes, 14)
    macd, hist = _macd(closes)
    result["macd"] = macd
    result["macd_hist"] = hist

    # 볼린저 밴드 (20, 2σ)
    if n >= 20:
        window = closes[-20:]
        mid = sum(window) / 20
        sd = _stdev(window)
        result["boll_mid"] = mid
        result["boll_upper"] = mid + 2 * sd
        result["boll_lower"] = mid - 2 * sd
        result["boll_pctb"] = (last - (mid - 2 * sd)) / (4 * sd) if sd else None

    # 기간 수익률
    def ret(days: int):
        if n > days:
            base = closes[-1 - days]
            return (last / base - 1) * 100 if base else None
        return None

    result["ret_1d"] = ret(1)
    result["ret_5d"] = ret(5)
    result["ret_20d"] = ret(20)
    result["ret_60d"] = ret(60)

    # 52주(약 250거래일) 고저 및 위치
    lookback = closes[-250:] if n >= 250 else closes
    hi = max(highs[-250:]) if highs else max(lookback)
    lo = min(lows[-250:]) if lows else min(lookback)
    result["hi_52w"] = hi
    result["lo_52w"] = lo
    result["pos_52w"] = (last - lo) / (hi - lo) * 100 if hi > lo else None

    # 연율화 변동성 (일간 로그수익률 표준편차 × √252)
    if n >= 21:
        rets = [
            (closes[i] / closes[i - 1] - 1)
            for i in range(1, n)
            if closes[i - 1]
        ][-20:]
        result["volatility"] = _stdev(rets) * (252 ** 0.5) * 100 if rets else None

    result["signal"] = _signal(result)
    return result


def _signal(m: dict) -> dict:
    """지표들을 종합해 단순 점수(-100~100)와 라벨 산출. 투자자문 아님."""
    score = 0.0
    reasons: list[str] = []
    last = m.get("last")

    def add(cond, pts, up_msg, down_msg):
        nonlocal score
        if cond is None:
            return
        if cond:
            score += pts
            reasons.append(up_msg)
        else:
            score -= pts
            reasons.append(down_msg)

    if last and m.get("sma20"):
        add(last > m["sma20"], 15, "20일선 위", "20일선 아래")
    if last and m.get("sma60"):
        add(last > m["sma60"], 20, "60일선 위(중기 강세)", "60일선 아래(중기 약세)")
    if m.get("sma20") and m.get("sma60"):
        add(m["sma20"] > m["sma60"], 15, "정배열(20>60)", "역배열(20<60)")
    rsi = m.get("rsi14")
    if rsi is not None:
        if rsi >= 70:
            score -= 10
            reasons.append(f"RSI 과매수 {rsi:.0f}")
        elif rsi <= 30:
            score += 10
            reasons.append(f"RSI 과매도 {rsi:.0f}")
    if m.get("macd_hist") is not None:
        add(m["macd_hist"] > 0, 15, "MACD 상방", "MACD 하방")
    if m.get("ret_20d") is not None:
        add(m["ret_20d"] > 0, 10, "20일 모멘텀 +", "20일 모멘텀 −")

    score = max(-100, min(100, score))
    if score >= 40:
        label = "강세"
    elif score >= 15:
        label = "약강세"
    elif score > -15:
        label = "중립"
    elif score > -40:
        label = "약약세"
    else:
        label = "약세"
    return {"score": round(score), "label": label, "reasons": reasons}
