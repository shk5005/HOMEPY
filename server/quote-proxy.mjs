#!/usr/bin/env node
/* ============================================================
   quote-proxy.mjs — 지니 시세 프록시 (의존성 0, Node 18+)

   왜 필요한가:
   토스 WTS 엔드포인트는 브라우저의 교차 출처 요청에 CORS 허용 헤더를
   내려주지 않는다. 정적 페이지에서 직접 호출하면 브라우저가 차단하므로,
   로컬에서 도는 이 얇은 프록시가 대신 호출하고 CORS 헤더를 붙여 돌려준다.

   실행:
     node server/quote-proxy.mjs              # 포트 8787
     node server/quote-proxy.mjs --port 9000
     node server/quote-proxy.mjs --probe 005930   # 원본 응답 진단
     node server/quote-proxy.mjs --probe-search 삼성전자

   보안: 127.0.0.1 에만 바인딩하고, 허용된 업스트림 호스트로만 요청한다
   (열린 프록시가 되지 않도록). 인증 정보를 다루지 않는다.
   ============================================================ */

import { createServer } from 'node:http';
import { readFileSync, existsSync } from 'node:fs';
import { maskSecret } from './providers/_extract.mjs';

/* ---------- .env 로딩 (의존성 없이) ----------
   API 키는 소스나 저장소에 두지 않는다. .env 는 .gitignore 에 있고,
   형식은 .env.example 에 있다. 이미 설정된 환경변수가 항상 우선한다. */
function loadEnv(file = '.env') {
  if (!existsSync(file)) return 0;
  let n = 0;
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/i);
    if (!m || line.trimStart().startsWith('#')) continue;
    const key = m[1];
    let val = m[2].trim().replace(/^["']|["']$/g, '');
    if (process.env[key] === undefined) { process.env[key] = val; n++; }
  }
  return n;
}
const envLoaded = loadEnv();

// .env 를 읽은 뒤에 어댑터를 가져와야 모듈 최상단의 설정이 반영된다
const toss = await import('./providers/toss.mjs');
const tossOpen = await import('./providers/toss-open.mjs');

const PROVIDERS = { toss, 'toss-open': tossOpen };
const ALLOWED_HOSTS = new Set(Object.values(PROVIDERS).map(p => p.HOST));

const argv = process.argv.slice(2);
const argOf = name => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : null;
};
const PORT = Number(argOf('--port')) || 8787;
// 키가 있으면 문서화된 오픈 API 를 먼저 쓰고, 없으면 비공식 WTS 로 떨어진다
const PROVIDER = argOf('--provider') || (tossOpen.hasKey() ? 'toss-open' : 'toss');

/* ---------- probe 모드: 원본 응답을 그대로 찍어 매핑을 확인 ---------- */
async function probe() {
  const p = PROVIDERS[PROVIDER];
  const searchQ = argOf('--probe-search');
  const quoteQ  = argOf('--probe');
  console.log(`\n프로바이더: ${p.label}`);
  if (p.describeRequest) {
    const d = p.describeRequest(searchQ ? 'search' : 'quote',
      searchQ || (quoteQ || '005930').split(',').map(x => x.trim()));
    console.log(`요청:     ${d.url}`);
    console.log(`인증방식: ${d.authStyle}`);
    console.log(`헤더:     ${JSON.stringify(d.headers)}`);
  }
  try {
    if (searchQ) {
      console.log(`\n▶ ${p.label} 검색 원본 응답 — "${searchQ}"\n`);
      const json = await p.raw('search', searchQ);
      console.log(JSON.stringify(json, null, 2).slice(0, 4000));
      console.log('\n▶ 파싱 결과:');
      console.log(JSON.stringify(await p.search(searchQ), null, 2));
    } else {
      const codes = quoteQ.split(',').map(s => s.trim());
      console.log(`\n▶ ${p.label} 시세 원본 응답 — ${codes.join(', ')}\n`);
      const json = await p.raw('quote', codes);
      console.log(JSON.stringify(json, null, 2).slice(0, 4000));
      console.log('\n▶ 파싱 결과:');
      console.log(JSON.stringify(await p.quote(codes), null, 2));
    }
    console.log(`
──────────────────────────────────────────────
파싱 결과에 null 이 많다면 응답 형태가 바뀐 것입니다.
위 '원본 응답'의 키 이름을 확인해
server/providers/toss.mjs 의 FIELD_MAP 에 추가하세요.
──────────────────────────────────────────────`);
  } catch (e) {
    console.error(`\n✖ ${p.label} 호출 실패: ${e.message}`);
    if (e.body) console.error('응답 일부:', e.body);
    if (e.hint) console.error(`힌트: ${e.hint}`);
    console.error(p.id === 'toss-open' ? `
확인할 점:
  1. 이 머신에서 ${p.HOST} 로 나가는 네트워크가 열려 있는지
  2. 401/403 이면 키와 인증 방식 (.env 의 TOSS_AUTH_STYLE)
  3. 404 면 엔드포인트 경로 (.env 의 TOSS_QUOTE_PATH / TOSS_SEARCH_PATH)
  4. 공식 문서의 base URL 이 ${p.BASE} 와 다른지 (.env 의 TOSS_API_BASE)` : `
확인할 점:
  1. 이 머신에서 ${p.HOST} 로 나가는 네트워크가 열려 있는지
  2. 토스가 해당 경로를 변경/차단했는지 (비공식 엔드포인트라 예고 없이 바뀝니다)
  3. 회사망·방화벽·VPN이 막고 있는지`);
    process.exitCode = 1;
  }
}

/* ---------- HTTP 서버 ---------- */
function send(res, status, body, extra = {}) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Cache-Control': 'no-store',
    ...extra
  });
  res.end(JSON.stringify(body));
}

/* 짧은 캐시 — 같은 종목을 연속 조회할 때 상대 서버 부담을 줄인다 */
const cache = new Map();
const TTL = 5000;
function cached(key, fn) {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.t < TTL) return Promise.resolve(hit.v);
  return fn().then(v => { cache.set(key, { t: Date.now(), v }); return v; });
}

const server = createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return send(res, 204, {});

  let url;
  try { url = new URL(req.url, `http://127.0.0.1:${PORT}`); }
  catch { return send(res, 400, { error: '잘못된 요청 경로' }); }

  const provider = PROVIDERS[url.searchParams.get('provider') || PROVIDER];
  // 업스트림은 등록된 프로바이더의 고정 호스트로만 나간다 (열린 프록시 방지).
  // TOSS_BASE 가 설정된 경우는 목 서버를 향한 테스트 실행이다.
  if (!provider || (!ALLOWED_HOSTS.has(provider.HOST) && !process.env.TOSS_BASE)) {
    return send(res, 400, { error: '허용되지 않은 프로바이더' });
  }

  try {
    if (url.pathname === '/api/health') {
      return send(res, 200, {
        ok: true, provider: provider.id, label: provider.label,
        // 키 자체가 아니라 '설정되었는지'만 알린다
        keyed: typeof provider.hasKey === 'function' ? provider.hasKey() : false
      });
    }

    if (url.pathname === '/api/search') {
      const q = (url.searchParams.get('q') || '').trim();
      if (!q) return send(res, 400, { error: '검색어(q)가 필요합니다' });
      const rows = await cached('s:' + q, () => provider.search(q));
      return send(res, 200, { provider: provider.id, rows });
    }

    if (url.pathname === '/api/quote') {
      const codes = (url.searchParams.get('codes') || '')
        .split(',').map(s => s.trim()).filter(Boolean).slice(0, 20);
      if (!codes.length) return send(res, 400, { error: '종목코드(codes)가 필요합니다' });
      const rows = await cached('q:' + codes.join(','), () => provider.quote(codes));
      return send(res, 200, {
        provider: provider.id, asOf: new Date().toISOString(), rows
      });
    }

    return send(res, 404, { error: '없는 경로' });
  } catch (e) {
    // 업스트림 실패는 502로 구분해 UI가 '수동 입력'으로 안내할 수 있게 한다.
    // 어댑터가 원인별 힌트를 붙였으면 그대로 쓴다 — 인증 실패와 경로 오류는
    // 사용자가 할 일이 서로 다르므로 뭉뚱그리면 안 된다.
    const fallbackHint = provider.id === 'toss'
      ? `${provider.label} 호출 실패. 비공식 엔드포인트라 형태가 바뀌었을 수 있습니다.`
      : `${provider.label} 호출 실패.`;
    return send(res, 502, {
      error: e.message,
      hint: (e.hint || fallbackHint) +
            ` 진단: node server/quote-proxy.mjs --probe 005930`,
      upstreamStatus: e.status ?? null
    });
  }
});

if (argv.includes('--probe') || argv.includes('--probe-search')) {
  probe();
} else {
  server.listen(PORT, '127.0.0.1', () => {
    const p = PROVIDERS[PROVIDER];
    const keyLine = p.hasKey?.()
      ? `   API 키: ${p.keyHint()}  (환경변수에서 로드)`
      : `   API 키: 없음 — 비공식 WTS 경로로 동작합니다`;
    console.log(`
지니 시세 프록시
   http://127.0.0.1:${PORT}
   프로바이더: ${p.label}
${keyLine}${envLoaded ? `\n   .env 에서 ${envLoaded}개 값 로드` : ''}

   GET /api/health
   GET /api/search?q=삼성전자
   GET /api/quote?codes=005930,000660

   실패 시 앱은 수동 시세 입력으로 자동 전환됩니다.
`);
  });
}
