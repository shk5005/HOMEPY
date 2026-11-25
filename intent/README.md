# intent/

모든 개발의 출발점. 코드보다 먼저, **무엇을 원하는지 · 왜 원하는지 · 어떤 제약이 있는지**를 적는다.
(Anthropic, *The AI-native SDLC playbook*, 2026-08-21 — Plan 단계 산출물)

## 흐름

```
intent.md (Plan) → spec.md (Design) → plan.md (Build) → 테스트 → PR/리뷰 → 장애 기록 → 새 intent.md
```

출발 경로는 세 가지: 아이디어 · 티켓 · 장애 알림. 어느 쪽이든 intent.md부터 만든다.

## 사용법

1. `_template.md`를 복사해 `YYYY-MM-DD-<짧은-이름>.md`로 만든다.
2. Claude와 브레인스토밍해 채운다. 예시 프롬프트:

   > 코드는 아직 쓰지 마. 내가 해결하려는 문제를 설명할 테니 분석가처럼
   > 범위·사용자·제약·성공 기준을 하나씩 질문해서 `intent/_template.md` 형식으로
   > 초안을 만들어줘. 내가 말하지 않은 내용은 추측하지 말고 Open questions에 넣어.

3. Claude가 잘못 이해한 부분은 요청자가 직접 고친다.
4. 프로덕트 오너(1인 프로젝트면 본인)가 검토한다. 승인 시 `Status: Accepted`로 바꿔 merge,
   거부 시 `Rejected`로 남기거나 PR을 닫는다. 커밋 이력이 곧 결정 기록이다.
5. 승인된 intent를 근거로 spec.md를 만든다. Open questions는 spec 단계에서 답하거나
   명시적으로 넘긴다 — 조용히 가정으로 바뀌지 않게 한다.

## 원칙

- intent에는 구현 방법을 쓰지 않는다 (그건 spec/plan의 몫).
- 모르는 것은 Open questions에 남긴다. 추측으로 채우지 않는다.
- 템플릿 섹션은 플레이북의 예시 템플릿 기준이며 정식 스키마는 아니다. 필요하면 조정한다.
