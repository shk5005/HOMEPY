/* ============================================================
   quotes.js — 브라우저측 시세 클라이언트

   정적 페이지는 토스 엔드포인트를 직접 호출할 수 없다(CORS).
   로컬 프록시(server/quote-proxy.mjs)를 통해서만 조회하며,
   프록시가 꺼져 있거나 상대가 막으면 **수동 입력으로 조용히 되돌아간다**.
   자동 시세는 편의 기능일 뿐, 앱의 필수 의존성이 아니다.
   ============================================================ */

const DEFAULT_PORT = 8787;
const LS_KEY = 'genie.proxy.url';
const TIMEOUT = 8000;

export const proxyUrl = () => {
  try { return localStorage.getItem(LS_KEY) || `http://127.0.0.1:${DEFAULT_PORT}`; }
  catch { return `http://127.0.0.1:${DEFAULT_PORT}`; }
};

export function setProxyUrl(url) {
  try { localStorage.setItem(LS_KEY, String(url || '').replace(/\/+$/, '')); } catch { /* 저장 불가 */ }
}

async function call(path, params = {}) {
  const url = new URL(proxyUrl() + path);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(json.error || `프록시 응답 ${res.status}`);
      err.hint = json.hint;
      err.upstreamStatus = json.upstreamStatus;
      throw err;
    }
    return json;
  } catch (e) {
    if (e.name === 'AbortError') {
      const err = new Error('시세 조회 시간 초과 (8초)');
      err.hint = '프록시가 응답하지 않습니다. 네트워크를 확인하세요.';
      throw err;
    }
    if (e instanceof TypeError) {
      // fetch 자체가 실패 = 프록시 미실행이 가장 흔한 원인
      const err = new Error('시세 프록시에 연결할 수 없습니다');
      err.hint = 'node server/quote-proxy.mjs 를 실행한 뒤 다시 시도하세요.';
      err.offline = true;
      throw err;
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** 프록시가 살아있는지 (UI 배지용) */
export async function health() {
  try {
    const j = await call('/api/health');
    return { ok: true, label: j.label };
  } catch (e) {
    return { ok: false, error: e.message, hint: e.hint, offline: e.offline };
  }
}

/** 종목명 검색 → [{ code, name }] */
export async function search(query) {
  const j = await call('/api/search', { q: query });
  return j.rows || [];
}

/** 시세 조회 → [{ code, name, price, change, changeRate, per, pbr, cap, band }] */
export async function quote(codes) {
  const j = await call('/api/quote', { codes: codes.join(',') });
  return { rows: j.rows || [], asOf: j.asOf };
}

/** 조회 시각을 프롬프트 앵커용 문자열로 — 'YYYY.MM.DD HH:mm (KST)' */
export function stampKST(iso) {
  const d = iso ? new Date(iso) : new Date();
  const kst = new Date(d.getTime() + (9 * 60 + d.getTimezoneOffset()) * 60000);
  const p = n => String(n).padStart(2, '0');
  return `${kst.getFullYear()}.${p(kst.getMonth() + 1)}.${p(kst.getDate())} ` +
         `${p(kst.getHours())}:${p(kst.getMinutes())} (KST)`;
}

/** 억/조 단위 시가총액 표기 */
export function formatCap(v) {
  if (v == null || !Number.isFinite(v)) return null;
  if (v >= 1e12) return (v / 1e12).toFixed(1).replace(/\.0$/, '') + '조원';
  if (v >= 1e8)  return Math.round(v / 1e8).toLocaleString('ko-KR') + '억원';
  return Math.round(v).toLocaleString('ko-KR') + '원';
}
