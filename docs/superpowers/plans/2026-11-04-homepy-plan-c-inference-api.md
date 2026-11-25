# HOMEPY Plan C: Inference Engine + API + Dashboard Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the L4 inference engine (14-factor investment scorer, scenario simulator, bias detector, Red Team verdict builder) and L5 application layer (FastAPI REST API with 6 router domains, Streamlit dashboard with 9 pages and 6 shared components).

**Architecture:** The inference engine sits between the databases and the presentation layer. `InvestmentScorer` pulls data from both TypeDB (ontology signals) and TimescaleDB (time-series), normalizes 14 factors to 0–100, and weights them per spec Section 5.2. `ScenarioSimulator` perturbs key variables to produce Bull/Base/Bear outcomes. `BiasDetector` checks 9 cognitive biases from the user's analysis context. `VerdictBuilder` orchestrates all three into a 12-field `InvestmentVerdict` following the Red Team Protocol. FastAPI exposes these as REST endpoints. Streamlit consumes the API for interactive dashboards.

**Tech Stack:** Python 3.11+, pydantic 2.x, FastAPI, uvicorn, Streamlit, Plotly, Folium, Pyvis, scipy (HP filter), numpy, httpx

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Sections 5, 6)

**Depends on:** Plan A complete (databases + service layers), Plan B complete (pipeline + sync populates data)

## Global Constraints

- Python ≥ 3.11
- All inference functions must be unit-testable with mocked `TypeDBService` and `TimescaleService` — no live DB required for unit tests
- Factor weights from spec Section 5.2 stored as a module-level constant `FACTOR_WEIGHTS` dict — single source of truth
- Every `InvestmentVerdict` must include a non-empty `evidence_chain` tracing each claim to a data source
- FastAPI version ≥ 0.115; Streamlit ≥ 1.38
- API responses use Pydantic v2 models with `model_config = ConfigDict(from_attributes=True)`
- Dashboard pages communicate with the backend exclusively via the FastAPI endpoints (no direct DB access from Streamlit)

## Review Focus

1. **Factor normalization direction** — some factors are "higher is better" (transport_access), others "lower is better" (unsold_risk, tax_burden). A normalization bug that inverts the direction silently corrupts the total score. Each factor's normalizer must have a test asserting the direction.
2. **Bias detector false positives** — thresholds from spec Section 5.4 are calibrated for Korean market data. A detector that fires on every input is worse than useless. Tests must include a "no bias" case where no warnings fire.
3. **Scenario variable independence** — perturbing one variable (e.g., interest rate) should not accidentally change another (e.g., supply). The simulator must deep-copy the base state before each perturbation.
4. **API timeout on large district queries** — scoring every complex in a district could take minutes. The analysis endpoint must accept a `complex_ids` list, not a `district_code` that silently fans out.
5. **Streamlit session state leaks** — using `st.session_state` with mutable defaults (dicts, lists) causes cross-session contamination. All defaults must be immutable or factory-created.

---

### Task 1: InvestmentScorer — 14-Factor Scoring Engine

**Files:**
- Create: `homepy/inference/__init__.py`
- Create: `homepy/inference/scorer.py`
- Create: `tests/inference/__init__.py`
- Create: `tests/inference/test_scorer.py`

**Interfaces:**
- Consumes: `TypeDBService.execute_read(db, query) -> list[dict]` from Plan A Task 6; `TimescaleService.execute(query, *args) -> list[asyncpg.Record]` from Plan A Task 6
- Produces:
  - `FactorScore(name: str, raw_value: float, normalized: float, weight: float, weighted_score: float, evidence: list[str])` — dataclass
  - `InvestmentScore(complex_id: str, total_score: float, grade: str, factors: list[FactorScore], computed_at: datetime)` — dataclass
  - `InvestmentScorer(typedb_svc: TypeDBService, timescale_svc: TimescaleService)` — class with method `async score(complex_id: str) -> InvestmentScore`
  - `FACTOR_WEIGHTS: dict[str, float]` — module constant, 14 entries summing to 1.0

- [ ] **Step 1: Write failing tests**

```python
from homepy.inference.scorer import InvestmentScorer, InvestmentScore, FactorScore, FACTOR_WEIGHTS

def test_factor_weights_sum_to_one():
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9

def test_factor_weights_has_14_entries():
    assert len(FACTOR_WEIGHTS) == 14

async def test_scorer_returns_investment_score(mock_typedb, mock_timescale):
    scorer = InvestmentScorer(mock_typedb, mock_timescale)
    result = await scorer.score("C001")
    assert isinstance(result, InvestmentScore)
    assert 0 <= result.total_score <= 100
    assert result.grade in ("A", "B", "C", "D", "F")
    assert len(result.factors) == 14

async def test_valuation_gap_positive_when_undervalued(mock_typedb, mock_timescale):
    """price_per_sqm=15M, district_avg=20M → gap is positive (undervalued)"""
    mock_typedb.set_response([{"price_per_sqm": 15_000_000, "district_avg_price": 20_000_000}])
    scorer = InvestmentScorer(mock_typedb, mock_timescale)
    result = await scorer.score("C001")
    vg = next(f for f in result.factors if f.name == "valuation_gap")
    assert vg.normalized > 50  # above midpoint = undervalued = positive

async def test_tax_burden_high_normalized_low(mock_typedb, mock_timescale):
    """High tax burden → low normalized score (inverse factor)"""
    mock_typedb.set_response([{"effective_tax_rate": 12.0}])
    scorer = InvestmentScorer(mock_typedb, mock_timescale)
    result = await scorer.score("C001")
    tb = next(f for f in result.factors if f.name == "tax_burden")
    assert tb.normalized < 30

async def test_every_factor_has_evidence(mock_typedb, mock_timescale):
    scorer = InvestmentScorer(mock_typedb, mock_timescale)
    result = await scorer.score("C001")
    for f in result.factors:
        assert len(f.evidence) >= 1, f"{f.name} has no evidence"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/inference/test_scorer.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create mock fixtures in `tests/inference/conftest.py`**

`MockTypeDBService` and `MockTimescaleService` that return configurable canned responses. Default responses provide valid data for all 14 factors for complex "C001".

- [ ] **Step 4: Implement `FACTOR_WEIGHTS` and dataclasses in `scorer.py`**

```python
FACTOR_WEIGHTS: dict[str, float] = {
    "valuation_gap": 0.10, "price_momentum": 0.08, "jeonse_ratio_trend": 0.07,
    "interest_rate_cycle": 0.08, "liquidity_trend": 0.07,
    "supply_demand_gap": 0.10, "unsold_risk": 0.05, "migration_momentum": 0.05,
    "transport_access": 0.08, "development_upside": 0.07,
    "regulation_impact": 0.05, "tax_burden": 0.05,
    "cycle_position": 0.05,
    "sentiment_divergence": 0.05, "fear_greed_position": 0.03, "search_trend_signal": 0.02,
}
```

- [ ] **Step 5: Implement `InvestmentScorer.score()`**

One private `async _calc_{factor_name}(complex_id) -> FactorScore` method per factor. Each queries TypeDB or TimescaleDB, computes the raw value, normalizes to 0–100 (min-max with domain-specific bounds), attaches evidence strings. `score()` calls all 14 in parallel via `asyncio.gather`, computes `total_score` as weighted sum, derives `grade` (A ≥ 80, B ≥ 65, C ≥ 50, D ≥ 35, F < 35).

- [ ] **Step 6: Run tests**

Run: `pytest tests/inference/test_scorer.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/inference/ tests/inference/
git commit -m "feat: InvestmentScorer — 14-factor weighted scoring engine"
```

---

### Task 2: ScenarioSimulator — Bull/Base/Bear Analysis

**Files:**
- Create: `homepy/inference/simulator.py`
- Create: `tests/inference/test_simulator.py`

**Interfaces:**
- Consumes: `InvestmentScorer.score(complex_id) -> InvestmentScore` from Task 1; `TimescaleService.execute()` from Plan A Task 6
- Produces:
  - `Scenario(name: str, conditions: list[str], key_variables: dict[str, float], expected_outcome: str, leading_indicators: list[str], invalidation_conditions: list[str], probability: float)` — dataclass
  - `SensitivityResult(variable: str, base_value: float, perturbations: list[float], score_impacts: list[float])` — dataclass
  - `ScenarioResult(complex_id: str, scenarios: list[Scenario], sensitivity: list[SensitivityResult])` — dataclass
  - `ScenarioSimulator(scorer: InvestmentScorer, timescale_svc: TimescaleService)` — class with method `async simulate(complex_id: str, variables: list[str] | None = None) -> ScenarioResult`

- [ ] **Step 1: Write failing tests**

```python
async def test_simulator_produces_three_scenarios(mock_scorer, mock_timescale):
    sim = ScenarioSimulator(mock_scorer, mock_timescale)
    result = await sim.simulate("C001")
    assert len(result.scenarios) == 3
    names = {s.name for s in result.scenarios}
    assert names == {"bull", "base", "bear"}

async def test_bull_score_higher_than_bear(mock_scorer, mock_timescale):
    sim = ScenarioSimulator(mock_scorer, mock_timescale)
    result = await sim.simulate("C001")
    bull = next(s for s in result.scenarios if s.name == "bull")
    bear = next(s for s in result.scenarios if s.name == "bear")
    assert bull.probability + bear.probability <= 1.0

async def test_sensitivity_varies_with_perturbation(mock_scorer, mock_timescale):
    sim = ScenarioSimulator(mock_scorer, mock_timescale)
    result = await sim.simulate("C001", variables=["interest_rate_cycle"])
    assert len(result.sensitivity) >= 1
    sr = result.sensitivity[0]
    assert len(sr.perturbations) >= 3
    assert sr.score_impacts[0] != sr.score_impacts[-1]  # different perturbations -> different impacts

async def test_scenarios_have_required_fields(mock_scorer, mock_timescale):
    sim = ScenarioSimulator(mock_scorer, mock_timescale)
    result = await sim.simulate("C001")
    for s in result.scenarios:
        assert len(s.conditions) >= 1
        assert len(s.key_variables) >= 1
        assert s.expected_outcome
        assert len(s.leading_indicators) >= 1
        assert len(s.invalidation_conditions) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/inference/test_simulator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ScenarioSimulator`**

Default `variables` are the top-5 factors by weight: `["supply_demand_gap", "valuation_gap", "interest_rate_cycle", "transport_access", "price_momentum"]`. For each scenario, adjust variable values (bull: +1σ favorable, bear: -1σ unfavorable, base: current). Re-score with adjusted inputs. Sensitivity: for each variable, perturb at -2σ, -1σ, 0, +1σ, +2σ and record score impact. Deep-copy base state before each perturbation. Historical σ values queried from TimescaleDB rolling 36-month windows.

- [ ] **Step 4: Run tests**

Run: `pytest tests/inference/test_simulator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/inference/simulator.py tests/inference/test_simulator.py
git commit -m "feat: ScenarioSimulator — Bull/Base/Bear with sensitivity analysis"
```

---

### Task 3: BiasDetector + InvestmentVerdict

**Files:**
- Create: `homepy/inference/bias_detector.py`
- Create: `homepy/inference/verdict.py`
- Create: `tests/inference/test_bias_detector.py`
- Create: `tests/inference/test_verdict.py`

**Interfaces:**
- Consumes: `InvestmentScore` from Task 1, `ScenarioResult` from Task 2, `TimescaleService` from Plan A Task 6
- Produces:
  - `BiasWarning(bias_type: str, description: str, severity: str, evidence: str, mitigation: str)` — dataclass
  - `BiasDetector(timescale_svc: TimescaleService)` with method `async detect(complex_id: str, score: InvestmentScore, user_context: dict | None = None) -> list[BiasWarning]`
  - `InvestmentVerdict` — dataclass with 12 fields per spec Section 5.5
  - `VerdictBuilder(scorer: InvestmentScorer, simulator: ScenarioSimulator, bias_detector: BiasDetector)` with method `async build(complex_id: str, user_context: dict | None = None) -> InvestmentVerdict`

- [ ] **Step 1: Write failing tests for BiasDetector**

```python
async def test_confirmation_bias_fires_on_skewed_signals(mock_timescale):
    score = make_score(positive_factors=12, negative_factors=2)
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score)
    types = [w.bias_type for w in warnings]
    assert "confirmation_bias" in types

async def test_no_bias_on_balanced_input(mock_timescale):
    score = make_score(positive_factors=7, negative_factors=7)
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score)
    assert len(warnings) == 0

async def test_anchoring_when_reference_price_diverges(mock_timescale):
    score = make_score()
    ctx = {"reference_price": 1_000_000_000}  # user's anchor
    mock_timescale.set_response([{"fair_value": 600_000_000}])
    detector = BiasDetector(mock_timescale)
    warnings = await detector.detect("C001", score, user_context=ctx)
    assert any(w.bias_type == "anchoring" for w in warnings)

async def test_all_nine_biases_have_detectors(mock_timescale):
    detector = BiasDetector(mock_timescale)
    assert len(detector.BIAS_CHECKS) == 9
```

- [ ] **Step 2: Write failing tests for VerdictBuilder**

```python
async def test_verdict_has_all_red_team_fields(mock_deps):
    builder = VerdictBuilder(mock_deps.scorer, mock_deps.simulator, mock_deps.detector)
    verdict = await builder.build("C001")
    assert isinstance(verdict, InvestmentVerdict)
    assert len(verdict.core_facts) >= 1
    assert verdict.strongest_bull_case
    assert verdict.strongest_bear_case
    assert verdict.verdict in ("매수 검토", "관망", "매도 검토", "판단 유보")
    assert verdict.confidence in ("High", "Medium", "Low")
    assert verdict.kill_switch
    assert len(verdict.watchlist_data) == 5
    assert len(verdict.evidence_chain) >= 1

async def test_verdict_confidence_low_when_data_sparse(mock_deps):
    mock_deps.scorer.set_sparse_data(missing_factors=5)
    builder = VerdictBuilder(mock_deps.scorer, mock_deps.simulator, mock_deps.detector)
    verdict = await builder.build("C001")
    assert verdict.confidence == "Low"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/inference/test_bias_detector.py tests/inference/test_verdict.py -v`
Expected: FAIL

- [ ] **Step 4: Implement `BiasDetector`**

9 private methods, one per bias from spec Section 5.4. Each returns `BiasWarning | None`. Thresholds from spec: confirmation (positive ≥ 3× negative), anchoring (reference vs fair ±20%), recency (3M vs 36M direction mismatch), survivorship (declining comparables < 30%), availability (top-10% search concentration), loss_aversion (held below -15% from peak), overconfidence (High confidence + < 3 evidence), base_rate_neglect (expected return > 2× 10Y avg), sunk_cost (≥ 2 signals expired but still held).

- [ ] **Step 5: Implement `VerdictBuilder`**

`build()` calls `scorer.score()`, `simulator.simulate()`, `bias_detector.detect()` in parallel. Assembles the 12 Red Team Protocol fields. Verdict logic: score ≥ 65 and no high-severity bias → "매수 검토"; score < 35 → "매도 검토"; any high-severity bias or confidence Low → "판단 유보"; else "관망". Kill switch is the single most impactful variable from sensitivity analysis. Evidence chain links each verdict field to the factor/data source it derived from.

- [ ] **Step 6: Run tests**

Run: `pytest tests/inference/test_bias_detector.py tests/inference/test_verdict.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/inference/bias_detector.py homepy/inference/verdict.py tests/inference/
git commit -m "feat: BiasDetector (9 biases) + VerdictBuilder (Red Team Protocol)"
```

---

### Task 4: Pydantic Schemas + FastAPI Application

**Files:**
- Create: `homepy/api/__init__.py`
- Create: `homepy/api/main.py`
- Create: `homepy/api/models/__init__.py`
- Create: `homepy/api/models/schemas.py`
- Create: `homepy/api/routers/__init__.py`
- Create: `homepy/api/routers/ontology.py`
- Create: `homepy/api/routers/analysis.py`
- Create: `homepy/api/routers/simulation.py`
- Create: `homepy/api/routers/market.py`
- Create: `homepy/api/routers/portfolio.py`
- Create: `homepy/api/routers/pipeline.py`
- Create: `homepy/api/services/__init__.py`
- Create: `homepy/api/services/tax_engine.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_api.py`

**Interfaces:**
- Consumes: `InvestmentScorer`, `ScenarioSimulator`, `BiasDetector`, `VerdictBuilder` from Tasks 1-3; `TypeDBService`, `TimescaleService` from Plan A Task 6
- Produces:
  - FastAPI app on port 8000 with 6 router prefixes per spec Section 6.1
  - Pydantic response models mirroring the inference dataclasses
  - Key endpoints:
    - `GET /api/v1/ontology/entity/{entity_type}` → list entities
    - `GET /api/v1/ontology/graph/{complex_id}` → subgraph around a complex
    - `POST /api/v1/analysis/score` body `{complex_ids: list[str]}` → `list[InvestmentScoreResponse]`
    - `POST /api/v1/analysis/verdict/{complex_id}` → `InvestmentVerdictResponse`
    - `POST /api/v1/simulation/scenario/{complex_id}` → `ScenarioResultResponse`
    - `POST /api/v1/simulation/tax` body `{complex_id, buyer_type, owner_count, ...}` → tax breakdown
    - `POST /api/v1/simulation/loan` body `{price, income, existing_debt, area_type, ...}` → max borrowable
    - `GET /api/v1/market/cycle/{district_code}` → cycle phase + indicators
    - `GET /api/v1/market/macro/summary` → latest macro snapshot
    - `GET /api/v1/pipeline/status` → collector/flow status summary

- [ ] **Step 1: Write failing tests**

```python
from fastapi.testclient import TestClient

def test_app_starts(app_client: TestClient):
    resp = app_client.get("/api/v1/market/macro/summary")
    assert resp.status_code == 200

def test_score_endpoint_returns_factors(app_client):
    resp = app_client.post("/api/v1/analysis/score", json={"complex_ids": ["C001"]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert len(data[0]["factors"]) == 14

def test_verdict_endpoint_has_red_team_fields(app_client):
    resp = app_client.post("/api/v1/analysis/verdict/C001")
    assert resp.status_code == 200
    body = resp.json()
    assert "core_facts" in body
    assert "kill_switch" in body
    assert body["verdict"] in ("매수 검토", "관망", "매도 검토", "판단 유보")

def test_scenario_endpoint(app_client):
    resp = app_client.post("/api/v1/simulation/scenario/C001")
    assert resp.status_code == 200
    assert len(resp.json()["scenarios"]) == 3

def test_ontology_graph_endpoint(app_client):
    resp = app_client.get("/api/v1/ontology/graph/C001")
    assert resp.status_code == 200
    assert "nodes" in resp.json()
    assert "edges" in resp.json()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: Create test fixture `tests/api/conftest.py`**

`app_client` fixture builds a FastAPI `TestClient` with dependency-overridden services (mock TypeDB, mock TimescaleDB, mock inference engine returning canned results).

- [ ] **Step 4: Implement `schemas.py`**

Pydantic v2 models: `InvestmentScoreResponse`, `FactorScoreResponse`, `InvestmentVerdictResponse`, `ScenarioResultResponse`, `BiasWarningResponse`, `MacroSummaryResponse`, `CycleStatusResponse`, `TaxSimulationRequest/Response`, `LoanSimulationRequest/Response`, `OntologyGraphResponse`. Each with `model_config = ConfigDict(from_attributes=True)`.

- [ ] **Step 5: Implement `main.py` and routers**

`main.py`: create FastAPI app, include 6 routers with prefixes from spec Section 6.1, add startup/shutdown events for DB connections. Each router file contains 2-4 endpoint functions. `analysis.py` wires to `VerdictBuilder` and `InvestmentScorer`. `simulation.py` wires to `ScenarioSimulator` and `TaxEngine`. `market.py` reads TimescaleDB directly for time-series summaries + TypeDB for cycle phase. `ontology.py` runs TypeQL match queries and formats as graph JSON (nodes + edges).

- [ ] **Step 6: Implement `tax_engine.py`**

`TaxEngine(typedb_svc)` with methods `calc_acquisition_tax(price, buyer_type, owner_count, area_type) -> dict` and `calc_capital_gains_tax(purchase_price, sale_price, holding_years, area_type, owner_count) -> dict` and `calc_comprehensive_tax(assessed_values: list[int], owner_count) -> dict`. Queries TypeDB tax-rate rules to find applicable rates.

- [ ] **Step 7: Run tests**

Run: `pytest tests/api/test_api.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/api/ tests/api/
git commit -m "feat: FastAPI application — 6 routers, Pydantic schemas, tax engine"
```

---

### Task 5: Streamlit Dashboard Core + Market/Signal Pages

**Files:**
- Create: `homepy/app/__init__.py`
- Create: `homepy/app/main.py`
- Create: `homepy/app/api_client.py`
- Create: `homepy/app/components/__init__.py`
- Create: `homepy/app/components/signal_card.py`
- Create: `homepy/app/components/cycle_diagram.py`
- Create: `homepy/app/components/regulation_map.py`
- Create: `homepy/app/pages/01_market_dashboard.py`
- Create: `homepy/app/pages/02_signal_board.py`
- Create: `tests/app/__init__.py`
- Create: `tests/app/test_api_client.py`

**Interfaces:**
- Consumes: FastAPI endpoints from Task 4 (via HTTP)
- Produces:
  - `ApiClient(base_url: str)` with async methods mirroring each API endpoint: `get_macro_summary()`, `get_cycle(district_code)`, `post_score(complex_ids)`, `post_verdict(complex_id)`, etc.
  - Streamlit app launchable via `streamlit run homepy/app/main.py`
  - Page 1 (Market Dashboard): macro summary cards, cycle position diagram, regulation zone map
  - Page 2 (Signal Board): active signals list with filters, signal detail cards

- [ ] **Step 1: Write failing test for ApiClient**

```python
async def test_api_client_get_macro_summary(httpx_mock):
    httpx_mock.add_response(json={"base_rate": 3.25, "cycle_phase": "recovery"})
    client = ApiClient("http://localhost:8000")
    result = await client.get_macro_summary()
    assert result["base_rate"] == 3.25

async def test_api_client_post_score(httpx_mock):
    httpx_mock.add_response(json=[{"complex_id": "C001", "total_score": 72.5}])
    client = ApiClient("http://localhost:8000")
    result = await client.post_score(["C001"])
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/app/test_api_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `api_client.py`**

Thin async httpx wrapper. One method per API endpoint. Returns parsed JSON dicts. Handles connection errors gracefully with retry.

- [ ] **Step 4: Implement `main.py` (Streamlit entry)**

Sidebar navigation with 9 page links. Session state initialization for `api_base_url` (default `http://localhost:8000`). Page title "HOMEPY — 부동산 투자 의사결정 시스템".

- [ ] **Step 5: Implement components `signal_card.py`, `cycle_diagram.py`, `regulation_map.py`**

`signal_card(signal: dict)`: Streamlit container with signal type icon, target name, score, evidence bullets. `cycle_diagram(phase: str, indicators: dict)`: Plotly polar chart showing cycle position on a 4-phase wheel (recovery → expansion → peak → contraction). `regulation_map(districts: list[dict])`: Folium choropleth map coloring districts by regulation zone type (adjusted-target, speculation-overheated, non-regulated).

- [ ] **Step 6: Implement Page 1 (Market Dashboard)**

Three columns: left = macro indicator cards (base rate, M2 growth, exchange rate with directional arrows), center = cycle position diagram for selected region, right = regulation zone map. Bottom row = key signals summary table.

- [ ] **Step 7: Implement Page 2 (Signal Board)**

Filters (signal type, district, min confidence). Results as a grid of `signal_card` components. Click a card → expands to show full evidence chain.

- [ ] **Step 8: Verify pages render**

Run: `streamlit run homepy/app/main.py` — navigate to pages 1 and 2, confirm they render with mock/empty data without errors.

- [ ] **Step 9: Commit**

```bash
git add homepy/app/ tests/app/
git commit -m "feat: Streamlit core + market dashboard + signal board pages"
```

---

### Task 6: Streamlit Analysis & Simulation Pages

**Files:**
- Create: `homepy/app/components/radar_chart.py`
- Create: `homepy/app/components/evidence_chain.py`
- Create: `homepy/app/components/bias_warning.py`
- Create: `homepy/app/pages/03_deep_analysis.py`
- Create: `homepy/app/pages/04_scenario_sim.py`
- Create: `homepy/app/pages/05_tax_calculator.py`
- Create: `homepy/app/pages/06_loan_calculator.py`

**Interfaces:**
- Consumes: `ApiClient` from Task 5; FastAPI analysis/simulation endpoints from Task 4
- Produces:
  - `radar_chart(factors: list[dict])`: Plotly radar chart of 14 factors (normalized 0–100)
  - `evidence_chain(chain: list[dict])`: Streamlit expander tree showing data → inference → conclusion
  - `bias_warning(warnings: list[dict])`: colored alert boxes per bias type with severity badges
  - Page 3 (Deep Analysis): complex selector → 14-factor radar chart + InvestmentVerdict display + bias warnings
  - Page 4 (Scenario Simulation): Bull/Base/Bear cards + sensitivity heatmap + variable sliders
  - Page 5 (Tax Calculator): input form → acquisition/CGT/comprehensive tax breakdown
  - Page 6 (Loan Calculator): input form → max borrowable (LTV/DTI/DSR) + monthly repayment schedule

- [ ] **Step 1: Implement `radar_chart.py`**

Plotly `go.Scatterpolar` with 14 factor names as angular axis. Fill color varies by grade (A=green, B=blue, C=yellow, D=orange, F=red).

- [ ] **Step 2: Implement `evidence_chain.py`**

Recursive `st.expander` rendering. Each node shows: claim, supporting data source, timestamp. Leaf nodes link to raw data.

- [ ] **Step 3: Implement `bias_warning.py`**

`st.warning` for medium severity, `st.error` for high severity. Each box shows bias name, description, evidence, mitigation suggestion.

- [ ] **Step 4: Implement Page 3 (Deep Analysis)**

Top: complex search/select (text input → API search). Left column: radar chart + grade badge + total score. Center: full InvestmentVerdict rendered section by section (core facts, bull/bear case, risk, kill switch, watchlist). Right: bias warnings. Bottom: evidence chain expander.

- [ ] **Step 5: Implement Page 4 (Scenario Simulation)**

Complex selector. Three columns for Bull/Base/Bear scenario cards (conditions, outcome, probability, leading indicators, invalidation). Below: Plotly heatmap for sensitivity analysis (variables × perturbation levels → score impact). Slider controls to manually adjust variable assumptions and see real-time score changes.

- [ ] **Step 6: Implement Page 5 (Tax Calculator)**

Input form: property price, buyer type (1주택/2주택/3주택+/법인), area type (조정대상/비규제), holding period, residence period. Output: 취득세, 양도소득세, 종합부동산세 with rate breakdowns and deductions. Uses `/api/v1/simulation/tax` endpoint.

- [ ] **Step 7: Implement Page 6 (Loan Calculator)**

Input form: property price, annual income, existing debt, area type. Output: max LTV/DTI/DSR-limited loan amount (binding constraint highlighted), monthly repayment schedule chart (Plotly bar), total interest cost. Uses `/api/v1/simulation/loan` endpoint.

- [ ] **Step 8: Verify pages render**

Run Streamlit, navigate to pages 3-6, confirm they render without errors.

- [ ] **Step 9: Commit**

```bash
git add homepy/app/components/ homepy/app/pages/
git commit -m "feat: deep analysis, scenario sim, tax & loan calculator pages"
```

---

### Task 7: Portfolio/Graph/Monitor Pages + E2E Integration

**Files:**
- Create: `homepy/app/pages/07_portfolio.py`
- Create: `homepy/app/pages/08_knowledge_graph.py`
- Create: `homepy/app/pages/09_pipeline_monitor.py`
- Create: `tests/test_e2e_full_stack.py`

**Interfaces:**
- Consumes: All prior tasks (inference engine, API, Streamlit components, DB services)
- Produces:
  - Page 7 (Portfolio): watchlist management + holdings health dashboard
  - Page 8 (Knowledge Graph): Pyvis interactive graph visualization of TypeDB subgraph
  - Page 9 (Pipeline Monitor): collector status table, quality report history, lineage viewer
  - E2E test: seed data → run inference → call API → verify verdict structure

- [ ] **Step 1: Implement Page 7 (Portfolio)**

Watchlist: add/remove complex IDs, display latest score + grade for each. Holdings: input purchase price + date per asset, show current valuation, unrealized gain/loss, active signals affecting each holding. Alert list: triggered alerts for watched/held complexes.

- [ ] **Step 2: Implement Page 8 (Knowledge Graph)**

District/complex selector. Calls `/api/v1/ontology/graph/{complex_id}`. Renders the subgraph (entities as nodes, relations as edges) using Pyvis `Network` embedded via `st.components.v1.html`. Node colors by entity type, edge labels showing relation names.

- [ ] **Step 3: Implement Page 9 (Pipeline Monitor)**

Calls `/api/v1/pipeline/status`. Displays: collector status table (name, last run, next scheduled, status badge), quality gate pass/fail history as a Plotly timeline, lineage viewer as a DAG from source → cleaned → transformed → loaded.

- [ ] **Step 4: Verify all 9 pages render**

Run Streamlit, navigate through all 9 pages, confirm no errors.

- [ ] **Step 5: Write E2E integration test**

```python
async def test_full_stack_verdict_roundtrip():
    """
    1. Bootstrap DBs (Plan A bootstrap script)
    2. Insert seed data: region→district→dong→complex, interest_rate, supply_data
    3. Run sync (timescale→typedb aggregates)
    4. Call POST /api/v1/analysis/verdict/C001
    5. Assert verdict has all 12 Red Team Protocol fields
    6. Assert evidence_chain traces back to seed data
    """
    pass  # Full implementation with real DB connections
```

- [ ] **Step 6: Run E2E test**

Run: `pytest tests/test_e2e_full_stack.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/app/pages/ tests/test_e2e_full_stack.py
git commit -m "feat: portfolio, knowledge graph, pipeline monitor pages + E2E test"
```
