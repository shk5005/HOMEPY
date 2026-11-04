# HOMEPY — 부동산 투자 의사결정 시스템 설계서

**설계일**: 2026-11-04
**아키텍처**: TypeDB 온톨로지 + Palantir Foundry 레이어 구조 (오픈소스 하이브리드)
**1차 목표**: 투자 의사결정 지원 시스템

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [전체 아키텍처 (L1~L5)](#2-전체-아키텍처)
3. [TypeDB 온톨로지 스키마](#3-typedb-온톨로지-스키마)
4. [데이터 파이프라인](#4-데이터-파이프라인)
5. [추론엔진 및 투자 시그널](#5-추론엔진-및-투자-시그널)
6. [API 및 애플리케이션](#6-api-및-애플리케이션)
7. [확장 로드맵](#7-확장-로드맵)
8. [기술 스택](#8-기술-스택)
9. [프로젝트 디렉터리 구조](#9-프로젝트-디렉터리-구조)

---

## 1. 시스템 개요

### 1.1 비전

TypeDB의 TypeQL 온톨로지 방식(실시간 추론엔진, 지식그래프)과 Palantir Foundry의 풀스택 플랫폼 아키텍처(데이터 파이프라인, 분석 워크플로우)를 결합하여 부동산 투자 의사결정을 데이터 기반으로 지원하는 시스템.

### 1.2 핵심 원칙

- **온톨로지 우선**: 부동산 도메인 지식을 엔티티-관계-속성-규칙으로 구조화
- **추론 기반 발견**: 숨겨진 관계와 기회/위험을 규칙 기반 추론으로 자동 탐지
- **근거 역추적**: 모든 시그널은 원시 데이터까지 역추적 가능
- **편향 감지**: 행동경제학적 인지 편향을 데이터로 탐지·경고
- **Red Team Protocol**: 낙관적 조언자가 아닌 독립적 투자 검증 시스템

### 1.3 Storage 이중 구조

- **TypeDB**: 온톨로지(엔티티·관계·규칙), 추론 실행, 지식그래프 탐색
- **TimescaleDB**: 시계열 원시 데이터(실거래가, 금리, 인구 등), 대량 집계

---

## 2. 전체 아키텍처

Palantir Foundry 5개 레이어를 오픈소스 스택으로 매핑합니다.

```
┌─────────────────────────────────────────────────────┐
│  L5. Application Layer (의사결정 UI)                  │
│      Streamlit Dashboard + FastAPI                   │
├─────────────────────────────────────────────────────┤
│  L4. Analytics & Decision Layer (분석/추론)            │
│      Python Inference Engine + TypeDB Rules          │
├─────────────────────────────────────────────────────┤
│  L3. Ontology Layer (온톨로지 지식그래프)               │
│      TypeDB (Entity-Relation-Attribute + Rules)      │
├─────────────────────────────────────────────────────┤
│  L2. Data Integration Layer (파이프라인)               │
│      Prefect (오케스트레이션) + Python ETL             │
├─────────────────────────────────────────────────────┤
│  L1. Data Connection Layer (데이터 소스 연결)          │
│      API Collectors + Web Crawlers                   │
├─────────────────────────────────────────────────────┤
│  Storage: TypeDB (온톨로지) ◄──► TimescaleDB (시계열)  │
└─────────────────────────────────────────────────────┘
```

| 레이어 | Palantir 대응 | 구현 | 역할 |
|--------|-------------|------|------|
| L1 | Data Connection | Python API/Crawlers | 17개 소스 데이터 수집 |
| L2 | Pipeline Builder | Prefect + Python ETL | 정제, 변환, 품질 검증, 적재 |
| L3 | Ontology | TypeDB + TypeQL | 7대 도메인 지식 구조화, 추론 규칙 |
| L4 | Quiver/Contour | Python + TypeDB Rules | 2단 추론, 투자 시그널, 편향 감지 |
| L5 | Slate/Workshop | Streamlit + FastAPI | 대시보드, 시뮬레이션, 포트폴리오 |

---

## 3. TypeDB 온톨로지 스키마

### 3.1 7대 도메인 엔티티

#### Domain 1: 공간 계층

```typeql
define
  region sub entity,
    owns region-code, owns region-name;

  district sub entity,
    owns district-code, owns district-name,
    owns regulation-zone-type;

  dong sub entity,
    owns dong-code, owns dong-name,
    owns land-transaction-permit;

  complex sub entity,
    owns complex-id, owns complex-name,
    owns total-units, owns built-year,
    owns floor-area-ratio, owns building-coverage,
    owns reconstruction-eligible,
    owns safety-grade,
    owns price-per-sqm,
    owns district-avg-price;

  unit-type sub entity,
    owns area-sqm, owns room-count, owns unit-count;
```

#### Domain 2: 거시경제

```typeql
define
  macro-indicator sub entity, abstract;

  interest-rate sub macro-indicator,
    owns indicator-date,
    owns base-rate,
    owns cd-rate-91d,
    owns cofix-rate,
    owns treasury-3y,
    owns treasury-10y,
    owns mortgage-rate-avg,
    owns rate-direction;

  exchange-rate sub macro-indicator,
    owns indicator-date,
    owns usd-krw,
    owns usd-krw-change-pct,
    owns capital-flow-direction;

  liquidity sub macro-indicator,
    owns indicator-date,
    owns m2-supply,
    owns m2-growth-rate,
    owns household-credit,
    owns household-credit-growth,
    owns mortgage-balance-total;

  price-index sub macro-indicator,
    owns indicator-date,
    owns cpi,
    owns cpi-change-yoy,
    owns gdp-growth-rate,
    owns unemployment-rate;
```

#### Domain 3: 부동산 사이클

```typeql
define
  real-estate-cycle sub entity,
    owns cycle-date,
    owns cycle-phase,
    owns cycle-sub-phase,
    owns leading-index,
    owns coincident-index,
    owns lagging-index,
    owns transaction-volume,
    owns volume-yoy-change,
    owns price-momentum,
    owns inventory-months;

  cycle-observation sub entity,
    owns observation-date,
    owns local-cycle-phase,
    owns price-change-mom,
    owns price-change-yoy,
    owns jeonse-price-change,
    owns sale-to-list-ratio;
```

#### Domain 4: 금융/대출

```typeql
define
  loan-product sub entity,
    owns loan-id, owns loan-name,
    owns loan-type,
    owns lender-type,
    owns interest-type,
    owns current-rate-min,
    owns current-rate-max,
    owns max-term-years;

  loan-regulation sub entity,
    owns regulation-id, owns regulation-name,
    owns regulation-type,
    owns effective-date, owns expiry-date;

  loan-regulation-rule sub entity,
    owns rule-id,
    owns target-area-type,
    owns target-housing-type,
    owns target-price-threshold,
    owns buyer-type,
    owns ltv-limit,
    owns dti-limit,
    owns dsr-limit,
    owns dsr-stress-rate;
```

#### Domain 5: 세제

```typeql
define
  tax-regime sub entity, abstract,
    owns tax-id, owns tax-name,
    owns effective-date, owns expiry-date;

  acquisition-tax sub tax-regime,
    owns acq-tax-description;

  acquisition-tax-rate sub entity,
    owns rate-id, owns buyer-type,
    owns housing-price-bracket, owns area-type,
    owns tax-rate-pct, owns surtax-rate-pct;

  capital-gains-tax sub tax-regime,
    owns cgt-description;

  cgt-rate-rule sub entity,
    owns rule-id, owns holding-period,
    owns residence-period, owns owner-count,
    owns area-type, owns base-rate-pct,
    owns surcharge-pct, owns long-term-deduction-pct,
    owns exemption-conditions;

  comprehensive-re-tax sub tax-regime,
    owns crt-description;

  crt-rate-rule sub entity,
    owns rule-id, owns owner-type,
    owns owner-count, owns taxable-base-bracket,
    owns tax-rate-pct, owns deduction-threshold;

  inheritance-tax sub tax-regime,
    owns inh-description;

  gift-tax sub tax-regime,
    owns gift-description;

  gift-tax-rate sub entity,
    owns rate-id, owns relationship-type,
    owns taxable-bracket, owns tax-rate-pct,
    owns deduction-amount;

  property-tax sub tax-regime,
    owns pt-description;
```

#### Domain 6: 규제/정책

```typeql
define
  policy sub entity,
    owns policy-id, owns policy-name,
    owns policy-category,
    owns policy-type,
    owns announcement-date,
    owns effective-date, owns expiry-date,
    owns policy-description;

  zone-designation sub entity,
    owns designation-id, owns zone-type,
    owns designation-date, owns release-date,
    owns is-active;

  price-control sub entity,
    owns control-id, owns control-type,
    owns control-detail, owns effective-date;

  subscription-regulation sub entity,
    owns subscription-id, owns target-area-type,
    owns required-saving-period,
    owns residency-requirement,
    owns ownership-restriction;
```

#### Domain 7: 수요/공급

```typeql
define
  population-data sub entity,
    owns data-date, owns total-population,
    owns household-count, owns household-growth-rate,
    owns avg-household-size, owns age-distribution-json;

  migration-data sub entity,
    owns data-date, owns net-migration,
    owns in-migration, owns out-migration;

  income-data sub entity,
    owns data-date, owns median-household-income,
    owns pir, owns income-growth-rate;

  supply-data sub entity,
    owns data-date, owns permits-issued,
    owns construction-starts, owns completions,
    owns presale-volume;

  unsold-inventory sub entity,
    owns data-date, owns unsold-total,
    owns unsold-after-completion, owns unsold-change-mom;

  reconstruction-supply sub entity,
    owns data-date, owns redevelopment-units,
    owns reconstruction-units, owns expected-year;
```

#### 인프라 + 개발호재 + 시장심리

```typeql
define
  infrastructure sub entity,
    owns infra-id, owns infra-name,
    owns infra-type, owns infra-status;

  development-project sub entity,
    owns project-id, owns project-name,
    owns project-type, owns project-stage,
    owns expected-completion;

  market-sentiment sub entity,
    owns sentiment-date,
    owns buyer-sentiment, owns seller-sentiment,
    owns jeonse-ratio, owns fear-greed-index,
    owns search-trend-index;
```

### 3.2 관계 (Relation)

```typeql
define

# 공간 계층
spatial-hierarchy sub relation,
  relates parent, relates child;
region plays spatial-hierarchy:parent;
district plays spatial-hierarchy:child;
district plays spatial-hierarchy:parent;
dong plays spatial-hierarchy:child;
dong plays spatial-hierarchy:parent;
complex plays spatial-hierarchy:child;

has-unit-type sub relation,
  relates complex-owner, relates type-spec;
complex plays has-unit-type:complex-owner;
unit-type plays has-unit-type:type-spec;

# 인프라 접근성
accessibility sub relation,
  relates location, relates facility,
  owns distance-meter, owns travel-time-min;
complex plays accessibility:location;
dong plays accessibility:location;
infrastructure plays accessibility:facility;

# 거시경제 → 사이클
macro-drives-cycle sub relation,
  relates macro-factor, relates cycle-state,
  owns correlation-strength, owns lag-months;
macro-indicator plays macro-drives-cycle:macro-factor;
real-estate-cycle plays macro-drives-cycle:cycle-state;

rate-affects-loan sub relation,
  relates rate-change, relates affected-loan,
  owns rate-pass-through-pct;
interest-rate plays rate-affects-loan:rate-change;
loan-product plays rate-affects-loan:affected-loan;

# 지역 지정/해제
zone-applied-to sub relation,
  relates designation, relates target-district;
zone-designation plays zone-applied-to:designation;
district plays zone-applied-to:target-district;
dong plays zone-applied-to:target-district;

# 대출규제 적용
regulation-applies sub relation,
  relates rule-source, relates rule-detail,
  owns applicable-area-type;
loan-regulation plays regulation-applies:rule-source;
loan-regulation-rule plays regulation-applies:rule-detail;

loan-constraint sub relation,
  relates constraint-rule, relates constrained-area,
  owns max-borrowable-pct;
loan-regulation-rule plays loan-constraint:constraint-rule;
district plays loan-constraint:constrained-area;

# 세제 적용
tax-applies-to sub relation,
  relates tax-rule, relates taxed-area,
  owns effective-rate-pct;
acquisition-tax-rate plays tax-applies-to:tax-rule;
district plays tax-applies-to:taxed-area;

cgt-applies-to sub relation,
  relates cgt-rule, relates taxed-area;
cgt-rate-rule plays cgt-applies-to:cgt-rule;
district plays cgt-applies-to:taxed-area;

crt-applies-to sub relation,
  relates crt-rule, relates taxed-complex;
crt-rate-rule plays crt-applies-to:crt-rule;
complex plays crt-applies-to:taxed-complex;

# 정책 영향
policy-impact sub relation,
  relates regulation, relates affected-area,
  owns impact-channel, owns impact-direction,
  owns impact-strength, owns expected-lag-months;
policy plays policy-impact:regulation;
district plays policy-impact:affected-area;

policy-targets-tax sub relation,
  relates policy-source, relates modified-tax;
policy plays policy-targets-tax:policy-source;
tax-regime plays policy-targets-tax:modified-tax;

# 수요/공급
demand-in-area sub relation,
  relates demand-data, relates demand-area;
population-data plays demand-in-area:demand-data;
migration-data plays demand-in-area:demand-data;
income-data plays demand-in-area:demand-data;
district plays demand-in-area:demand-area;

supply-in-area sub relation,
  relates supply-data, relates supply-area;
supply-data plays supply-in-area:supply-data;
unsold-inventory plays supply-in-area:supply-data;
reconstruction-supply plays supply-in-area:supply-data;
district plays supply-in-area:supply-area;

# 사이클 관측
cycle-observed-at sub relation,
  relates observation, relates observed-district;
cycle-observation plays cycle-observed-at:observation;
district plays cycle-observed-at:observed-district;

# 개발호재
development-influence sub relation,
  relates project, relates beneficiary,
  owns influence-radius-km, owns expected-premium-pct;
development-project plays development-influence:project;
complex plays development-influence:beneficiary;
dong plays development-influence:beneficiary;

# 심리
sentiment-observation sub relation,
  relates observed-area, relates sentiment-data;
district plays sentiment-observation:observed-area;
market-sentiment plays sentiment-observation:sentiment-data;

# 비교 대상
comparable sub relation,
  relates subject, relates comparison,
  owns similarity-score;
complex plays comparable:subject;
complex plays comparable:comparison;
```

### 3.3 추론 규칙 (Rules)

#### Rule Group 1: 거시경제 → 시장 전환

```typeql
define

rule monetary-easing-signal:
  when {
    $ir isa interest-rate, has rate-direction "falling", has indicator-date $d1;
    $lq isa liquidity, has m2-growth-rate $m2g, has indicator-date $d2;
    $d1 == $d2; $m2g > 5.0;
  } then {
    (trigger: $ir, amplifier: $lq) isa recovery-signal;
  };

rule rate-hike-pressure:
  when {
    $ir isa interest-rate, has base-rate $br, has rate-direction "rising";
    $lq isa liquidity, has household-credit-growth $hcg;
    $hcg > 6.0; $br > 3.0;
  } then {
    (pressure-source: $ir, debt-risk: $lq) isa downward-pressure;
  };
```

#### Rule Group 2: 대출 규제 → 구매력 제약

```typeql
define

rule multi-owner-loan-block:
  when {
    $zd isa zone-designation, has zone-type "adjusted-target", has is-active true;
    $dist isa district;
    (designation: $zd, target-district: $dist) isa zone-applied-to;
    $lr isa loan-regulation-rule,
      has target-area-type "adjusted-target",
      has buyer-type "multi-owner",
      has ltv-limit $ltv;
    $ltv <= 0;
  } then {
    (blocked-area: $dist, blocking-rule: $lr) isa loan-blocked-signal;
  };

rule dsr-purchasing-power:
  when {
    $lr isa loan-regulation-rule, has dsr-limit $dsr, has dsr-stress-rate $stress;
    $ir isa interest-rate, has mortgage-rate-avg $mr;
    $dist isa district;
    (constraint-rule: $lr, constrained-area: $dist) isa loan-constraint;
    $effective-rate = $mr + $stress;
    $effective-rate > 5.5;
  } then {
    (constrained-district: $dist, cause: $lr) isa purchasing-power-squeeze;
  };
```

#### Rule Group 3: 세금 부담 → 거래/보유

```typeql
define

rule cgt-lockin-effect:
  when {
    $cgt isa cgt-rate-rule, has area-type "adjusted-target",
      has owner-count $oc, has surcharge-pct $sc;
    $oc >= 2; $sc >= 20;
    $dist isa district;
    (cgt-rule: $cgt, taxed-area: $dist) isa cgt-applies-to;
    $zd isa zone-designation, has zone-type "adjusted-target", has is-active true;
    (designation: $zd, target-district: $dist) isa zone-applied-to;
  } then {
    (locked-area: $dist, locking-tax: $cgt) isa tax-lockin-signal;
  };

rule crt-selling-pressure:
  when {
    $crt isa crt-rate-rule, has owner-count $oc, has tax-rate-pct $rate;
    $oc >= 2; $rate >= 1.2;
    $c isa complex;
    (crt-rule: $crt, taxed-complex: $c) isa crt-applies-to;
  } then {
    (pressured-complex: $c, tax-cause: $crt) isa holding-cost-pressure;
  };

rule acquisition-tax-relief:
  when {
    $at1 isa acquisition-tax-rate, has buyer-type "multi-owner",
      has area-type "adjusted-target", has tax-rate-pct $old-rate;
    $at2 isa acquisition-tax-rate, has buyer-type "multi-owner",
      has area-type "non-regulated", has tax-rate-pct $new-rate;
    $old-rate > $new-rate;
    $dist isa district;
    $zd isa zone-designation, has zone-type "adjusted-target", has is-active false;
    (designation: $zd, target-district: $dist) isa zone-applied-to;
  } then {
    (opportunity-area: $dist) isa tax-relief-opportunity;
  };
```

#### Rule Group 4: 수요/공급 불균형

```typeql
define

rule supply-shortage-pressure:
  when {
    $sd isa supply-data, has completions $comp;
    $md isa migration-data, has net-migration $mig;
    $dist isa district;
    (supply-data: $sd, supply-area: $dist) isa supply-in-area;
    (demand-data: $md, demand-area: $dist) isa demand-in-area;
    $mig > 1000; $comp < 3000;
  } then {
    (shortage-area: $dist) isa supply-demand-gap-up;
  };

rule oversupply-risk:
  when {
    $sd isa supply-data, has completions $comp;
    $ui isa unsold-inventory, has unsold-total $unsold;
    $md isa migration-data, has net-migration $mig;
    $dist isa district;
    (supply-data: $sd, supply-area: $dist) isa supply-in-area;
    (supply-data: $ui, supply-area: $dist) isa supply-in-area;
    (demand-data: $md, demand-area: $dist) isa demand-in-area;
    $comp > 10000; $mig < 0; $unsold > 500;
  } then {
    (oversupplied-area: $dist) isa supply-demand-gap-down;
  };
```

#### Rule Group 5: 가치 평가

```typeql
define

rule undervalued-complex:
  when {
    $c isa complex, has complex-id $cid;
    $d isa dong;
    (parent: $d, child: $c) isa spatial-hierarchy;
    (location: $c, facility: $inf) isa accessibility, has distance-meter $dist;
    $dist < 500;
    $inf isa infrastructure, has infra-type "subway";
    $c has price-per-sqm $price;
    $c has district-avg-price $avg;
    $price < $avg;
  } then {
    (subject: $c) isa undervalued-signal;
  };
```

#### Rule Group 6: 복합 투자 시그널

```typeql
define

rule strong-buy-candidate:
  when {
    $c isa complex;
    (subject: $c) isa undervalued-signal;
    $dist isa district; $dong isa dong;
    (parent: $dist, child: $dong) isa spatial-hierarchy;
    (parent: $dong, child: $c) isa spatial-hierarchy;
    (trigger: $ir, amplifier: $lq) isa recovery-signal;
    (opportunity-area: $dist) isa tax-relief-opportunity;
  } then {
    (buy-candidate: $c, macro-support: $ir, tax-support: $dist) isa strong-buy-signal;
  };

rule cycle-peak-warning:
  when {
    $rc isa real-estate-cycle, has cycle-phase "peak";
    $ir isa interest-rate, has rate-direction "rising";
    $co isa cycle-observation, has price-change-yoy $yoy;
    $yoy > 15.0;
    $dist isa district;
    (observation: $co, observed-district: $dist) isa cycle-observed-at;
  } then {
    (warning-area: $dist, cycle-risk: $rc) isa cycle-peak-danger;
  };

rule reverse-jeonse-risk:
  when {
    $ms isa market-sentiment, has jeonse-ratio $jr; $jr > 0.75;
    $ir isa interest-rate, has rate-direction "rising";
    $sd isa supply-data, has completions $comp; $comp > 5000;
    $dist isa district;
    (observed-area: $dist, sentiment-data: $ms) isa sentiment-observation;
    (supply-data: $sd, supply-area: $dist) isa supply-in-area;
  } then {
    (risk-area: $dist) isa reverse-jeonse-danger;
  };

rule gap-investment-risk:
  when {
    $dist isa district;
    (observed-area: $dist, sentiment-data: $s) isa sentiment-observation;
    $s isa market-sentiment, has jeonse-ratio $jr, has buyer-sentiment $bs;
    $jr > 0.70; $bs < 40;
  } then {
    (risky-area: $dist) isa gap-risk-signal;
  };

rule development-spillover:
  when {
    $dp isa development-project, has project-type "GTX";
    $c isa complex;
    (project: $dp, beneficiary: $c) isa development-influence,
      has influence-radius-km $r;
    $r <= 2.0;
  } then {
    (candidate: $c, catalyst: $dp) isa transport-premium;
  };

rule land-permit-reconstruction-play:
  when {
    $dong isa dong, has land-transaction-permit true;
    $c isa complex;
    (parent: $dong, child: $c) isa spatial-hierarchy;
    $c has reconstruction-eligible true;
    $c has built-year $yr; $yr < 1990;
  } then {
    (long-term-target: $c, regulated-dong: $dong) isa reconstruction-deep-value;
  };
```

### 3.4 TimescaleDB 분담표

| 도메인 | TimescaleDB | TypeDB |
|--------|-------------|--------|
| 거시경제 | 금리·환율·M2 일별 시계열 | 방향성, 임계값 판단용 스냅샷 |
| 부동산사이클 | 가격지수, 거래량 시계열 | 사이클 위상, 선행지수 최신값 |
| 대출 | 대출 잔액·금리 시계열 | 규제 규칙(LTV/DTI/DSR), 구매력 추론 |
| 세제 | 세수·실효세율 시계열 | 세율 규칙 체계, 세금 영향 추론 |
| 규제/정책 | 지정/해제 이력 | 현행 지정 상태, 정책 영향 관계 |
| 수요 | 인구·이동·소득 시계열 | 수급 갭 추론, PIR 비교 |
| 공급 | 인허가·착공·준공·미분양 시계열 | 공급과잉/부족 추론 |
| 가격 | 실거래가 원시 데이터 (수백만 건) | 단지별 최신 평당가 (동기화) |
| 심리 | 심리지수·검색트렌드 시계열 | 공포/탐욕 상태, 역전세 리스크 추론 |

---

## 4. 데이터 파이프라인

### 4.1 파이프라인 구조

```
Raw Data Lake → Stage 1 (Clean) → Stage 2 (Transform) → Stage 3 (Load & Sync)
                                                              ↓
                                              TypeDB ◄──► TimescaleDB
```

### 4.2 데이터 소스 수집기 (17개)

| # | 수집기 | 소스 | 주기 | 도메인 |
|---|--------|------|------|--------|
| 1 | `collect_real_trade` | 국토부 실거래가 API | 일 1회 | 가격 |
| 2 | `collect_complex_info` | 국토부 건축물대장 API | 주 1회 | 공간 |
| 3 | `collect_official_price` | 국토부 공시가격 API | 연 1회 | 가격·세제 |
| 4 | `collect_price_index` | 한국부동산원 API | 주 1회 | 사이클 |
| 5 | `collect_interest_rate` | 한국은행 ECOS API | 일 1회 | 거시경제 |
| 6 | `collect_exchange_rate` | 한국은행 ECOS API | 일 1회 | 거시경제 |
| 7 | `collect_liquidity` | 한국은행 ECOS API | 월 1회 | 거시경제 |
| 8 | `collect_macro_index` | 통계청 KOSIS API | 월 1회 | 거시경제 |
| 9 | `collect_population` | 통계청 KOSIS API | 월 1회 | 수요 |
| 10 | `collect_migration` | 통계청 KOSIS API | 월 1회 | 수요 |
| 11 | `collect_income` | 통계청 KOSIS API | 분기 1회 | 수요 |
| 12 | `collect_supply` | 국토부 주택통계 API | 월 1회 | 공급 |
| 13 | `collect_unsold` | 국토부 미분양 API | 월 1회 | 공급 |
| 14 | `collect_loan_rate` | 은행연합회 API + 크롤러 | 주 1회 | 금융 |
| 15 | `collect_regulation` | 국토부 고시 + 크롤러 | 이벤트 기반 | 규제 |
| 16 | `collect_tax_rule` | 국세법령정보 + TaxDoctor | 이벤트 기반 | 세제 |
| 17 | `collect_sentiment` | 한국부동산원 + 네이버 트렌드 | 주 1회 | 심리 |

### 4.3 ETL 3단계

- **Stage 1 (Clean & Validate)**: 스키마 검증, 결측치 처리, 이상치 탐지, 중복 제거, 코드 표준화
- **Stage 2 (Transform & Enrich)**: 평당가 계산, 이동평균, 사이클 위상 분류, 수급 갭 계산, PIR, 실효세율 시뮬레이션, 공포/탐욕 지수 합성
- **Stage 3 (Load & Sync)**: TimescaleDB 대량 적재, TypeDB 엔티티/관계 UPSERT, 집계 속성 동기화, 추론 트리거

### 4.4 오케스트레이션 스케줄

| 스케줄 | 수집기 | 변환 | 비고 |
|--------|--------|------|------|
| Daily 06:00 KST | 실거래가, 금리, 환율 | 가격 지표 | 핵심 일일 업데이트 |
| Weekly 월 07:00 | 가격지수, 대출금리, 심리, 단지정보 | 사이클+심리 | 주간 종합 |
| Monthly 15일 08:00 | 유동성, 인구, 이동, 공급, 미분양, CPI | 거시+수급+사이클 재분류 | 월간 종합 |
| Event-Driven | 규제변경, 세법변경 | 검증 후 적재 | 수동 검토 게이트 |
| Annual | 공시가격 | 세제 기준 갱신 | 공시가 발표 시 |
| Post-Load | - | 속성동기화→추론→시그널→알림 | 매 Load 후 자동 |

### 4.5 DB 간 동기화

- **① TimescaleDB → TypeDB**: 집계 속성 (평당가, 평균가, 금리방향 등) — 매 Load 후 즉시
- **② TypeDB → TimescaleDB**: 추론 결과 시그널 — 추론 실행 후 즉시, 이력 보존
- **③ 양방향 → Catalog**: 데이터 계보 메타데이터 — Append-only

### 4.6 데이터 품질 게이트

| 전환 | 기준 |
|------|------|
| Raw → Cleaned | 결측률 ≤5%, 중복률 ≤1%, 스키마 일치 |
| Cleaned → Transformed | 이상치 ≤2%, 참조 무결성, 시계열 연속성 |
| Transformed → Loaded | 건수 변동 ≤10%, 값 범위 검증, 소스 간 교차 검증 |

---

## 5. 추론엔진 및 투자 시그널

### 5.1 2단 추론 아키텍처

- **1차 추론 (TypeDB Native)**: 관계 기반 패턴 매칭, 쿼리 시점 자동 추론
- **2차 추론 (Python Engine)**: 시계열 분석, 다중 팩터 스코어링, 행동경제학 편향 감지, 시나리오 시뮬레이션

### 5.2 다중 팩터 투자 스코어링 (14팩터)

```
가격 팩터 (25%)
  valuation_gap:        0.10   적정가 대비 괴리율
  price_momentum:       0.08   가격 모멘텀 (3/6/12M)
  jeonse_ratio_trend:   0.07   전세가율 추세

거시경제 팩터 (15%)
  interest_rate_cycle:  0.08   금리 사이클 위치
  liquidity_trend:      0.07   유동성 방향

수급 팩터 (20%)
  supply_demand_gap:    0.10   수급 갭
  unsold_risk:          0.05   미분양 리스크
  migration_momentum:   0.05   인구 이동 모멘텀

입지/인프라 팩터 (15%)
  transport_access:     0.08   교통 접근성
  development_upside:   0.07   개발 호재 프리미엄

규제/세제 팩터 (10%)
  regulation_impact:    0.05   규제 영향 (+ = 완화)
  tax_burden:           0.05   세금 부담도 (역수)

사이클 팩터 (5%)
  cycle_position:       0.05   지역 사이클 위치

심리 팩터 (10%)
  sentiment_divergence: 0.05   심리-펀더멘탈 괴리
  fear_greed_position:  0.03   공포/탐욕 지수 위치
  search_trend_signal:  0.02   검색 트렌드 이상 신호
```

### 5.3 시나리오 시뮬레이터

핵심 변수 3~5개를 변동시켜 Bull/Base/Bear 시나리오 생성. 각 시나리오에 발생 조건, 핵심 변수, 예상 결과, 선행지표, 무효화 조건을 포함.

### 5.4 행동경제학 편향 감지 (9항목)

| 편향 | 탐지 방법 | 임계값 |
|------|----------|--------|
| Confirmation Bias | 호재/악재 시그널 비율 | positive가 negative의 3배 이상 |
| Anchoring | 참조가격 vs 적정가 비교 | ±20% 이상 괴리 |
| Recency Bias | 3개월 vs 36개월 추세 비교 | 방향 반대 |
| Survivorship Bias | 비교 대상 완전성 | 하락 단지 30% 미만 |
| Availability Heuristic | 검색량-관심 상관 | 상위 10% 지역 편중 |
| Loss Aversion | 손절 기준 이탈 보유 | 고점 대비 -15% 이하 |
| Overconfidence | 확신 vs 근거 수 비교 | High인데 근거 3개 미만 |
| Base Rate Neglect | 기대수익 vs 역사적 평균 | 10년 평균의 2배 이상 |
| Sunk Cost | 근거 소멸 후 보유 | 시그널 2개 이상 소멸 |

### 5.5 최종 출력 형식 (InvestmentVerdict)

Red Team Protocol 준수:

1. 핵심 사실
2. 가장 강력한 투자 논리
3. 가장 강력한 반대 논리
4. 시장이 놓치고 있을 가능성이 있는 변수
5. 가장 중요한 Risk
6. 현재 판단 (매수 검토 / 관망 / 매도 검토 / 판단 유보)
7. 판단의 신뢰도 (High / Medium / Low)
8. 판단을 뒤집을 Kill Switch
9. 앞으로 관찰해야 할 데이터 5개
10. 행동경제학 편향 경고
11. 시나리오 분석
12. 근거 역추적 체인

---

## 6. API 및 애플리케이션

### 6.1 API 도메인 (FastAPI)

| 도메인 | 엔드포인트 | 주요 기능 |
|--------|-----------|----------|
| `/api/v1/ontology/` | 엔티티 조회, 관계 탐색, 지식그래프 | TypeDB 지식그래프 탐색 |
| `/api/v1/analysis/` | 투자 스코어, 시그널, 편향 감지, 비교 | 14팩터 스코어링 + 시그널 |
| `/api/v1/simulation/` | 시나리오, 세금, 대출, 현금흐름 | 시뮬레이션 실행 |
| `/api/v1/market/` | 사이클, 거시지표, 수급, 규제지도, 심리 | 시장 현황 데이터 |
| `/api/v1/portfolio/` | 워치리스트, 보유자산, 알림, 이력 | 개인 포트폴리오 관리 |
| `/api/v1/pipeline/` | 수집 상태, 모니터링, 데이터 품질 | 파이프라인 운영 |

### 6.2 대시보드 (Streamlit, 9페이지)

1. **시장 대시보드**: 거시지표 요약, 사이클 위치도, 규제지역 지도
2. **투자 시그널 보드**: 활성 시그널 목록, 필터, 시그널 카드
3. **단지 심층 분석**: 14팩터 레이더차트, 시나리오, 세금/대출 시뮬
4. **시나리오 시뮬레이션**: Bull/Base/Bear, 민감도 분석
5. **세금 계산기**: 취득세·양도세·종부세 시뮬레이터
6. **대출 한도 계산기**: LTV/DTI/DSR 기반 최대 대출액·월상환액
7. **포트폴리오 관리**: 보유자산 건강도, 워치리스트 알림
8. **온톨로지 시각화**: 지식그래프 인터랙티브 탐색
9. **파이프라인 모니터링**: 수집기 상태, 품질 리포트, 데이터 계보

---

## 7. 확장 로드맵

### 7.1 Phase 구조

| Phase | 내용 | 기간 | 기존 재활용률 |
|-------|------|------|-------------|
| **Phase 0** | 핵심 인프라 (DB 설치, 파이프라인 셋업) | 2개월 | - |
| **Phase 1** | 투자 의사결정 지원 (본 설계 범위) | 3개월 | - |
| **Phase 2** | 시장 모니터링 / 조기경보 | 2개월 | 85% |
| **Phase 3** | 정책 시뮬레이션 | 2개월 | 70% |
| **Phase 4** | 고급 분석 (ML, NLP, 멀티에이전트) | 3개월 | 50% |

### 7.2 Phase 2: 시장 모니터링 / 조기경보

- 이상탐지 엔진 (Z-score, Isolation Forest)
- 조기경보 TypeDB 규칙 추가 (스마트머니 감지, 갭 축소 등)
- 실시간 대시보드 (이상 감지 히트맵, 경보 타임라인)
- 알림 시스템 (Slack/카카오톡)
- 4단계 경보 체계 (WATCH → ADVISORY → WARNING → CRITICAL)

### 7.3 Phase 3: 정책 시뮬레이션

- 정책 영향 전파 그래프 (다단계 추론 체인)
- 세제 변경 시뮬레이터 (가상 세제안 → 포트폴리오 영향)
- 규제 지정/해제 시뮬레이터 (영향 체인 시각화)
- 정책 백테스팅 (과거 정책 재현 → 추론 정확도 검증)

### 7.4 Phase 4: 고급 분석

- ML 가격 예측 (TypeDB 관계 피처 + TimescaleDB 시계열 피처, LightGBM + SHAP)
- 자연어 인터페이스 (자연어 → TypeQL 변환)
- 리포트 자동생성 (InvestmentVerdict → PDF/HTML)
- 멀티에이전트 분석 (Bull/Bear/행동경제학/정책 에이전트 토론)

### 7.5 독립 확장

- 경매 분석 모듈: 법원경매 데이터 연동 + 낙찰가 예측
- 상업용 부동산: 오피스/상가/물류 온톨로지 확장
- 해외 비교: 글로벌 부동산 사이클 비교 분석

---

## 8. 기술 스택

| 레이어 | 기술 | 역할 |
|--------|------|------|
| Runtime | Docker Compose / K8s | 컨테이너 오케스트레이션 |
| Knowledge Graph | TypeDB 2.x | 온톨로지 + 추론 |
| Time-Series DB | TimescaleDB (PostgreSQL) | 시계열 저장·집계 |
| ETL Orchestration | Prefect 2.x | 파이프라인 스케줄링 |
| Data Quality | Great Expectations | 데이터 품질 검증 |
| Data Catalog | 자체 구축 (PostgreSQL) | 메타데이터·Lineage |
| Object Storage | MinIO / Local FS | 원시·정제 데이터 보관 |
| API | FastAPI | REST API 게이트웨이 |
| Dashboard | Streamlit | 분석 대시보드 UI |
| Visualization | Plotly + Folium + Pyvis | 차트 + 지도 + 그래프 |
| ML (Phase 4) | LightGBM + SHAP | 가격 예측 + 설명 |
| LLM (Phase 4) | Claude API | 자연어 + 에이전트 |
| Notification | Slack API + 카카오톡 | 알림 전달 |
| Language | Python 3.11+ | 전체 통합 언어 |

---

## 9. 프로젝트 디렉터리 구조

```
homepy/
├── collectors/                    # L1: 데이터 수집기
│   ├── base.py
│   ├── molit_trade.py
│   ├── molit_building.py
│   ├── molit_official_price.py
│   ├── reb_index.py
│   ├── bok_ecos.py
│   ├── kosis.py
│   ├── molit_supply.py
│   ├── loan_rates.py
│   ├── regulation_monitor.py
│   ├── tax_rule_monitor.py
│   └── sentiment.py
│
├── pipelines/                     # L2: ETL 파이프라인
│   ├── flows/
│   │   ├── daily_flow.py
│   │   ├── weekly_flow.py
│   │   ├── monthly_flow.py
│   │   └── event_flow.py
│   ├── stages/
│   │   ├── clean.py
│   │   ├── transform.py
│   │   └── load.py
│   ├── transformers/
│   │   ├── price_transformer.py
│   │   ├── macro_transformer.py
│   │   ├── cycle_classifier.py
│   │   ├── supply_demand.py
│   │   ├── tax_calculator.py
│   │   └── sentiment_composer.py
│   └── quality/
│       ├── expectations/
│       └── gates.py
│
├── sync/                          # DB 동기화
│   ├── timescale_to_typedb.py
│   ├── typedb_to_timescale.py
│   └── lineage_tracker.py
│
├── inference/                     # L4: 추론엔진
│   ├── scorer.py                  # InvestmentScorer (14팩터)
│   ├── simulator.py               # ScenarioSimulator
│   ├── bias_detector.py           # BiasDetector (9항목)
│   └── verdict.py                 # InvestmentVerdict
│
├── api/                           # L5: API
│   ├── main.py
│   ├── routers/
│   │   ├── ontology.py
│   │   ├── analysis.py
│   │   ├── simulation.py
│   │   ├── market.py
│   │   ├── portfolio.py
│   │   └── pipeline.py
│   ├── services/
│   │   ├── typedb_service.py
│   │   ├── timescale_service.py
│   │   └── tax_engine.py
│   └── models/
│       └── schemas.py
│
├── app/                           # L5: 대시보드
│   ├── main.py
│   ├── pages/
│   │   ├── 01_market_dashboard.py
│   │   ├── 02_signal_board.py
│   │   ├── 03_deep_analysis.py
│   │   ├── 04_scenario_sim.py
│   │   ├── 05_tax_calculator.py
│   │   ├── 06_loan_calculator.py
│   │   ├── 07_portfolio.py
│   │   ├── 08_knowledge_graph.py
│   │   └── 09_pipeline_monitor.py
│   └── components/
│       ├── radar_chart.py
│       ├── cycle_diagram.py
│       ├── regulation_map.py
│       ├── evidence_chain.py
│       ├── bias_warning.py
│       └── signal_card.py
│
├── storage/
│   ├── timescale/
│   │   ├── schema.sql
│   │   └── hypertables.sql
│   └── typedb/
│       ├── schema.tql
│       └── rules.tql
│
├── data/
│   ├── raw/
│   ├── cleaned/
│   ├── transformed/
│   └── catalog/
│
├── docker-compose.yml
├── pyproject.toml
└── README.md
```
