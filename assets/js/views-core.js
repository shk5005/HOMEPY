/* ============================================================
   views-core.js — 대시보드 / 종목 발굴 / 교차 검증
   ============================================================ */

import * as D from './data.js';
import * as C from './calc.js';
import * as P from './prompts.js';
import * as S from './store.js';
import { esc, chipGroup, promptBox, table, stat } from './ui.js';

/* ---------------- 대시보드 ---------------- */
export function dashboard() {
  const st = S.get();
  const pr = S.progress();
  const picks = st.picks || [];

  return `
  <div class="page-eyebrow">AI 강제 차단 시스템 · 행동경제학 헷지</div>
  <h1 class="page-title">주식투자비서 지니</h1>
  <p class="page-desc">
    지니는 종목을 대신 골라주지 않습니다. 대신 <strong>당신이 실수하지 못하게 막습니다.</strong>
    기준 없는 추천, 단일 AI 맹신, 단일 지표, 출처 없는 수치, 손절가 없는 매수 —
    이 다섯 가지 함정을 구조적으로 차단하는 파이프라인입니다.
  </p>

  <div class="trap-hero">
    <h2>일반 투자자가 빠지는 '함정 5가지'</h2>
    <p>AI가 강제 차단하도록 설계</p>
    ${D.TRAPS.map((t, i) => `
      <div class="trap-row">
        <span class="trap-n">${i + 1}</span>
        <span class="trap-bad">${esc(t.bad)}</span>
        <span class="trap-arrow">▶</span>
        <span class="trap-fix">${esc(t.fix)}</span>
      </div>`).join('')}
  </div>

  <div class="card">
    <h3 class="card-title">📍 진행 상황</h3>
    <p class="card-sub">지니 파이프라인 6단계 · ${pr}% 완료</p>
    <div class="bar"><i style="width:${pr}%"></i></div>
    <div class="stat-row">
      ${stat('선택 종목', picks.length + '개', picks.map(p => p.name).join(', ') || '아직 없음')}
      ${stat('교차검증 AI', Object.values(st.cross).filter(t => t?.trim().length > 40).length + ' / 3', '2곳 이상 합의 필요')}
      ${stat('안전마진', st.valuation.marginPct + '%', '적정가 대비 할인')}
      ${stat('손절 기준', '-' + st.risk.stop + '%', '매수 전 필수 설정')}
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">🧭 지니 파이프라인</h3>
    <p class="card-sub">순서대로 진행하세요. 앞 단계를 건너뛰면 뒤 단계가 함정이 됩니다.</p>
    <div class="step-grid">
      ${[
        { r: 'discovery', i: '🔎', t: '① 종목 발굴', d: 'RICE 프롬프트로 기준부터 세운다' },
        { r: 'cross',     i: '⚖️', t: '② 교차 검증', d: '3개 AI 답변의 교집합만 남긴다' },
        { r: 'steps',     i: '🔬', t: '③ 심층 분석', d: 'STEP 1~5 · WHAT→WHEN' },
        { r: 'valuation', i: '💰', t: '④ 밸류에이션', d: '다각 멀티플 + 안전마진' },
        { r: 'risk',      i: '🛡', t: '⑤ 리스크', d: 'Bull/Base/Bear + 손절가 먼저' },
        { r: 'portfolio', i: '📦', t: '⑥ 포트폴리오', d: '투자점수 기반 차등배분' }
      ].map(s => `
        <button class="step-card ${st.done[s.r] ? 'done' : ''}" data-route="${s.r}">
          <span class="emo">${s.i}</span>
          <div class="t">${s.t}</div>
          <div class="d">${esc(s.d)}</div>
        </button>`).join('')}
    </div>
  </div>

  <div class="card-dark">
    <h3 class="card-title">🛠 애널리스트의 핵심 분석 도구 6가지</h3>
    <p class="card-sub">전문가가 종목을 평가할 때 쓰는 도구 — 지니는 이 6개를 전부 강제합니다</p>
    <div class="step-grid">
      ${D.TOOLS_6.map(t => `
        <div style="background:#16293f;border:1px solid #24384f;border-radius:12px;padding:15px 16px">
          <div style="font-size:15px;font-weight:800;color:#f4c65e">${esc(t.k)}</div>
          <div style="font-size:12px;color:#9db0c7;margin-top:5px;line-height:1.5">${esc(t.d)}</div>
          ${t.s ? `<div style="font-size:10.5px;color:#6f849c;margin-top:6px">— ${esc(t.s)}</div>` : ''}
        </div>`).join('')}
    </div>
  </div>

  <div class="alert alert-warn">
    <span>⚠️</span>
    <div><strong>지니는 투자 자문 도구가 아닙니다.</strong>
    생성된 프롬프트와 계산 결과는 의사결정 보조 자료이며, 모든 수치는 AI 답변에서 나온 값이므로
    반드시 거래소·DART 원문으로 교차 확인하세요. 최종 투자 판단과 그 책임은 투자자 본인에게 있습니다.</div>
  </div>`;
}

/* ---------------- 종목 발굴 ---------------- */
export function discovery() {
  const cfg = S.get().discovery;
  const style = D.STYLES.find(s => s.id === cfg.style) || D.STYLES[0];

  return `
  <div class="page-eyebrow">① 종목 발굴</div>
  <h1 class="page-title">섹터별 유망 종목 발굴</h1>
  <p class="page-desc">감과 유튜브 추천을 벗어나, 월스트리트 기준으로 자동 스크리닝합니다.</p>

  <div class="card">
    <dl class="rail">
      <dt>WHY</dt><dd>"괜찮은 주식 추천해줘" 같은 막연한 질문에는 온갖 답변이 나옵니다.
        필터를 먼저 고정해야 답변도 재현 가능해집니다.</dd>
      <dt>HOW</dt><dd>섹터 × 스타일 × 스크리닝 필터 × 기간 × 목표수익률을 조합해
        RICE(Role·Instruction·Context·Example) 프롬프트를 자동 생성합니다.</dd>
      <dt>OUTPUT</dt><dd>추천 종목 TOP ${cfg.count} + 매수·목표·손절가 + 추천 근거 + 출처 URL
        <span class="muted">→ 다음 단계에서 3개 AI 교차 검증</span></dd>
    </dl>
  </div>

  <div class="card">
    <h3 class="card-title">🎛 스크리닝 조건</h3>
    <p class="card-sub">거장 기준을 강제 설정합니다 — 함정 ① 차단</p>

    <div class="field">
      <div class="field-label">투자 섹터 <span class="field-hint">복수 선택 가능</span></div>
      ${chipGroup({ name: 'sectors', options: D.SECTORS, value: cfg.sectors, multi: true })}
    </div>

    <div class="field">
      <div class="field-label">투자 스타일</div>
      ${chipGroup({ name: 'style', options: D.STYLES, value: cfg.style })}
      <div class="alert alert-info" style="margin-top:10px">
        <span>📐</span><div><strong>${esc(style.label)} 기본 필터:</strong> ${esc(style.filter)}</div>
      </div>
    </div>

    <div class="split">
      <div class="field">
        <div class="field-label">투자 기간</div>
        ${chipGroup({ name: 'horizon', options: D.HORIZONS, value: cfg.horizon })}
      </div>
      <div class="field">
        <div class="field-label">목표 수익률</div>
        ${chipGroup({ name: 'target', options: D.TARGET_RETURNS.map(v => ({ id: String(v), label: v + '%' })), value: String(cfg.target) })}
      </div>
    </div>

    <div class="split">
      <div class="field">
        <div class="field-label">추천 개수</div>
        ${chipGroup({ name: 'count', options: D.PICK_COUNTS.map(v => ({ id: String(v), label: v + '개' })), value: String(cfg.count) })}
      </div>
      <div class="field">
        <div class="field-label">위험 성향</div>
        ${chipGroup({ name: 'risk', options: ['저위험', '중위험', '고위험'], value: cfg.risk })}
      </div>
    </div>

    <div class="split">
      <div class="field">
        <div class="field-label">스크리닝 필터 <span class="field-hint">비우면 스타일 기본값 사용</span></div>
        <input class="input" data-bind="discovery.filter" value="${esc(cfg.filter)}"
          placeholder="예: PEG 1.5 이하, 매출 CAGR 15%+, 영업이익 개선">
      </div>
      <div class="field">
        <div class="field-label">중점 분석 <span class="field-hint">선택</span></div>
        <input class="input" data-bind="discovery.focus" value="${esc(cfg.focus)}"
          placeholder="예: 시장점유율 확대, 신사업 진출">
      </div>
    </div>

    <div class="field">
      <div class="field-label">대상 시장</div>
      ${chipGroup({ name: 'market', options: ['한국 코스피 200', '코스닥 150', '미국 S&P 500', '나스닥 100'], value: cfg.market })}
    </div>

    <div class="field mb0">
      <div class="field-label">제외 조건 <span class="field-hint">줄바꿈으로 구분</span></div>
      <textarea class="textarea" data-bind="discovery.exclusions" style="min-height:80px"
        placeholder="한 줄에 하나씩">${esc((cfg.exclusions || []).join('\n'))}</textarea>
    </div>
  </div>

  <button class="btn btn-navy btn-lg btn-block" data-action="gen-discovery">
    ✨ RICE 프롬프트 생성
  </button>
  <div id="discovery-out" class="mt"></div>`;
}

export function discoveryPromptHTML() {
  const cfg = S.get().discovery;
  const text = P.discoveryPrompt({ ...cfg, count: cfg.count, target: cfg.target });
  return promptBox('RICE 프롬프트 (AI에 붙여넣을 부분)', text, 'p-discovery') + `
    <div class="alert alert-ok mt">
      <span>➡️</span>
      <div><strong>다음 단계:</strong> 이 프롬프트를 ChatGPT · Claude · Perplexity
      <strong>세 곳 모두</strong>에 넣고, 각 답변을 ② 교차 검증에 붙여넣으세요.
      한 곳만 쓰면 함정 ②에 그대로 빠집니다.</div>
    </div>
    <button class="btn btn-gold btn-lg btn-block mt" data-route="cross">
      ⚖️ 3개 AI 답변 교차 검증하러 가기 →
    </button>`;
}

/* ---------------- 교차 검증 ---------------- */
export function cross() {
  const st = S.get();
  return `
  <div class="page-eyebrow">② 교차 검증</div>
  <h1 class="page-title">3개 AI 교차 검증</h1>
  <p class="page-desc">
    같은 조건으로 세 AI에 물으면 답이 다릅니다. 그 <strong>다른 부분이 리스크</strong>이고,
    <strong>겹치는 부분이 신호</strong>입니다. 지니는 교집합만 남깁니다.
  </p>

  <div class="alert alert-warn">
    <span>🚫</span>
    <div><strong>함정 ② 차단:</strong> 하나의 AI만 믿기 → 3개의 AI로 교차 검증.
    각 AI 답변을 그대로 아래에 붙여넣으면 지니가 종목명을 자동 추출해 합의 수준을 계산합니다.</div>
  </div>

  <div class="split-3">
    ${D.AI_PANELS.map(p => `
      <div class="ai-col ${p.cls}">
        <h4>${p.dot} ${esc(p.label)}</h4>
        <div class="cnt" data-count="${p.id}">답변을 붙여넣으세요</div>
        <textarea class="textarea code" data-bind="cross.${p.id}"
          placeholder="${esc(p.label)} 답변 전체를 붙여넣기">${esc(st.cross[p.id] || '')}</textarea>
      </div>`).join('')}
  </div>

  <button class="btn btn-navy btn-lg btn-block mt" data-action="run-cross">
    🔀 교차 검증 분석 (API 불필요)
  </button>

  <div id="cross-out" class="mt"></div>`;
}

export function crossResultHTML() {
  const st = S.get();
  const panels = D.AI_PANELS.map(p => ({
    ...p, text: st.cross[p.id] || '', tickers: C.extractTickers(st.cross[p.id])
  }));
  const filled = panels.filter(p => p.text.trim().length > 40);

  if (filled.length < 2) {
    return `<div class="alert alert-bad"><span>⛔</span>
      <div><strong>최소 2개 AI 답변이 필요합니다.</strong> 현재 ${filled.length}개 입력됨.
      교차 검증의 목적은 한 모델의 편향을 다른 모델로 상쇄하는 것입니다.</div></div>`;
  }

  const cv = C.crossValidate(panels);
  const consensus = [...cv.consensus3, ...cv.consensus2];

  const picked = new Set(S.pickNames().map(n => n.replace(/\s/g, '')));
  const isPicked = n => picked.has(n.replace(/\s/g, ''));
  const chips = arr => arr.length
    ? `<div class="tickers">${arr.map(r => `
        <button class="tk hit${r.sources.length >= 3 ? '3' : '2'}" data-add-pick="${esc(r.name)}"
          title="${isPicked(r.name) ? '이미 담김' : '클릭해 분석 대상에 추가'}">
          ${isPicked(r.name) ? '✔ ' : '+ '}${esc(r.name)}
          <span class="badge-pill ${r.sources.length >= 3 ? 'bp-green' : 'bp-gold'}">${r.sources.length}/3</span>
        </button>`).join('')}</div>`
    : '<p class="muted">해당 없음</p>';

  return `
  <div class="card">
    <h3 class="card-title">🔀 교차 검증 결과</h3>
    <p class="card-sub">${filled.length}개 AI 답변에서 종목명을 추출해 언급 횟수로 합의 수준을 판정했습니다.</p>

    <div class="stat-row">
      ${stat('3/3 만장일치', cv.consensus3.length + '개', '가장 강한 신호')}
      ${stat('2/3 합의', cv.consensus2.length + '개', '검토 대상')}
      ${stat('단독 추천', cv.single.length + '개', '근거 확인 필요')}
    </div>

    <div class="field">
      <div class="field-label">✅✅✅ 만장일치 추천 <span class="field-hint">3개 AI 모두 언급 — 클릭해 분석 대상에 추가</span></div>
      ${chips(cv.consensus3)}
    </div>
    <div class="field">
      <div class="field-label">✅✅ 2곳 합의 <span class="field-hint">클릭해 분석 대상에 추가</span></div>
      ${chips(cv.consensus2)}
    </div>
    <div class="field mb0">
      <div class="field-label">⚠️ 단독 추천 <span class="field-hint">왜 나머지 2곳이 빠뜨렸는지 확인 후 판단</span></div>
      ${cv.single.length
        ? `<div class="tickers">${cv.single.slice(0, 24).map(r => `
            <button class="tk" data-add-pick="${esc(r.name)}">${isPicked(r.name) ? '✔ ' : '+ '}${esc(r.name)}
            <span class="badge-pill bp-navy">${esc(r.sources[0])}</span></button>`).join('')}</div>`
        : '<p class="muted">해당 없음</p>'}
    </div>
  </div>

  ${consensus.length ? `
  <div class="alert alert-ok">
    <span>🎯</span>
    <div><strong>공통 ${consensus.length}종목:</strong> ${consensus.map(c => esc(c.name)).join(', ')}
    — 종목 칩을 클릭해 분석 대상에 담은 뒤 ③ 심층 분석으로 넘어가세요.
    ${picked.size ? `<br><strong>현재 담긴 종목 ${picked.size}개:</strong> ${S.pickNames().map(esc).join(', ')}` : ''}</div>
  </div>` : ''}

  ${promptBox('종합 비교 프롬프트 (근거 충돌 지점 찾기)',
    P.crossCheckPrompt(panels, consensus), 'p-cross')}

  <button class="btn btn-gold btn-lg btn-block mt" data-route="steps">
    🔬 선택 종목 함께 분석하기 →
  </button>`;
}
