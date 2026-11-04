# HOMEPY Plan B: Data Pipeline Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the L1 data collection layer (17 API collectors) and L2 data integration layer (ETL pipeline with Prefect orchestration), plus the DB synchronization bridge between TimescaleDB and TypeDB.

**Architecture:** Each collector inherits from `BaseCollector` and produces Parquet files in `data/raw/{source}/{date}/`. Prefect flows orchestrate 3-stage ETL (Clean → Transform → Load). The sync layer copies aggregated TimescaleDB values into TypeDB entity attributes and writes TypeDB inference results back to TimescaleDB's `ts_signals` table.

**Tech Stack:** Python 3.11+, httpx (async HTTP), pandas, Prefect 2.x, Great Expectations, Parquet (pyarrow), typedb-driver, asyncpg

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Sections 4.1–4.6)

**Depends on:** Plan A complete (both databases running with schemas loaded)

## Global Constraints

- Python ≥ 3.11
- All API keys loaded from environment variables, never hardcoded
- Raw data stored as Parquet in `data/raw/{source_name}/{YYYY-MM-DD}/`
- Cleaned data in `data/cleaned/{source_name}/{YYYY-MM-DD}/`
- Transformed data in `data/transformed/{domain}/{YYYY-MM-DD}/`
- Every collector must be testable with mocked HTTP responses (no live API calls in tests)
- Great Expectations suites stored in `pipelines/quality/expectations/`
- Prefect flows must be callable both via Prefect scheduler and directly as Python functions

## Review Focus

1. **API rate limiting** — Korean government APIs (MOLIT, KOSIS, ECOS) typically limit to 1000 requests/day. Collectors must respect rate limits with backoff and not crash when throttled.
2. **Parquet schema evolution** — when a government API adds a column, the collector must not break. Tests should verify that extra columns are preserved, not dropped.
3. **Timezone handling** — Korean data is KST (UTC+9). All timestamps stored in TimescaleDB must be UTC. Conversion must happen in Stage 1 (Clean), not at query time.
4. **Empty API responses** — some APIs return empty results for future dates or holidays. The pipeline must treat this as "no data" (skip), not "error" (fail).
5. **TypeDB transaction size** — inserting >1000 entities in a single TypeDB transaction can timeout. The sync layer must batch inserts in groups of 500.

---

### Task 1: BaseCollector & First Collector (BOK ECOS Interest Rate)

**Files:**
- Create: `homepy/collectors/__init__.py`
- Create: `homepy/collectors/base.py`
- Create: `homepy/collectors/bok_ecos.py`
- Create: `tests/collectors/__init__.py`
- Create: `tests/collectors/test_bok_ecos.py`
- Create: `tests/collectors/fixtures/ecos_interest_rate_response.json`

**Interfaces:**
- Consumes: nothing (first pipeline task)
- Produces:
  - `BaseCollector(source_name: str, api_base_url: str)` with methods: `async collect(start_date: date, end_date: date) -> Path` (returns path to saved Parquet), `async _fetch(endpoint: str, params: dict) -> dict`, `_save_raw(df: pd.DataFrame, date: date) -> Path`
  - `BokEcosCollector(api_key: str)` subclass, `collect()` fetches base rate, CD 91d, COFIX, treasury rates from ECOS API.

- [ ] **Step 1: Write failing test with mocked HTTP**

```python
@pytest.fixture
def mock_ecos_response():
    with open("tests/collectors/fixtures/ecos_interest_rate_response.json") as f:
        return json.load(f)

async def test_bok_ecos_collects_interest_rates(mock_ecos_response, tmp_path):
    collector = BokEcosCollector(api_key="test", data_dir=tmp_path)
    with respx.mock:
        respx.get(re.compile(r".*/StatisticSearch/.*")).respond(json=mock_ecos_response)
        result_path = await collector.collect(date(2026, 1, 1), date(2026, 1, 31))
    df = pd.read_parquet(result_path)
    assert "base_rate" in df.columns
    assert len(df) > 0
```

- [ ] **Step 2: Create fixture file**

`ecos_interest_rate_response.json` — a minimal valid ECOS API response with StatisticSearch result containing 3 rows of interest rate data.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/collectors/test_bok_ecos.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement `BaseCollector`**

Abstract base with `__init__(source_name, api_base_url, data_dir)`, `_fetch` using httpx.AsyncClient with retry (3 attempts, exponential backoff), `_save_raw` writing DataFrame to `data_dir/raw/{source_name}/{date}/data.parquet`.

- [ ] **Step 5: Implement `BokEcosCollector`**

Subclass of BaseCollector. `collect()` calls ECOS StatisticSearch API for 4 stat codes (base rate, CD, COFIX, treasury). Parses the response list into a DataFrame with columns: `ts, base_rate, cd_rate_91d, cofix_rate, treasury_3y, treasury_10y, mortgage_rate_avg`. Derives `rate_direction` from 3-month trend.

- [ ] **Step 6: Run tests**

Run: `pytest tests/collectors/test_bok_ecos.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add homepy/collectors/ tests/collectors/
git commit -m "feat: BaseCollector + BOK ECOS interest rate collector"
```

---

### Task 2: Remaining Macro & Price Collectors

**Files:**
- Create: `homepy/collectors/molit_trade.py`
- Create: `homepy/collectors/reb_index.py`
- Create: `homepy/collectors/kosis.py`
- Create: `tests/collectors/test_molit_trade.py`
- Create: `tests/collectors/test_reb_index.py`
- Create: `tests/collectors/test_kosis.py`
- Create: fixture JSON files for each

**Interfaces:**
- Consumes: `BaseCollector` from Task 1
- Produces:
  - `MolitTradeCollector(api_key)` — `collect(region_code, start_ym, end_ym) -> Path`. Columns: `ts, district_code, dong_code, complex_name, area_sqm, floor, price, trade_type`
  - `RebIndexCollector(api_key)` — `collect(start_date, end_date) -> Path`. Columns: `ts, region_code, price_index, price_change_mom, price_change_yoy, jeonse_index`
  - `KosisCollector(api_key)` — `collect(stat_id, start_date, end_date) -> Path`. Generic KOSIS wrapper. Stat IDs for population, migration, income, CPI, GDP.

- [ ] **Step 1: Write failing tests (3 test files, one per collector)**

Each test mocks the respective API, calls `collect()`, and asserts the Parquet output has the expected columns and at least 1 row.

- [ ] **Step 2: Create fixture JSON files**

Minimal valid responses for each API (MOLIT real trade XML, REB JSON, KOSIS JSON).

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/collectors/ -v -k "molit or reb or kosis"`
Expected: FAIL

- [ ] **Step 4: Implement all three collectors**

Each extends BaseCollector. MolitTradeCollector handles XML response parsing. RebIndexCollector and KosisCollector handle JSON. All produce Parquet in the standard `data/raw/{source}/{date}/` layout.

- [ ] **Step 5: Run tests**

Run: `pytest tests/collectors/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/collectors/ tests/collectors/
git commit -m "feat: MOLIT trade, REB index, KOSIS collectors"
```

---

### Task 3: Supply, Loan, Regulation, Sentiment Collectors

**Files:**
- Create: `homepy/collectors/molit_supply.py`
- Create: `homepy/collectors/molit_building.py`
- Create: `homepy/collectors/molit_official_price.py`
- Create: `homepy/collectors/loan_rates.py`
- Create: `homepy/collectors/regulation_monitor.py`
- Create: `homepy/collectors/tax_rule_monitor.py`
- Create: `homepy/collectors/sentiment.py`
- Create: corresponding test files and fixtures

**Interfaces:**
- Consumes: `BaseCollector` from Task 1
- Produces:
  - `MolitSupplyCollector` — columns: `ts, district_code, permits_issued, construction_starts, completions, presale_volume, unsold_total, unsold_after_completion`
  - `LoanRateCollector` — columns: `ts, loan_type, lender_type, interest_type, rate_min, rate_max`
  - `RegulationMonitor` — columns: `ts, zone_type, district_code, action (designate/release)`
  - `SentimentCollector` — columns: `ts, district_code, buyer_sentiment, seller_sentiment, search_trend_index`
  - Others follow same pattern

- [ ] **Step 1: Write failing tests (one per collector, mocked HTTP)**

- [ ] **Step 2: Create fixture files**

- [ ] **Step 3: Implement all 7 collectors**

`MolitBuildingCollector` and `MolitOfficialPriceCollector` handle building registry and official price APIs. `TaxRuleMonitor` wraps TaxDoctor MCP or national tax law crawling. Each follows BaseCollector pattern.

- [ ] **Step 4: Run all collector tests**

Run: `pytest tests/collectors/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/collectors/ tests/collectors/
git commit -m "feat: supply, loan, regulation, sentiment collectors (7 collectors)"
```

---

### Task 4: ETL Stage 1 — Clean & Validate

**Files:**
- Create: `homepy/pipelines/__init__.py`
- Create: `homepy/pipelines/stages/__init__.py`
- Create: `homepy/pipelines/stages/clean.py`
- Create: `homepy/pipelines/quality/__init__.py`
- Create: `homepy/pipelines/quality/gates.py`
- Create: `tests/pipelines/__init__.py`
- Create: `tests/pipelines/test_clean.py`

**Interfaces:**
- Consumes: Parquet files from collectors (Task 1-3)
- Produces:
  - `clean_source(source_name: str, raw_path: Path) -> CleanResult` where `CleanResult = namedtuple("CleanResult", ["output_path", "quality_report", "passed"])`. Output in `data/cleaned/{source}/{date}/`.
  - `QualityGate(null_ratio_max: float, duplicate_ratio_max: float, schema_match: bool)` with method `check(df: pd.DataFrame, expected_schema: dict) -> QualityReport`

- [ ] **Step 1: Write failing tests**

```python
def test_clean_removes_duplicates():
    raw = pd.DataFrame({"ts": ["2026-01-01"]*3, "base_rate": [3.25]*3})
    result = clean_source("test", raw_path_with_dupes)
    df = pd.read_parquet(result.output_path)
    assert len(df) == 1

def test_clean_flags_high_null_ratio():
    raw = pd.DataFrame({"ts": [None]*10, "base_rate": [3.25]*10})
    result = clean_source("test", raw_path_with_nulls)
    assert not result.passed  # >5% null ratio
```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement `clean.py`**

Source-specific cleaning rules as a registry dict (spec Section 4.3 Stage 1 table). Common steps: schema validation, dedup by natural key, null handling per source, outlier flagging via IQR. Timezone conversion (KST→UTC) for all `ts` columns. Saves to cleaned directory.

- [ ] **Step 4: Implement `gates.py`**

`QualityGate` class checks null ratio, duplicate ratio, schema match. Returns `QualityReport` with pass/fail and details.

- [ ] **Step 5: Run tests**

Run: `pytest tests/pipelines/test_clean.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/pipelines/ tests/pipelines/
git commit -m "feat: ETL Stage 1 — clean & validate with quality gates"
```

---

### Task 5: ETL Stage 2 — Transform & Enrich

**Files:**
- Create: `homepy/pipelines/stages/transform.py`
- Create: `homepy/pipelines/transformers/__init__.py`
- Create: `homepy/pipelines/transformers/price_transformer.py`
- Create: `homepy/pipelines/transformers/macro_transformer.py`
- Create: `homepy/pipelines/transformers/cycle_classifier.py`
- Create: `homepy/pipelines/transformers/supply_demand.py`
- Create: `homepy/pipelines/transformers/sentiment_composer.py`
- Create: `tests/pipelines/test_transform.py`

**Interfaces:**
- Consumes: Cleaned Parquet from Task 4
- Produces:
  - `transform_domain(domain: str, cleaned_paths: dict[str, Path]) -> Path` — outputs to `data/transformed/{domain}/{date}/`
  - `PriceTransformer.transform(df) -> df` — adds `price_per_sqm`, moving averages (3/6/12M), YoY/MoM change, district aggregates
  - `MacroTransformer.transform(df) -> df` — adds `rate_direction`, `real_interest_rate`, `liquidity_growth_rate`
  - `CycleClassifier.classify(price_index_df, macro_df) -> df` — HP filter + phase classification (recovery/expansion/peak/contraction), leading/coincident indices
  - `SupplyDemandTransformer.transform(supply_df, population_df, migration_df) -> df` — supply-demand gap, PIR, months of inventory
  - `SentimentComposer.compose(sentiment_df, volume_df, jeonse_df, search_df) -> df` — fear/greed index (0-100)

- [ ] **Step 1: Write failing tests**

```python
def test_price_transformer_calculates_per_sqm():
    df = pd.DataFrame({"price": [500000000], "area_sqm": [84.0]})
    result = PriceTransformer().transform(df)
    assert "price_per_sqm" in result.columns
    assert result.iloc[0]["price_per_sqm"] == pytest.approx(500000000 / 84.0)

def test_cycle_classifier_detects_expansion():
    # 12 months of steadily rising price index
    df = pd.DataFrame({
        "ts": pd.date_range("2025-01", periods=12, freq="MS"),
        "price_index": range(100, 112)
    })
    result = CycleClassifier().classify(df, macro_df=None)
    assert result.iloc[-1]["cycle_phase"] == "expansion"

def test_sentiment_composer_fear_greed():
    df = pd.DataFrame({
        "buyer_sentiment": [25],  # low = fear
        "jeonse_ratio": [0.80],   # high = fear
        "volume_change": [-15.0], # negative = fear
        "search_trend": [30],     # low = fear
    })
    result = SentimentComposer().compose(df)
    assert result.iloc[0]["fear_greed_index"] < 30  # fear territory
```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement transformers**

Each transformer is a class with a `transform(df) -> df` method. CycleClassifier uses scipy for HP filter (lambda=14400 for monthly). SentimentComposer normalizes 4 components to 0-100 and averages with weights (buyer_sentiment 0.35, jeonse_ratio 0.25, volume_change 0.25, search_trend 0.15).

- [ ] **Step 4: Implement `transform.py` orchestrator**

`transform_domain` selects the right transformer(s) by domain name, passes cleaned data, saves to transformed directory.

- [ ] **Step 5: Run tests**

Run: `pytest tests/pipelines/test_transform.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/pipelines/ tests/pipelines/test_transform.py
git commit -m "feat: ETL Stage 2 — 5 domain transformers with cycle classifier"
```

---

### Task 6: ETL Stage 3 — Load & DB Sync

**Files:**
- Create: `homepy/pipelines/stages/load.py`
- Create: `homepy/sync/__init__.py`
- Create: `homepy/sync/timescale_to_typedb.py`
- Create: `homepy/sync/typedb_to_timescale.py`
- Create: `homepy/sync/lineage_tracker.py`
- Create: `tests/pipelines/test_load.py`
- Create: `tests/sync/test_sync.py`

**Interfaces:**
- Consumes: Transformed Parquet from Task 5, DB service layers from Plan A Task 6
- Produces:
  - `load_to_timescale(domain: str, transformed_path: Path, timescale_svc: TimescaleService) -> int` — bulk inserts, returns row count
  - `sync_aggregates_to_typedb(timescale_svc, typedb_svc) -> SyncReport` — runs aggregation queries on TimescaleDB, upserts attributes on TypeDB entities
  - `sync_signals_to_timescale(typedb_svc, timescale_svc) -> int` — queries TypeDB for inferred signals, inserts to `ts_signals`
  - `LineageTracker.record(source, stage, output, quality_report) -> None` — appends to catalog

- [ ] **Step 1: Write failing tests**

```python
async def test_load_to_timescale_inserts_rows():
    df = pd.DataFrame({
        "ts": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
        "base_rate": [3.25], "rate_direction": ["falling"]
    })
    path = save_test_parquet(df)
    count = await load_to_timescale("macro", path, timescale_svc)
    assert count == 1

async def test_sync_aggregates_updates_typedb():
    # Pre-insert price data into TimescaleDB, complex into TypeDB
    # Run sync, verify TypeDB complex now has price-per-sqm attribute
    pass

async def test_sync_signals_writes_to_timescale():
    # Pre-load TypeDB with data that triggers undervalued-signal rule
    # Run sync, verify ts_signals has a row
    pass
```

- [ ] **Step 2: Run to verify failures**

- [ ] **Step 3: Implement `load.py`**

Reads transformed Parquet, maps columns to table schema, calls `TimescaleService.insert_batch`. Handles column name mapping (snake_case Parquet → snake_case SQL).

- [ ] **Step 4: Implement `timescale_to_typedb.py`**

Runs predefined aggregation queries (spec Section 4.5 mapping table). For each mapping: query TimescaleDB → for each row, build TypeQL `match $e isa <type>, has <key> <val>; delete $e has <attr> $old; insert $e has <attr> <new>;`. Batches of 500 inserts per transaction.

- [ ] **Step 5: Implement `typedb_to_timescale.py`**

Queries TypeDB for inferred relation instances (e.g., `match (subject: $c) isa undervalued-signal; get $c;`). Converts each to a `ts_signals` row with columns: `ts, signal_type, target_id, target_type, confidence, rule_name`.

- [ ] **Step 6: Implement `lineage_tracker.py`**

Simple append-only JSON log in `data/catalog/lineage.jsonl`. Each record: `{timestamp, source, stage, input_path, output_path, row_count, quality_passed}`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/pipelines/test_load.py tests/sync/test_sync.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/pipelines/stages/load.py homepy/sync/ tests/
git commit -m "feat: ETL Stage 3 load + bidirectional DB sync + lineage tracking"
```

---

### Task 7: Prefect Flows & Orchestration

**Files:**
- Create: `homepy/pipelines/flows/__init__.py`
- Create: `homepy/pipelines/flows/daily_flow.py`
- Create: `homepy/pipelines/flows/weekly_flow.py`
- Create: `homepy/pipelines/flows/monthly_flow.py`
- Create: `homepy/pipelines/flows/event_flow.py`
- Create: `tests/pipelines/test_flows.py`

**Interfaces:**
- Consumes: Collectors (Tasks 1-3), Stages (Tasks 4-6)
- Produces:
  - `daily_pipeline() -> FlowResult` — Prefect flow: collect (real_trade, interest_rate, exchange_rate) → clean → transform(price, macro) → load → sync → inference trigger
  - `weekly_pipeline() -> FlowResult` — price_index, loan_rate, sentiment, complex_info
  - `monthly_pipeline() -> FlowResult` — liquidity, population, migration, supply, unsold, macro_index
  - `event_pipeline(event_type: str) -> FlowResult` — regulation or tax_rule change

- [ ] **Step 1: Write failing test**

```python
async def test_daily_flow_runs_end_to_end(mock_all_apis):
    result = await daily_pipeline(date=date(2026, 1, 15))
    assert result.state.is_completed()
    assert result.collected_sources == ["real_trade", "interest_rate", "exchange_rate"]
```

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement flows**

Each flow is a `@flow`-decorated async function. Tasks within use `@task`. Daily flow: parallel collect 3 sources → sequential clean → transform(price) + transform(macro) in parallel → load → sync_aggregates → sync_signals. Error handling: if one collector fails, the others continue; a critical quality gate failure stops the load.

- [ ] **Step 4: Run flow tests**

Run: `pytest tests/pipelines/test_flows.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add homepy/pipelines/flows/ tests/pipelines/test_flows.py
git commit -m "feat: Prefect orchestration flows (daily, weekly, monthly, event)"
```
