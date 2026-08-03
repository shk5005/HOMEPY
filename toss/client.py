"""토스증권 Open API 클라이언트.

공식 문서: https://developers.tossinvest.com/docs
- 인증: OAuth2 Client Credentials  (POST /oauth2/token, HTTP Basic)
- 데이터: GET /api/v1/prices, /api/v1/candles, /api/v1/orderbook 등

주의(정확도 표기):
  · 토큰 발급 경로/방식은 공식 문서로 확인된 값입니다(신뢰도 높음).
  · 데이터 엔드포인트 경로는 공개 자료 기준의 최선값이며, 쿼리 파라미터명과
    응답 필드명은 계정마다/버전마다 다를 수 있습니다. 이 모듈은 응답을
    "관용적으로" 파싱하므로 필드명이 조금 달라도 최대한 동작합니다.
    실제 값은 개발자센터 콘솔의 응답으로 최종 확인하세요.
    엔드포인트/파라미터는 아래 ENDPOINTS 한 곳에서만 고치면 됩니다.
"""
from __future__ import annotations

import base64
import time
import urllib.parse
import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from typing import Any


DEFAULT_BASE_URL = "https://openapi.tossinvest.com"

# ---------------------------------------------------------------------------
# 엔드포인트 정의 — 스펙이 바뀌면 여기만 수정하세요.
# ---------------------------------------------------------------------------
ENDPOINTS = {
    "token": "/oauth2/token",
    "prices": "/api/v1/prices",
    "candles": "/api/v1/candles",
    "orderbook": "/api/v1/orderbook",
    "stock_info": "/api/v1/stock-info",
    "exchange_rates": "/api/v1/exchange-rates",
}

# 여러 응답 스키마에 대응하기 위한 후보 필드명들(관용적 파싱).
_PRICE_FIELDS = {
    "last": ["close", "price", "last", "tradePrice", "currentPrice"],
    "prev_close": ["prevClose", "base", "previousClose", "prdyClose"],
    "change": ["change", "changePrice", "diff"],
    "change_rate": ["changeRate", "changeRatio", "fluctuationRate", "rate"],
    "volume": ["volume", "accVolume", "tradeVolume", "acmlVol"],
    "high": ["high", "highPrice", "dayHigh"],
    "low": ["low", "lowPrice", "dayLow"],
    "open": ["open", "openPrice"],
    "name": ["name", "stockName", "companyName", "hname"],
    "currency": ["currency", "curr", "currencyCode"],
    "market": ["market", "exchange", "marketCode"],
    "upper_limit": ["upperLimit", "upper", "maxPrice", "highLimit"],
    "lower_limit": ["lowerLimit", "lower", "minPrice", "lowLimit"],
    "shares": ["shares", "listedShares", "sharesOutstanding", "issuedShares", "listShrs"],
}
_INFO_FIELDS = {
    "name": ["name", "stockName", "companyName", "hname"],
    "market": ["market", "exchange", "marketCode"],
    "currency": ["currency", "curr", "currencyCode"],
    "shares": ["shares", "listedShares", "sharesOutstanding", "issuedShares", "listShrs"],
    "listed": ["listingStatus", "listed", "status"],
}
_CANDLE_FIELDS = {
    "dt": ["dt", "date", "time", "timestamp", "baseDt"],
    "open": ["open", "openPrice", "o"],
    "high": ["high", "highPrice", "h"],
    "low": ["low", "lowPrice", "l"],
    "close": ["close", "closePrice", "c", "price"],
    "volume": ["volume", "acc", "v", "tradeVolume"],
}


class TossAPIError(RuntimeError):
    """API 호출 실패. status_code 와 body(가능 시)를 담습니다."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _pick(d: dict, keys: list[str], default=None):
    """후보 키 목록에서 처음으로 존재하는 값을 반환."""
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _to_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


@dataclass
class TossClient:
    """토스증권 Open API 클라이언트 (표준 라이브러리만 사용).

    사용 예:
        client = TossClient(client_id, client_secret)
        client.authenticate()
        rows = client.get_prices(["A005930", "NVDA"])
    """

    client_id: str
    client_secret: str
    base_url: str = DEFAULT_BASE_URL
    account: str | None = None
    timeout: int = 15

    _token: str | None = field(default=None, init=False, repr=False)
    _token_exp: float = field(default=0.0, init=False, repr=False)

    # -- 인증 ---------------------------------------------------------------
    def authenticate(self) -> str:
        """Client Credentials 로 access_token 발급(캐싱)."""
        if self._token and time.time() < self._token_exp - 30:
            return self._token

        url = self.base_url.rstrip("/") + ENDPOINTS["token"]
        body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise TossAPIError(
                f"토큰 발급 실패 (HTTP {e.code}). client_id/secret 및 IP 등록을 확인하세요.",
                status_code=e.code,
                body=_safe_read(e),
            ) from e
        except urllib.error.URLError as e:
            raise TossAPIError(f"토큰 서버 연결 실패: {e.reason}") from e

        token = payload.get("access_token")
        if not token:
            raise TossAPIError(f"응답에 access_token 이 없습니다: {payload}")
        self._token = token
        self._token_exp = time.time() + float(payload.get("expires_in", 3600))
        return token

    # -- 저수준 GET ---------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any] | None = None, _retry: bool = True) -> Any:
        token = self.authenticate()
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        url = self.base_url.rstrip("/") + path + query
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if self.account:
            headers["X-Tossinvest-Account"] = self.account
        req = urllib.request.Request(url, method="GET", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401 and _retry:
                self._token = None  # 토큰 만료 → 1회 재발급 후 재시도
                return self._get(path, params, _retry=False)
            raise TossAPIError(
                f"요청 실패 {path} (HTTP {e.code})",
                status_code=e.code,
                body=_safe_read(e),
            ) from e
        except urllib.error.URLError as e:
            raise TossAPIError(f"연결 실패 {path}: {e.reason}") from e

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        """{"result": ...} / {"data": ...} 래핑을 벗겨냅니다."""
        if isinstance(payload, dict):
            for key in ("result", "data", "results", "items", "prices", "candles"):
                if key in payload:
                    return payload[key]
        return payload

    # -- 고수준 조회 --------------------------------------------------------
    def get_prices(self, codes: list[str]) -> list[dict]:
        """현재가/등락 조회. 국내(A005930)·미국(NVDA/US...) 코드 혼용 가능."""
        raw = self._unwrap(self._get(ENDPOINTS["prices"], {"codes": ",".join(codes)}))
        rows = raw if isinstance(raw, list) else [raw]
        out = []
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            out.append(_normalize_price(r, fallback_code=codes[i] if i < len(codes) else None))
        return out

    def get_candles(self, code: str, interval: str = "day", count: int = 120) -> list[dict]:
        """일/주/월/분봉 캔들. 오래된→최근 순으로 정렬해 반환."""
        raw = self._unwrap(
            self._get(ENDPOINTS["candles"], {"code": code, "interval": interval, "count": count})
        )
        rows = raw if isinstance(raw, list) else raw.get("candles", []) if isinstance(raw, dict) else []
        candles = [_normalize_candle(r) for r in rows if isinstance(r, dict)]
        candles = [c for c in candles if c["close"] is not None]
        candles.sort(key=lambda c: str(c["dt"]))
        return candles

    def get_orderbook(self, code: str) -> dict:
        return self._unwrap(self._get(ENDPOINTS["orderbook"], {"code": code}))

    def orderbook_summary(self, code: str) -> dict:
        """호가에서 매수/매도 총잔량·불균형·스프레드를 계산.

        불균형 = (매수잔량 − 매도잔량) / (매수잔량 + 매도잔량)  (−1~+1, +면 매수 우위)
        """
        raw = self.get_orderbook(code)
        bids = _collect_qty(raw, ["bids", "bid", "buy", "buyOrders"], ["bidQty", "buyQty", "qty", "quantity", "restQty"])
        asks = _collect_qty(raw, ["asks", "ask", "sell", "sellOrders"], ["askQty", "sellQty", "qty", "quantity", "restQty"])
        best_bid = _pick(raw, ["bestBid", "bidPrice", "bidPrice1"])
        best_ask = _pick(raw, ["bestAsk", "askPrice", "askPrice1"])
        spread_pct = None
        bb, ba = _to_float(best_bid), _to_float(best_ask)
        if bb and ba and ba > 0:
            spread_pct = (ba - bb) / ba * 100
        total = bids + asks
        return {
            "bid_qty": bids or None,
            "ask_qty": asks or None,
            "imbalance": ((bids - asks) / total) if total else None,
            "spread_pct": spread_pct,
        }

    def get_stock_info(self, code: str) -> dict:
        raw = self._unwrap(self._get(ENDPOINTS["stock_info"], {"code": code}))
        r = raw[0] if isinstance(raw, list) and raw else raw
        if not isinstance(r, dict):
            return {}
        return {
            "name": _pick(r, _INFO_FIELDS["name"]),
            "market": _pick(r, _INFO_FIELDS["market"]),
            "currency": _pick(r, _INFO_FIELDS["currency"]),
            "shares": _to_float(_pick(r, _INFO_FIELDS["shares"])),
            "listed": _pick(r, _INFO_FIELDS["listed"]),
        }

    def get_exchange_rate(self, base: str = "USD", quote: str = "KRW") -> float | None:
        """환율 조회(선택). 엔드포인트가 없으면 None 을 반환합니다."""
        try:
            raw = self._unwrap(self._get(ENDPOINTS.get("exchange_rates", "/api/v1/exchange-rates"),
                                         {"base": base, "quote": quote}))
        except TossAPIError:
            return None
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, dict) and quote in str(r.values()):
                    return _to_float(_pick(r, ["rate", "value", "price", "close"]))
            raw = raw[0] if raw else {}
        if isinstance(raw, dict):
            return _to_float(_pick(raw, ["rate", "value", "price", "close", f"{base}{quote}"]))
        return None


def _normalize_price(r: dict, fallback_code: str | None = None) -> dict:
    last = _to_float(_pick(r, _PRICE_FIELDS["last"]))
    prev = _to_float(_pick(r, _PRICE_FIELDS["prev_close"]))
    change = _to_float(_pick(r, _PRICE_FIELDS["change"]))
    rate = _to_float(_pick(r, _PRICE_FIELDS["change_rate"]))
    if change is None and last is not None and prev is not None:
        change = last - prev
    if rate is None and change is not None and prev:
        rate = change / prev * 100.0
    return {
        "code": _pick(r, ["code", "stockCode", "symbol", "isuCd"], fallback_code),
        "name": _pick(r, _PRICE_FIELDS["name"]),
        "last": last,
        "prev_close": prev,
        "change": change,
        "change_rate": rate,
        "open": _to_float(_pick(r, _PRICE_FIELDS["open"])),
        "high": _to_float(_pick(r, _PRICE_FIELDS["high"])),
        "low": _to_float(_pick(r, _PRICE_FIELDS["low"])),
        "volume": _to_float(_pick(r, _PRICE_FIELDS["volume"])),
        "currency": _pick(r, _PRICE_FIELDS["currency"]),
        "market": _pick(r, _PRICE_FIELDS["market"]),
        "upper_limit": _to_float(_pick(r, _PRICE_FIELDS["upper_limit"])),
        "lower_limit": _to_float(_pick(r, _PRICE_FIELDS["lower_limit"])),
        "shares": _to_float(_pick(r, _PRICE_FIELDS["shares"])),
        "_raw": r,
    }


def _normalize_candle(r: dict) -> dict:
    return {
        "dt": _pick(r, _CANDLE_FIELDS["dt"]),
        "open": _to_float(_pick(r, _CANDLE_FIELDS["open"])),
        "high": _to_float(_pick(r, _CANDLE_FIELDS["high"])),
        "low": _to_float(_pick(r, _CANDLE_FIELDS["low"])),
        "close": _to_float(_pick(r, _CANDLE_FIELDS["close"])),
        "volume": _to_float(_pick(r, _CANDLE_FIELDS["volume"])),
    }


def _collect_qty(raw: dict, list_keys: list[str], qty_keys: list[str]) -> float:
    """호가 응답에서 매수(또는 매도) 잔량 합계를 관용적으로 추출."""
    if not isinstance(raw, dict):
        return 0.0
    total = 0.0
    for lk in list_keys:
        levels = raw.get(lk)
        if isinstance(levels, list):
            for lv in levels:
                q = _to_float(_pick(lv, qty_keys)) if isinstance(lv, dict) else _to_float(lv)
                if q:
                    total += q
    return total


def _safe_read(e: urllib.error.HTTPError) -> str | None:
    try:
        return e.read().decode()[:2000]
    except Exception:  # noqa: BLE001
        return None
