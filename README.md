# 토스증권 국내·국외 주식 분석 대시보드

토스증권 **Open API**(`https://openapi.tossinvest.com`)에 연결해 **국내(KRX)** 와
**국외(US)** 종목의 시세·캔들 데이터를 받아, 이동평균·RSI·MACD·모멘텀·변동성 등을
계산하고 결과를 **자체 완결형 인터랙티브 HTML 대시보드**로 생성합니다.

> ⚠️ **투자 참고용입니다. 투자자문이 아닙니다.** 모든 지표는 자동 계산 결과이며
> 투자 판단과 손익 책임은 이용자 본인에게 있습니다.

## 미리보기 (네트워크 불필요)

```bash
python main.py --demo
# → out/report.html 생성 후 브라우저로 열기
```

`examples/report_sample.html` 을 브라우저로 바로 열어도 UI를 확인할 수 있습니다
(샘플 데이터).

## 실데이터로 실행

### 1. 자격증명 발급
토스증권 PC 웹(WTS) → **설정 → Open API** 에서 `Client Id`(`tsck_live_…`)와
`Client Secret`(`tssk_live_…`)을 발급합니다. IP 등록이 필요할 수 있습니다.

### 2. 환경변수 설정
`.env.example` 를 `.env` 로 복사해 값을 채웁니다. (`.env` 는 `.gitignore` 로 제외됨)

```bash
cp .env.example .env
# .env 편집:
#   TOSSINVEST_CLIENT_ID=tsck_live_...
#   TOSSINVEST_CLIENT_SECRET=tssk_live_...
```

또는 셸에서 직접:
```bash
export TOSSINVEST_CLIENT_ID=tsck_live_...
export TOSSINVEST_CLIENT_SECRET=tssk_live_...
```

### 3. 실행
```bash
# 기본 관심종목(삼성전자·SK하이닉스… / NVDA·AAPL…)
python main.py

# 종목 지정
python main.py --domestic A005930,A000660,A035420 \
               --overseas NVDA,AAPL,TSLA \
               --out out/report.html

# 캔들 주기/개수
python main.py --interval day --count 130
```

생성된 `out/report.html` 을 브라우저에서 열면 국내/국외 탭, 종목 카드(현재가·
스파크라인·지표), 52주 위치, 신호 점수, 비교 표를 볼 수 있습니다.

> **의존성 없음** — 파이썬 3.9+ 표준 라이브러리만 사용합니다 (`pip install` 불필요).

## 종목코드 형식

| 시장 | 형식 | 예시 |
|------|------|------|
| 국내 KRX | `A` + 6자리 | 삼성전자 `A005930`, SK하이닉스 `A000660` |
| 국외 US | 티커 또는 `US…` | `NVDA`, `AAPL` |

기본 관심종목은 `toss/symbols.py` 에서 수정합니다.

## 계산 지표

- **추세**: SMA(20/60/120), 정·역배열
- **모멘텀**: RSI(14), MACD 히스토그램, 1/5/20/60일 수익률
- **밴드/위치**: 볼린저(20, 2σ), 52주 고저 및 현재 위치(%)
- **위험**: 최근 20일 로그수익률 기반 연율 변동성
- **종합 신호**: 위 지표를 가중합해 −100~+100 점수와 라벨(강세/중립/약세) 산출

## 구조

```
main.py                CLI: 조회 → 분석 → HTML 생성 (--demo 지원)
toss/
  client.py            Open API 클라이언트(OAuth2 토큰 캐싱, prices/candles/orderbook)
  analysis.py          기술적 지표 계산(SMA·EMA·RSI·MACD·볼린저·변동성·신호)
  symbols.py           기본 관심종목(국내/국외)
  report.py            자체 완결형 HTML 대시보드 렌더러(canvas 차트, 라이트/다크)
examples/report_sample.html   샘플(오프라인) 리포트
```

## API 엔드포인트 (참고)

| 용도 | 메서드 · 경로 |
|------|---------------|
| 토큰 발급 | `POST /oauth2/token` (HTTP Basic, `grant_type=client_credentials`) |
| 현재가 | `GET /api/v1/prices` |
| 캔들 | `GET /api/v1/candles` |
| 호가 | `GET /api/v1/orderbook` |

- 토큰 발급 방식은 공식 문서로 확인된 값입니다.
- 데이터 엔드포인트의 **쿼리 파라미터명·응답 필드명**은 API 버전에 따라 다를 수
  있어, `client.py` 는 여러 후보 필드명을 관용적으로 파싱합니다. 필드가 맞지 않으면
  4xx 응답 본문이 그대로 출력되니 이를 보고 `toss/client.py` 상단의 `ENDPOINTS` /
  `_PRICE_FIELDS` / `_CANDLE_FIELDS` 를 조정하세요.
- 최신 정확한 스펙: 토스증권 개발자센터 <https://developers.tossinvest.com/docs>

## 보안

- `Client Secret` 은 **환경변수/`.env` 로만** 주입하세요. 코드·저장소·공개 파일에
  절대 커밋하지 마세요(`.gitignore` 로 `.env` 제외됨).
- 생성되는 HTML(`out/`, `examples/`)에는 시세·지표만 담기며 자격증명은 포함되지
  않습니다.

## 실행 환경 관련 참고

- claude.ai에 게시되는 **아티팩트 페이지는 브라우저 CSP 때문에 외부 API를 직접
  호출할 수 없습니다.** 따라서 실데이터 연결은 이 저장소의 파이썬 도구를 본인 PC에서
  실행하는 방식으로 동작합니다. 게시된 아티팩트는 UI 미리보기(샘플 데이터)입니다.
