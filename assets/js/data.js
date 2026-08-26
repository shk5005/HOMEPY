/* ============================================================
   data.js — 지니 도메인 상수
   출처: 참조 자료 "AI 투자 3단계 Chain of Questions"
   ============================================================ */

export const SECTORS = [
  'AI','반도체','2차전지','바이오','방산','조선','원전','로봇',
  'IT/소프트웨어','자동차','금융','에너지','엔터/미디어','헬스케어',
  '건설','유통/소비재','통신','우주항공','화학','철강'
];

export const STYLES = [
  { id:'growth',   label:'성장주',    filter:'매출 CAGR 20%+ 3년 연속, 영업이익률 개선, ROE 15%+' },
  { id:'value',    label:'가치주',    filter:'PBR 1.0 이하, PER 업종평균 이하, 배당수익률 3%+' },
  { id:'dividend', label:'배당주',    filter:'배당수익률 4%+, 5년 연속 배당, 배당성향 60% 이하' },
  { id:'turn',     label:'턴어라운드', filter:'적자→흑자 전환, 영업이익률 개선폭 3%p+, 부채비율 축소' },
  { id:'quality',  label:'퀄리티',    filter:'ROIC 15%+, FCF 마진 10%+, 부채비율 100% 이하' },
  { id:'momentum', label:'모멘텀',    filter:'52주 신고가 근접, 기관·외국인 순매수 20일 연속' }
];

export const HORIZONS = ['3개월','6개월','1년','2년+'];
export const TARGET_RETURNS = [15,20,30,50];
export const PICK_COUNTS = [3,5,7,10];
export const SAFETY_MARGINS = [10,20,30,40];

/* 모닝스타 경제적 해자 5분류 */
export const MOATS = [
  { id:'brand',   icon:'🏆', label:'브랜드 파워', q:'프리미엄 가격을 받을 수 있는가?' },
  { id:'switch',  icon:'🔗', label:'전환비용',   q:'고객이 떠나기 어려운가?' },
  { id:'network', icon:'🌐', label:'네트워크 효과', q:'쓰는 사람이 늘수록 가치가 커지는가?' },
  { id:'cost',    icon:'📉', label:'원가 우위',   q:'규모/공정으로 더 싸게 만드는가?' },
  { id:'intan',   icon:'📜', label:'무형자산(특허)', q:'특허·라이선스·규제 장벽이 있는가?' }
];
export const MOAT_GRADES = ['강','중','약','없음'];

/* 애널리스트 6대 핵심 분석 도구 */
export const TOOLS_6 = [
  { k:'PEG',        d:'성장 대비 주가가 싼가?',       s:'피터 린치 기준' },
  { k:'경제적 해자', d:'경쟁사가 못 따라오나?',        s:'워런 버핏 강조' },
  { k:'DCF',        d:'미래 현금흐름의 현재 가치',     s:'그레이엄 원전' },
  { k:'듀퐁 분해',   d:'ROE = 마진 × 회전율 × 레버리지', s:'1920s 듀퐁사' },
  { k:'시나리오',    d:'Bull / Base / Bear · 확률 가중 기대수익', s:'' },
  { k:'안전마진',    d:'적정가의 2/3 이하 매수',       s:'그레이엄 원전' }
];

/* 일반 투자자가 빠지는 함정 5가지 → 지니가 강제 차단 */
export const TRAPS = [
  { bad:"기준 없이 '추천해줘'", fix:'거장 기준 강제 설정' },
  { bad:'하나의 AI만 믿기',     fix:'3개의 AI로 교차 검증' },
  { bad:'하나의 지표만 보기',    fix:'PER·PBR·DCF 가중 + 안전마진 20%' },
  { bad:'환각·출처 없는 수치',   fix:'신뢰성 룰 5가지 탑재' },
  { bad:'손절가 없이 매수',      fix:'Bull/Base/Bear + 손절가 먼저' }
];

/* 할루시네이션 방지 5대 신뢰성 보강 룰 — 모든 프롬프트 말미에 강제 부착 */
export const GUARD_RULES = [
  "출처 없는 수치는 반드시 '확인 불가'로 표기할 것.",
  "'약', '대략', '대량' 등의 모호한 추정 표현은 절대 사용하지 말 것.",
  "모든 수치와 핵심 지표에는 출처 URL을 의무적으로 첨부할 것.",
  "학습된 과거 데이터에만 의존하지 말고, 반드시 실시간 웹 검색 결과를 활용할 것.",
  "화폐 단위는 원화(KRW)로 명시하고, 환율 적용 시점을 명기할 것.",
  "표의 빈칸을 채우기 위해 가상의 값을 임의로 만들어내지 말 것.",
  "출처는 거래소·공시(DART)·한국은행 등 원본(1급) 자료를 최우선으로 활용하고, SNS나 커뮤니티 글은 출처로 취급하지 말 것."
];

/* 5단계 심층 분석 (+ 보조 분석) */
export const STEPS = [
  { id:'swot',  n:'STEP 1', icon:'🔍', title:'종합 SWOT',   q:'WHAT',     desc:'뭐 하는 회사야?' },
  { id:'perf',  n:'STEP 2', icon:'📈', title:'실적 분석',   q:'WHY',      desc:'비즈니스가 진짜인가?' },
  { id:'fin',   n:'STEP 3', icon:'📊', title:'재무 분석',   q:'HOW',      desc:'숫자가 견고한가?' },
  { id:'val',   n:'STEP 4', icon:'💰', title:'밸류에이션',  q:'HOW MUCH', desc:'지금 얼마짜리인가?' },
  { id:'tech',  n:'STEP 5', icon:'📉', title:'기술적 분석', q:'WHEN',     desc:'지금이 타이밍인가?' },
  { id:'qual',  n:'추가',   icon:'💎', title:'질적 분석',   q:'MOAT',     desc:'재무에 안 나오는 가치' },
  { id:'dart',  n:'추가',   icon:'📋', title:'공시(DART)',  q:'NEWS',     desc:'최근 자본 이벤트' },
  { id:'earn',  n:'추가',   icon:'📞', title:'어닝콜 분석', q:'TONE',     desc:'경영진 톤 변화' },
  { id:'etf',   n:'대안',   icon:'🧺', title:'ETF 분석',    q:'ALT',      desc:'개별주 부담 시 대안' }
];

/* 상대가치 핵심 멀티플 + 학술·실무 표준 가중치 */
export const MULTIPLES = [
  { id:'per',    label:'PER (주가수익비율)',  formula:'적정 PER × 예상 EPS',        use:'흑자 안정 기업',   w:30 },
  { id:'pbr',    label:'PBR (주가순자산비율)', formula:'적정 PBR × BPS (PBR=ROE÷요구수익률)', use:'자산주·금융', w:20 },
  { id:'ev',     label:'EV/EBITDA',          formula:'영업가치 ÷ 영업현금흐름',      use:'자본구조 무관 비교', w:20 },
  { id:'psr',    label:'PSR (주가매출비율)',  formula:'적정 PSR × 주당매출',         use:'적자·고성장 기업', w:10 },
  { id:'rule40', label:'EV/Sales + Rule of 40', formula:'성장률 + 영업이익률 ≥ 40',  use:'SaaS·적자 성장주', w:10 },
  { id:'peg',    label:'PEG (PER ÷ 성장률)',  formula:'PER ÷ EPS 성장률(%)',        use:'성장주 (PEG<1 매수)', w:10 }
];

/* 시나리오 기본 확률 (참조 자료 기준) */
export const SCENARIO_DEFAULTS = [
  { id:'bull', label:'Bull (낙관)', prob:30, cls:'sc-bull', note:'모든 것이 잘 풀릴 때' },
  { id:'base', label:'Base (기본)', prob:50, cls:'sc-base', note:'가장 현실적인 경우' },
  { id:'bear', label:'Bear (비관)', prob:20, cls:'sc-bear', note:'최악의 상황' }
];

/* 리스크 3분류 */
export const RISK_TYPES = [
  { k:'기업 고유 리스크', d:'실적, 경쟁, 규제, 재무, 키맨' },
  { k:'섹터/산업 리스크', d:'업황 사이클, 사이클, 기술 변화' },
  { k:'매크로 리스크',    d:'금리, 환율, 경기, 지정학' }
];

/* 투자점수 배점 (총 100점) */
export const SCORE_WEIGHTS = [
  { id:'growth', label:'성장',      max:30 },
  { id:'moat',   label:'해자',      max:30 },
  { id:'val',    label:'밸류에이션', max:20 },
  { id:'mom',    label:'모멘텀',    max:20 }
];

/* Core-Satellite 차등배분 밴드 */
export const ALLOC_BANDS = [
  { id:'core',  label:'핵심 Core',  icon:'🏛', min:35, max:40, minScore:75 },
  { id:'sub',   label:'주력 Sub',   icon:'🎯', min:20, max:25, minScore:55 },
  { id:'watch', label:'관망 Watch', icon:'👀', min:10, max:15, minScore:0  }
];

/* Chain of Questions — 3단계 질문 사슬 */
export const CHAIN = [
  { n:1, title:'근거 중심의 국면 판정 + 확신도 요구',
    goal:'1회성 의견이 아니라, 표 형식 데이터와 확신도(0~100)를 투명하게 밝히도록 강제한다.' },
  { n:2, title:'반대 근거 강제 요구 (낙관 편향 방지)',
    goal:'AI 특유의 낙관 성향을 깨고, 투자자가 못 보는 반대편 리스크를 강제 탐색시킨다.' },
  { n:3, title:'감시 지표 & 킬 스위치(Kill Switch) 설정',
    goal:'감이 아니라 기계적으로 대응할 수 있는 나만의 행동 지침서를 확보한다.' }
];

export const AI_PANELS = [
  { id:'gpt',    label:'ChatGPT',    cls:'ai-gpt',    dot:'🟢' },
  { id:'claude', label:'Claude',     cls:'ai-claude', dot:'🟠' },
  { id:'plx',    label:'Perplexity', cls:'ai-plx',    dot:'🔵' }
];
