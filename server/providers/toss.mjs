/* ============================================================
   providers/toss.mjs — 토스증권 WTS 어댑터 (비공식, 키 불필요)

   ⚠️ 토스 웹 트레이딩(WTS)이 내부적으로 쓰는 **비문서화** 경로다.
   예고 없이 응답 형태가 바뀌거나 차단될 수 있다.
   API 키가 설정되어 있으면 프록시는 toss-open 을 먼저 쓰고,
   이 어댑터는 키가 없을 때의 대체 경로로 남는다.
   ============================================================ */

import {
  pick, rowsOf, sectionRows, deepFind, FIELD_MAP,
  normalizeQuote, withPrefix
} from './_extract.mjs';

export const id = 'toss';
export const label = '토스증권 (비공식 WTS)';
export const HOST = 'wts-info-api.tossinvest.com';

/* TOSS_BASE 로 업스트림을 바꿔 끼울 수 있다 (목 서버 테스트용) */
const BASE = process.env.TOSS_BASE || `https://${HOST}`;

/* 브라우저처럼 보이는 최소 헤더 — 일부 경로가 Referer/Origin 을 요구한다 */
const HEADERS = {
  'Accept': 'application/json, text/plain, */*',
  'Accept-Language': 'ko-KR,ko;q=0.9',
  'Origin': 'https://www.tossinvest.com',
  'Referer': 'https://www.tossinvest.com/',
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
                '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
};

export const normalizeCode = withPrefix;

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

const searchUrl = q => `${BASE}/api/v3/search-all/wts-auto-complete` +
  `?query=${encodeURIComponent(q)}&sections=${encodeURIComponent(JSON.stringify([{ type: 'SCREENER' }]))}`;
const quoteUrl = codes =>
  `${BASE}/api/v2/stock-prices?meta=true&codes=${encodeURIComponent(codes.map(withPrefix).join(','))}`;

/** 종목명 검색 → [{ code, name }] */
export async function search(query) {
  const json = await getJSON(searchUrl(query));
  // 섹션 중첩을 먼저 본다 — rowsOf 는 result 객체를 단일 행으로 감싸 목록을 놓친다
  let rows = sectionRows(json);
  if (!rows.length) rows = rowsOf(json);
  return rows
    .map(r => ({
      code: pick(r, FIELD_MAP.code) || deepFind(r, /code$/i, { numeric: false }),
      name: pick(r, FIELD_MAP.name) || deepFind(r, /name$/i, { numeric: false })
    }))
    .filter(r => r.code && r.name)
    .slice(0, 12);
}

/** 시세 조회 → 표준 시세 객체 배열 */
export async function quote(codes) {
  const list = codes.map(withPrefix).filter(Boolean);
  if (!list.length) return [];
  const json = await getJSON(quoteUrl(list));
  return rowsOf(json).map(r => normalizeQuote(r, 'toss'))
                     .filter(r => r.price != null || r.code);
}

/** 진단용 원본 응답 */
export async function raw(kind, arg) {
  return getJSON(kind === 'search' ? searchUrl(arg) : quoteUrl(arg));
}
