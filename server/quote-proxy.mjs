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
import * as toss from './providers/toss.mjs';

const PROVIDERS = { toss };
const ALLOWED_HOSTS = new Set(Object.values(PROVIDERS).map(p => p.HOST));

const argv = process.argv.slice(2);
const argOf = name => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : null;
};
const PORT = Number(argOf('--port')) || 8787;
const PROVIDER = argOf('--provider') || 'toss';

/* ---------- probe 모드: 원본 응답을 그대로 찍어 매핑을 확인 ---------- */
async function probe() {
  const p = PROVIDERS[PROVIDER];
  const searchQ = argOf('--probe-search');
  const quoteQ  = argOf('--probe');
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
    console.error(`
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
      return send(res, 200, { ok: true, provider: provider.id, label: provider.label });
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
    // 업스트림 실패는 502로 구분해 UI가 '수동 입력'으로 안내할 수 있게 한다
    return send(res, 502, {
      error: e.message,
      hint: `${provider.label} 호출 실패. 비공식 엔드포인트라 형태가 바뀌었을 수 있습니다. ` +
            `node server/quote-proxy.mjs --probe 005930 으로 원본 응답을 확인하세요.`,
      upstreamStatus: e.status ?? null
    });
  }
});

if (argv.includes('--probe') || argv.includes('--probe-search')) {
  probe();
} else {
  server.listen(PORT, '127.0.0.1', () => {
    console.log(`
🧞 지니 시세 프록시
   http://127.0.0.1:${PORT}
   프로바이더: ${PROVIDERS[PROVIDER].label}

   GET /api/health
   GET /api/search?q=삼성전자
   GET /api/quote?codes=005930,000660

   ⚠️ 토스증권은 공개 개발자 API를 제공하지 않습니다.
      이 프록시는 비공식 WTS 엔드포인트를 호출하므로
      예고 없이 응답이 바뀌거나 차단될 수 있습니다.
      실패 시 앱은 수동 시세 입력으로 자동 전환됩니다.
`);
  });
}
