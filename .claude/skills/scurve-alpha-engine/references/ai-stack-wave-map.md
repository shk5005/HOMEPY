# AI 스택 · S-Curve 위치 지도 (2026 스냅샷)

> ⚠️ **시점 경고**: 이 파일은 원 소스(2026-06-09 방송) + 2026 상반기 공개자료 기준 스냅샷이다.
> 단계 판정은 시간이 지나면 반드시 바뀐다. 사용 시 최신 침투율·Capex·매출·마진 데이터로
> 재확인하고, 확인 못한 항목은 `[확인 불가]`로 표기할 것.

## 1. 핵심 통찰 — "하나의 S-curve"가 아니라 "S-curve의 연쇄"

AI는 단일 기술이 아니라 스택 층마다 서로 다른 단계에 있는 **연속적 S-curve**다. 투자 기회의
본질은 "모든 층이 동시에 폭발"이 아니라 **"각 층의 변곡점이 시간차를 두고 순차적으로 온다"**
는 데 있다. 이 시차가 자본순환(Capital Rotation)을 만든다.

7단계 축: ① 발명 → ② 정체 → ③ 초기채택 → ④ 비용하락 → ⑤ 인프라구축 → ⑥ 폭발적채택 → ⑦ 포화

## 2. AI 6개 S-curve 분해표 (2026 판정)

| AI 영역 | S-curve 단계 | 판정 |
|---|---|---|
| LLM / Foundation Model | ⑤→⑥ | 🟢 폭발적 채택 진입 |
| AI Infrastructure | ⑤ | 🟢 대규모 구축 중(정중앙) |
| AI Coding / Agent | ③→⑤ | 🟢 변곡점 |
| Enterprise AI | ③→④ | 🟡 초기채택 → ROI 검증 |
| AI Application | ③ | 🟡 초기 |
| Physical AI / Robotics | ②→③ | 🟡 초기채택 직전 |

**AI 전체 평균 ≈ 4.5~5단계** = "비용하락 + 인프라구축 → 폭발적 채택"의 변곡점 구간.

세부 점수(참고):

| 영역 | 단계 | 판정 |
|---|---|---|
| LLM 사용 | 6/7 | 🟢 폭발적 채택 |
| AI Coding | 5→6 | 🟢 변곡점 |
| AI Infrastructure | 5/7 | 🟢 대규모 구축 |
| Enterprise AI | 3→4 | 🟡 초기채택 |
| AI Agent | 3→5 | 🟡 변곡점 진입 |
| AI Application | 3/7 | 🟡 초기 |
| Robotics / Physical AI | 2→3 | 🟡 초기 |
| AI 노동대체 | 2→3 | 🔵 장기 초기 |

## 3. 왜 코딩이 첫 Killer Application인가

- Copilot(코드 조각 생성) → **Agentic Coding**(코드 작성·탐색·실행·디버깅·테스트·수정·반복)으로
  전환되며 AI가 인간의 "작업(task)" 자체를 수행하기 시작.
- 정보 생성 단계 → **경제적 작업 수행** 단계로 이동 = 노동 생산함수의 변화.
- **Recursive Improvement 루프**: 코딩은 AI가 AI를 개선하는 데 쓰이는 영역 →
  코드 작성 → AI 시스템 개선 → 더 좋은 Coding Agent → 더 많은 코드. 일반 SaaS와 다른 복리 해자.

## 4. 소프트웨어 재편 — "죽는다"가 아니라 "이동한다"

- 구조 변화: `Human → Software → Human work` (구 SaaS) → `Human → AI Agent → SW/DB/API → 작업완료`.
- SW가 "인간을 돕는 도구"에서 "AI Agent의 백엔드 인프라"로 전락할 위험.
- 가치 이동: **"소프트웨어 UI" → "System of Record"**. UI 가치는 하락하나, 데이터·계약·
  네트워크·기록자 지위는 오히려 강화될 수 있음(예: Slack = 프로그램이 아니라 "모든 직원이 이미
  그 안에 있다"는 사실이 해자).
- 판정 원칙: SaaS를 일괄 Short로 보지 말 것. "단순 DB 전락" vs "Agent 기반 System of Record로 강화"를
  기업별로 구분.

## 5. Hardware Renaissance — Decommoditization

- 구 데이터센터: Intel CPU + DRAM + PCB + Ethernet + Server = 표준화 → Commodity화.
- AI 워크로드: GPU + HBM + Advanced Networking + 액침냉각 + 40-layer PCB + 전력 + 광통신 +
  특수부품 = 복잡도 급증 → **Commodity → Critical Infrastructure** 역전.
- 결과 체인: AI → 하드웨어 복잡성↑ → 기술 차별화 → 가격↑ → 마진↑.
- 과거 비핵심이던 자산이 병목으로: PCB · Copper Clad Laminate · Ethernet · 액침냉각 · 광통신 ·
  전력공급 · HBM. (원 소스 언급 사례: Celestica, Corning, PCB/CCL 공급망 등 — 종목 언급은 사실
  확인 후 `[미검증]` 라벨로 다룰 것.)

## 6. Wave 자본순환 지도 (1~7)

| Wave | 내용 | 2026 상태 |
|---|---|---|
| 1 Compute | GPU → HBM → Network | 진행 중 |
| 2 Infrastructure | Data Center → Cooling → Power → Grid | 진행 중 |
| 3 Model | LLM → Multimodal → Reasoning | 진행 중 |
| 4 Agent | Coding → Enterprise Agent → Autonomous Workflow | **현재 변곡점** |
| 5 Application | AI-native Software | 초기 |
| 6 Physical AI | Robotics → Autonomous Factory/Logistics | 아직 초기 |
| 7 Economy | AI 노동 → 생산성 → 산업구조 → 자본배분 | 아직 초기 |

투자 함의: GPU→HBM→데이터센터→전력의 1차 파동에서 **Agent → SW 재편 → AI 노동 → Robotics**의
2·3차 파동으로 자본이 이동하는 순간을 포착하는 것이 핵심. 동시에 "S-curve 상승"과 "Capex
과잉투자"를 양면으로 모니터링(2026 빅테크 미래 데이터센터 임차 commitment ≈ $1.09조 규모라는
보도는 이 양면성의 예 — `[미검증]`, 원 출처 재확인 필요).

## 7. Osborne 체크리스트 (아이디어 확장용)

- **Magnify**: AI 사용량 10배 → Compute/Power/Network/Memory 병목.
- **Minimize**: AI 모델 비용 1/10 → 사용량 폭발.
- **Substitute**: Human labor→AI Agent, SaaS UI→Agent Interface, CPU→GPU/ASIC.
- **Rearrange**: `App→Human→Data` → `Agent→Data→App`.
- **Eliminate**: UI 제거 → "No Interface".
- **Reverse**: "AI가 SW를 죽인다" ↔ "AI가 SW를 더 중요한 인프라로 만든다".
- **Combine**: AI+Robotics / +Energy / +Data Center / +Healthcare / +Finance.
- **Adapt**: Cloud S-curve 패턴을 AI에 적용.

## 8. Munger 편향 ↔ 대응 매트릭스

| 투자자의 오류 | Sacerdote식 대응 |
|---|---|
| 최근성 편향 | 장기 S-curve로 사고 |
| 선형적 사고 | 지수적/변곡 성장 인식 |
| 확증편향 | 전체 Supply Chain 조사 |
| 행동 편향(조급함) | 초기 1~2년 놓쳐도 무방 |
| 군중심리 | 시장이 싫어하는 Hardware도 검토 |
| 앵커링 | 현재 EPS가 아니라 미래 EPS 기준 |
| 손실회피 | S-curve 전체를 조망 |
| 과잉확신 | S-curve가 꺾인 사례(예: 특정 성장주)도 인정 |

핵심: **"주가가 많이 올랐다"** 가 아니라 **"장기 이익체력이 주가 상승보다 더 빠르게 증가했는가"**
를 물어 앵커링을 제거한다.

## 9. 시간지평별 핵심 변수

| 기간 | 핵심 변수 | 투자 관점 |
|---|---|---|
| 단기 | AI Capex | GPU/Memory/Network |
| 중기 | Model 경쟁 | Foundation Model 진영 |
| 중기 | Agentic AI | Coding/Enterprise Agent |
| 중장기 | Software 재편 | SaaS 승자/패자 |
| 장기 | AI 노동대체 | GDP/TAM 자체 변화 |
| 초장기 | Physical AI | Robotics + Energy + AI |

2026 결론: Application layer는 아직 승자·해자가 불명확 → **Infrastructure + Foundation Model +
Agentic Coding을 먼저 보는 것**이 Sacerdote식 접근.
