/* ============================================================
   views-analysis.js — 심층 분석 / 밸류에이션 / 리스크 / 포트폴리오 / 체인
   ============================================================ */

import * as D from './data.js';
import * as C from './calc.js';
import * as P from './prompts.js';
import * as S from './store.js';
import { esc, chipGroup, promptBox, table, stat } from './ui.js';
import * as Q from './quotes.js';

/* ---------- 공통: 분석 대상 종목 편집기 ---------- */
export function pickEditor() {
  const st = S.get();
  const picks = st.picks || [];
  return `
  <div class="card">
    <h3 class="card-title">🎯 분석 대상 종목</h3>
    <p class="card-sub">실시간 시세를 입력하면 프롬프트에 <strong>시세 앵커</strong>로 박혀
      AI의 과거 학습값 사용을 차단합니다 — 함정 ④ 대응</p>

    <div class="btn-row" style="margin-bottom:6px">
      <input class="input" id="pick-name" placeholder="종목명 또는 코드 (예: SK하이닉스 / 000660)" style="flex:1;min-width:200px">
      <button class="btn btn-navy btn-sm" data-action="add-pick">+ 추가</button>
      <button class="btn btn-ghost btn-sm" data-action="search-quote">🔍 토스 검색</button>
    </div>
    <div id="quote-search" class="mb0"></div>

    <div class="quote-bar">
      <span class="quote-badge" id="proxy-badge" data-action="check-proxy" role="button"
            title="클릭하면 시세 프록시 연결을 확인합니다">⚪ 프록시 확인 중…</span>
      <button class="btn btn-gold btn-sm" data-action="refresh-quotes">🔄 시세 자동 조회</button>
      <span class="muted" id="quote-msg"></span>
    </div>

    ${picks.length ? `
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr>
          <th>종목</th><th>종목코드</th><th>현재가(원)</th><th>등락(원)</th><th>PER</th><th>PBR</th>
          <th>시총</th><th>52주 밴드</th><th></th>
        </tr></thead>
        <tbody>
          ${picks.map((p, i) => `
          <tr>
            <td class="name">${esc(p.name)}${p.source === 'toss' ? ' <span class="badge-pill bp-green" title="토스 자동 조회">자동</span>' : ''}</td>
            <td><input class="input mono" style="width:88px;padding:6px 9px" data-pick="${i}.code"
                 value="${esc(p.code ?? '')}" placeholder="6자리"></td>
            <td><input class="input" style="width:110px;padding:6px 9px" data-pick="${i}.price"
                 value="${esc(p.price ?? '')}" placeholder="숫자만"></td>
            <td><input class="input" style="width:92px;padding:6px 9px" data-pick="${i}.change"
                 value="${esc(p.change ?? '')}" placeholder="±숫자"></td>
            <td><input class="input" style="width:72px;padding:6px 9px" data-pick="${i}.per"
                 value="${esc(p.per ?? '')}" placeholder="배수"></td>
            <td><input class="input" style="width:72px;padding:6px 9px" data-pick="${i}.pbr"
                 value="${esc(p.pbr ?? '')}" placeholder="배수"></td>
            <td><input class="input" style="width:110px;padding:6px 9px" data-pick="${i}.cap"
                 value="${esc(p.cap ?? '')}" placeholder="예: 47,000억원"></td>
            <td><input class="input" style="width:150px;padding:6px 9px" data-pick="${i}.band"
                 value="${esc(p.band ?? '')}" placeholder="예: 최저~최고"></td>
            <td><button class="btn btn-ghost btn-sm" data-del-pick="${i}">삭제</button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div class="field mt mb0">
      <div class="field-label">시세 조회 시점 <span class="field-hint">자동 조회 시 자동으로 채워집니다</span></div>
      <input class="input" data-bind="asOf" value="${esc(st.asOf)}"
        placeholder="예: 2026.08.26 15:30 (KST)" style="max-width:320px">
    </div>
    ` : `<div class="alert alert-info"><span>ℹ️</span>
      <div>아직 종목이 없습니다. 위에서 직접 추가하거나, ② 교차 검증에서 합의 종목을 클릭해 담으세요.</div></div>`}
  </div>`;
}

/* ---------------- ③ 심층 분석 허브 ---------------- */
export function steps(activeStep) {
  const st = S.get();
  const names = S.pickNames();

  if (activeStep) return stepDetail(activeStep);

  return `
  <div class="page-eyebrow">③ 심층 분석</div>
  <h1 class="page-title">STEP 1~5 · 애널리스트 분석 사슬</h1>
  <p class="page-desc">WHAT → WHY → HOW → HOW MUCH → WHEN.
    질문의 순서가 곧 분석의 순서입니다. 순서를 지키면 낙관 편향이 끼어들 자리가 줄어듭니다.</p>

  ${pickEditor()}

  <div class="card">
    <h3 class="card-title">🔬 분석 단계 선택</h3>
    <p class="card-sub">${names.length ? `대상: <strong>${names.map(esc).join(', ')}</strong>` : '⚠️ 분석 대상 종목을 먼저 추가하세요'}</p>
    <div class="step-grid">
      ${D.STEPS.map(s => `
        <button class="step-card ${st.done[s.id] ? 'done' : ''}" data-route="steps/${s.id}">
          ${st.done[s.id] ? '<span class="badge">완료 ✓</span>' : `<span class="badge">${esc(s.n)}</span>`}
          <span class="emo">${s.icon}</span>
          <div class="t">${esc(s.title)}</div>
          <div class="d"><strong>${esc(s.q)}</strong> — ${esc(s.desc)}</div>
        </button>`).join('')}
    </div>
  </div>

  <div class="card-dark">
    <h3 class="card-title">💎 5가지 해자 매트릭스 (모닝스타 5분류)</h3>
    <p class="card-sub">STEP '질적 분석'에서 이 매트릭스를 채우게 됩니다</p>
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>해자</th><th>핵심 질문</th><th>강할 때 나타나는 증거</th></tr></thead>
        <tbody>
          ${D.MOATS.map(m => `<tr>
            <td class="name">${m.icon} ${esc(m.label)}</td>
            <td>${esc(m.q)}</td>
            <td class="muted">${esc({
              brand:'업종 평균 대비 높은 판가·마진, 재구매율',
              switch:'고객 이탈률 5% 미만, 장기 계약 비중',
              network:'사용자 증가 시 단위 비용 하락, 양면시장',
              cost:'업종 최저 원가, 규모의 경제·수직계열화',
              intan:'핵심 특허 다수, 규제 인허가 장벽'
            }[m.id])}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
  </div>

  <button class="btn btn-gold btn-lg btn-block" data-route="valuation">
    💰 다음 단계 — 밸류에이션 →
  </button>`;
}

function stepDetail(stepId) {
  const spec = D.STEPS.find(s => s.id === stepId);
  if (!spec) return steps(null);
  const st = S.get();
  const names = S.pickNames();
  const ctx = {
    names, horizon: st.analysis.horizon, risk: st.analysis.risk,
    quotes: quotesFor(st), asOf: st.asOf || '조회 시점 미입력'
  };

  return `
  <button class="btn btn-ghost btn-sm" data-route="steps">← 분석 단계로 돌아가기</button>
  <div class="page-eyebrow" style="margin-top:16px">${esc(spec.n)} · ${esc(spec.q)}</div>
  <h1 class="page-title">${spec.icon} ${esc(spec.title)}</h1>
  <p class="page-desc">${esc(spec.desc)}</p>

  ${names.length ? '' : `<div class="alert alert-bad"><span>⛔</span>
    <div>분석 대상 종목이 없습니다. <button class="btn btn-ghost btn-sm" data-route="steps">종목 추가하기</button></div></div>`}

  <div class="card">
    <h3 class="card-title">📌 대상 · 조건</h3>
    <div class="tickers">${names.length
      ? names.map(n => `<span class="tk">${esc(n)}</span>`).join('')
      : '<span class="muted">없음</span>'}</div>
    <div class="split">
      <div class="field mb0">
        <div class="field-label">투자 기간</div>
        ${chipGroup({ name: 'a-horizon', options: D.HORIZONS, value: st.analysis.horizon })}
      </div>
      <div class="field mb0">
        <div class="field-label">위험 성향</div>
        ${chipGroup({ name: 'a-risk', options: ['저위험', '중위험', '고위험'], value: st.analysis.risk })}
      </div>
    </div>
  </div>

  ${promptBox(`${spec.title} — RICE 프롬프트`, P.stepPrompt(stepId, ctx), 'p-step-' + stepId)}

  <div class="btn-row mt">
    <button class="btn btn-navy" data-action="mark-done" data-step="${esc(stepId)}">
      ${st.done[stepId] ? '✓ 완료 표시됨 (해제)' : '이 단계 완료로 표시'}
    </button>
    <button class="btn btn-ghost" data-route="steps">다른 단계 보기</button>
  </div>`;
}

function quotesFor(st) {
  return (st.picks || [])
    .filter(p => C.num(p.price) != null)
    .map(p => ({
      name: p.name, price: C.num(p.price), change: C.num(p.change),
      per: p.per || null, pbr: p.pbr || null, cap: p.cap || null, band: p.band || null
    }));
}

/* ---------------- ④ 밸류에이션 ---------------- */
export function valuation() {
  const st = S.get();
  const v = st.valuation;
  const rows = D.MULTIPLES.map(m => ({
    ...m,
    value: C.num(v.rows?.[m.id]?.value),
    weight: C.num(v.rows?.[m.id]?.weight) ?? m.w
  }));
  const rel = C.relativeValue(rows);
  const buy = C.withSafetyMargin(rel.fair, v.marginPct);
  const first = (st.picks || [])[0];
  const cur = C.num(first?.price);
  const up = C.upside(rel.fair, cur);

  return `
  <div class="page-eyebrow">④ 밸류에이션</div>
  <h1 class="page-title">지금 얼마짜리인가</h1>
  <p class="page-desc">좋은 회사와 좋은 주식은 다릅니다.
    <strong>하나의 지표만 보는 함정 ③</strong>을 막기 위해 여러 멀티플을 가중 종합합니다.</p>

  <div class="card">
    <div class="field">
      <div class="field-label">평가 방법 <span class="field-hint">MECE 3분류</span></div>
      ${chipGroup({ name: 'val-method', options: [
        { id: 'relative', label: '상대가치' }, { id: 'absolute', label: '절대가치' }, { id: 'both', label: '종합' }
      ], value: v.method })}
    </div>
    <div class="field mb0">
      <div class="field-label">안전마진 <span class="field-hint">그레이엄 원전 — 적정가의 2/3 이하 매수</span></div>
      ${chipGroup({ name: 'margin', options: D.SAFETY_MARGINS.map(m => ({ id: String(m), label: m + '%' })), value: String(v.marginPct) })}
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">🧮 멀티플별 적정주가 계산기</h3>
    <p class="card-sub">AI 답변에서 나온 멀티플별 적정주가를 입력하면 가중 종합가를 계산합니다.
      값을 비워두면 그 지표는 가중에서 제외됩니다.</p>
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>지표</th><th>산식</th><th>적합 대상</th><th>적정주가(원)</th><th>가중치(%)</th></tr></thead>
        <tbody>
          ${D.MULTIPLES.map(m => `
          <tr>
            <td class="name">${esc(m.label)}</td>
            <td class="muted">${esc(m.formula)}</td>
            <td class="muted">${esc(m.use)}</td>
            <td><input class="input" style="width:120px;padding:6px 9px" data-val="${m.id}.value"
                 value="${esc(v.rows?.[m.id]?.value ?? '')}" placeholder="예: 420000"></td>
            <td><input class="input" style="width:74px;padding:6px 9px" data-val="${m.id}.weight"
                 value="${esc(v.rows?.[m.id]?.weight ?? m.w)}"></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <div class="stat-row">
      ${stat('가중 종합 적정가', rel.fair != null ? C.won(rel.fair) : '—', `가중치 합 ${rel.totalWeight}%`)}
      ${stat(`안전마진 ${v.marginPct}% 적용 매수가`, buy != null ? C.won(buy) : '—', '이 가격 이하에서만 매수')}
      ${stat('현재가', cur != null ? C.won(cur) : '—', first?.name || '종목 미선택')}
      ${stat('상승여력', up != null ? C.pct(up) : '—', up != null ? (up > 0 ? '적정가까지' : '이미 적정가 초과') : '현재가 입력 필요')}
    </div>

    ${rel.fair != null && cur != null ? `
      <div class="alert ${cur <= buy ? 'alert-ok' : (cur <= rel.fair ? 'alert-warn' : 'alert-bad')}">
        <span>${cur <= buy ? '✅' : (cur <= rel.fair ? '⚠️' : '⛔')}</span>
        <div>${cur <= buy
          ? `현재가가 안전마진 매수가(${C.won(buy)}) <strong>이하</strong>입니다. 매수 검토 구간입니다.`
          : (cur <= rel.fair
            ? `현재가가 적정가 이하지만 안전마진 매수가(${C.won(buy)})는 넘습니다. <strong>기다리거나 분할 진입</strong>하세요.`
            : `현재가가 가중 적정가(${C.won(rel.fair)})를 <strong>초과</strong>합니다. 좋은 회사여도 지금은 비쌉니다.`)}
        </div>
      </div>` : ''}
  </div>

  <div class="card">
    <h3 class="card-title">📐 PEG · 듀퐁 보조 계산기</h3>
    <div class="split">
      <div>
        <div class="field-label">PEG = PER ÷ EPS 성장률(%)</div>
        <div class="btn-row" style="margin-bottom:8px">
          <input class="input" id="peg-per" placeholder="PER (예: 20)" style="width:130px">
          <input class="input" id="peg-g" placeholder="성장률% (예: 25)" style="width:150px">
          <button class="btn btn-navy btn-sm" data-action="calc-peg">계산</button>
        </div>
        <div id="peg-out" class="muted">PEG &lt; 1 이면 피터 린치 기준 매수 구간</div>
      </div>
      <div>
        <div class="field-label">듀퐁 3분해 — ROE = 순이익률 × 자산회전율 × 레버리지</div>
        <div class="btn-row" style="margin-bottom:8px">
          <input class="input" id="du-m" placeholder="순이익률%" style="width:110px">
          <input class="input" id="du-t" placeholder="자산회전율" style="width:110px">
          <input class="input" id="du-l" placeholder="레버리지" style="width:105px">
          <button class="btn btn-navy btn-sm" data-action="calc-dupont">계산</button>
        </div>
        <div id="du-out" class="muted">ROE가 같아도 그 출처가 마진인지 부채인지에 따라 질이 다릅니다</div>
      </div>
    </div>
  </div>

  ${promptBox('STEP 4 · 밸류에이션 RICE 프롬프트',
    P.stepPrompt('val', { names: S.pickNames(), horizon: st.analysis.horizon, risk: st.analysis.risk,
      quotes: quotesFor(st), asOf: st.asOf || '조회 시점 미입력' }), 'p-val')}

  <button class="btn btn-gold btn-lg btn-block mt" data-route="risk">
    🛡 다음 단계 — 리스크 분석 →
  </button>`;
}

/* ---------------- ⑤ 리스크 · 시나리오 ---------------- */
export function risk() {
  const st = S.get();
  const r = st.risk;
  const picks = (st.picks || []).filter(p => C.num(p.price) != null);
  const rec = C.recoveryNeeded(-50);

  const guideRows = picks.map(p => {
    const cur = C.num(p.price);
    const g = C.priceGuide(cur, r);
    const t = r.targets?.[p.name] || {};
    const scenarios = [
      { id: 'bull', prob: r.probs.bull, target: C.num(t.bull) },
      { id: 'base', prob: r.probs.base, target: C.num(t.base) },
      { id: 'bear', prob: r.probs.bear, target: C.num(t.bear) }
    ];
    const er = C.expectedReturn(scenarios, cur);
    const rv = C.rrVerdict(g.riskReward);
    return [
      `<span class="name">${esc(p.name)}</span>`,
      `<span class="num">${C.won(cur)}</span>`,
      `<span class="num neg">${C.won(g.stopPrice)}</span>`,
      `<span class="num pos">${C.won(g.tp1Price)}</span>`,
      `<span class="num pos">${C.won(g.tp2Price)}</span>`,
      `<span class="num">1 : ${g.riskReward?.toFixed(1) ?? '—'}</span>`,
      `<span class="num ${er == null ? '' : (er >= 0 ? 'pos' : 'neg')}">${er == null ? '목표가 입력' : C.pct(er)}</span>`,
      `<span class="badge-pill ${rv.cls === 'pos' ? 'bp-green' : rv.cls === 'neg' ? 'bp-red' : 'bp-gold'}">${esc(rv.label)}</span>`
    ];
  });

  return `
  <div class="page-eyebrow">⑤ 리스크 분석</div>
  <h1 class="page-title">시나리오 · 손익관리</h1>
  <p class="page-desc">수익보다 손실 회피가 먼저입니다.
    <strong>-50%는 -50%가 아니라, +${rec.toFixed(0)}%가 나와야 원금 회복</strong>이라는 뜻입니다.</p>

  <div class="alert alert-bad">
    <span>🚫</span>
    <div><strong>함정 ⑤ 차단:</strong> 손절가 없이 매수 → Bull/Base/Bear + 손절가를 <strong>사기 전에</strong> 먼저 정합니다.
    아래 표가 비어 있으면 아직 매수할 준비가 안 된 것입니다.</div>
  </div>

  <div class="card">
    <h3 class="card-title">⚙️ 손익관리 기준</h3>
    <p class="card-sub">기계적으로 지킬 수 있는 숫자로 미리 고정합니다</p>
    <div class="split-3">
      <div class="field mb0">
        <div class="field-label">손절 기준 (-%)</div>
        ${chipGroup({ name: 'stop', options: [10, 15, 20, 25].map(v => ({ id: String(v), label: '-' + v + '%' })), value: String(r.stop) })}
      </div>
      <div class="field mb0">
        <div class="field-label">1차 익절 (+%)</div>
        ${chipGroup({ name: 'tp1', options: [10, 15, 20, 25].map(v => ({ id: String(v), label: '+' + v + '%' })), value: String(r.tp1) })}
      </div>
      <div class="field mb0">
        <div class="field-label">2차 익절 (+%)</div>
        ${chipGroup({ name: 'tp2', options: [30, 40, 50, 70].map(v => ({ id: String(v), label: '+' + v + '%' })), value: String(r.tp2) })}
      </div>
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">🎲 시나리오별 목표가</h3>
    <p class="card-sub">확률 합계 ${r.probs.bull + r.probs.base + r.probs.bear}% ·
      ${D.SCENARIO_DEFAULTS.map(s => `<span class="${s.cls}">${esc(s.label)} ${r.probs[s.id]}%</span>`).join(' / ')}</p>

    <div class="split-3" style="margin-bottom:16px">
      ${D.SCENARIO_DEFAULTS.map(s => `
        <div class="field mb0">
          <div class="field-label"><span class="${s.cls}">${esc(s.label)}</span> 확률(%)</div>
          <input class="input" data-prob="${s.id}" value="${r.probs[s.id]}" style="max-width:110px">
          <div class="muted" style="margin-top:5px">${esc(s.note)}</div>
        </div>`).join('')}
    </div>

    ${picks.length ? `
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>종목</th><th>현재가</th>
          <th class="sc-bull">Bull 목표가</th><th class="sc-base">Base 목표가</th><th class="sc-bear">Bear 목표가</th></tr></thead>
        <tbody>
          ${picks.map(p => `<tr>
            <td class="name">${esc(p.name)}</td>
            <td class="num">${C.won(C.num(p.price))}</td>
            ${['bull', 'base', 'bear'].map(k => `
              <td><input class="input" style="width:125px;padding:6px 9px"
                data-target="${esc(p.name)}.${k}"
                value="${esc(st.risk.targets?.[p.name]?.[k] ?? '')}" placeholder="목표가"></td>`).join('')}
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : `<div class="alert alert-info"><span>ℹ️</span>
      <div>현재가가 입력된 종목이 없습니다. ③ 심층 분석에서 종목과 현재가를 먼저 입력하세요.</div></div>`}
  </div>

  ${guideRows.length ? `
  <div class="card">
    <h3 class="card-title">🧭 결정 가이드 — 종목별 매수 · 손절 · 익절</h3>
    <p class="card-sub">"한 달 내 반토막 나도 버틸 수 있는가"를 사기 전에 결정하세요</p>
    ${table(
      ['종목', '현재가', `손절가(-${r.stop}%)`, `1차 익절(+${r.tp1}%)`, `2차 익절(+${r.tp2}%)`, 'Risk/Reward', '기대수익률', '판정'],
      guideRows)}
    <div class="alert alert-info mt">
      <span>📏</span>
      <div><strong>Risk/Reward 1:2 이상</strong>이면 투자 고려 — 1회 손실을 2회 수익으로 덮을 수 있다는 뜻입니다.
      1:1 미만이면 기대수익보다 감수 위험이 큽니다.</div>
    </div>
  </div>` : ''}

  ${promptBox('리스크 분석 RICE 프롬프트 (숨은 리스크 3개 + 시나리오)',
    P.riskPrompt({ names: S.pickNames(), quotes: quotesFor(st), asOf: st.asOf || '조회 시점 미입력',
      probs: r.probs, stop: r.stop, tp1: r.tp1, tp2: r.tp2 }), 'p-risk')}

  <button class="btn btn-gold btn-lg btn-block mt" data-route="portfolio">
    📦 다음 단계 — 포트폴리오 분석 →
  </button>`;
}

/* ---------------- ⑥ 포트폴리오 차등배분 ---------------- */
export function portfolio() {
  const st = S.get();
  const capital = C.num(st.portfolio.capital) || 0;
  const picks = st.picks || [];

  const holdings = picks.map(p => {
    const sc = st.scores?.[p.name] || {};
    const t = C.totalScore(sc, D.SCORE_WEIGHTS);
    const cur = C.num(p.price);
    const tg = st.risk.targets?.[p.name] || {};
    const er = C.expectedReturn([
      { prob: st.risk.probs.bull, target: C.num(tg.bull) },
      { prob: st.risk.probs.base, target: C.num(tg.base) },
      { prob: st.risk.probs.bear, target: C.num(tg.bear) }
    ], cur);
    return { name: p.name, price: cur, scorePct: t.pct, scoreSum: t.sum, expected: er };
  });

  const scored = holdings.filter(h => h.scoreSum > 0);
  const alloc = scored.length ? C.allocate(scored, D.ALLOC_BANDS, capital) : null;
  const stats = alloc ? C.portfolioStats(alloc.rows, alloc.cashWeight) : null;
  const bandColor = { core: '#1e3550', sub: '#2a4463', watch: '#4a6382' };

  return `
  <div class="page-eyebrow">⑥ 포트폴리오</div>
  <h1 class="page-title">차등배분 — Core · Satellite</h1>
  <p class="page-desc">균등배분은 생각을 멈춘 배분입니다.
    <strong>투자점수가 높은 종목에 더 싣는</strong> 것이 확신도를 자본에 반영하는 방법입니다.</p>

  <div class="card">
    <div class="field mb0">
      <div class="field-label">총 투자금 (원)</div>
      <input class="input" data-bind="portfolio.capital" value="${esc(st.portfolio.capital)}"
        style="max-width:240px" placeholder="10000000">
      <div class="muted" style="margin-top:6px">${C.won(capital)}</div>
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">🏅 종목별 투자점수 (총 100점)</h3>
    <p class="card-sub">${D.SCORE_WEIGHTS.map(w => `${w.label} ${w.max}점`).join(' + ')} —
      AI 분석 결과를 근거로 직접 채점하세요</p>
    ${picks.length ? `
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>종목</th>
          ${D.SCORE_WEIGHTS.map(w => `<th>${esc(w.label)} /${w.max}</th>`).join('')}
          <th>총점</th><th>등급</th></tr></thead>
        <tbody>
          ${holdings.map(h => {
            const g = C.scoreGrade(h.scorePct);
            return `<tr>
              <td class="name">${esc(h.name)}</td>
              ${D.SCORE_WEIGHTS.map(w => `
                <td><input class="input" style="width:66px;padding:6px 9px"
                  data-score="${esc(h.name)}.${w.id}" max="${w.max}"
                  value="${esc(st.scores?.[h.name]?.[w.id] ?? '')}" placeholder="0"></td>`).join('')}
              <td class="num"><strong>${h.scoreSum} / 100</strong></td>
              <td><span class="badge-pill ${g.cls}">${esc(g.label)}</span></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>` : `<div class="alert alert-info"><span>ℹ️</span><div>분석 대상 종목이 없습니다.</div></div>`}
  </div>

  ${alloc ? `
  <div class="card">
    <h3 class="card-title">📦 차등배분 결과 (총 ${C.won(capital)})</h3>
    <p class="card-sub">핵심 Core 35~40% · 주력 Sub 20~25% · 관망 Watch 10~15% — 잔여분은 현금</p>

    <div class="wbar">
      ${alloc.rows.map(r => `<span style="width:${r.weight}%;background:${bandColor[r.band.id]}"
        title="${esc(r.name)} ${r.weight.toFixed(1)}%">${r.weight >= 8 ? esc(r.name) : ''}</span>`).join('')}
      ${alloc.cashWeight > 0.5 ? `<span style="width:${alloc.cashWeight}%;background:#b9a980;color:#2b2311">
        ${alloc.cashWeight >= 8 ? '현금' : ''}</span>` : ''}
    </div>

    ${table(['종목', '비중', '금액', '매수 주식수', '역할', '비중 근거'],
      alloc.rows.map(r => [
        `<span class="name">${esc(r.name)}</span>`,
        `<span class="num"><strong>${r.weight.toFixed(1)}%</strong></span>`,
        `<span class="num">${C.won(r.amount)}</span>`,
        `<span class="num">${r.shares != null ? r.shares.toLocaleString('ko-KR') + '주' : '현재가 필요'}</span>`,
        `${r.band.icon} ${esc(r.band.label)}`,
        `<span class="muted">투자점수 ${r.scoreSum}/100 · ${esc(r.band.label)} 밴드(${r.band.min}~${r.band.max}%)</span>`
      ]).concat(alloc.cashWeight > 0.5 ? [[
        '<span class="name">현금</span>',
        `<span class="num"><strong>${alloc.cashWeight.toFixed(1)}%</strong></span>`,
        `<span class="num">${C.won(alloc.cash)}</span>`,
        '—', '💵 현금 버퍼',
        '<span class="muted">시장 급락 시 추가 매수 여력</span>'
      ]] : []))}

    ${stats ? `
    <h3 class="card-title mt">📊 포트폴리오 종합 성과</h3>
    ${table(['지표', '값', '설명'], [
      ['기대수익률', `<span class="num ${stats.expected == null ? '' : stats.expected >= 0 ? 'pos' : 'neg'}">${stats.expected == null ? '시나리오 목표가 입력 필요' : C.pct(stats.expected)}</span>`, '확률가중 평균 (현금 비중 반영)'],
      ['VaR 99% (연)', `<span class="num neg">${stats.var99 == null ? '변동성 입력 필요' : C.pct(stats.var99)}</span>`, '99% 신뢰구간 최대 예상 손실'],
      ['보유 종목 수', `<span class="num">${stats.names}개</span>`, '3~5개가 관리 가능한 범위'],
      ['현금 비중', `<span class="num">${alloc.cashWeight.toFixed(1)}%</span>`, '시장 상황 대응 여력']
    ])}` : ''}

    <div class="alert alert-warn mt">
      <span>🔁</span>
      <div><strong>리밸런싱 트리거:</strong> ① 특정 종목 비중이 밴드 상한을 5%p 초과 ②
      투자점수 재채점 시 등급이 한 단계 하락 ③ 손절가 도달 —
      셋 중 하나라도 켜지면 이 화면으로 돌아와 다시 배분하세요.</div>
    </div>
  </div>` : `<div class="alert alert-info"><span>ℹ️</span>
    <div>투자점수를 하나 이상 입력하면 차등배분이 계산됩니다.</div></div>`}

  ${promptBox('포트폴리오 차등배분 RICE 프롬프트',
    P.portfolioPrompt({ names: S.pickNames(), capital, quotes: quotesFor(st),
      asOf: st.asOf || '조회 시점 미입력', stop: st.risk.stop, tp1: st.risk.tp1, tp2: st.risk.tp2 }), 'p-port')}

  <button class="btn btn-navy btn-lg btn-block mt" data-route="chain">
    🔗 마지막 단계 — Chain of Questions →
  </button>`;
}

/* ---------------- Chain of Questions ---------------- */
export function chain() {
  const st = S.get();
  const c = st.chain;

  return `
  <div class="page-eyebrow">질문 사슬</div>
  <h1 class="page-title">Chain of Questions · 3단계</h1>
  <p class="page-desc">
    한 번 묻고 끝내면 AI는 좋은 이야기만 합니다.
    <strong>판정 → 반증 → 킬 스위치</strong> 순으로 사슬을 걸어야 답이 검증 가능해집니다.
  </p>

  <div class="card">
    <div class="field mb0">
      <div class="field-label">분석 대상 <span class="field-hint">종목명 또는 시장</span></div>
      <input class="input" data-bind="chain.subject" value="${esc(c.subject)}"
        placeholder="예: SK하이닉스 / 코스피 / 반도체 섹터" style="max-width:420px">
    </div>
  </div>

  ${D.CHAIN.map(step => `
    <div class="card">
      <h3 class="card-title">
        <span class="badge-pill bp-navy">${step.n}단계</span> ${esc(step.title)}
      </h3>
      <p class="card-sub">${esc(step.goal)}</p>
      ${step.n === 2 ? `
        <div class="field">
          <div class="field-label">1단계에서 AI가 내린 판정 <span class="field-hint">붙여넣으면 2단계 프롬프트에 포함됩니다</span></div>
          <textarea class="textarea" data-bind="chain.prevVerdict" style="min-height:80px"
            placeholder="예: 국면 = 확장 후반, 확신도 72/100">${esc(c.prevVerdict)}</textarea>
        </div>` : ''}
      ${promptBox(`${step.n}단계 프롬프트`, P.chainPrompt(step.n, c), 'p-chain-' + step.n)}
    </div>`).join('')}

  <div class="card-dark">
    <h3 class="card-title">🔴 킬 스위치 표 — 3단계에서 받게 될 결과물</h3>
    <p class="card-sub">감으로 버티지 않기 위한, 나만의 기계적 행동 지침서</p>
    ${table(['감시 지표', '어디서(사이트)', '확인 주기', '이 신호가 켜지면(행동 지침)'], [
      ['<span class="muted">예: 반도체 재고순환지표</span>', '<span class="muted">통계청 KOSIS</span>', '<span class="muted">월 1회</span>', '<span class="muted">3개월 연속 상승 시 비중 절반 축소</span>'],
      ['<span class="muted">예: 외국인 순매수 누적</span>', '<span class="muted">KRX 정보데이터시스템</span>', '<span class="muted">주 1회</span>', '<span class="muted">4주 연속 순매도 시 신규 매수 중단</span>'],
      ['<span class="muted">예: 기준금리 · 국고채 10년</span>', '<span class="muted">한국은행 ECOS</span>', '<span class="muted">월 1회</span>', '<span class="muted">50bp 이상 급등 시 성장주 비중 축소</span>']
    ])}
    <div class="alert alert-warn mt mb0">
      <span>🔑</span>
      <div>위는 <strong>형식 예시</strong>입니다. 실제 지표·임계값은 3단계 프롬프트를 AI에 넣어
      당신 종목에 맞게 받으세요. 3개 중 <strong>2개가 켜지면 전량 청산</strong> 같은 규칙까지 미리 정해두는 것이 핵심입니다.</div>
    </div>
  </div>

  <div class="card">
    <h3 class="card-title">🛡 할루시네이션 방지 신뢰성 룰</h3>
    <p class="card-sub">지니가 생성하는 <strong>모든</strong> 프롬프트 말미에 자동으로 붙습니다 — 함정 ④ 차단</p>
    <ol style="font-size:13px;color:var(--ink-2);line-height:1.9;padding-left:20px;margin:0">
      ${D.GUARD_RULES.map(r => `<li>${esc(r)}</li>`).join('')}
    </ol>
  </div>`;
}
