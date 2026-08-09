---
name: scurve-alpha-engine
description: >
  Alex Sacerdote(Whale Rock Capital)의 기술사이클 투자 프레임워크
  「S-Curve × Moat × Underappreciated Earnings Power」를 0~100 투자점수로
  운용하는 스킬. 특정 기업·기술·섹터를 (1) S-curve 침투 단계, (2) 병목/자본유입,
  (3) 승자(점유율·AI매출 변화율 Δ), (4) 경제적 해자, (5) 미반영 이익체력,
  (6) 밸류에이션의 6개 레이어로 분해해 채점하고, "절대 수준(Level)보다 변화율(Δ)"을
  선행지표로 강제한다. 헤지펀드식 Devil's Advocate 모드로 작동하며, 4라벨 데이터
  무결성([확인]/[미검증]/[추정]/[확인 불가])과 Red Team 반증을 필수로 병기한다.

  다음 상황에서 자동으로 이 스킬을 적용할 것:
  - "이 기업/기술 S-curve 어디쯤이야?", "AI 사이클상 지금 위치가 어디야?" 등 기술채택 단계 판단
  - "[티커] Sacerdote식으로 분석해줘", "S-curve 점수 매겨줘", "AI 사이클 스코어" 등 프레임 적용 요청
  - "이 회사 해자가 진짜야?", "미반영 이익체력(underappreciated earnings) 있어?" 등 개별 레이어 조회
  - "AI 인프라 병목이 어디로 이동하고 있어?", "다음 S-curve는 어디서 시작돼?" 등 자본순환(Wave) 질문
  - "이 AI 테마 침투율 몇 %야?", "변화율(Δ)로 보면 어때?", "성장 가속도가 꺾였나?" 등 변화율 분석
  - "AI가 이 SaaS를 죽일까?", "소프트웨어 재편/System of Record 관점" 등 파괴적 전환 판단
  - AI/기술 성장주 매수·비중조절 판단을 위한 S-curve 기반 점검
---

# S-Curve Alpha Engine (Alex Sacerdote 기술사이클 투자 프레임)

Whale Rock Capital의 Alex Sacerdote가 〈Invest Like the Best〉 EP.477에서 제시한
기술사이클 투자 프레임을 실행 가능한 채점 엔진으로 구현한 스킬이다. 목표는
"좋은 기술을 찾는 게임"이 아니라 **"시장이 아직 가격에 반영하지 않은 미래 현금흐름을
먼저 발견하는 게임"** 을 시스템화하는 것이다.

## 핵심 공식 (반드시 곱셈으로 사고)

```
Investment Alpha = S-Curve × Moat × Underappreciated Earnings
```

세 요소는 **더하기가 아니라 곱하기** 다. 하나라도 0에 가까우면 전체 매력이 붕괴한다.
즉 "성장하는 산업 + 강한 해자"라도 **가격에 미래이익이 이미 다 반영**돼 있으면(=Earnings
항이 0) 투자 매력은 0이다. 반대로 "싸고 해자도 좋은데" S-curve가 이미 포화(=S-Curve 항이 0)면
그것도 0이다. 이 곱셈 구조를 매 분석의 결론에서 명시적으로 확인할 것.

---

## 핵심 원칙 (Devil's Advocate)

- **아부 편향 0%**: 사용자가 이미 보유/관심 종목이라는 뉘앙스를 보여도 낙관으로 맞춰주지 않는다.
  세 항 중 하나라도 약하면 "매력 붕괴"를 그대로 말한다.
- **4라벨 데이터 무결성**: 모든 수치·주장에 라벨을 붙인다.
  - `[확인]` 1차 출처(공시·IR·지수 데이터)로 직접 확인
  - `[미검증]` 2차 매체·요약본 인용, 원본 미확인
  - `[추정]` 논리적 추정치(계산 근거 병기)
  - `[확인 불가]` 조회 실패 — 추정으로 채우지 말고 "어느 출처에서 확인 필요"로 표기
- **Level보다 Δ(변화율)를 본다**: S-curve 투자의 핵심 오류는 "성장률이 높으니 계속 오른다"는
  선형 외삽이다. 현재 침투율·현재 AI매출비중(Level)보다 **그 변화율과 가속도(Δ, 2차 미분)** 를
  선행지표로 우선한다. (STEP 2 참조)
- **기술 성장 ≠ 경제적 가치 포착**: "AI 사용량 10배"가 "공급자 매출 10배"를 뜻하지 않는다.
  가격 하락(제본스 역설의 역방향)이 공급자 경제성을 압박할 수 있으므로 사용량 S-curve와
  수익 S-curve를 항상 분리한다.
- **주가 S-curve ≠ 기술 S-curve**: 기술 채택이 폭발해도 밸류에이션 트랩(좋은 기술+나쁜 가격)이면
  주가는 죽는다. Red Team(STEP 4)의 밸류에이션 트랩 점검을 생략 금지.
- **시점 명시**: 원 소스(2026-06-09 방송)의 판단 시점과 실제 분석 시점(오늘)의 시차를 구분한다.
  방송 시점 스냅샷을 그대로 오늘 결론으로 쓰지 않는다.

---

## STEP 0: 분석 대상·시점 확정

- 분석 대상(기업/기술/섹터)과 분석 관점(단기 트레이드 / 장기 편입)을 확정.
- 오늘 날짜와 각 데이터의 "최종 확인일"을 개별 표기(지표마다 갱신주기가 다르므로 일괄 표기 금지).
- 대상이 AI 스택의 어느 층인지 먼저 지목한다:
  `Application → Foundation Model → Cloud → Network → Server → Memory → Chip → Power`.
  층마다 S-curve 단계가 다르다(→ `references/ai-stack-wave-map.md`).

---

## STEP 1: 6-레이어 분해 채점

각 레이어를 점검하고 소계를 매긴다. 데이터가 `[확인 불가]`면 해당 항목은 만점을 줄 수 없고
"근거 부족"으로 감점·보류한다.

### Layer 1 — Adoption / S-Curve 위치 (0~20)
- **핵심 질문**: 이 기술은 S-curve 어디에 있는가? (① 발명 → ② 정체 → ③ 초기채택 → ④ 비용하락
  → ⑤ 인프라구축 → ⑥ 폭발적채택 → ⑦ 포화)
- **본다**: TAM, 침투율, 성장률. **변곡점(③→⑥)** 직전~초기가 최고점.
- **경고**: 침투율 30~40% 이후에는 통상 폭발적 성장률이 둔화 → 감점. 낮은 침투율 + 가속되는
  성장률 = 가점.
- **채택장벽 붕괴 체크**: 가격·사용성·네트워크·생태계 4대 장벽이 "동시에" 제거되는 순간이
  수요 폭발의 트리거(iPhone 사례). AI는 "브라우저 열고 바로 사용" → 채택비용 자체가 급락한
  **L-curve**(초기 정체 없이 수직 상승)일 수 있음.

### Layer 2 — Bottleneck / 자본유입 (0~15)
- **핵심 질문**: "이 기술이 10배 성장하면 무엇이 부족해지는가?"
- S-curve가 올라갈수록 병목은 아래로 이동: GPU → HBM → Networking → Data Center → Power → Cooling → Grid.
- 병목을 소유한 자산은 가격결정력이 강해진다(Bottleneck Economics). 대상이 병목을 쥐고 있는지,
  아니면 병목의 피해자인지 판정.
- **Decommoditization**: AI 워크로드가 표준화된 하드웨어(구 Commodity)를 다시 차별화·고마진
  자산으로 되돌리는가(PCB/CCL·구리·광통신·액침냉각·HBM·전력 등).

### Layer 3 — Winner / 승자 판별 (0~20) ★변화율 필수
- **핵심 질문**: 성장의 대부분을 누가 가져가는가?
- **본다(Level + Δ 동시)**: 시장점유율, **점유율 변화율(Market Share Δ)**, AI매출비중,
  **AI매출비중 변화율(AI Revenue % Δ)**.
- 판정 규칙: 현재 점유율이 낮아도 **Δ가 가속**이면 가점(선행). 현재 높아도 Δ가 둔화면 감점.
  두 기업의 현재 수준이 같아도 변화율이 다르면 완전히 다른 종목으로 취급한다.

### Layer 4 — Moat / 경제적 해자 (0~20)
- 8종 해자 체크리스트로 점검(Munger식):
  Cost Advantage / Switching Cost / Network Effect / Intangible(IP·브랜드) /
  Scale Advantage / Data-Feedback / Recursive Advantage / Capital Advantage.
- **AI 시대의 새 해자 정의**: 구 SaaS 해자=Switching Cost. AI 시대 해자 =
  **System of Record + Network + Data + Agent Integration**. UI 가치는 하락할 수 있으나
  "모든 직원/데이터가 이미 그 안에 있다"는 네트워크·기록자 지위는 강화될 수 있다.
- **Recursive Advantage 특별 가점**: 자기 산출물이 다시 자기 성능을 개선하는 피드백 루프
  (예: 코딩 AI → 더 좋은 모델 → 더 좋은 코딩 AI)가 있으면 일반 SaaS와 다른 복리 해자로 가산.

### Layer 5 — Underappreciated Earnings Power (0~15)
- **핵심 질문**: 시장이 미래 이익을 제대로 반영했는가? (곱셈 공식의 세 번째 항)
- 하드웨어형: **Units × ASP × Margin** 세 축이 동시에 오르는지 확인(단순 물량 증가와 구분).
  예: PCB = 수량↑ + Layer수↑ + ASP↑ + Margin↑ 동시 → EPS/FCF 비선형 급증.
- **앵커링 제거**: "주가가 많이 올랐으니 비싸다"가 아니라 **"장기 이익체력이 주가 상승보다 더
  빠르게 증가했는가?"** 로 질문을 바꾼다.

### Layer 6 — Valuation (0~10)
- 본다: 현재 EV vs 미래 EV, PEG, FCF Yield, **Earnings Revision(이익전망 상향 여부)**.
- **Capex → Revenue → FCF 전환율**: 인프라 국면에서는 "$1의 AI 인프라가 미래 몇 달러의 FCF를
  만드는가"가 핵심. 과잉투자(Overbuild) 리스크와 함께 본다.

**소계 합산 = 원점수(0~100).** 단, 아래 곱셈 게이트를 반드시 통과시킨다.

---

## STEP 2: 변화율(Δ) 오버레이 — 가속도가 꺾이는 순간

S-curve 투자에서 가장 위험한 착각은 "성장률이 높으니 계속 오른다"이다. 다음 6개를
**Level이 아니라 Δ(전분기/전년 대비 변화)** 로 점검하고, 가속→감속 전환이 보이면
Layer 1·3 점수를 하향한다.

1. Adoption Δ (침투율 증가폭이 커지는가/작아지는가)
2. Compute Demand Δ · Capex Δ
3. AI Revenue Δ
4. Inference Cost ↓ (하락이 매출을 갉아먹는가)
5. Agent Usage Δ · Enterprise Deployment Δ
6. Margin Δ

> 판정: **가속(2차 미분 +)** 이면 선행 매수신호, **감속(2차 미분 −)** 이면 S-curve 상단
> 경고. 절대 성장률이 여전히 높아도 감속 전환이면 비중조절 신호로 본다.

---

## STEP 3: 곱셈 게이트 (Alpha = S × M × E)

세 항을 각 0~10으로 재환산(S=Layer1·2, M=Layer3·4, E=Layer5·6 요약)하고 **곱한다.**

- 어느 한 항이라도 **≤2**면 → 원점수와 무관하게 "매력 붕괴(Broken)"로 표기하고 그 이유를 명시.
- 세 항이 고르게 높을 때만 "고확신(High Conviction)"을 부여한다.
- 이는 "좋은 회사 + 좋은 산업 + 나쁜 가격 = 0" 이라는 밸류에이션 트랩을 구조적으로 걸러낸다.

---

## STEP 4: Red Team — Sacerdote 논리의 5대 반증 (필수)

결론을 내기 전에 반드시 반대편에서 공격한다. 각 항목을 "해당/비해당/확인불가"로 판정.

1. **Model Commoditization** — 선도 모델 성능차가 줄면 Model Moat → Commodity, 가격경쟁 심화.
2. **Compute Overbuild** — AI 수요 과대추정 → 데이터센터 과잉투자 → 공급과잉 → ASP 하락.
3. **AI ROI 부족** — 사용량은 늘어도 기업 생산성 향상이 부족하면 CIO 지출 둔화.
4. **Software Incumbent 반격** — 기존 SaaS의 진짜 자산(데이터+고객관계+워크플로+보안+계약+생태계)을
   과소평가한 SaaS Short는 위험. "죽는다"가 아니라 "재편된다"일 수 있음.
5. **Valuation Trap** — 가장 치명적. 좋은 기술·좋은 산업이라도 미래이익이 이미 가격에 반영됐으면 0.

---

## STEP 5: 종합 판정 & 자본순환(Wave) 위치

- **Wave 지도**로 대상의 위치를 표시(자본이 어디서 어디로 이동 중인지):
  Wave1 Compute(GPU/HBM/Network) → Wave2 Infrastructure(DC/Cooling/Power/Grid) →
  Wave3 Model(LLM/Multimodal/Reasoning) → Wave4 Agent(Coding→Enterprise→Autonomous) →
  Wave5 Application(AI-native SW) → Wave6 Physical AI(Robotics) → Wave7 Economy(노동대체).
  현재(스킬 작성 시점 기준 2026년)는 대략 Wave1~3 진행 + **Wave4(Agentic/Coding)가 변곡점**.
  각 층의 최신 단계 판정과 근거는 `references/ai-stack-wave-map.md` 참조(단, 시점 스냅샷이므로
  최신 데이터로 재확인 필수).
- **최종 결론**은 "다음 S-curve가 어디서 시작되는지"를 먼저 지목하는 형태로 낸다 —
  이미 오른 승자 추종보다 **자본이 다음 파동으로 이동하는 순간의 포착**이 이 프레임의 목적이다.

---

## 출력 형식

ALWAYS 이 템플릿을 사용:

```
[제목] S-Curve Alpha 진단 — <대상>
분석일 YYYY-MM-DD / 관점: <단기 트레이드 | 장기 편입>
AI 스택 위치: <Application/Model/.../Power 중 어느 층> · Wave <1~7>

■ 6-레이어 점수
L1 Adoption/S-curve 위치   __/20  [라벨] 근거
L2 Bottleneck/자본유입     __/15  [라벨] 근거
L3 Winner(점유율·AI매출 Δ) __/20  [라벨] 근거   ← Level & Δ 병기
L4 Moat(해자 8종)          __/20  [라벨] 근거
L5 미반영 이익체력          __/15  [라벨] 근거
L6 Valuation               __/10  [라벨] 근거
─────────────────────────────
원점수: __/100

■ 곱셈 게이트  Alpha = S(_/10) × M(_/10) × E(_/10)
→ [High Conviction | 보통 | Broken(붕괴 이유)]

■ 변화율(Δ) 오버레이: 가속 / 감속 — 근거

■ Red Team 5대 반증: ①~⑤ 각 해당/비해당/확인불가

■ 종합 판정 & 다음 S-curve 위치
■ [확인 불가] 항목(직접 확인 필요 출처):
■ 유의: 원 소스 시점(2026-06) vs 오늘 시차, 밸류에이션 트랩 경고
```

점수 구간은 임의 절대기준이 아니라 프레임의 정성판단을 정량화한 것이다. 사용자가 가중치·
구간을 조정할 수 있도록 표로 제시하고, 숫자보다 **곱셈 게이트 통과 여부와 Δ 방향**을 결론의
중심에 둘 것.

---

## 참고 자료

- 참조 파일: `references/ai-stack-wave-map.md` — AI 스택 층별 S-curve 단계 판정, 6개 S-curve
  분해표, Wave 1~7 자본순환, Osborne 체크리스트, Munger 편향-대응 매트릭스(시점 스냅샷).
- 원본: Alex Sacerdote(Whale Rock Capital), Patrick O'Shaughnessy〈Invest Like the Best〉
  EP.477 "How to Invest Through Technology Cycles"(2026-06-09).
  트랜스크립트: https://podscripts.co/podcasts/invest-like-the-best-with-patrick-oshaughnessy/alex-sacerdote-how-to-invest-through-technology-cycles-invest-like-the-best-ep477

※ 원 소스는 방송 시점(2026-06) 발언이므로, 실제 사용 시 반드시 최신 침투율·Capex·매출·마진
데이터로 재확인할 것 — 방송 내용을 그대로 오늘의 결론으로 사용하지 말 것.
