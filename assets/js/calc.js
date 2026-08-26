/* ============================================================
   calc.js — 지니 계산 엔진 (순수 함수, 부작용 없음)
   밸류에이션 / 시나리오 / 투자점수 / 차등배분
   ============================================================ */

export const num = v => {
  const n = parseFloat(String(v ?? '').replace(/[^0-9.\-]/g, ''));
  return Number.isFinite(n) ? n : null;
};
export const won  = v => v == null ? '확인 불가' : '₩' + Math.round(v).toLocaleString('ko-KR');
export const pct  = (v, d = 1) => v == null ? '확인 불가' : (v >= 0 ? '+' : '') + v.toFixed(d) + '%';
export const mult = (v, d = 1) => v == null ? '확인 불가' : v.toFixed(d) + '배';
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/* ---------- 밸류에이션 ---------- */

/** 상대가치: 각 멀티플 기반 적정주가를 가중 평균한다. */
export function relativeValue(rows) {
  const valid = rows.filter(r => r.value != null && r.weight > 0);
  if (!valid.length) return { fair: null, totalWeight: 0, rows };
  const totalWeight = valid.reduce((s, r) => s + r.weight, 0);
  const fair = valid.reduce((s, r) => s + r.value * r.weight, 0) / totalWeight;
  return { fair, totalWeight, rows: valid };
}

/** 안전마진 적용 매수가 = 적정가 × (1 - margin%) */
export function withSafetyMargin(fair, marginPct) {
  if (fair == null) return null;
  return fair * (1 - marginPct / 100);
}

/** 상승여력 = (적정가 / 현재가 - 1) */
export function upside(fair, current) {
  if (fair == null || !current) return null;
  return (fair / current - 1) * 100;
}

/** PEG = PER ÷ EPS 성장률(%). <1 저평가, >2 고평가 */
export function peg(per, growthPct) {
  if (!per || !growthPct) return null;
  return per / growthPct;
}
export function pegVerdict(v) {
  if (v == null) return { label: '확인 불가', cls: 'muted' };
  if (v < 1)  return { label: '저평가 (피터 린치 매수구간)', cls: 'pos' };
  if (v <= 2) return { label: '적정',  cls: '' };
  return { label: '고평가',  cls: 'neg' };
}

/** 듀퐁 3분해: ROE = 순이익률 × 자산회전율 × 재무레버리지 */
export function dupont({ netMargin, assetTurnover, leverage }) {
  if ([netMargin, assetTurnover, leverage].some(v => v == null)) return null;
  return netMargin * assetTurnover * leverage;
}

/** 적정 PBR = ROE ÷ 요구수익률 (잔여이익 근사) */
export function fairPBR(roe, requiredReturn) {
  if (!roe || !requiredReturn) return null;
  return roe / requiredReturn;
}

/** Rule of 40 = 매출성장률(%) + 영업이익률(%) */
export function ruleOf40(growthPct, opMarginPct) {
  if (growthPct == null || opMarginPct == null) return null;
  return growthPct + opMarginPct;
}

/* ---------- 시나리오 · 리스크 ---------- */

/**
 * 확률 가중 기대수익률.
 * scenarios: [{ id, prob(%), target(원) }]
 */
export function expectedReturn(scenarios, current) {
  if (!current) return null;
  const rows = scenarios.filter(s => s.target != null && s.prob != null);
  if (!rows.length) return null;
  const pSum = rows.reduce((s, r) => s + r.prob, 0);
  if (pSum <= 0) return null;
  const e = rows.reduce((s, r) => s + (r.prob / pSum) * (r.target / current - 1), 0);
  return e * 100;
}

/** 시나리오별 수익률 배열 */
export function scenarioReturns(scenarios, current) {
  return scenarios.map(s => ({
    ...s,
    ret: (s.target != null && current) ? (s.target / current - 1) * 100 : null
  }));
}

/**
 * 손절·익절 가격 구간.
 * 참조 자료 기준: 손절 -20%, 1차 익절 +15%, 2차 익절 +30%
 */
export function priceGuide(current, { stop = 20, tp1 = 15, tp2 = 30 } = {}) {
  if (!current) return null;
  const stopPrice = current * (1 - stop / 100);
  const tp1Price  = current * (1 + tp1 / 100);
  const tp2Price  = current * (1 + tp2 / 100);
  const risk   = current - stopPrice;
  const reward = tp2Price - current;
  return {
    stopPrice, tp1Price, tp2Price,
    riskReward: risk > 0 ? reward / risk : null,
    stop, tp1, tp2
  };
}

/** Risk/Reward 판정 — 1:2 이상이면 투자 고려 가능 */
export function rrVerdict(rr) {
  if (rr == null) return { label: '확인 불가', cls: 'muted' };
  if (rr >= 3) return { label: '우수 (1:3+)', cls: 'pos' };
  if (rr >= 2) return { label: '양호 (1:2+)', cls: 'pos' };
  if (rr >= 1) return { label: '주의 (1:1대)', cls: '' };
  return { label: '부적합 (손실 위험 > 기대수익)', cls: 'neg' };
}

/** -50% 손실은 +100% 수익이 있어야 회복된다 (행동경제학 헷지의 근거) */
export function recoveryNeeded(lossPct) {
  const l = Math.abs(lossPct);
  if (l >= 100) return null;
  return (1 / (1 - l / 100) - 1) * 100;
}

/** 정규분포 근사 VaR 99% (1년, 단순 파라메트릭) */
export function var99(volPct, expectedPct = 0) {
  if (volPct == null) return null;
  return expectedPct - 2.326 * volPct;
}

/* ---------- 투자점수 ---------- */

/** scores: { growth, moat, val, mom } — 각 항목 원점수 */
export function totalScore(scores, weights) {
  let sum = 0, max = 0;
  for (const w of weights) {
    const v = num(scores?.[w.id]);
    if (v != null) sum += clamp(v, 0, w.max);
    max += w.max;
  }
  return { sum, max, pct: max ? (sum / max) * 100 : 0 };
}

export function scoreGrade(pct) {
  if (pct >= 80) return { label: 'A · 핵심 편입',  cls: 'bp-green' };
  if (pct >= 65) return { label: 'B · 주력 편입',  cls: 'bp-gold'  };
  if (pct >= 50) return { label: 'C · 소액 관망',  cls: 'bp-gold'  };
  return              { label: 'D · 편입 보류',  cls: 'bp-red'   };
}

/* ---------- 차등배분 (Core-Satellite) ---------- */

/**
 * 투자점수 기반 차등배분.
 * 1) 점수로 밴드(core/sub/watch) 배정 → 밴드 중앙값을 초기 비중으로
 * 2) 밴드 내에서 점수 비례 미세조정
 * 3) 합계 100%로 정규화 후 밴드 상·하한으로 클램프, 잔차는 최상위 종목에 배분
 */
export function allocate(holdings, bands, totalCapital) {
  if (!holdings.length) return { rows: [], cash: totalCapital, totalWeight: 0 };

  const withBand = holdings.map(h => {
    const band = bands.find(b => h.scorePct >= b.minScore) || bands[bands.length - 1];
    const span = band.max - band.min;
    // 밴드 내 상대 위치: 밴드 하한 점수 대비 초과분을 0~1로 환산
    const nextMin = band.minScore;
    const headroom = Math.max(1, 100 - nextMin);
    const rel = clamp((h.scorePct - nextMin) / headroom, 0, 1);
    return { ...h, band, raw: band.min + span * rel };
  });

  const rawSum = withBand.reduce((s, h) => s + h.raw, 0);
  // 100%를 넘거나 모자라면 비례 스케일링 후 밴드 클램프
  let rows = withBand.map(h => ({ ...h, weight: (h.raw / rawSum) * 100 }));
  rows = rows.map(h => ({ ...h, weight: clamp(h.weight, h.band.min, h.band.max) }));

  let sum = rows.reduce((s, h) => s + h.weight, 0);
  const cashWeight = Math.max(0, 100 - sum);

  // 배분 합이 100%를 넘으면 비례 축소
  if (sum > 100) {
    rows = rows.map(h => ({ ...h, weight: (h.weight / sum) * 100 }));
    sum = 100;
  }

  rows = rows.map(h => ({
    ...h,
    amount: totalCapital * (h.weight / 100),
    shares: h.price ? Math.floor(totalCapital * (h.weight / 100) / h.price) : null
  }));

  rows.sort((a, b) => b.weight - a.weight);
  return { rows, cash: totalCapital * (cashWeight / 100), cashWeight, totalWeight: sum };
}

/** 포트폴리오 종합 성과 (가중 평균) */
export function portfolioStats(rows, cashWeight = 0) {
  const wsum = rows.reduce((s, r) => s + r.weight, 0);
  if (!wsum) return null;
  const wavg = key => {
    const valid = rows.filter(r => num(r[key]) != null);
    if (!valid.length) return null;
    const w = valid.reduce((s, r) => s + r.weight, 0);
    return valid.reduce((s, r) => s + num(r[key]) * r.weight, 0) / w;
  };
  const expected = wavg('expected');
  const beta = wavg('beta');
  const vol = wavg('vol');
  // 현금 비중은 기대수익·베타·변동성을 0으로 희석
  const dilute = v => v == null ? null : v * (wsum / (wsum + cashWeight));
  return {
    expected: dilute(expected),
    beta: dilute(beta),
    vol: dilute(vol),
    var99: var99(dilute(vol), dilute(expected)),
    names: rows.length
  };
}

/* ---------- 교차검증 (3-AI 합의) ---------- */

/**
 * AI 답변 텍스트에서 한국 종목명 후보를 추출한다.
 * 번호 목록 / 볼드 / 표 첫 칸 / 괄호 종목코드 패턴을 훑는다.
 */
export function extractTickers(text) {
  if (!text || !text.trim()) return [];
  const found = new Map();
  const add = raw => {
    let s = String(raw).trim()
      .replace(/^[\d]+[.)\]]\s*/, '')
      .replace(/[*_`#|]/g, '')
      .replace(/\((\d{6})\)/, '')
      .replace(/\s*\d{6}\s*$/, '')
      .replace(/[:：].*$/, '')
      .trim();
    // 한글/영문 종목명만, 2~20자
    if (!/^[가-힣A-Za-z0-9&.\-\s]{2,20}$/.test(s)) return;
    if (!/[가-힣A-Za-z]/.test(s)) return;
    // 흔한 비-종목 단어 제외
    if (/^(종목|순위|현재가|매수가|목표가|손절가|추천|근거|출처|결론|요약|표|기준|리스크|섹터|투자|분석|이유|주가|시장|전망|의견|참고|주의|합계|평균|총계|비고|없음|확인)/.test(s)) return;
    const key = s.replace(/\s/g, '');
    if (key.length < 2) return;
    found.set(key, found.get(key) || s);
  };

  for (const line of text.split(/\r?\n/)) {
    const t = line.trim();
    if (!t) continue;
    // 마크다운 표 행: | 삼성전자 | ... |
    if (t.startsWith('|')) {
      const cells = t.split('|').map(c => c.trim()).filter(Boolean);
      if (cells.length >= 2 && !/^[-:\s]+$/.test(cells[0])) {
        // 첫 칸이 순위 숫자면 두 번째 칸이 종목명
        add(/^\d+$/.test(cells[0]) ? cells[1] : cells[0]);
      }
      continue;
    }
    // 번호 목록: 1. 삼성전자 (005930)
    const numbered = t.match(/^\s*\d+[.)\]]\s*\*{0,2}([^*(\-–—:：]{2,20})/);
    if (numbered) { add(numbered[1]); continue; }
    // 볼드 강조: **SK하이닉스**
    const bold = t.match(/\*\*([^*]{2,20})\*\*/);
    if (bold) { add(bold[1]); continue; }
    // 불릿: - 한미반도체 (042700)
    const bullet = t.match(/^\s*[-•·]\s*([^(\-–—:：]{2,20})/);
    if (bullet) add(bullet[1]);
  }
  return [...found.values()];
}

/** 3개 AI 답변의 교집합 — 2곳 이상 언급된 종목을 합의 종목으로 본다. */
export function crossValidate(panels) {
  const norm = s => s.replace(/\s/g, '').toLowerCase();
  const tally = new Map();
  for (const p of panels) {
    const seen = new Set();
    for (const name of p.tickers) {
      const k = norm(name);
      if (seen.has(k)) continue;
      seen.add(k);
      const rec = tally.get(k) || { name, sources: [] };
      rec.sources.push(p.id);
      tally.set(k, rec);
    }
  }
  const all = [...tally.values()].sort((a, b) => b.sources.length - a.sources.length);
  return {
    consensus3: all.filter(r => r.sources.length >= 3),
    consensus2: all.filter(r => r.sources.length === 2),
    single:     all.filter(r => r.sources.length === 1),
    all
  };
}
