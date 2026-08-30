/* ============================================================
   _extract.mjs — 응답 형태 변화에 견디는 값 추출 유틸

   토스 계열 어댑터(비공식 WTS / 오픈 API)가 공유한다.
   문서화된 스키마가 없거나 바뀔 수 있으므로, 후보 키를 순서대로
   시도하고 마지막에는 키 이름 패턴으로 깊이 탐색한다.
   ============================================================ */

/** obj에서 'a.b.c' 경로 값을 꺼낸다 */
export function at(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

/** 후보 경로들을 순서대로 시도하고, 첫 번째 유효값을 반환 */
export function pick(obj, paths, { numeric = false } = {}) {
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

/** 마지막 폴백: 키 이름이 정규식에 맞는 첫 값을 깊이 탐색 */
export function deepFind(obj, re, { numeric = true, depth = 5 } = {}) {
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

/** 응답 배열의 위치도 버전마다 달라 후보를 훑는다 */
export function rowsOf(json) {
  const cands = ['result', 'result.products', 'result.items', 'result.stocks',
                 'data', 'data.result', 'data.items', 'items', 'products', 'stocks'];
  for (const c of cands) {
    const v = at(json, c);
    if (Array.isArray(v) && v.length) return v;
  }
  if (Array.isArray(json) && json.length) return json;
  const r = at(json, 'result') ?? at(json, 'data');
  if (r && typeof r === 'object' && !Array.isArray(r)) return [r];
  return [];
}

/** 섹션 중첩 목록(검색 응답)에서 행을 끌어낸다 */
export function sectionRows(json) {
  const secs = at(json, 'result.sections') || at(json, 'sections');
  if (!Array.isArray(secs)) return [];
  return secs.flatMap(sec => (
    Array.isArray(sec?.data) ? sec.data :
    Array.isArray(sec?.products) ? sec.products :
    Array.isArray(sec?.items) ? sec.items : []
  ));
}

/** 필드 매핑 — 응답 형태가 바뀌면 여기에 후보 키를 추가하면 된다 */
export const FIELD_MAP = {
  code:   ['code', 'productCode', 'stockCode', 'isinCode', 'symbol', 'shortCode', 'ticker'],
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

/** 한 행을 표준 시세 객체로 정규화 */
export function normalizeQuote(r, source) {
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
    source
  };
}

/** 토스 종목코드 정규화: 005930 → A005930 */
export function withPrefix(input) {
  const s = String(input || '').trim().toUpperCase();
  if (/^[A-Z]\d{6}$/.test(s)) return s;
  if (/^\d{6}$/.test(s)) return 'A' + s;
  return s;
}

/** 접두사 없는 순수 코드: A005930 → 005930 */
export const bare = c => String(c || '').replace(/^[A-Z](?=\d{6}$)/, '');

/** 비밀값 마스킹 — 로그·진단 출력에 원문 키가 남지 않게 한다 */
export function maskSecret(v) {
  const s = String(v || '');
  if (!s) return '(없음)';
  if (s.length <= 12) return s.slice(0, 3) + '***';
  return s.slice(0, 9) + '***' + s.slice(-4) + ` (${s.length}자)`;
}
