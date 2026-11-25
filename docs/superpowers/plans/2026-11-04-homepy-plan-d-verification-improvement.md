# HOMEPY Plan D: Continuous Verification & Improvement System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the meta-system that verifies, calibrates, monitors, and continuously improves HOMEPY itself. This includes a backtesting engine that measures inference accuracy against actual market outcomes, an auto-calibrator that proposes weight/threshold adjustments with human approval gates, real-time data quality and system performance monitors, self-healing error recovery, CI/CD pipelines, and an improvement tracking dashboard.

**Architecture:** The verification layer sits alongside L4 (Inference) and observes all outputs. `Backtester` replays past verdicts against actual price movements. `AutoCalibrator` proposes weight/threshold changes based on backtesting evidence, requiring user approval. `DataMonitor` watches pipeline inputs for drift and freshness. `SystemMonitor` tracks query performance and resource usage. `SelfHealer` implements automatic recovery patterns. All events flow to `ImprovementTracker` for auditable history. A 10th Streamlit dashboard page visualizes system health.

**Tech Stack:** Python 3.11+, pytest, mypy, ruff, GitHub Actions, Redis (optional caching), scipy (statistics), numpy, Plotly

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Section 10)

**Depends on:** Plan C complete (inference engine producing InvestmentVerdicts, API serving, dashboard running)

## Global Constraints

- Python ≥ 3.11
- All calibration proposals are proposals — never auto-applied without explicit user approval (except normalization ranges and σ values, which are statistical refreshes)
- Every system change (weight, threshold, component version) must create an `ImprovementRecord` before taking effect
- Backtest results stored in TimescaleDB `ts_backtest_results` hypertable for time-series analysis
- Recovery events stored in `data/catalog/recovery_log.jsonl` (append-only)
- CI quality gates: ruff 0 warnings, mypy strict, tests 100% pass, coverage ≥ 80%

## Review Focus

1. **Backtest lookahead bias** — the backtester must use only data that was available at verdict time, never future data. Tests must verify that a backtest run on date D queries only data with `ts ≤ D`.
2. **Calibration feedback loops** — auto-calibrating weights based on recent performance can overfit to recent market regimes. The calibrator must use rolling windows (≥ 36 months) and out-of-sample validation, not just in-sample fit. A test should show that a calibration trained on 12 months and validated on the next 6 months rejects an overfit proposal.
3. **Monitor alert fatigue** — too many low-severity alerts cause operators to ignore all alerts. Each monitor must track its own false-positive rate and auto-suppress alerts with FP rate > 30%.
4. **Self-healer infinite loops** — a self-healer that retries a permanently broken API wastes resources. Every recovery action must have a max-retry count and a cooldown period, and the test must verify that exceeding max-retry escalates to human.
5. **CI flaky tests** — integration tests that depend on TypeDB/TimescaleDB timing can be flaky. Tests must use explicit healthcheck waits, not sleep. The CI pipeline must retry once on failure before reporting red.

---

### Task 1: Backtest Data Model + TimescaleDB Schema

**Files:**
- Create: `homepy/verification/__init__.py`
- Create: `homepy/verification/models.py`
- Modify: `storage/timescale/schema.sql` (add `ts_backtest_results`, `ts_calibration_log`, `ts_system_metrics`)
- Modify: `storage/timescale/hypertables.sql` (add hypertables for new tables)
- Create: `tests/verification/__init__.py`
- Create: `tests/verification/test_backtest_schema.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6
- Produces:
  - `BacktestRecord(verdict_id, complex_id, verdict_date, predicted_verdict, predicted_score, predicted_scenarios, actual_price_change_3m, actual_price_change_6m, actual_price_change_12m, direction_correct, scenario_hit, factor_contributions, bias_warnings_issued, bias_warnings_valid)` — dataclass
  - `CalibrationProposal(proposal_id, created_at, category, current_values, proposed_values, rationale, backtest_evidence, expected_improvement, risk_assessment, rollback_plan, status)` — dataclass
  - `ImprovementRecord(record_id, timestamp, category, component, before_state, after_state, trigger, evidence, impact_metrics, approved_by, rollback_possible)` — dataclass
  - `RecoveryEvent(event_id, timestamp, failure_type, component, auto_action, success, human_escalated, resolution_time_seconds)` — dataclass
  - 3 new TimescaleDB tables: `ts_backtest_results`, `ts_calibration_log`, `ts_system_metrics`

- [ ] **Step 1: Write failing test**

```python
async def test_backtest_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for table in ["ts_backtest_results", "ts_calibration_log", "ts_system_metrics"]:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)",
                table
            )
            assert exists, f"Table '{table}' missing"

async def test_backtest_tables_are_hypertables(db_pool):
    async with db_pool.acquire() as conn:
        hypertables = await conn.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        names = {r["hypertable_name"] for r in hypertables}
        for table in ["ts_backtest_results", "ts_calibration_log", "ts_system_metrics"]:
            assert table in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/verification/test_backtest_schema.py -v`
Expected: FAIL

- [ ] **Step 3: Define dataclasses in `verification/models.py`**

All 4 dataclasses from spec Section 10.2–10.6: `BacktestRecord`, `CalibrationProposal`, `ImprovementRecord`, `RecoveryEvent`.

- [ ] **Step 4: Add 3 new tables to `storage/timescale/schema.sql`**

`ts_backtest_results`: columns match `BacktestRecord` fields, `ts` = `verdict_date`, JSON columns for `predicted_scenarios`, `factor_contributions`. `ts_calibration_log`: `ts` = `created_at`, JSON for `current_values`/`proposed_values`/`backtest_evidence`. `ts_system_metrics`: `ts` TIMESTAMPTZ, `component` TEXT, `metric_name` TEXT, `metric_value` DOUBLE, for performance tracking.

- [ ] **Step 5: Add hypertable creation to `storage/timescale/hypertables.sql`**

`SELECT create_hypertable('ts_backtest_results', 'ts', if_not_exists => TRUE);` and same for the other two. Compression policy for results older than 180 days.

- [ ] **Step 6: Run tests**

Run: `pytest tests/verification/test_backtest_schema.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/verification/ storage/timescale/ tests/verification/
git commit -m "feat: verification data models + TimescaleDB backtest/calibration tables"
```

---

### Task 2: Backtesting Engine

**Files:**
- Create: `homepy/verification/backtester.py`
- Create: `tests/verification/test_backtester.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6, `BacktestRecord` from Task 1, historical `InvestmentVerdict` data from `ts_signals`
- Produces:
  - `BacktestResult(period_start, period_end, total_verdicts, direction_accuracy, signal_hit_rate, scenario_capture_rate, bias_validity_rate, factor_ic: dict[str, float], underperforming_factors: list[str])` — dataclass
  - `Backtester(timescale_svc: TimescaleService)` with methods:
    - `async run(lookback_months: int = 3) -> BacktestResult`
    - `async evaluate_verdict(verdict_id: str) -> BacktestRecord`
    - `async factor_ic_analysis(months: int = 12) -> dict[str, float]`

- [ ] **Step 1: Write failing tests**

```python
async def test_backtest_no_lookahead(mock_timescale):
    """Verdict from 2026-01-15 must only use data with ts <= 2026-01-15"""
    bt = Backtester(mock_timescale)
    record = await bt.evaluate_verdict("V001")
    for query in mock_timescale.executed_queries:
        assert "2026-01-15" in query or "ts <=" in query

async def test_direction_accuracy_calculation(mock_timescale):
    mock_timescale.set_verdicts([
        {"verdict": "매수 검토", "score": 75, "actual_3m": 5.0},   # correct
        {"verdict": "매수 검토", "score": 70, "actual_3m": -3.0},  # wrong
        {"verdict": "매도 검토", "score": 30, "actual_3m": -5.0},  # correct
    ])
    bt = Backtester(mock_timescale)
    result = await bt.run(lookback_months=3)
    assert result.direction_accuracy == pytest.approx(66.67, abs=0.1)

async def test_factor_ic_identifies_weak_factors(mock_timescale):
    bt = Backtester(mock_timescale)
    ic = await bt.factor_ic_analysis(months=12)
    assert all(isinstance(v, float) for v in ic.values())
    assert len(ic) == 14

async def test_underperforming_factors_flagged(mock_timescale):
    """Factors with IC < 0 should appear in underperforming list"""
    mock_timescale.set_factor_data({"tax_burden": -0.05, "unsold_risk": -0.02})
    bt = Backtester(mock_timescale)
    result = await bt.run(lookback_months=12)
    assert "tax_burden" in result.underperforming_factors
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/verification/test_backtester.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `Backtester`**

`evaluate_verdict`: loads historical verdict from `ts_signals`, queries actual price data at verdict_date + 3m/6m/12m from `ts_real_trade`, compares direction. `run`: evaluates all verdicts in the lookback window, aggregates metrics. `factor_ic_analysis`: for each factor, computes rank correlation (Spearman) between factor score at verdict time and subsequent 3-month price change. IC < 0 = factor is anti-predictive. No future data leakage — all queries filter `WHERE ts <= verdict_date`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/verification/test_backtester.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/verification/backtester.py tests/verification/test_backtester.py
git commit -m "feat: backtesting engine — direction accuracy, factor IC, no lookahead"
```

---

### Task 3: Auto-Calibrator

**Files:**
- Create: `homepy/verification/calibrator.py`
- Create: `tests/verification/test_calibrator.py`

**Interfaces:**
- Consumes: `BacktestResult` and `Backtester.factor_ic_analysis()` from Task 2, `FACTOR_WEIGHTS` from Plan C Task 1, `BiasDetector.BIAS_CHECKS` thresholds from Plan C Task 3
- Produces:
  - `AutoCalibrator(backtester: Backtester, timescale_svc: TimescaleService)` with methods:
    - `async propose_weight_update() -> CalibrationProposal`
    - `async propose_threshold_update() -> CalibrationProposal`
    - `async refresh_normalization_ranges() -> dict[str, tuple[float, float]]` (auto-apply)
    - `async apply_proposal(proposal_id: str) -> ImprovementRecord` (after user approval)
    - `async reject_proposal(proposal_id: str, reason: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
async def test_weight_proposal_uses_rolling_window(mock_backtester, mock_timescale):
    cal = AutoCalibrator(mock_backtester, mock_timescale)
    proposal = await cal.propose_weight_update()
    assert proposal.category == "weight"
    assert proposal.status == "proposed"
    assert "36" in proposal.rationale or "rolling" in proposal.rationale.lower()

async def test_weight_proposal_rejects_overfit(mock_backtester, mock_timescale):
    """If in-sample IC is great but out-of-sample IC is bad, proposal should warn"""
    mock_backtester.set_ic_split(
        in_sample={"valuation_gap": 0.3, "price_momentum": 0.25},
        out_of_sample={"valuation_gap": -0.1, "price_momentum": 0.02}
    )
    cal = AutoCalibrator(mock_backtester, mock_timescale)
    proposal = await cal.propose_weight_update()
    assert "overfit" in proposal.risk_assessment.lower() or proposal.status == "rejected"

async def test_weights_still_sum_to_one(mock_backtester, mock_timescale):
    cal = AutoCalibrator(mock_backtester, mock_timescale)
    proposal = await cal.propose_weight_update()
    assert abs(sum(proposal.proposed_values.values()) - 1.0) < 1e-9

async def test_normalization_refresh_auto_applies(mock_backtester, mock_timescale):
    cal = AutoCalibrator(mock_backtester, mock_timescale)
    ranges = await cal.refresh_normalization_ranges()
    assert isinstance(ranges, dict)
    for factor, (lo, hi) in ranges.items():
        assert lo < hi

async def test_apply_creates_improvement_record(mock_backtester, mock_timescale):
    cal = AutoCalibrator(mock_backtester, mock_timescale)
    proposal = await cal.propose_weight_update()
    record = await cal.apply_proposal(proposal.proposal_id)
    assert isinstance(record, ImprovementRecord)
    assert record.category == "calibration"
    assert record.rollback_possible is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/verification/test_calibrator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `AutoCalibrator`**

`propose_weight_update`: runs `factor_ic_analysis` over a 36-month rolling window, splits into 30-month train / 6-month validation. New weights = IC-proportional rebalance (each weight ∝ max(IC, 0), normalized to sum=1.0). If validation IC degrades for >3 factors, mark `risk_assessment` as overfit risk. `propose_threshold_update`: for each bias detector, compute F1-score on historical bias-warning-vs-actual-outcome data, propose threshold that maximizes F1. `refresh_normalization_ranges`: query 36-month rolling 5th/95th percentiles per factor from TimescaleDB, update ranges (auto-apply, no approval needed). `apply_proposal`: updates the module-level constant via a JSON config file `config/calibration.json`, creates an `ImprovementRecord`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/verification/test_calibrator.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/verification/calibrator.py tests/verification/test_calibrator.py
git commit -m "feat: auto-calibrator — IC-based weight proposals with overfit protection"
```

---

### Task 4: Data Quality Monitor + System Performance Monitor

**Files:**
- Create: `homepy/verification/data_monitor.py`
- Create: `homepy/verification/system_monitor.py`
- Create: `tests/verification/test_data_monitor.py`
- Create: `tests/verification/test_system_monitor.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6, pipeline metadata from `data/catalog/lineage.jsonl`
- Produces:
  - `DataMonitor(timescale_svc: TimescaleService)` with methods:
    - `async check_freshness() -> list[FreshnessAlert]`
    - `async check_distribution_drift(source: str, window_days: int = 30) -> DriftResult`
    - `async check_anomalies(source: str) -> list[AnomalyAlert]`
    - `async check_cross_source_consistency() -> list[ConsistencyAlert]`
  - `SystemMonitor(timescale_svc: TimescaleService)` with methods:
    - `async record_query_time(component: str, query: str, duration_ms: float) -> None`
    - `async get_performance_summary() -> PerformanceSummary`
    - `async detect_slow_queries(threshold_ms: float = 1000) -> list[SlowQuery]`
  - Alert dataclasses: `FreshnessAlert`, `DriftResult`, `AnomalyAlert`, `ConsistencyAlert`, `SlowQuery`

- [ ] **Step 1: Write failing tests for DataMonitor**

```python
async def test_freshness_alert_when_stale(mock_timescale):
    mock_timescale.set_last_collection("interest_rate", datetime(2026, 11, 1))
    dm = DataMonitor(mock_timescale)
    alerts = await dm.check_freshness()
    stale = [a for a in alerts if a.source == "interest_rate"]
    assert len(stale) == 1
    assert stale[0].severity in ("WARNING", "ADVISORY")

async def test_no_freshness_alert_when_current(mock_timescale):
    mock_timescale.set_last_collection("interest_rate", datetime.now(timezone.utc))
    dm = DataMonitor(mock_timescale)
    alerts = await dm.check_freshness()
    assert not any(a.source == "interest_rate" for a in alerts)

async def test_drift_detection_kl_divergence(mock_timescale):
    dm = DataMonitor(mock_timescale)
    result = await dm.check_distribution_drift("interest_rate")
    assert isinstance(result.kl_divergence, float)
    assert result.drifted == (result.kl_divergence > 0.1)

async def test_anomaly_z_score(mock_timescale):
    mock_timescale.set_latest_value("base_rate", 8.0)  # normal ~3.0
    mock_timescale.set_90d_stats("base_rate", mean=3.25, std=0.5)
    dm = DataMonitor(mock_timescale)
    anomalies = await dm.check_anomalies("interest_rate")
    assert len(anomalies) >= 1
```

- [ ] **Step 2: Write failing tests for SystemMonitor**

```python
async def test_record_and_retrieve_metrics(mock_timescale):
    sm = SystemMonitor(mock_timescale)
    await sm.record_query_time("typedb", "match $x isa region;", 1500.0)
    slow = await sm.detect_slow_queries(threshold_ms=1000)
    assert len(slow) == 1
    assert slow[0].duration_ms == 1500.0

async def test_performance_summary(mock_timescale):
    sm = SystemMonitor(mock_timescale)
    summary = await sm.get_performance_summary()
    assert "typedb" in summary.components
    assert summary.components["typedb"].p95_ms >= 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/verification/test_data_monitor.py tests/verification/test_system_monitor.py -v`
Expected: FAIL

- [ ] **Step 4: Implement `DataMonitor`**

`check_freshness`: queries `MAX(ts)` per source table from TimescaleDB, compares against expected schedule (daily: +2h, weekly: +1d, monthly: +2d). `check_distribution_drift`: queries last 30 days and previous 30 days as histograms, computes KL-divergence via `scipy.special.kl_div`. `check_anomalies`: queries latest value and 90-day rolling stats, flags |Z| > 3.0. `check_cross_source_consistency`: compares overlapping metrics (e.g., base_rate from ECOS vs CD rate trend) for directional consistency.

- [ ] **Step 5: Implement `SystemMonitor`**

`record_query_time`: inserts into `ts_system_metrics`. `get_performance_summary`: aggregates p50/p95/p99 per component from last 24 hours. `detect_slow_queries`: queries `ts_system_metrics WHERE metric_value > threshold`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/verification/test_data_monitor.py tests/verification/test_system_monitor.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/verification/data_monitor.py homepy/verification/system_monitor.py tests/verification/
git commit -m "feat: data quality monitor (drift, freshness, anomaly) + system performance monitor"
```

---

### Task 5: Self-Healing Engine + Recovery Log

**Files:**
- Create: `homepy/verification/self_healer.py`
- Create: `tests/verification/test_self_healer.py`

**Interfaces:**
- Consumes: `TimescaleService`, `TypeDBService` from Plan A Task 6; collector and pipeline components from Plan B
- Produces:
  - `RecoveryPolicy(failure_type: str, max_retries: int, backoff_base_seconds: float, cooldown_seconds: float, escalate_after: int)` — dataclass
  - `SelfHealer(timescale_svc, typedb_svc, recovery_log_path: Path)` with methods:
    - `async handle_failure(failure_type: str, component: str, error: Exception) -> RecoveryEvent`
    - `async reconnect_db(db_type: str) -> bool`
    - `async archive_old_data(days_threshold: int = 90) -> int` (bytes freed)
    - `get_recovery_history(hours: int = 24) -> list[RecoveryEvent]`
  - `DEFAULT_POLICIES: dict[str, RecoveryPolicy]` — module constant

- [ ] **Step 1: Write failing tests**

```python
async def test_api_error_retries_with_backoff(mock_deps):
    healer = SelfHealer(mock_deps.timescale, mock_deps.typedb, tmp_path / "recovery.jsonl")
    event = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("timeout"))
    assert event.auto_action == "retry"
    assert event.success  # mock succeeds on retry

async def test_max_retries_escalates_to_human(mock_deps):
    mock_deps.set_permanent_failure("bok_ecos")
    healer = SelfHealer(mock_deps.timescale, mock_deps.typedb, tmp_path / "recovery.jsonl")
    event = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("down"))
    assert event.human_escalated is True
    assert event.success is False

async def test_recovery_log_persists(mock_deps, tmp_path):
    log_path = tmp_path / "recovery.jsonl"
    healer = SelfHealer(mock_deps.timescale, mock_deps.typedb, log_path)
    await healer.handle_failure("api_error", "test", ConnectionError("test"))
    history = healer.get_recovery_history(hours=1)
    assert len(history) == 1
    assert log_path.exists()

async def test_cooldown_prevents_rapid_retries(mock_deps, tmp_path):
    healer = SelfHealer(mock_deps.timescale, mock_deps.typedb, tmp_path / "recovery.jsonl")
    e1 = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("err"))
    e2 = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("err"))
    # Second call within cooldown should not retry
    assert e2.auto_action == "cooldown_active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/verification/test_self_healer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `SelfHealer`**

`DEFAULT_POLICIES` per spec Section 10.6 table: `api_error` (3 retries, 2s backoff, 300s cooldown), `db_disconnect` (5 retries, 1s backoff, 60s cooldown), `quality_gate_fail` (0 retries, escalate immediately), `inference_timeout` (1 retry with reduced batch, 120s cooldown), `disk_space` (archive action, 3600s cooldown). `handle_failure`: looks up policy, checks cooldown, retries with exponential backoff, logs to JSONL, escalates if max retries exceeded. Thread-safe with an asyncio lock per component.

- [ ] **Step 4: Run tests**

Run: `pytest tests/verification/test_self_healer.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/verification/self_healer.py tests/verification/test_self_healer.py
git commit -m "feat: self-healing engine — retry policies, cooldown, escalation, recovery log"
```

---

### Task 6: CI/CD Pipeline + Improvement Tracker

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/data-quality.yml`
- Create: `.github/workflows/dependency-audit.yml`
- Create: `homepy/verification/improvement_tracker.py`
- Create: `tests/verification/test_improvement_tracker.py`

**Interfaces:**
- Consumes: `CalibrationProposal`, `ImprovementRecord`, `RecoveryEvent` from Task 1; `TimescaleService` from Plan A Task 6
- Produces:
  - `ImprovementTracker(timescale_svc: TimescaleService)` with methods:
    - `async record(record: ImprovementRecord) -> str` (returns record_id)
    - `async list_recent(days: int = 30) -> list[ImprovementRecord]`
    - `async get_improvement_stats() -> ImprovementStats` (counts by category, trend)
    - `async rollback(record_id: str) -> ImprovementRecord`
  - 3 GitHub Actions workflows

- [ ] **Step 1: Write failing tests for ImprovementTracker**

```python
async def test_record_and_retrieve(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    record = ImprovementRecord(
        record_id="", timestamp=datetime.now(), category="calibration",
        component="scorer", before_state={"valuation_gap": 0.10},
        after_state={"valuation_gap": 0.12}, trigger="backtest_ic_analysis",
        evidence={"ic_before": 0.05, "ic_after": 0.12},
        impact_metrics=None, approved_by="user", rollback_possible=True
    )
    rid = await tracker.record(record)
    assert rid
    recent = await tracker.list_recent(days=1)
    assert len(recent) >= 1

async def test_rollback_restores_before_state(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    record = ImprovementRecord(
        record_id="R001", timestamp=datetime.now(), category="calibration",
        component="scorer", before_state={"valuation_gap": 0.10},
        after_state={"valuation_gap": 0.12}, trigger="test",
        evidence={}, impact_metrics=None, approved_by="user", rollback_possible=True
    )
    await tracker.record(record)
    rollback = await tracker.rollback("R001")
    assert rollback.before_state == {"valuation_gap": 0.12}  # swap
    assert rollback.after_state == {"valuation_gap": 0.10}    # restored

async def test_improvement_stats(mock_timescale):
    tracker = ImprovementTracker(mock_timescale)
    stats = await tracker.get_improvement_stats()
    assert "calibration" in stats.by_category
    assert "bugfix" in stats.by_category
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/verification/test_improvement_tracker.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `ImprovementTracker`**

`record`: generates UUID for `record_id` if empty, inserts into `ts_calibration_log`. `list_recent`: queries by date range. `rollback`: reads the record, creates a new reverse-record (before↔after), applies the `before_state` to the config file, records the rollback itself.

- [ ] **Step 4: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      typedb:
        image: vaticle/typedb:2.28.0
        ports: ["1729:1729"]
      timescaledb:
        image: timescale/timescaledb:latest-pg16
        ports: ["5432:5432"]
        env:
          POSTGRES_DB: homepy
          POSTGRES_USER: homepy
          POSTGRES_PASSWORD: homepy
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: mypy homepy/ --strict
      - run: pytest --cov=homepy --cov-fail-under=80 -v
```

- [ ] **Step 5: Create `.github/workflows/data-quality.yml`**

Scheduled workflow (weekly) that runs `DataMonitor.check_freshness()` and `check_distribution_drift()` against production-like data, posts results as a GitHub issue if any WARNING+ alerts.

- [ ] **Step 6: Create `.github/workflows/dependency-audit.yml`**

Scheduled workflow (weekly) that runs `pip-audit` and `safety check`, opens an issue if any critical or high-severity vulnerabilities found.

- [ ] **Step 7: Run tests**

Run: `pytest tests/verification/test_improvement_tracker.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/ homepy/verification/improvement_tracker.py tests/verification/
git commit -m "feat: CI/CD pipelines + improvement tracker with rollback"
```

---

### Task 7: Improvement Dashboard (Streamlit Page 10) + Integration

**Files:**
- Create: `homepy/app/pages/10_improvement_dashboard.py`
- Modify: `homepy/api/routers/pipeline.py` (add verification endpoints)
- Modify: `homepy/api/models/schemas.py` (add verification response models)
- Create: `tests/test_e2e_verification.py`

**Interfaces:**
- Consumes: `Backtester`, `AutoCalibrator`, `DataMonitor`, `SystemMonitor`, `SelfHealer`, `ImprovementTracker` from Tasks 1-6; `ApiClient` from Plan C Task 5
- Produces:
  - 4 new API endpoints:
    - `GET /api/v1/pipeline/verification/accuracy` → backtest accuracy summary
    - `GET /api/v1/pipeline/verification/proposals` → pending calibration proposals
    - `POST /api/v1/pipeline/verification/proposals/{id}/approve` → approve a proposal
    - `GET /api/v1/pipeline/verification/health` → system health overview
  - Streamlit Page 10 (Improvement Dashboard) with 8 sections per spec Section 10.8

- [ ] **Step 1: Add verification endpoints to `pipeline.py` router**

4 new endpoints. The approval endpoint calls `AutoCalibrator.apply_proposal()` and records via `ImprovementTracker`.

- [ ] **Step 2: Add Pydantic response models to `schemas.py`**

`BacktestSummaryResponse`, `CalibrationProposalResponse`, `SystemHealthResponse`, `ImprovementRecordResponse`.

- [ ] **Step 3: Implement Page 10 (Improvement Dashboard)**

8 sections per spec Section 10.8:
1. System health summary: status badges per component (inference, pipeline, TypeDB, TimescaleDB)
2. Inference accuracy trend: Plotly line chart of direction_accuracy and signal_hit_rate over time
3. Calibration proposals: list with approve/reject buttons using `st.button`
4. Data quality heatmap: Plotly heatmap (source × date → quality score)
5. Performance dashboard: API response time p50/p95 bar chart
6. Recovery history: recent auto-recovery events table
7. Improvement timeline: all `ImprovementRecord` entries as a Plotly timeline
8. Tech stack health: dependency versions + vulnerability status table

- [ ] **Step 4: Write E2E integration test**

```python
async def test_verification_roundtrip():
    """
    1. Insert historical verdicts and actual price data
    2. Run backtester
    3. Run auto-calibrator → get proposal
    4. Call API /verification/accuracy → check metrics
    5. Call API /verification/proposals → see pending proposal
    6. Approve proposal via API
    7. Verify ImprovementRecord created
    """
    pass
```

- [ ] **Step 5: Run E2E test**

Run: `pytest tests/test_e2e_verification.py -v`
Expected: PASS

- [ ] **Step 6: Verify Page 10 renders**

Run Streamlit, navigate to page 10, confirm all 8 sections render without errors.

- [ ] **Step 7: Commit**

```bash
git add homepy/app/pages/10_improvement_dashboard.py homepy/api/ tests/test_e2e_verification.py
git commit -m "feat: improvement dashboard + verification API endpoints + E2E test"
```
