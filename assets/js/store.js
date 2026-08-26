/* ============================================================
   store.js — 상태 관리 + localStorage 영속화
   ============================================================ */

const KEY = 'genie.state.v1';

const DEFAULT = {
  discovery: {
    sectors: ['AI', '반도체'],
    style: 'growth',
    horizon: '6개월',
    target: 30,
    count: 5,
    market: '한국 코스피 200',
    risk: '중위험',
    filter: '',
    focus: '',
    exclusions: ['최근 2년 연속 적자 기업', '감사의견 비적정 기업', '시가총액 1,000억 미만']
  },
  cross: { gpt: '', claude: '', plx: '' },
  picks: [],                 // [{ name, price, per, pbr, cap, band, change }]
  asOf: '',
  analysis: { horizon: '6개월', risk: '중위험' },
  valuation: {
    marginPct: 20,
    method: 'relative',
    rows: {}                 // { per:{value,weight}, ... }
  },
  risk: {
    stop: 20, tp1: 15, tp2: 30,
    probs: { bull: 30, base: 50, bear: 20 },
    targets: {}              // { '종목명': { bull, base, bear } }
  },
  scores: {},                // { '종목명': { growth, moat, val, mom } }
  portfolio: { capital: 10000000 },
  chain: { subject: '', prevVerdict: '' },
  done: {}                   // { stepId: true }
};

function deepMerge(base, patch) {
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) return patch;
  const out = Array.isArray(base) ? [...base] : { ...base };
  for (const k of Object.keys(patch)) {
    out[k] = (k in out && out[k] && typeof out[k] === 'object' && !Array.isArray(out[k]))
      ? deepMerge(out[k], patch[k])
      : patch[k];
  }
  return out;
}

const clone = o => JSON.parse(JSON.stringify(o));

let state = clone(DEFAULT);
const listeners = new Set();

export function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) state = deepMerge(clone(DEFAULT), JSON.parse(raw));
  } catch { /* 저장소 접근 불가(프라이빗 모드 등) — 기본값으로 진행 */ }
  return state;
}

export function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); }
  catch { /* 용량 초과·차단 — 앱은 메모리 상태로 계속 동작 */ }
}

export const get = () => state;

export function set(patch, { silent = false } = {}) {
  state = deepMerge(state, patch);
  save();
  if (!silent) listeners.forEach(fn => fn(state));
  return state;
}

/** 배열/맵 전체 교체가 필요할 때 (deepMerge 우회) */
export function replace(path, value) {
  const keys = path.split('.');
  let node = state;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!node[keys[i]] || typeof node[keys[i]] !== 'object') node[keys[i]] = {};
    node = node[keys[i]];
  }
  node[keys[keys.length - 1]] = value;
  save();
  listeners.forEach(fn => fn(state));
  return state;
}

export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function reset() {
  state = clone(DEFAULT);
  save();
  listeners.forEach(fn => fn(state));
}

export function markDone(stepId, value = true) {
  set({ done: { [stepId]: value } });
}

/** 현재 선택 종목명 배열 */
export const pickNames = () => (state.picks || []).map(p => p.name);

/** 진행률 (0~100) — 파이프라인 6단계 기준 */
export function progress() {
  const gates = [
    !!(state.discovery.sectors?.length),
    Object.values(state.cross).some(t => t && t.trim().length > 40),
    (state.picks || []).length > 0,
    Object.keys(state.done).some(k => ['swot','perf','fin','val','tech','qual'].includes(k) && state.done[k]),
    Object.keys(state.risk.targets || {}).length > 0,
    Object.keys(state.scores || {}).length > 0
  ];
  return Math.round(gates.filter(Boolean).length / gates.length * 100);
}
