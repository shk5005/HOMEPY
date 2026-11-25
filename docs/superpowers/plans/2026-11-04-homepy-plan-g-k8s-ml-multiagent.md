# HOMEPY Plan G: Infrastructure Modernization & Advanced Analytics (Phase 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from Docker Compose to Kubernetes with Helm charts and HPA auto-scaling, add ML-based price prediction (LightGBM + SHAP) as a 15th scoring factor, build a natural language → TypeQL query interface via Claude API, implement auto-report generation (PDF/HTML), and create a 4-agent debate system (Bull/Bear/Behavioral/Policy) for multi-perspective investment analysis.

**Architecture:** Kubernetes orchestrates all services via a Helm chart — StatefulSets for TypeDB and TimescaleDB, Deployments with HPA for FastAPI, single Deployment for Streamlit, Redis with Sentinel. The ML pipeline extracts 5 relational features from TypeDB and 5 time-series features from TimescaleDB, trains a LightGBM model on a 12-month rolling window, explains predictions via SHAP, and integrates as InvestmentScorer's 15th factor with automatic fallback to rule-based scoring. The NLP layer uses Claude API to convert natural language to validated TypeQL queries. The multi-agent system runs a 4-round structured debate protocol — independent analysis, cross-rebuttal, policy re-evaluation, consensus/dissent — then VerdictBuilder synthesizes the final InvestmentVerdict.

**Tech Stack:** Python 3.11+, Kubernetes 1.28+, Helm 3, lightgbm, shap, mlflow, anthropic (Claude SDK), Jinja2, WeasyPrint, pytest, mypy, ruff

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Section 13)

**Depends on:** Plan F complete (multi-user authentication, real-time data pipeline, policy simulation engine)

## Global Constraints

- Python ≥ 3.11, Kubernetes ≥ 1.28, Helm ≥ 3.12
- ML model never auto-deploys — every model version requires `ImprovementRecord` + user approval before serving (statistical refreshes like normalization ranges are exempt per Plan D)
- ML fallback to rule-based scoring when MAPE ≥ 15% or direction accuracy < 60%
- Claude API calls must be rate-limited (max 10 req/min) and cached (identical queries within 5 minutes)
- TypeQL generated from natural language is always validated against the schema before execution — never run unvalidated LLM output
- Multi-agent debate must not force consensus — dissent is recorded as-is
- All new Helm templates must pass `helm lint` and `helm template` validation
- CI quality gates from Plan D apply: ruff 0 warnings, mypy strict, tests 100% pass, coverage ≥ 80%

## Review Focus

1. **ML training data leakage** — the LightGBM training pipeline must split data chronologically (train on months 1–12, validate on months 13–15), never randomly. A test must verify that no validation-period data appears in the training set.
2. **TypeQL injection via NLP** — natural language input is untrusted. The generated TypeQL must be pattern-matched against an allowlist of query shapes (match/get only, no insert/delete/define). A test must show that "delete all data" input produces a rejection, not a TypeQL delete statement.
3. **Agent confirmation bias in debates** — the BullAgent and BearAgent must use the same data inputs and produce analyses independently before seeing each other's output. A test must verify that Round 1 outputs are generated without access to other agents' Round 1 outputs.
4. **Helm secrets exposure** — `secrets.yaml` must reference external secret stores (K8s Secrets, env vars) and never contain plaintext credentials. A test must grep the rendered template for hardcoded passwords/tokens.
5. **SHAP attribution completeness** — SHAP values for all features must sum to the model's prediction minus the base value (within floating-point tolerance). A test must verify `abs(sum(shap_values) - (prediction - base_value)) < 0.01`.

---

### Task 1: Helm Chart Scaffolding + K8s Manifests

**Files:**
- Create: `charts/homepy/Chart.yaml`
- Create: `charts/homepy/values.yaml`
- Create: `charts/homepy/values-dev.yaml`
- Create: `charts/homepy/values-prod.yaml`
- Create: `charts/homepy/templates/typedb-statefulset.yaml`
- Create: `charts/homepy/templates/timescaledb-statefulset.yaml`
- Create: `charts/homepy/templates/redis-deployment.yaml`
- Create: `charts/homepy/templates/fastapi-deployment.yaml`
- Create: `charts/homepy/templates/streamlit-deployment.yaml`
- Create: `charts/homepy/templates/ingress.yaml`
- Create: `charts/homepy/templates/configmap.yaml`
- Create: `charts/homepy/templates/secrets.yaml`
- Create: `tests/k8s/__init__.py`
- Create: `tests/k8s/test_helm_chart.py`

**Interfaces:**
- Consumes: `docker-compose.yml` (existing service definitions for port mappings, env vars, volume mounts)
- Produces:
  - Helm chart at `charts/homepy/` deployable via `helm install homepy ./charts/homepy`
  - `values.yaml` with all configurable parameters (image tags, replica counts, resource limits, PVC sizes)
  - `values-dev.yaml` overrides: single replicas, small PVCs, debug logging
  - `values-prod.yaml` overrides: multi-replica FastAPI, large PVCs, production logging

- [ ] **Step 1: Write failing tests**

```python
import subprocess, yaml

def test_helm_lint_passes():
    result = subprocess.run(
        ["helm", "lint", "charts/homepy"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"helm lint failed: {result.stderr}"

def test_helm_template_renders_all_resources():
    result = subprocess.run(
        ["helm", "template", "homepy", "charts/homepy"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    docs = list(yaml.safe_load_all(result.stdout))
    kinds = {d["kind"] for d in docs if d}
    assert "StatefulSet" in kinds
    assert "Deployment" in kinds
    assert "Ingress" in kinds
    assert "ConfigMap" in kinds
    assert "Secret" in kinds
    assert "HorizontalPodAutoscaler" in kinds

def test_secrets_template_has_no_plaintext():
    result = subprocess.run(
        ["helm", "template", "homepy", "charts/homepy"],
        capture_output=True, text=True
    )
    for doc in yaml.safe_load_all(result.stdout):
        if doc and doc.get("kind") == "Secret":
            for key, val in doc.get("data", {}).items():
                assert val != "", f"Secret {key} appears empty/plaintext"

def test_statefulset_has_pvc():
    result = subprocess.run(
        ["helm", "template", "homepy", "charts/homepy"],
        capture_output=True, text=True
    )
    for doc in yaml.safe_load_all(result.stdout):
        if doc and doc.get("kind") == "StatefulSet":
            vcts = doc["spec"].get("volumeClaimTemplates", [])
            assert len(vcts) > 0, f"StatefulSet {doc['metadata']['name']} missing PVC"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/k8s/test_helm_chart.py -v`
Expected: FAIL — `charts/homepy/` directory does not exist

- [ ] **Step 3: Create `Chart.yaml` and `values.yaml`**

`Chart.yaml`: name `homepy`, version `0.1.0`, appVersion matching project version, description referencing the HOMEPY system. `values.yaml`: image repository/tag for each component (typedb, timescaledb, redis, fastapi, streamlit), replica counts (fastapi: 2, streamlit: 1), resource requests/limits, PVC sizes (typedb: 10Gi, timescaledb: 50Gi), ingress host, configmap keys for all `env:` references from the spec's `ALERT_CHANNELS`.

- [ ] **Step 4: Create `values-dev.yaml` and `values-prod.yaml`**

Dev overrides: fastapi replicas 1, PVC sizes halved, log level DEBUG, ingress host `homepy-dev.local`. Prod overrides: fastapi replicas 2, full PVC sizes, log level WARNING, ingress host from values.

- [ ] **Step 5: Create StatefulSet templates (TypeDB, TimescaleDB)**

`typedb-statefulset.yaml`: 1 replica, volumeClaimTemplate for `/opt/typedb/server/data`, port 1729, readiness probe on 1729. `timescaledb-statefulset.yaml`: 1 replica, volumeClaimTemplate for `/var/lib/postgresql/data`, port 5432, readiness probe via `pg_isready`, env vars from Secret (POSTGRES_PASSWORD).

- [ ] **Step 6: Create Deployment templates (Redis, FastAPI, Streamlit) + Ingress + ConfigMap + Secrets**

`redis-deployment.yaml`: 1 replica, port 6379. `fastapi-deployment.yaml`: replicas from values, port 8000, liveness/readiness probes on `/health`, env vars from ConfigMap and Secret. `streamlit-deployment.yaml`: 1 replica, port 8501. `ingress.yaml`: Nginx class, paths `/api` → fastapi, `/` → streamlit. `configmap.yaml`: non-secret config (log level, cache TTLs, TypeDB host/port). `secrets.yaml`: references to DB passwords, API keys via `{{ .Values.secrets.* }}` — values are base64-encoded, sourced from values file or external secret manager.

- [ ] **Step 7: Run tests**

Run: `pytest tests/k8s/test_helm_chart.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add charts/ tests/k8s/
git commit -m "feat: Helm chart scaffolding — StatefulSets, Deployments, Ingress, ConfigMap, Secrets"
```

---

### Task 2: HPA + K8s Migration Script

**Files:**
- Create: `charts/homepy/templates/hpa.yaml`
- Create: `scripts/migrate_to_k8s.sh`
- Create: `scripts/migrate_volumes.sh`
- Create: `tests/k8s/test_hpa.py`
- Create: `tests/k8s/test_migration.py`

**Interfaces:**
- Consumes: Helm chart from Task 1, existing `docker-compose.yml`, existing data volumes
- Produces:
  - `hpa.yaml`: HPA manifest matching spec (minReplicas=2, maxReplicas=10, CPU 70%)
  - `migrate_to_k8s.sh`: script to export Docker Compose data, create K8s namespace, apply PVCs, import data
  - `migrate_volumes.sh`: exports TimescaleDB via `pg_dump`, TypeDB via `typedb server export`, copies to PVCs

- [ ] **Step 1: Write failing tests**

```python
import subprocess, yaml

def test_hpa_spec_matches_design():
    result = subprocess.run(
        ["helm", "template", "homepy", "charts/homepy"],
        capture_output=True, text=True
    )
    for doc in yaml.safe_load_all(result.stdout):
        if doc and doc.get("kind") == "HorizontalPodAutoscaler":
            spec = doc["spec"]
            assert spec["minReplicas"] == 2
            assert spec["maxReplicas"] == 10
            metrics = spec["metrics"]
            cpu_metric = next(m for m in metrics if m["resource"]["name"] == "cpu")
            assert cpu_metric["resource"]["target"]["averageUtilization"] == 70
            assert spec["scaleTargetRef"]["name"] == "homepy-fastapi"

def test_migration_script_syntax():
    """Migration script must be valid bash"""
    result = subprocess.run(
        ["bash", "-n", "scripts/migrate_to_k8s.sh"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"Syntax error: {result.stderr}"

def test_volume_migration_script_syntax():
    result = subprocess.run(
        ["bash", "-n", "scripts/migrate_volumes.sh"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/k8s/test_hpa.py tests/k8s/test_migration.py -v`
Expected: FAIL

- [ ] **Step 3: Create `hpa.yaml`**

Exact spec from Section 13.1: `apiVersion: autoscaling/v2`, scaleTargetRef `homepy-fastapi`, minReplicas 2, maxReplicas 10, CPU averageUtilization 70.

- [ ] **Step 4: Create `migrate_to_k8s.sh`**

Steps: check prerequisites (kubectl, helm, docker), create namespace `homepy`, run `migrate_volumes.sh`, `helm install homepy ./charts/homepy -f values-prod.yaml`, wait for pods ready, run smoke test (curl `/health`). Idempotent — skips steps already completed.

- [ ] **Step 5: Create `migrate_volumes.sh`**

Steps: `docker exec` into TimescaleDB container → `pg_dump` → save to host, `docker exec` into TypeDB → `typedb server export` → save to host. Create PVCs if not exist. Copy dumps into PVCs via temporary pod. Restore TimescaleDB via `psql`, TypeDB via `typedb server import`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/k8s/test_hpa.py tests/k8s/test_migration.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add charts/homepy/templates/hpa.yaml scripts/ tests/k8s/
git commit -m "feat: HPA auto-scaling (CPU 70%, 2-10 replicas) + K8s migration scripts"
```

---

### Task 3: ML Feature Engineering Pipeline

**Files:**
- Create: `homepy/ml/__init__.py`
- Create: `homepy/ml/features.py`
- Create: `homepy/ml/models.py`
- Modify: `storage/timescale/schema.sql` (add `ts_ml_features` table)
- Modify: `storage/timescale/hypertables.sql` (add hypertable for `ts_ml_features`)
- Create: `tests/ml/__init__.py`
- Create: `tests/ml/test_features.py`

**Interfaces:**
- Consumes: `TypeDBService` from Plan A Task 5, `TimescaleService` from Plan A Task 6
- Produces:
  - `MLFeatureSet(complex_id: str, feature_date: date, relational_features: dict[str, float], timeseries_features: dict[str, float], combined: np.ndarray)` — dataclass
  - `RelationalFeatureExtractor(typedb_svc: TypeDBService)` with method:
    - `async extract(complex_id: str) -> dict[str, float]` — returns 5 features: `adjacent_complex_count`, `development_upside_count`, `regulation_intensity`, `effective_tax_rate`, `cycle_phase_encoded`
  - `TimeSeriesFeatureExtractor(timescale_svc: TimescaleService)` with method:
    - `async extract(complex_id: str, as_of: date) -> dict[str, float]` — returns 5 features: `price_ma_ratio` (3M/12M), `volume_change_rate`, `interest_rate_cumulative`, `jeonse_ratio_trend`, `search_zscore`
  - `FeatureCombiner()` with method:
    - `combine(relational: dict, timeseries: dict) -> MLFeatureSet` — normalizes and concatenates

- [ ] **Step 1: Write failing tests**

```python
async def test_relational_extractor_returns_five_features(mock_typedb):
    mock_typedb.set_query_result("adjacent_count", [{"count": 12}])
    mock_typedb.set_query_result("development_count", [{"count": 3}])
    ext = RelationalFeatureExtractor(mock_typedb)
    features = await ext.extract("C001")
    assert len(features) == 5
    expected_keys = {
        "adjacent_complex_count", "development_upside_count",
        "regulation_intensity", "effective_tax_rate", "cycle_phase_encoded"
    }
    assert set(features.keys()) == expected_keys
    assert all(isinstance(v, float) for v in features.values())

async def test_timeseries_extractor_returns_five_features(mock_timescale):
    ext = TimeSeriesFeatureExtractor(mock_timescale)
    features = await ext.extract("C001", date(2026, 10, 1))
    assert len(features) == 5
    expected_keys = {
        "price_ma_ratio", "volume_change_rate",
        "interest_rate_cumulative", "jeonse_ratio_trend", "search_zscore"
    }
    assert set(features.keys()) == expected_keys

async def test_timeseries_extractor_respects_as_of_date(mock_timescale):
    """Must not use data after as_of date"""
    ext = TimeSeriesFeatureExtractor(mock_timescale)
    await ext.extract("C001", date(2026, 6, 15))
    for query in mock_timescale.executed_queries:
        assert "2026-06-15" in query or "ts <=" in query

def test_combiner_produces_no_nan():
    combiner = FeatureCombiner()
    rel = {"adjacent_complex_count": 10.0, "development_upside_count": 3.0,
           "regulation_intensity": 0.7, "effective_tax_rate": 0.02,
           "cycle_phase_encoded": 2.0}
    ts = {"price_ma_ratio": 1.05, "volume_change_rate": -0.1,
          "interest_rate_cumulative": 0.5, "jeonse_ratio_trend": -0.03,
          "search_zscore": 1.2}
    result = combiner.combine(rel, ts)
    assert not np.any(np.isnan(result.combined))
    assert result.combined.shape == (10,)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ml/test_features.py -v`
Expected: FAIL

- [ ] **Step 3: Define ML dataclasses in `ml/models.py`**

`MLFeatureSet`, `MLPrediction(complex_id, prediction_date, predicted_change_3m, confidence, shap_values: dict[str, float], model_version: str)`, `ModelMetrics(mape, direction_accuracy, r_squared, feature_importances: dict[str, float])`.

- [ ] **Step 4: Implement `RelationalFeatureExtractor` in `ml/features.py`**

Each of 5 features is one TypeQL query: `adjacent_complex_count` counts complexes within 500m via `accessibility` relation, `development_upside_count` counts connected `development-factor` entities, `regulation_intensity` averages regulation weights, `effective_tax_rate` reads from tax-calculation results, `cycle_phase_encoded` maps cycle phase to ordinal (recovery=1, expansion=2, peak=3, contraction=4).

- [ ] **Step 5: Implement `TimeSeriesFeatureExtractor`**

`price_ma_ratio`: 3-month MA / 12-month MA from `ts_real_trade`. `volume_change_rate`: (current_month_volume - prev_month) / prev_month. `interest_rate_cumulative`: sum of rate changes over 6 months from `ts_macro`. `jeonse_ratio_trend`: slope of linear regression on 6-month jeonse ratio. `search_zscore`: (current - 90d mean) / 90d std from `ts_sentiment`. All queries filter `WHERE ts <= as_of`.

- [ ] **Step 6: Implement `FeatureCombiner`**

Min-max normalizes each feature using 36-month rolling percentiles (5th/95th), concatenates into numpy array. Missing values filled with median of available history.

- [ ] **Step 7: Add `ts_ml_features` table and hypertable**

Schema: `ts TIMESTAMPTZ, complex_id TEXT, feature_name TEXT, feature_value DOUBLE PRECISION`. Hypertable on `ts`. Compression after 90 days.

- [ ] **Step 8: Run tests**

Run: `pytest tests/ml/test_features.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add homepy/ml/ storage/timescale/ tests/ml/
git commit -m "feat: ML feature engineering — 5 relational + 5 time-series features with combiner"
```

---

### Task 4: LightGBM Price Prediction Model

**Files:**
- Create: `homepy/ml/trainer.py`
- Create: `homepy/ml/predictor.py`
- Create: `tests/ml/test_trainer.py`
- Create: `tests/ml/test_predictor.py`

**Interfaces:**
- Consumes: `MLFeatureSet` and `FeatureCombiner` from Task 3, `TimescaleService` from Plan A Task 6
- Produces:
  - `ModelTrainer(timescale_svc: TimescaleService, feature_combiner: FeatureCombiner)` with methods:
    - `async train(training_months: int = 12, validation_months: int = 3) -> ModelMetrics`
    - `async get_shap_values(complex_id: str) -> dict[str, float]`
  - `PricePredictor(model_path: str, feature_combiner: FeatureCombiner)` with methods:
    - `async predict(complex_id: str) -> MLPrediction`
    - `is_healthy() -> bool` — returns False when MAPE ≥ 15% or direction accuracy < 60%
  - `FALLBACK_ENABLED: bool` — when `PricePredictor.is_healthy()` is False, `InvestmentScorer` uses rule-based score instead

- [ ] **Step 1: Write failing tests**

```python
def test_training_data_no_leakage(mock_timescale):
    """Validation data must come after training data chronologically"""
    trainer = ModelTrainer(mock_timescale, FeatureCombiner())
    train_set, val_set = trainer._split_data(
        start=date(2025, 1, 1), train_months=12, val_months=3
    )
    assert train_set["date"].max() < val_set["date"].min()

def test_shap_values_sum_to_prediction():
    trainer = ModelTrainer(mock_timescale, FeatureCombiner())
    trainer._model = _make_trained_model()
    shap_vals = trainer._compute_shap(sample_features)
    base = trainer._model.predict(sample_features, raw_score=True).mean()
    prediction = trainer._model.predict(sample_features)[0]
    assert abs(sum(shap_vals.values()) - (prediction - base)) < 0.01

async def test_predictor_fallback_on_low_accuracy():
    predictor = PricePredictor("dummy_path", FeatureCombiner())
    predictor._metrics = ModelMetrics(mape=20.0, direction_accuracy=55.0,
                                      r_squared=0.1, feature_importances={})
    assert not predictor.is_healthy()

async def test_predictor_returns_prediction_with_shap(mock_model):
    predictor = PricePredictor(mock_model, FeatureCombiner())
    result = await predictor.predict("C001")
    assert isinstance(result, MLPrediction)
    assert len(result.shap_values) == 10
    assert result.model_version != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ml/test_trainer.py tests/ml/test_predictor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ModelTrainer`**

`train`: queries `ts_ml_features` for training window (N months), splits chronologically (training_months for train, validation_months for validation), fits `lightgbm.LGBMRegressor` (objective `regression`, n_estimators 500, learning_rate 0.05, num_leaves 31), evaluates on validation set (MAPE, direction accuracy, R²). Registers model via MLflow if metrics meet thresholds. `get_shap_values`: uses `shap.TreeExplainer` on the trained model, returns feature name → SHAP value mapping.

- [ ] **Step 4: Implement `PricePredictor`**

Loads model from MLflow or local path. `predict`: runs feature extraction → model inference → SHAP explanation, returns `MLPrediction`. `is_healthy`: checks latest `ModelMetrics` — returns False if MAPE ≥ 15% or direction_accuracy < 60%, triggering fallback to rule-based scoring in `InvestmentScorer`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/ml/test_trainer.py tests/ml/test_predictor.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/ml/trainer.py homepy/ml/predictor.py tests/ml/
git commit -m "feat: LightGBM price prediction — SHAP explainer, MLflow registry, auto-fallback"
```

---

### Task 5: Natural Language → TypeQL Interface

**Files:**
- Create: `homepy/nlp/__init__.py`
- Create: `homepy/nlp/query_generator.py`
- Create: `homepy/nlp/validator.py`
- Create: `homepy/api/routers/nlp.py`
- Create: `tests/nlp/__init__.py`
- Create: `tests/nlp/test_query_generator.py`
- Create: `tests/nlp/test_validator.py`

**Interfaces:**
- Consumes: `TypeDBService` from Plan A Task 5, Claude API (`anthropic` SDK)
- Produces:
  - `TypeQLGenerator(api_key: str, schema_context: str)` with method:
    - `async generate(natural_language: str) -> str` — returns validated TypeQL query
  - `TypeQLValidator(schema: str)` with methods:
    - `validate(typeql: str) -> tuple[bool, str]` — returns (is_valid, error_message)
    - `is_safe(typeql: str) -> bool` — rejects insert/delete/define/undefine statements
  - `NLPQueryResult(original_query: str, generated_typeql: str, results: list[dict], execution_time_ms: float)` — dataclass
  - Router: `POST /api/v1/nlp/query` accepting `{"query": str}`, returning `NLPQueryResult`

- [ ] **Step 1: Write failing tests**

```python
def test_validator_rejects_delete():
    v = TypeQLValidator(HOMEPY_SCHEMA)
    assert not v.is_safe("match $x isa complex; delete $x;")

def test_validator_rejects_insert():
    v = TypeQLValidator(HOMEPY_SCHEMA)
    assert not v.is_safe("insert $x isa complex, has complex-name 'hacked';")

def test_validator_rejects_define():
    v = TypeQLValidator(HOMEPY_SCHEMA)
    assert not v.is_safe("define malicious-type sub entity;")

def test_validator_accepts_match_get():
    v = TypeQLValidator(HOMEPY_SCHEMA)
    valid, _ = v.validate(
        'match $c isa complex, has complex-name $n; get $c, $n;'
    )
    assert valid

async def test_generator_produces_valid_typeql(mock_claude_api):
    mock_claude_api.set_response(
        'match $dist isa district, has district-name "강남구"; '
        '$c isa complex; (parent: $dist, child: $c) isa spatial-hierarchy; get $c;'
    )
    gen = TypeQLGenerator("fake-key", HOMEPY_SCHEMA)
    gen._client = mock_claude_api
    result = await gen.generate("강남구 단지 찾아줘")
    v = TypeQLValidator(HOMEPY_SCHEMA)
    assert v.is_safe(result)

async def test_generator_rejects_malicious_input(mock_claude_api):
    mock_claude_api.set_response("delete $x isa complex;")
    gen = TypeQLGenerator("fake-key", HOMEPY_SCHEMA)
    gen._client = mock_claude_api
    with pytest.raises(ValueError, match="unsafe"):
        await gen.generate("delete all data from the database")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/nlp/ -v`
Expected: FAIL

- [ ] **Step 3: Implement `TypeQLValidator`**

`is_safe`: regex check that query contains only `match` and `get` keywords (no `insert`, `delete`, `define`, `undefine`). `validate`: parses TypeQL structure — checks balanced braces, valid variable syntax (`$var`), entity/relation types exist in schema. Returns `(True, "")` or `(False, "reason")`.

- [ ] **Step 4: Implement `TypeQLGenerator`**

System prompt includes HOMEPY's TypeDB schema (entity types, relation types, attribute types) and 3 few-shot examples (including the spec's 강남구 역세권 example). User message is the natural language query. Response is parsed, validated via `TypeQLValidator.is_safe()` and `TypeQLValidator.validate()`. Rate-limited to 10 requests/minute via a token bucket. Identical queries within 5 minutes return cached results.

- [ ] **Step 5: Create NLP router in `api/routers/nlp.py`**

`POST /api/v1/nlp/query`: accepts `NLPQueryRequest(query: str)`, runs `TypeQLGenerator.generate()`, executes via `TypeDBService`, returns `NLPQueryResult`. Requires `analyst` or `admin` role. Rate-limited per user.

- [ ] **Step 6: Run tests**

Run: `pytest tests/nlp/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/nlp/ homepy/api/routers/nlp.py tests/nlp/
git commit -m "feat: natural language → TypeQL interface — Claude API, validation, injection prevention"
```

---

### Task 6: Multi-Agent Debate System

**Files:**
- Create: `homepy/agents/__init__.py`
- Create: `homepy/agents/base.py`
- Create: `homepy/agents/bull.py`
- Create: `homepy/agents/bear.py`
- Create: `homepy/agents/behavioral.py`
- Create: `homepy/agents/policy.py`
- Create: `homepy/agents/orchestrator.py`
- Create: `homepy/agents/models.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/test_agents.py`
- Create: `tests/agents/test_orchestrator.py`

**Interfaces:**
- Consumes: `InvestmentScorer` from Plan C Task 1, `BiasDetector` from Plan C Task 3, `VerdictBuilder` from Plan C Task 3, Claude API
- Produces:
  - `AgentAnalysis(agent_name: str, verdict: str, confidence: float, key_arguments: list[str], data_cited: list[str], identified_biases: list[str])` — dataclass
  - `DebateRound(round_number: int, agent_outputs: dict[str, str])` — dataclass
  - `DebateResult(rounds: list[DebateRound], consensus_reached: bool, final_verdict: str | None, dissenting_views: list[AgentAnalysis], transcript: str)` — dataclass
  - `BaseAgent(api_key: str)` abstract class with methods:
    - `async analyze(data: dict) -> AgentAnalysis`
    - `async rebut(other_analysis: AgentAnalysis) -> str`
    - `async respond_to_rebuttal(rebuttal: str) -> str`
  - `BullAgent`, `BearAgent`, `BehavioralAgent`, `PolicyAgent` — concrete implementations
  - `DebateOrchestrator(agents: list[BaseAgent], verdict_builder: VerdictBuilder)` with method:
    - `async run_debate(complex_id: str, data: dict) -> DebateResult`

- [ ] **Step 1: Write failing tests**

```python
async def test_round1_agents_are_independent(mock_claude_api):
    """Round 1 outputs must be generated without seeing other agents' outputs"""
    bull = BullAgent(mock_claude_api)
    bear = BearAgent(mock_claude_api)
    data = {"score": 72, "factors": {"valuation_gap": 0.8}}
    bull_result = await bull.analyze(data)
    bear_result = await bear.analyze(data)
    # Each agent's prompt must not contain the other's analysis
    bull_prompt = mock_claude_api.last_prompts["BullAgent"]
    bear_prompt = mock_claude_api.last_prompts["BearAgent"]
    assert "BearAgent" not in bull_prompt
    assert "BullAgent" not in bear_prompt

async def test_behavioral_detects_planted_bias(mock_claude_api):
    mock_claude_api.set_behavioral_response(
        '{"identified_biases": ["confirmation_bias", "recency_bias"]}'
    )
    behavioral = BehavioralAgent(mock_claude_api)
    bull_analysis = AgentAnalysis(
        agent_name="BullAgent", verdict="매수 검토", confidence=0.9,
        key_arguments=["최근 3개월 상승"], data_cited=["price_momentum"],
        identified_biases=[]
    )
    result = await behavioral.analyze_bias(bull_analysis)
    assert "confirmation_bias" in result or "recency_bias" in result

async def test_orchestrator_four_rounds(mock_claude_api):
    agents = [BullAgent(mock_claude_api), BearAgent(mock_claude_api),
              BehavioralAgent(mock_claude_api), PolicyAgent(mock_claude_api)]
    orch = DebateOrchestrator(agents, VerdictBuilder())
    result = await orch.run_debate("C001", sample_data)
    assert len(result.rounds) == 4

async def test_orchestrator_allows_dissent(mock_claude_api):
    """Forced consensus must not happen — dissent is preserved"""
    mock_claude_api.set_no_consensus()
    agents = [BullAgent(mock_claude_api), BearAgent(mock_claude_api),
              BehavioralAgent(mock_claude_api), PolicyAgent(mock_claude_api)]
    orch = DebateOrchestrator(agents, VerdictBuilder())
    result = await orch.run_debate("C001", sample_data)
    assert not result.consensus_reached
    assert len(result.dissenting_views) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/ -v`
Expected: FAIL

- [ ] **Step 3: Define agent dataclasses in `agents/models.py`**

`AgentAnalysis`, `DebateRound`, `DebateResult` as specified in Interfaces.

- [ ] **Step 4: Implement `BaseAgent` in `agents/base.py`**

Abstract class with `analyze`, `rebut`, `respond_to_rebuttal` methods. Each method calls Claude API with agent-specific system prompt. Stores agent name and perspective description.

- [ ] **Step 5: Implement 4 agent subclasses**

`BullAgent` (system prompt: maximize positive signals, cite upside data), `BearAgent` (system prompt: maximize risk signals, cite downside data), `BehavioralAgent` (system prompt: detect cognitive biases in other agents' analyses using the 9-bias framework from spec Section 5.4), `PolicyAgent` (system prompt: analyze regulation/policy 2nd and 3rd order effects). Each agent's `analyze` receives the same raw data dict and produces an independent `AgentAnalysis`.

- [ ] **Step 6: Implement `DebateOrchestrator`**

Round 1: call all 4 agents' `analyze()` in parallel (`asyncio.gather`), store results independently. Round 2: Bull rebuts Bear and vice versa; Behavioral points out biases in Bull and Bear analyses. Round 3: Policy agent requests re-evaluation under regulation scenarios. Round 4: each agent states final position — if ≥ 3 agree on verdict direction, consensus; otherwise dissent with minority views preserved. `VerdictBuilder` integrates all 4 perspectives into final `InvestmentVerdict`, noting any dissent in the verdict's `scenario_analysis` field.

- [ ] **Step 7: Run tests**

Run: `pytest tests/agents/ -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/agents/ tests/agents/
git commit -m "feat: multi-agent debate system — Bull/Bear/Behavioral/Policy 4-round protocol"
```

---

### Task 7: Report Generator + Advanced Dashboard Pages + E2E

**Files:**
- Create: `homepy/reports/__init__.py`
- Create: `homepy/reports/generator.py`
- Create: `homepy/reports/templates/verdict_report.html`
- Create: `homepy/api/routers/reports.py`
- Create: `app/pages/11_nlp_query.py`
- Create: `app/pages/12_multiagent.py`
- Create: `tests/reports/__init__.py`
- Create: `tests/reports/test_generator.py`
- Create: `tests/e2e/test_phase4_e2e.py`

**Interfaces:**
- Consumes: `InvestmentVerdict` from Plan C Task 3, `DebateResult` from Task 6, `NLPQueryResult` from Task 5, `MLPrediction` from Task 4
- Produces:
  - `ReportGenerator(template_dir: str)` with methods:
    - `generate_html(verdict: InvestmentVerdict, debate: DebateResult | None) -> str`
    - `generate_pdf(verdict: InvestmentVerdict, debate: DebateResult | None) -> bytes`
  - Router: `POST /api/v1/reports/generate` accepting complex_id, returning PDF/HTML
  - Streamlit Page 11: NLP query input + result visualization
  - Streamlit Page 12: Multi-agent debate visualization (agent cards, debate transcript, consensus meter)

- [ ] **Step 1: Write failing tests**

```python
def test_report_has_five_sections():
    gen = ReportGenerator("homepy/reports/templates")
    html = gen.generate_html(sample_verdict, sample_debate)
    assert "투자 요약" in html
    assert "14팩터 상세 분석" in html
    assert "시나리오 분석" in html
    assert "편향 경고 및 리스크" in html
    assert "근거 데이터 부록" in html

def test_report_pdf_is_valid():
    gen = ReportGenerator("homepy/reports/templates")
    pdf_bytes = gen.generate_pdf(sample_verdict, sample_debate)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 1000

async def test_e2e_nlp_to_report(test_client):
    """End-to-end: NL query → TypeQL → analysis → debate → report"""
    nlp_resp = await test_client.post("/api/v1/nlp/query", json={
        "query": "강남구에서 저평가된 단지"
    })
    assert nlp_resp.status_code == 200
    complexes = nlp_resp.json()["results"]
    assert len(complexes) > 0

    complex_id = complexes[0]["id"]
    report_resp = await test_client.post("/api/v1/reports/generate", json={
        "complex_id": complex_id, "format": "html", "include_debate": True
    })
    assert report_resp.status_code == 200
    assert "투자 요약" in report_resp.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/reports/ tests/e2e/test_phase4_e2e.py -v`
Expected: FAIL

- [ ] **Step 3: Create report Jinja2 template**

`verdict_report.html`: 5-section structure matching spec — 투자 요약 (verdict summary, score, grade, confidence), 14팩터 상세 분석 (radar chart SVG, factor breakdown table), 시나리오 분석 (Bull/Base/Bear table with conditions and indicators), 편향 경고 및 리스크 (bias warnings, kill switch, top 5 risks), 근거 데이터 부록 (evidence chain, data sources, timestamps). If debate result is provided, add a 6th section with agent perspectives and consensus/dissent.

- [ ] **Step 4: Implement `ReportGenerator`**

`generate_html`: loads Jinja2 template, renders with verdict + debate data. `generate_pdf`: calls `generate_html`, converts to PDF via WeasyPrint. Handles missing debate gracefully (omits agent section).

- [ ] **Step 5: Create reports router**

`POST /api/v1/reports/generate`: accepts `{complex_id, format: "html"|"pdf", include_debate: bool}`. Runs scoring → optional debate → report generation. Returns HTML or PDF bytes. Requires `analyst` or `admin` role.

- [ ] **Step 6: Create Streamlit Page 11 (NLP Query)**

Text input for natural language query. Shows generated TypeQL (expandable). Displays results as table/cards. Links each result to deep analysis page.

- [ ] **Step 7: Create Streamlit Page 12 (Multi-Agent Debate)**

Complex selector. "Start Debate" button. 4 agent cards showing each perspective. Debate transcript with round-by-round expansion. Consensus meter (agree/disagree gauge). Download report button (PDF).

- [ ] **Step 8: Run tests**

Run: `pytest tests/reports/ tests/e2e/test_phase4_e2e.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add homepy/reports/ homepy/api/routers/reports.py app/pages/11_nlp_query.py app/pages/12_multiagent.py tests/reports/ tests/e2e/
git commit -m "feat: report generator (PDF/HTML) + NLP query page + multi-agent dashboard + E2E"
```
