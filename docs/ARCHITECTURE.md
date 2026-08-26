# 지니 — 앱 구조 상세

참조 자료의 화면 캡처 33장을 분석해 도출한 구조입니다.

## 1. 화면 흐름

```
대시보드 (#dashboard)
 ├─ 함정 5가지 배너 · 진행률 · 애널리스트 6대 도구
 └─ 파이프라인 카드 6개 → 각 단계로 진입

① 종목 발굴 (#discovery)
 └─ [RICE 프롬프트 생성] → 프롬프트 박스 (복사 / .txt 저장)
      └─ "3개 AI 교차 검증하러 가기"

② 교차 검증 (#cross)
 ├─ ChatGPT / Claude / Perplexity 3열 입력
 └─ [교차 검증 분석] → 3/3 · 2/3 · 단독 분류
      ├─ 종목 칩 클릭 → 분석 대상에 담기
      └─ 종합 비교 프롬프트 (근거 충돌 지점 찾기)

③ 심층 분석 (#steps)
 ├─ 분석 대상 종목 편집기 (시세 앵커 입력)
 ├─ STEP 카드 9개 → #steps/<id>
 │    └─ 단계별 RICE 프롬프트 + [완료 표시]
 └─ 해자 5분류 매트릭스 안내

④ 밸류에이션 (#valuation)   ⑤ 리스크 (#risk)   ⑥ 포트폴리오 (#portfolio)
🔗 Chain of Questions (#chain)
```

라우팅은 `location.hash` 기반이며, `steps/<stepId>` 형태의 2단 라우트를 지원합니다.

## 2. 상태 모델 (`store.js`)

```js
{
  discovery: { sectors[], style, horizon, target, count, market, risk, filter, focus, exclusions[] },
  cross:     { gpt, claude, plx },              // AI 답변 원문
  picks:     [{ name, price, change, per, pbr, cap, band }],
  asOf:      "2026.08.26 15:30 (KST)",          // 시세 조회 시점
  analysis:  { horizon, risk },
  valuation: { marginPct, method, rows: { per:{value,weight}, ... } },
  risk:      { stop, tp1, tp2, probs:{bull,base,bear}, targets:{ 종목명:{bull,base,bear} } },
  scores:    { 종목명: { growth, moat, val, mom } },
  portfolio: { capital },
  chain:     { subject, prevVerdict },
  done:      { stepId: true }                   // 진행 표시
}
```

`deepMerge` 기반 부분 갱신 + `replace(path, value)` 로 배열/맵 전체 교체를 지원하며,
매 변경마다 localStorage에 저장됩니다. 저장소 접근이 차단된 환경(프라이빗 모드 등)에서는
메모리 상태로 계속 동작합니다.

## 3. 계산식 (`calc.js`)

| 함수 | 계산식 |
|------|--------|
| `relativeValue` | 적정가 = Σ(멀티플별 적정주가 × 가중치) ÷ Σ가중치 |
| `withSafetyMargin` | 매수가 = 적정가 × (1 − 안전마진%) |
| `upside` | 상승여력 = (적정가 ÷ 현재가 − 1) × 100 |
| `peg` | PEG = PER ÷ EPS 성장률(%) · <1 저평가 |
| `dupont` | ROE = 순이익률 × 자산회전율 × 재무레버리지 |
| `fairPBR` | 적정 PBR = ROE ÷ 요구수익률 |
| `ruleOf40` | 매출성장률(%) + 영업이익률(%) ≥ 40 |
| `expectedReturn` | E[r] = Σ(확률ᵢ ÷ Σ확률) × (목표가ᵢ ÷ 현재가 − 1) |
| `priceGuide` | 손절 = 현재가×(1−20%) · 1차 익절 ×(1+15%) · 2차 ×(1+30%) |
| `riskReward` | (2차 익절 − 현재가) ÷ (현재가 − 손절가) |
| `recoveryNeeded` | 회복률 = 1 ÷ (1 − 손실률) − 1  → −50%면 +100% |
| `var99` | VaR 99% = 기대수익 − 2.326 × 변동성 |
| `totalScore` | 성장/30 + 해자/30 + 밸류/20 + 모멘텀/20 |
| `allocate` | 점수 → 밴드 배정 → 밴드 내 비례 조정 → 정규화 → 밴드 클램프 → 잔여 현금 |

### 차등배분 알고리즘
1. 투자점수로 밴드 배정 — Core(75점+) / Sub(55점+) / Watch(그 외)
2. 밴드 하한 + (밴드 폭 × 밴드 내 상대 위치)로 원시 비중 산출
3. 합계 100% 기준 정규화 후 밴드 상·하한으로 클램프
4. 100%에 못 미치는 잔여분은 **현금 버퍼**로 남김

예) 85 / 73 / 65점 → 40% Core · 25% Sub · 25% Sub · 10% 현금

### 종목명 추출 (`extractTickers`)
AI 답변에서 4가지 패턴을 훑습니다.
- 마크다운 표 행 — `| 1 | SK하이닉스 | ... |` (첫 칸이 숫자면 둘째 칸)
- 번호 목록 — `1. **SK하이닉스** (000660)`
- 볼드 강조 — `**한미반도체**`
- 불릿 — `- 이오테크닉스: 어닐링 성장`

종목코드 `(000660)`, 마크다운 기호, 콜론 이후 설명을 제거하고
'종목·순위·현재가·추천·근거' 등 표 머리글 단어를 걸러냅니다.

## 4. 프롬프트 체계 (`prompts.js`)

모든 프롬프트는 동일한 골격을 따릅니다.

```
[R - Role]         20년 경력 CFA 애널리스트 페르소나 (고정)
[I - Instruction]  단계별 지시 + WHY / HOW / OUTPUT
[C - Context]      시장·기간·위험성향 + 판정 확신도 요구
[E - Example]      결과 표 형식 지정
[시세 앵커]         현재가·PER·PBR·시총·52주 밴드 + 조회 시점
[필수 규칙]         할루시네이션 차단 7개 항목 (자동 부착)
```

`compose()` 가 블록을 결합하고 `guardBlock()` 을 **항상** 마지막에 붙입니다 —
어떤 경로로 프롬프트를 생성하든 신뢰성 룰이 빠질 수 없는 구조입니다.

## 5. UI 규칙

- **이벤트 위임**: `document.body` 한 곳에서 `data-route` · `data-action` · `data-bind` ·
  `data-pick` · `data-val` · `data-target` · `data-score` · `data-prob` 속성을 처리
- **지연 재렌더**: 계산에 영향을 주는 입력은 `change` 시 `setTimeout(0)` 으로 재렌더를 미루고,
  재렌더 후 포커스와 캐럿 위치를 복원 — 필드 간 이동 중 입력이 사라지는 문제를 방지
- **XSS**: 사용자 입력(AI 답변·종목명)은 `esc()` 로 이스케이프한 뒤 템플릿에 삽입
- **반응형**: 900px 이하에서 사이드바가 상단 가로 배치로 전환, 표는 가로 스크롤
