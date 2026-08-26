/* ============================================================
   providers/toss.mjs — 토스증권 WTS 시세 어댑터

   ⚠️ 토스증권은 공개 개발자 API를 제공하지 않는다.
   아래 엔드포인트는 토스증권 웹 트레이딩(WTS)이 내부적으로 쓰는
   **비공식·비문서화** 경로이며, 사전 통보 없이 응답 형태가 바뀌거나
   차단될 수 있다. 그래서 필드 매핑을 한 곳(FIELD_MAP)에 모으고,
   여러 후보 키를 순서대로 시도한 뒤 마지막에는 깊이 탐색으로 폴백한다.
   응답 형태가 바뀌면 FIELD_MAP만 고치면 된다.
   ============================================================ */

export const id = 'toss';
export const label = '토스증권 (비공식 WTS)';
export const HOST = 'wts-info-api.tossinvest.com';

/* TOSS_BASE 로 업스트림을 바꿔 끼울 수 있다 (목 서버 테스트용).
   지정하지 않으면 실제 토스 WTS 호스트를 쓴다. */
const BASE = process.env.TOSS_BASE || `https://${HOST}`;

/* 브라우저처럼 보이는 최소 헤더 — 일부 경로가 Referer/Origin을 요구한다 */
const HEADERS = {
  'Accept': 'application/json, text/plain, */*',
  'Accept-Language': 'ko-KR,ko;q=0.9',
  'Origin': 'https://www.tossinvest.com',
  'Referer': 'https://www.tossinvest.com/',
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
                '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
};

/* ---------- 값 추출 유틸 (응답 형태 변화에 견디도록) ---------- */

/** obj에서 'a.b.c' 경로 값을 꺼낸다 */
function at(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

/** 후보 경로들을 순서대로 시도하고, 첫 번째 유효값을 반환 */
function pick(obj, paths, { numeric = false } = {}) {
  for (const p of paths) {
    const v = at(obj, p);
    if (v == null || v === '') continue;
    if (numeric) {
      const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/[,\s]/g, ''));
      if (Number.isFinite(n)) return n;
      continue;
    }
    return v;
  }
  return null;
}

/** 마지막 폴백: 키 이름이 정규식에 맞는 첫 숫자 값을 깊이 탐색 */
function deepFind(obj, re, { numeric = true, depth = 5 } = {}) {
  const seen = new Set();
  const walk = (node, d) => {
    if (!node || typeof node !== 'object' || d > depth || seen.has(node)) return undefined;
    seen.add(node);
    for (const [k, v] of Object.entries(node)) {
      if (re.test(k)) {
        if (!numeric) { if (v != null && v !== '') return v; }
        else {
          const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/[,\s]/g, ''));
          if (Number.isFinite(n)) return n;
        }
      }
    }
    for (const v of Object.values(node)) {
      const r = walk(v, d + 1);
      if (r !== undefined) return r;
    }
    return undefined;
  };
  const r = walk(obj, 0);
  return r === undefined ? null : r;
}

/** 응답 배열 위치도 버전마다 달라 후보를 훑는다 */
function rowsOf(json) {
  const cands = ['result', 'result.products', 'result.items', 'result.stocks',
                 'data', 'data.result', 'items', 'products', 'stocks'];
  for (const c of cands) {
    const v = at(json, c);
    if (Array.isArray(v) && v.length) return v;
  }
  if (Array.isArray(json) && json.length) return json;
  // 단일 객체 응답
  const r = at(json, 'result') ?? at(json, 'data');
  if (r && typeof r === 'object' && !Array.isArray(r)) return [r];
  return [];
}

/* ---------- 필드 매핑 (응답 형태가 바뀌면 여기만 수정) ---------- */
export const FIELD_MAP = {
  code:   ['code', 'productCode', 'stockCode', 'isinCode', 'symbol', 'shortCode'],
  name:   ['name', 'productName', 'stockName', 'korName', 'nameKo', 'displayName'],
  price:  ['close', 'currentPrice', 'price', 'last', 'tradePrice', 'closePrice', 'nowPrice'],
  prev:   ['base', 'basePrice', 'prevClose', 'previousClose', 'prevPrice'],
  change: ['change', 'changeAmount', 'changePrice', 'diff'],
  rate:   ['changeRate', 'changeRatio', 'fluctuationRate', 'rate'],
  volume: ['volume', 'accTradeVolume', 'tradeVolume'],
  cap:    ['marketCap', 'marketCapitalization', 'marketValue', 'capitalization'],
  high52: ['week52High', 'wk52High', 'high52Week', 'yearHigh', 'highPrice52Week'],
  low52:  ['week52Low',  'wk52Low',  'low52Week',  'yearLow',  'lowPrice52Week'],
  per:    ['per', 'PER', 'priceEarningsRatio'],
  pbr:    ['pbr', 'PBR', 'priceBookValueRatio']
};

/** 토스 종목코드 정규화: 005930 → A005930 */
export function normalizeCode(input) {
  const s = String(input || '').trim().toUpperCase();
  if (/^[A-Z]\d{6}$/.test(s)) return s;      // 이미 A005930 형태
  if (/^\d{6}$/.test(s)) return 'A' + s;     // 6자리 숫자
  return s;                                   // 해외 티커 등은 그대로
}

async function getJSON(url) {
  const res = await fetch(url, { headers: HEADERS });
  const text = await res.text();
  if (!res.ok) {
    const err = new Error(`토스 응답 ${res.status} ${res.statusText}`);
    err.status = res.status;
    err.body = text.slice(0, 400);
    throw err;
  }
  try { return JSON.parse(text); }
  catch {
    const err = new Error('토스 응답이 JSON이 아닙니다 (차단 페이지일 수 있음)');
    err.body = text.slice(0, 400);
    throw err;
  }
}

/* ---------- 공개 API ---------- */

/** 종목명 검색 → [{ code, name }] */
export async function search(query) {
  const sections = encodeURIComponent(JSON.stringify([{ type: 'SCREENER' }, { type: 'NEWS' }]));
  const url = `${BASE}/api/v3/search-all/wts-auto-complete` +
              `?query=${encodeURIComponent(query)}&sections=${sections}`;
  const json = await getJSON(url);

  // 검색 응답은 섹션 안에 목록이 중첩된 형태가 흔하다.
  // rowsOf()는 result 객체를 통째로 단일 행으로 감싸므로 섹션을 먼저 확인한다.
  const secs = at(json, 'result.sections') || at(json, 'sections');
  let rows = [];
  if (Array.isArray(secs)) {
    rows = secs.flatMap(sec => (
      Array.isArray(sec?.data) ? sec.data :
      Array.isArray(sec?.products) ? sec.products :
      Array.isArray(sec?.items) ? sec.items : []
    ));
  }
  if (!rows.length) rows = rowsOf(json);
  return rows
    .map(r => ({
      code: pick(r, FIELD_MAP.code) || deepFind(r, /code$/i, { numeric: false }),
      name: pick(r, FIELD_MAP.name) || deepFind(r, /name$/i, { numeric: false })
    }))
    .filter(r => r.code && r.name)
    .slice(0, 12);
}

/** 시세 조회 → [{ code, name, price, change, changeRate, ... }] */
export async function quote(codes) {
  const list = codes.map(normalizeCode).filter(Boolean);
  if (!list.length) return [];
  const q = encodeURIComponent(list.join(','));
  const json = await getJSON(`${BASE}/api/v2/stock-prices?meta=true&codes=${q}`);
  const rows = rowsOf(json);

  return rows.map(r => {
    const price = pick(r, FIELD_MAP.price, { numeric: true }) ?? deepFind(r, /(close|price)$/i);
    const prev  = pick(r, FIELD_MAP.prev,  { numeric: true })
                  ?? deepFind(r, /^(base|prev|previous).*(price|close)?$|^(prevClose|basePrice)$/i);
    let change  = pick(r, FIELD_MAP.change, { numeric: true });
    let rate    = pick(r, FIELD_MAP.rate,   { numeric: true });

    // 등락폭·등락률은 서로에게서 유도 가능 — 없는 쪽을 채운다
    if (change == null && price != null && prev != null) change = price - prev;
    if (rate == null && change != null && prev) rate = (change / prev) * 100;
    // 비율이 0.0142 처럼 소수로 오는 경우 %로 환산
    if (rate != null && Math.abs(rate) < 1 && change && price && Math.abs(change / price) > 0.01) {
      rate = rate * 100;
    }

    const high = pick(r, FIELD_MAP.high52, { numeric: true });
    const low  = pick(r, FIELD_MAP.low52,  { numeric: true });

    return {
      code:   pick(r, FIELD_MAP.code) ?? null,
      name:   pick(r, FIELD_MAP.name) ?? null,
      price, change, changeRate: rate,
      volume: pick(r, FIELD_MAP.volume, { numeric: true }),
      cap:    pick(r, FIELD_MAP.cap,    { numeric: true }),
      per:    pick(r, FIELD_MAP.per,    { numeric: true }),
      pbr:    pick(r, FIELD_MAP.pbr,    { numeric: true }),
      high52: high, low52: low,
      band:   (high != null && low != null)
                ? `${low.toLocaleString('ko-KR')}~${high.toLocaleString('ko-KR')}원` : null,
      source: 'toss'
    };
  }).filter(r => r.price != null || r.code);
}

/** 진단용 원본 응답 (probe 모드) */
export async function raw(kind, arg) {
  if (kind === 'search') {
    const sections = encodeURIComponent(JSON.stringify([{ type: 'SCREENER' }]));
    return getJSON(`${BASE}/api/v3/search-all/wts-auto-complete?query=${encodeURIComponent(arg)}&sections=${sections}`);
  }
  const q = encodeURIComponent(arg.map(normalizeCode).join(','));
  return getJSON(`${BASE}/api/v2/stock-prices?meta=true&codes=${q}`);
}

export const _internal = { pick, at, deepFind, rowsOf };
