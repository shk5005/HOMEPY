# 시세 자동 조회 — 설정과 문제 해결

## 왜 프록시가 필요한가

지니는 정적 페이지입니다. 토스 WTS 엔드포인트는 교차 출처 요청에
`Access-Control-Allow-Origin` 헤더를 내려주지 않으므로, 브라우저에서 직접
호출하면 **CORS 정책에 의해 차단**됩니다.

```
브라우저 ──✖ CORS 차단 ──> wts-info-api.tossinvest.com
브라우저 ──> 127.0.0.1:8787 (로컬 프록시) ──> wts-info-api.tossinvest.com
                            └ CORS 헤더 부착해서 응답
```

프록시는 의존성이 없는 Node 스크립트 한 개이며 `127.0.0.1` 에만 바인딩합니다.

## API 키 설정 (토스증권 오픈 API)

```bash
cp .env.example .env      # 그리고 키를 채운다
node server/quote-proxy.mjs
```

```
GENIE_TOSS_API_KEY=발급받은_키
```

키가 설정되면 프록시가 **오픈 API**(`toss-open`)를 쓰고,
없으면 비공식 WTS(`toss`)로 자동 폴백합니다. 기동 로그에 어느 쪽인지 표시됩니다.

**키는 저장소에 넣지 마세요.** `.env` 는 `.gitignore` 에 있고, 키는
프록시 프로세스 안에서만 존재합니다 — 브라우저로 내려가지 않으며,
로그·진단 출력에는 `tsck_live***abcd (32자)` 형태로 마스킹되어 나옵니다.

### 엔드포인트·인증 방식이 다르다면

공식 문서를 확인하지 못한 채 기본값을 넣어두었습니다. 코드를 고칠 필요 없이
`.env` 값만 바꾸면 됩니다.

| 변수 | 기본값 | 언제 바꾸나 |
|------|--------|-------------|
| `TOSS_API_BASE` | `https://openapi.tossinvest.com` | base URL 이 다를 때 |
| `TOSS_AUTH_STYLE` | `bearer` | 401/403 → `header`·`query`·`basic` 시도 |
| `TOSS_AUTH_HEADER` | `X-API-Key` | `AUTH_STYLE=header` 일 때 헤더 이름 |
| `TOSS_QUOTE_PATH` | `/v1/stocks/prices` | 404 일 때 |
| `TOSS_SEARCH_PATH` | `/v1/stocks/search` | 404 일 때 |
| `TOSS_CODE_PARAM` | `codes` | 종목코드 파라미터 이름이 다를 때 |

`--probe` 가 실제로 보내는 URL·인증방식·헤더를 먼저 출력하므로,
문서와 대조해 어긋난 값만 고치면 됩니다.

## 실행

```bash
node server/quote-proxy.mjs                  # 기본 8787 포트
node server/quote-proxy.mjs --port 9000      # 포트 변경
```

포트를 바꿨다면 브라우저 콘솔에서 한 번 지정하세요.

```js
localStorage.setItem('genie.proxy.url', 'http://127.0.0.1:9000')
```

## 엔드포인트

| 경로 | 설명 |
|------|------|
| `GET /api/health` | 프록시·프로바이더 상태 |
| `GET /api/search?q=삼성전자` | 종목 검색 → `[{ code, name }]` |
| `GET /api/quote?codes=005930,000660` | 시세 조회 (최대 20종목) |

## 문제 해결

### 🟡 프록시 미실행
`node server/quote-proxy.mjs` 가 떠 있는지, 포트가 맞는지 확인하세요.
앱은 이 상태에서도 **수동 입력으로 정상 동작**합니다.

### 🔴 연결 실패 / 502
프록시는 떴지만 토스 호출이 실패한 경우입니다. 상태 코드별로 할 일이 다르며,
프록시가 원인별 힌트를 그대로 전달합니다.

| 코드 | 원인 | 조치 |
|------|------|------|
| 401 / 403 | 키 또는 인증 방식 | 키 유효성 확인, `TOSS_AUTH_STYLE` 변경 |
| 404 | 엔드포인트 경로 | `TOSS_QUOTE_PATH` / `TOSS_SEARCH_PATH` 확인 |
| 429 | 호출 한도 초과 | 잠시 후 재시도 |
| 그 외 | 네트워크·차단 | 방화벽·VPN·사내망 확인 |

원본 응답을 확인하세요.

```bash
node server/quote-proxy.mjs --probe 005930
node server/quote-proxy.mjs --probe-search 삼성전자
```

- **403 / 차단 페이지** — 회사망·방화벽·VPN이 막고 있거나 토스가 차단한 경우
- **JSON이 아님** — 엔드포인트가 이동했거나 점검 중

### 시세는 받아왔는데 값이 `null`
응답 형태가 바뀐 것입니다. `--probe` 출력의 **원본 응답** 키 이름을 보고
`server/providers/toss.mjs` 의 `FIELD_MAP` 에 후보 키를 추가하세요.

```js
export const FIELD_MAP = {
  price: ['close', 'currentPrice', 'price', /* ← 새 키를 여기에 */],
  ...
};
```

어댑터는 후보 키를 순서대로 시도하고, 모두 실패하면 키 이름 패턴으로
깊이 탐색까지 시도합니다. 전일종가만 찾으면 등락폭·등락률은 자동 유도됩니다.

## 목 서버로 검증하기

실제 토스에 붙지 않고 파싱 로직만 확인하려면 업스트림을 바꿔 끼울 수 있습니다.

```bash
TOSS_BASE=http://127.0.0.1:9911 node server/quote-proxy.mjs
```

## 다른 프로바이더 추가

`server/providers/` 에 같은 인터페이스로 모듈을 추가하고
`quote-proxy.mjs` 의 `PROVIDERS` 에 등록하면 됩니다.

```js
export const id = 'myprovider';
export const label = '표시 이름';
export const HOST = 'api.example.com';
export async function search(query) { /* → [{ code, name }] */ }
export async function quote(codes)  { /* → [{ code, name, price, change, ... }] */ }
export async function raw(kind, arg) { /* probe용 원본 JSON */ }
```

공식 API를 쓰고 싶다면 **한국투자증권 KIS Developers** 가 문서화된 대안입니다
(앱키 발급 + OAuth 토큰 필요). 참조 자료의 원본 화면도 한국투자증권 시세를 썼습니다.
