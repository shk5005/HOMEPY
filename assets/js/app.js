/* ============================================================
   app.js — 라우터 + 이벤트 컨트롤러
   ============================================================ */

import * as D from './data.js';
import * as C from './calc.js';
import * as S from './store.js';
import { esc, qs, qsa, bindChips, bindPromptBox, toast } from './ui.js';
import * as VC from './views-core.js';
import * as VA from './views-analysis.js';

const NAV = [
  { group: '파이프라인', items: [
    { r: 'dashboard', ico: '🏠', label: '대시보드' },
    { r: 'discovery', ico: '🔎', label: '종목 발굴',   step: '①' },
    { r: 'cross',     ico: '⚖️', label: '교차 검증',   step: '②' },
    { r: 'steps',     ico: '🔬', label: '심층 분석',   step: '③' },
    { r: 'valuation', ico: '💰', label: '밸류에이션',  step: '④' },
    { r: 'risk',      ico: '🛡', label: '리스크 분석', step: '⑤' },
    { r: 'portfolio', ico: '📦', label: '포트폴리오',  step: '⑥' }
  ]},
  { group: '검증 도구', items: [
    { r: 'chain', ico: '🔗', label: 'Chain of Questions' }
  ]}
];

const DONE_KEY = { discovery: 'discovery', cross: 'cross', valuation: 'val',
                   risk: 'risk', portfolio: 'portfolio' };

function renderNav(route) {
  const st = S.get();
  const base = route.split('/')[0];
  return NAV.map(g => `
    <div class="nav-group-label">${esc(g.group)}</div>
    ${g.items.map(i => {
      const done = st.done[DONE_KEY[i.r] || i.r];
      return `<button class="nav-item ${base === i.r ? 'active' : ''} ${done ? 'done' : ''}" data-route="${i.r}">
        <span class="ico">${i.ico}</span><span>${esc(i.label)}</span>
        ${i.step ? `<span class="nav-step">${i.step}</span>` : ''}
      </button>`;
    }).join('')}`).join('');
}

function viewFor(route) {
  const [base, sub] = route.split('/');
  switch (base) {
    case 'discovery': return VC.discovery();
    case 'cross':     return VC.cross();
    case 'steps':     return VA.steps(sub || null);
    case 'valuation': return VA.valuation();
    case 'risk':      return VA.risk();
    case 'portfolio': return VA.portfolio();
    case 'chain':     return VA.chain();
    default:          return VC.dashboard();
  }
}

let current = 'dashboard';

export function go(route, { push = true } = {}) {
  current = route;
  if (push) location.hash = '#' + route;
  qs('#nav').innerHTML = renderNav(route);
  const main = qs('#main');
  main.innerHTML = viewFor(route);
  main.scrollIntoView({ block: 'start' });
  window.scrollTo(0, 0);

  // 라우트 진입 후 지연 렌더 (교차검증 결과 등 재계산이 필요한 영역)
  if (route === 'cross') updateCrossCounts();
}

function rerender() { go(current, { push: false }); }

/* 계산 결과 반영을 위한 재렌더는 포커스 이동이 끝난 뒤로 미룬다.
   동기 재렌더는 사용자가 막 이동한 입력칸을 DOM에서 제거해 입력을 잃게 만든다. */
const FOCUS_KEYS = ['pick', 'val', 'target', 'score', 'prob', 'bind'];

function focusSignature() {
  const el = document.activeElement;
  if (!el || !el.dataset) return null;
  for (const k of FOCUS_KEYS) {
    if (el.dataset[k] != null) {
      return { attr: `data-${k}`, value: el.dataset[k], caret: el.selectionStart };
    }
  }
  return null;
}

function restoreFocus(sig) {
  if (!sig) return;
  const next = document.querySelector(`[${sig.attr}="${CSS.escape(sig.value)}"]`);
  if (!next) return;
  next.focus();
  if (sig.caret != null) {
    try { next.setSelectionRange(sig.caret, sig.caret); } catch { /* number 타입 등은 미지원 */ }
  }
}

let rerenderTimer;
function scheduleRerender() {
  clearTimeout(rerenderTimer);
  // 0ms 지연: change → focus 순서가 끝난 뒤 실행되어, 새로 포커스된 칸을 그대로 되살린다
  rerenderTimer = setTimeout(() => {
    const sig = focusSignature();
    rerender();
    restoreFocus(sig);
  }, 0);
}

/* ---------- 입력 바인딩 ---------- */

function setPath(path, value) {
  const keys = path.split('.');
  const patch = {};
  let node = patch;
  keys.forEach((k, i) => {
    if (i === keys.length - 1) node[k] = value;
    else { node[k] = {}; node = node[k]; }
  });
  S.set(patch, { silent: true });
}

function updateCrossCounts() {
  for (const p of D.AI_PANELS) {
    const el = qs(`[data-count="${p.id}"]`);
    if (!el) continue;
    const text = S.get().cross[p.id] || '';
    const n = C.extractTickers(text).length;
    el.textContent = text.trim().length > 40
      ? `종목 후보 ${n}개 추출됨`
      : '답변을 붙여넣으세요';
  }
}

/* ---------- 이벤트 위임 ---------- */

function bindGlobal() {
  const root = document.body;

  // 라우팅
  root.addEventListener('click', e => {
    const nav = e.target.closest('[data-route]');
    if (nav) { e.preventDefault(); go(nav.dataset.route); }
  });

  // 텍스트/숫자 입력 → 상태 (재렌더 없이)
  root.addEventListener('input', e => {
    const el = e.target;

    if (el.dataset.bind) {
      let v = el.value;
      if (el.dataset.bind === 'discovery.exclusions') v = v.split('\n').map(s => s.trim()).filter(Boolean);
      setPath(el.dataset.bind, v);
      if (el.dataset.bind.startsWith('cross.')) updateCrossCounts();
      return;
    }

    // 종목 시세 필드: data-pick="0.price"
    if (el.dataset.pick) {
      const [idx, key] = el.dataset.pick.split('.');
      const picks = [...S.get().picks];
      picks[+idx] = { ...picks[+idx], [key]: el.value };
      S.replace('picks', picks);
      return;
    }

    // 밸류에이션: data-val="per.value"
    if (el.dataset.val) {
      const [id, key] = el.dataset.val.split('.');
      const rows = { ...(S.get().valuation.rows || {}) };
      rows[id] = { ...(rows[id] || {}), [key]: el.value };
      S.replace('valuation.rows', rows);
      return;
    }

    // 시나리오 목표가: data-target="종목명.bull"
    if (el.dataset.target) {
      const i = el.dataset.target.lastIndexOf('.');
      const name = el.dataset.target.slice(0, i);
      const key = el.dataset.target.slice(i + 1);
      const t = { ...(S.get().risk.targets || {}) };
      t[name] = { ...(t[name] || {}), [key]: el.value };
      S.replace('risk.targets', t);
      return;
    }

    // 확률: data-prob="bull"
    if (el.dataset.prob) {
      setPath('risk.probs.' + el.dataset.prob, C.num(el.value) ?? 0);
      return;
    }

    // 투자점수: data-score="종목명.growth"
    if (el.dataset.score) {
      const i = el.dataset.score.lastIndexOf('.');
      const name = el.dataset.score.slice(0, i);
      const key = el.dataset.score.slice(i + 1);
      const sc = { ...(S.get().scores || {}) };
      sc[name] = { ...(sc[name] || {}), [key]: el.value };
      S.replace('scores', sc);
    }
  });

  // 계산 결과 즉시 반영이 필요한 필드는 blur 시 재렌더
  root.addEventListener('change', e => {
    const el = e.target;
    const affectsCalc =
      el.dataset.val || el.dataset.target || el.dataset.prob || el.dataset.score ||
      el.dataset.pick?.endsWith('.price') ||
      el.dataset.bind === 'portfolio.capital';
    if (affectsCalc) scheduleRerender();
  });

  // 칩 선택
  bindChips(root, (name, value) => {
    const map = {
      sectors:  () => S.replace('discovery.sectors', value),
      style:    () => S.set({ discovery: { style: value } }),
      horizon:  () => S.set({ discovery: { horizon: value } }),
      target:   () => S.set({ discovery: { target: +value } }),
      count:    () => S.set({ discovery: { count: +value } }),
      risk:     () => S.set({ discovery: { risk: value } }),
      market:   () => S.set({ discovery: { market: value } }),
      'a-horizon': () => S.set({ analysis: { horizon: value } }),
      'a-risk':    () => S.set({ analysis: { risk: value } }),
      'val-method': () => S.set({ valuation: { method: value } }),
      margin:   () => S.set({ valuation: { marginPct: +value } }),
      stop:     () => S.set({ risk: { stop: +value } }),
      tp1:      () => S.set({ risk: { tp1: +value } }),
      tp2:      () => S.set({ risk: { tp2: +value } })
    };
    (map[name] || (() => {}))();
    // 칩 변경은 계산에 즉시 영향 → 재렌더 (섹터 다중선택은 제외해 클릭 흐름 유지)
    if (name !== 'sectors') rerender();
  });

  // 액션 버튼
  root.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (btn) return handleAction(btn.dataset.action, btn);

    const add = e.target.closest('[data-add-pick]');
    if (add) return addPick(add.dataset.addPick);

    const del = e.target.closest('[data-del-pick]');
    if (del) {
      const picks = [...S.get().picks];
      const removed = picks.splice(+del.dataset.delPick, 1)[0];
      S.replace('picks', picks);
      toast(`${removed?.name ?? '종목'} 삭제됨`);
      rerender();
    }
  });

  bindPromptBox(root);
}

function addPick(name) {
  const clean = String(name || '').trim();
  if (!clean) return toast('종목명을 입력하세요');
  const picks = [...S.get().picks];
  if (picks.some(p => p.name.replace(/\s/g, '') === clean.replace(/\s/g, ''))) {
    return toast(`${clean} 은(는) 이미 담겨 있습니다`);
  }
  if (picks.length >= 10) return toast('최대 10종목까지 담을 수 있습니다');
  picks.push({ name: clean, price: '', change: '', per: '', pbr: '', cap: '', band: '' });
  S.replace('picks', picks);
  toast(`${clean} 추가됨 (총 ${picks.length}종목)`);
  // 교차검증 화면에서는 전체 재렌더 시 결과 패널이 사라지므로 해당 패널만 갱신한다
  if (current === 'cross') {
    const out = qs('#cross-out');
    if (out) { out.innerHTML = VC.crossResultHTML(); return; }
  }
  rerender();
}

function handleAction(action, btn) {
  switch (action) {
    case 'gen-discovery':
      qs('#discovery-out').innerHTML = VC.discoveryPromptHTML();
      S.markDone('discovery');
      qs('#discovery-out').scrollIntoView({ behavior: 'smooth', block: 'start' });
      break;

    case 'run-cross': {
      qs('#cross-out').innerHTML = VC.crossResultHTML();
      const filled = Object.values(S.get().cross).filter(t => t?.trim().length > 40).length;
      if (filled >= 2) S.markDone('cross');
      qs('#cross-out').scrollIntoView({ behavior: 'smooth', block: 'start' });
      break;
    }

    case 'add-pick':
      addPick(qs('#pick-name')?.value);
      break;

    case 'mark-done': {
      const step = btn.dataset.step;
      S.markDone(step, !S.get().done[step]);
      rerender();
      break;
    }

    case 'calc-peg': {
      const per = C.num(qs('#peg-per')?.value);
      const g   = C.num(qs('#peg-g')?.value);
      const v   = C.peg(per, g);
      const vd  = C.pegVerdict(v);
      qs('#peg-out').innerHTML = v == null
        ? '<span class="muted">PER과 성장률을 모두 입력하세요</span>'
        : `PEG = <strong class="mono">${v.toFixed(2)}</strong> — <span class="${vd.cls}">${esc(vd.label)}</span>`;
      break;
    }

    case 'calc-dupont': {
      const m = C.num(qs('#du-m')?.value);
      const t = C.num(qs('#du-t')?.value);
      const l = C.num(qs('#du-l')?.value);
      const roe = C.dupont({ netMargin: m, assetTurnover: t, leverage: l });
      qs('#du-out').innerHTML = roe == null
        ? '<span class="muted">세 값을 모두 입력하세요</span>'
        : `ROE = <strong class="mono">${roe.toFixed(1)}%</strong>
           <span class="muted">(${m}% × ${t} × ${l})</span> —
           ${l >= 3 ? '<span class="neg">레버리지 의존도가 높습니다</span>'
                    : '<span class="pos">레버리지 부담이 크지 않습니다</span>'}`;
      break;
    }

    case 'reset':
      if (confirm('저장된 모든 입력(종목·시세·점수·AI 답변)을 삭제하고 초기화할까요?')) {
        S.reset();
        toast('초기화되었습니다');
        go('dashboard');
      }
      break;
  }
}

/* ---------- 부팅 ---------- */
S.load();
bindGlobal();
window.addEventListener('hashchange', () => {
  const r = location.hash.replace(/^#/, '') || 'dashboard';
  if (r !== current) go(r, { push: false });
});
go(location.hash.replace(/^#/, '') || 'dashboard', { push: false });
