/* ============================================================
   providers/toss-open.mjs — 토스증권 오픈 API 어댑터 (API 키 사용)

   ⚠️ 이 어댑터는 공개 문서를 확인하지 못한 상태에서 작성되었다.
   개발 환경의 이그레스 정책이 tossinvest.com 전체를 막고 있어
   실제 엔드포인트 경로·인증 방식·응답 형태를 검증할 수 없었다.

   그래서 확정할 수 없는 것들을 전부 **환경변수로 빼두었다.**
   공식 문서를 보고 값만 맞추면 코드를 고칠 필요가 없다.

     GENIE_TOSS_API_KEY   API 키 (필수)
     TOSS_API_BASE        기본 https://openapi.tossinvest.com
     TOSS_AUTH_STYLE      bearer(기본) | header | query | basic
     TOSS_AUTH_HEADER     header 방식일 때 헤더 이름 (기본 X-API-Key)
     TOSS_AUTH_PARAM      query 방식일 때 파라미터 이름 (기본 apiKey)
     TOSS_QUOTE_PATH      기본 /v1/stocks/prices
     TOSS_SEARCH_PATH     기본 /v1/stocks/search
     TOSS_CODE_PARAM      기본 codes
     TOSS_QUERY_PARAM     기본 query

   키는 절대 코드나 저장소에 넣지 않는다. 진단 출력에도 마스킹해서만 남는다.
   ============================================================ */

import {
  pick, rowsOf, sectionRows, deepFind, FIELD_MAP,
  normalizeQuote, withPrefix, maskSecret
} from './_extract.mjs';

export const id = 'toss-open';
export const label = '토스증권 오픈 API';

const env = (k, d) => process.env[k] || d;

export const BASE = env('TOSS_API_BASE', 'https://openapi.tossinvest.com').replace(/\/+$/, '');
export const HOST = new URL(BASE).host;

const KEY          = env('GENIE_TOSS_API_KEY', '');
const AUTH_STYLE   = env('TOSS_AUTH_STYLE', 'bearer').toLowerCase();
const AUTH_HEADER  = env('TOSS_AUTH_HEADER', 'X-API-Key');
const AUTH_PARAM   = env('TOSS_AUTH_PARAM', 'apiKey');
const QUOTE_PATH   = env('TOSS_QUOTE_PATH', '/v1/stocks/prices');
const SEARCH_PATH  = env('TOSS_SEARCH_PATH', '/v1/stocks/search');
const CODE_PARAM   = env('TOSS_CODE_PARAM', 'codes');
const QUERY_PARAM  = env('TOSS_QUERY_PARAM', 'query');

export const hasKey = () => !!KEY;
export const keyHint = () => maskSecret(KEY);

/** 인증을 헤더 또는 쿼리에 싣는다 */
function authorize(url) {
  const headers = {
    'Accept': 'application/json',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'User-Agent': 'genie-stock-advisor/1.0'
  };
  switch (AUTH_STYLE) {
    case 'header': headers[AUTH_HEADER] = KEY; break;
    case 'basic':  headers.Authorization = 'Basic ' + Buffer.from(KEY + ':').toString('base64'); break;
    case 'query':  url.searchParams.set(AUTH_PARAM, KEY); break;
    case 'bearer':
    default:       headers.Authorization = `Bearer ${KEY}`; break;
  }
  return headers;
}

/** 진단용 — 실제로 어떤 요청을 보내는지 (키는 마스킹) */
export function describeRequest(kind, arg) {
  const url = buildUrl(kind, arg);
  const headers = authorize(new URL(url));   // 사본에만 실어 원본 로그를 더럽히지 않는다
  const shown = Object.fromEntries(Object.entries(headers).map(([k, v]) =>
    [k, /authorization|api-key|apikey/i.test(k) ? maskSecret(KEY) : v]));
  const shownUrl = AUTH_STYLE === 'query'
    ? url.replace(new RegExp(`(${AUTH_PARAM}=)[^&]*`), `$1${maskSecret(KEY)}`)
    : url;
  return { url: shownUrl, authStyle: AUTH_STYLE, headers: shown };
}

function buildUrl(kind, arg) {
  if (kind === 'search') {
    const u = new URL(BASE + SEARCH_PATH);
    u.searchParams.set(QUERY_PARAM, arg);
    return u.toString();
  }
  const u = new URL(BASE + QUOTE_PATH);
  u.searchParams.set(CODE_PARAM, arg.map(withPrefix).join(','));
  return u.toString();
}

async function getJSON(kind, arg) {
  if (!KEY) {
    const e = new Error('토스 오픈 API 키가 설정되지 않았습니다');
    e.hint = 'GENIE_TOSS_API_KEY 환경변수를 설정하거나 .env 파일에 넣으세요.';
    throw e;
  }
  const url = new URL(buildUrl(kind, arg));
  const headers = authorize(url);

  const res = await fetch(url, { headers });
  const text = await res.text();

  if (!res.ok) {
    const e = new Error(`토스 오픈 API 응답 ${res.status} ${res.statusText}`);
    e.status = res.status;
    e.body = text.slice(0, 400);
    if (res.status === 401 || res.status === 403) {
      e.hint = `인증 실패. 키가 유효한지, 인증 방식이 맞는지 확인하세요 ` +
               `(현재 TOSS_AUTH_STYLE=${AUTH_STYLE}). 키: ${maskSecret(KEY)}`;
    } else if (res.status === 404) {
      e.hint = `엔드포인트 경로가 다를 수 있습니다 (현재 ${kind === 'search' ? SEARCH_PATH : QUOTE_PATH}). ` +
               `TOSS_SEARCH_PATH / TOSS_QUOTE_PATH 로 바꿀 수 있습니다.`;
    } else if (res.status === 429) {
      e.hint = '호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.';
    }
    throw e;
  }
  try { return JSON.parse(text); }
  catch {
    const e = new Error('오픈 API 응답이 JSON이 아닙니다');
    e.body = text.slice(0, 400);
    throw e;
  }
}

/** 종목명 검색 → [{ code, name }] */
export async function search(query) {
  const json = await getJSON('search', query);
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
  const json = await getJSON('quote', list);
  return rowsOf(json).map(r => normalizeQuote(r, 'toss-open'))
                     .filter(r => r.price != null || r.code);
}

/** 진단용 원본 응답 */
export async function raw(kind, arg) {
  return getJSON(kind, kind === 'search' ? arg : arg);
}
