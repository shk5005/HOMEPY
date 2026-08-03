# 토스증권 국내·국외 주식 분석 대시보드

토스증권 **Open API**(`https://openapi.tossinvest.com`)에 연결해 **국내(KRX)** 와
**국외(US)** 종목의 시세·캔들 데이터를 받아, 이동평균·RSI·MACD·모멘텀·변동성 등을
계산하고 결과를 **자체 완결형 인터랙티브 HTML 대시보드**로 생성합니다.

> ⚠️ **투자 참고용입니다. 투자자문이 아닙니다.** 모든 지표는 자동 계산 결과이며
> 투자 판단과 손익 책임은 이용자 본인에게 있습니다.

## 가장 빠른 실행 (원클릭 스크립트)

클론 후 자격증명만 넣으면 삼성전자 리포트까지 자동으로 생성·열기 합니다.

```bash
# macOS / Linux
./run.sh                 # 실행하면 Client Id/Secret 을 물어보고 → out/samsung.html 생성·열기
./run.sh --demo          # 네트워크 없이 샘플 미리보기

# Windows: run.bat 더블클릭 (또는 명령창에서 run.bat)
```

`run.sh`/`run.bat` 는 Python 확인 → (필요 시) 자격증명 입력 → `main.py` 실행 →
브라우저로 리포트 열기까지 한 번에 처리합니다. 세부 제어가 필요하면 아래 수동 방법을 쓰세요.

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

## 인사이트 (대시보드 패널)

토스 API 원자료를 교차 분석해 개별 종목 너머의 흐름을 봅니다.

| 패널 | 의미 | 출처 API |
|------|------|----------|
| **위험 대비 모멘텀** | 20일 수익률 × 연율 변동성 스캐터(점 크기=거래대금, 색=신호) | 캔들 |
| **매수·매도 압력** | 호가 잔량 불균형 (+매수 우위 / −매도 우위) | 호가 |
| **거래대금 상위** | 현재가 × 거래량 (국외는 원화 환산) | 현재가·환율 |
| **시가총액** | 현재가 × 발행주식수 (국외는 원화 환산) | 현재가·기업정보·환율 |
| **52주·일중 위치** | 52주 범위 내 위치(%), 오늘 저가~고가 중 위치 | 현재가 |
| **종목 상세** | 헤더 클릭 정렬 가능한 원자료 표 | 전체 |

## 계산 지표

- **추세**: SMA(20/60/120), 정·역배열
- **모멘텀**: RSI(14), MACD 히스토그램, 1/5/20/60일 수익률
- **밴드/위치**: 볼린저(20, 2σ), 52주 고저 및 현재 위치(%)
- **위험**: 최근 20일 로그수익률 기반 연율 변동성
- **종합 신호**: 위 지표를 가중합해 −100~+100 점수와 라벨(강세/중립/약세) 산출

> 호가·발행주식수·환율은 API 응답에 포함될 때만 채워지며, 누락 시 해당 패널은
> "데이터 없음"으로 표시됩니다(현재가·캔들만으로도 대부분 지표는 계산됩니다).

## 구조

```
main.py                CLI: 조회 → 분석 → HTML 생성 (--demo 지원)
toss/
  client.py            Open API 클라이언트(OAuth2, prices/candles/orderbook/stock-info/환율)
  analysis.py          기술적 지표 계산(SMA·EMA·RSI·MACD·볼린저·변동성·신호)
  insights.py          교차 인사이트 파생(거래대금·시총·호가불균형·원화환산 등)
  symbols.py           기본 관심종목(국내/국외)
  report.py            인사이트 대시보드 렌더러(canvas 스캐터·랭킹·정렬표, 라이트/다크)
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
