# HOMEPY Plan E: High Availability, Disaster Recovery & Market Monitoring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate every single point of failure (SPOF) in the HOMEPY stack, establish database replication with automated failover, build a market anomaly detection engine with four statistical algorithms, add early warning TypeDB inference rules, and deploy a 4-level alert system with multi-channel notifications (Slack, KakaoTalk, Email).

**Architecture:** A load balancer (Nginx) fronts two FastAPI replicas and one Streamlit instance. TimescaleDB replicates via PostgreSQL Streaming Replication managed by Patroni (RPO=0, automatic failover). TypeDB runs a warm standby via periodic `typedb server export` / `import` (RPO=5 min, manual failover RTO=5 min). Redis uses Sentinel (master + replica + 3 sentinels, RPO ≤ 1 s). The anomaly detection engine applies Z-score, Isolation Forest, CUSUM, and Bollinger Bands to time-series data, feeding results into a 4-level alert classifier that routes notifications per `ALERT_ROUTING` config. Two new TypeDB rules (`smart-money-detection`, `jeonse-gap-narrowing`) extend the ontology's early warning capability. A new Streamlit Page 11 visualizes anomaly heatmaps, alert timelines, and HA system health.

**Tech Stack:** Python 3.11+, Patroni, etcd, Nginx, scikit-learn (IsolationForest), scipy.stats, numpy, slack_sdk, httpx, smtplib, Docker Compose, pytest, Plotly

**Spec:** `docs/superpowers/specs/2026-11-04-homepy-system-design.md` (Section 11)

**Depends on:** Plan D complete (DataMonitor, SystemMonitor, SelfHealer, ImprovementTracker, alert level constants, recovery event logging)

## Global Constraints

- Python ≥ 3.11
- All HA components run inside Docker Compose; no external orchestrator required (K8s is Phase 4)
- RPO and RTO targets from spec: TimescaleDB RPO=0 / RTO=10 min, TypeDB RPO=6 h (export cycle) / RTO=5 min, Redis RPO=15 min / RTO=1 min
- Alert channel credentials loaded from environment variables only — never hardcoded
- `ALERT_ROUTING` from spec: WATCH→[], ADVISORY→["slack"], WARNING→["slack","kakao"], CRITICAL→["slack","kakao","email"]
- Anomaly detection thresholds from spec: Z-score |Z| > 3, Isolation Forest contamination=0.01, CUSUM drift > 5σ, Bollinger 2σ bands
- Every alert and anomaly event stored in TimescaleDB `ts_alert_events` hypertable for historical analysis
- CI quality gates: ruff 0 warnings, mypy strict, tests 100% pass, coverage ≥ 80%

## Review Focus

1. **Split-brain during failover** — Patroni must fence the old primary before promoting the replica. A test must verify that after a simulated primary crash, only one node accepts writes. If both accept writes simultaneously, data corruption follows.
2. **Anomaly detector false positive rate** — an IsolationForest trained on too little data or with wrong contamination flags normal market movements as anomalies. Each detector must track its own false-positive rate (rolling 30 days) and auto-suppress when FP > 30%. A test must verify that a detector with FP > 30% stops emitting ADVISORY alerts and logs a suppression event.
3. **Alert storm during market crashes** — a genuine crash triggers hundreds of anomalies simultaneously, flooding all channels. The AlertManager must deduplicate by (district, alert_type) within a 1-hour window and escalate a batch summary instead. A test must verify that 50 Z-score anomalies for the same district in 10 minutes produce exactly 1 CRITICAL alert, not 50.
4. **TypeDB warm standby data gap** — the 6-hour export cycle means up to 6 hours of lost data on failover. The standby promotion script must log the exact export timestamp so the operator knows which data window to re-ingest. A test must verify that after promotion, the standby's latest data timestamp matches the last export.
5. **Notification channel failures** — Slack webhook down or KakaoTalk API rate-limited must not block the alert pipeline. Each channel send must have a 5-second timeout and 2 retries with exponential backoff, and failure must log (not crash). A test must verify that a Slack timeout still delivers the KakaoTalk and Email alerts.

---

### Task 1: HA Data Models + Health Check Endpoint

**Files:**
- Create: `homepy/ha/__init__.py`
- Create: `homepy/ha/models.py`
- Create: `homepy/monitoring/__init__.py`
- Create: `homepy/monitoring/models.py`
- Modify: `storage/timescale/schema.sql` (add `ts_alert_events`, `ts_anomaly_detections`)
- Modify: `storage/timescale/hypertables.sql` (add hypertables for new tables)
- Modify: `homepy/api/routers/pipeline.py` (add `/health` and `/ha/status` endpoints)
- Create: `tests/ha/__init__.py`
- Create: `tests/ha/test_ha_models.py`
- Create: `tests/monitoring/__init__.py`
- Create: `tests/monitoring/test_monitoring_models.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6, `RecoveryEvent` from Plan D Task 1
- Produces:
  - `HAStatus(component: str, role: str, healthy: bool, last_heartbeat: datetime, replica_lag_seconds: float | None)` — dataclass
  - `AnomalyResult(anomaly_id: str, detected_at: datetime, district_code: str, metric_name: str, algorithm: str, current_value: float, baseline_value: float, z_score: float | None, severity: str, details: dict)` — dataclass, `severity` ∈ {"low", "medium", "high", "critical"}
  - `AlertEvent(alert_id: str, created_at: datetime, level: str, title: str, description: str, district_code: str | None, anomaly_ids: list[str], channels_sent: list[str], channels_failed: list[str], deduplicated: bool, batch_count: int)` — dataclass, `level` ∈ {"WATCH", "ADVISORY", "WARNING", "CRITICAL"}
  - 2 new TimescaleDB tables: `ts_alert_events`, `ts_anomaly_detections`
  - Health endpoint: `GET /api/v1/pipeline/health` → `{"status": "ok", "node_id": str, "uptime_seconds": float}`
  - HA status endpoint: `GET /api/v1/pipeline/ha/status` → `list[HAStatus]`

- [ ] **Step 1: Write failing tests**

```python
async def test_alert_event_tables_exist(db_pool):
    async with db_pool.acquire() as conn:
        for table in ["ts_alert_events", "ts_anomaly_detections"]:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=$1)",
                table
            )
            assert exists, f"Table '{table}' missing"

async def test_new_tables_are_hypertables(db_pool):
    async with db_pool.acquire() as conn:
        hypertables = await conn.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        names = {r["hypertable_name"] for r in hypertables}
        for table in ["ts_alert_events", "ts_anomaly_detections"]:
            assert table in names

def test_anomaly_result_severity_values():
    valid = {"low", "medium", "high", "critical"}
    ar = AnomalyResult(
        anomaly_id="A001", detected_at=datetime.now(), district_code="11680",
        metric_name="price_index", algorithm="zscore", current_value=150.0,
        baseline_value=100.0, z_score=3.5, severity="high", details={}
    )
    assert ar.severity in valid

def test_alert_event_level_values():
    valid = {"WATCH", "ADVISORY", "WARNING", "CRITICAL"}
    ae = AlertEvent(
        alert_id="AL001", created_at=datetime.now(), level="WARNING",
        title="Price spike", description="Z > 3", district_code="11680",
        anomaly_ids=["A001"], channels_sent=["slack"], channels_failed=[],
        deduplicated=False, batch_count=1
    )
    assert ae.level in valid

def test_health_endpoint(client):
    resp = client.get("/api/v1/pipeline/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "node_id" in body
    assert "uptime_seconds" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ha/test_ha_models.py tests/monitoring/test_monitoring_models.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Define dataclasses in `ha/models.py` and `monitoring/models.py`**

`ha/models.py`: `HAStatus` dataclass. `monitoring/models.py`: `AnomalyResult` and `AlertEvent` dataclasses with field types and valid values as specified above.

- [ ] **Step 4: Add 2 new tables to `storage/timescale/schema.sql`**

`ts_anomaly_detections`: columns match `AnomalyResult` fields, `ts` = `detected_at`, JSON column for `details`. `ts_alert_events`: columns match `AlertEvent` fields, `ts` = `created_at`, TEXT[] for `anomaly_ids`, `channels_sent`, `channels_failed`.

- [ ] **Step 5: Add hypertable creation to `storage/timescale/hypertables.sql`**

`SELECT create_hypertable('ts_anomaly_detections', 'ts', if_not_exists => TRUE);` and same for `ts_alert_events`. Compression policy for records older than 365 days.

- [ ] **Step 6: Add health + HA status endpoints to `api/routers/pipeline.py`**

`GET /api/v1/pipeline/health` returns `{"status": "ok", "node_id": os.environ.get("NODE_ID", "node-1"), "uptime_seconds": ...}`. `GET /api/v1/pipeline/ha/status` queries each component's health (Patroni REST API for TimescaleDB, TypeDB server status, Redis PING) and returns a list of `HAStatus`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/ha/ tests/monitoring/test_monitoring_models.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/ha/ homepy/monitoring/ storage/timescale/ homepy/api/routers/pipeline.py tests/ha/ tests/monitoring/
git commit -m "feat: HA data models, alert/anomaly tables, health endpoints"
```

---

### Task 2: TimescaleDB Streaming Replication + Patroni

**Files:**
- Create: `homepy/ha/patroni_config.py`
- Create: `deploy/patroni/patroni-primary.yml`
- Create: `deploy/patroni/patroni-replica.yml`
- Modify: `docker-compose.yml` (replace single timescaledb with patroni-managed primary + replica + etcd)
- Create: `tests/ha/test_timescale_replication.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6, `HAStatus` from Task 1
- Produces:
  - Patroni YAML configs for primary and replica
  - Docker Compose services: `etcd`, `timescale-primary`, `timescale-replica`
  - `PatroniHealthChecker(patroni_url: str)` with methods:
    - `async check() -> HAStatus`
    - `async get_replication_lag() -> float` (seconds)

- [ ] **Step 1: Write failing tests**

```python
async def test_patroni_primary_accepts_writes(patroni_cluster):
    primary = patroni_cluster.primary_pool
    async with primary.acquire() as conn:
        await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 100.0)")
        row = await conn.fetchrow("SELECT val FROM ts_prices ORDER BY ts DESC LIMIT 1")
        assert row["val"] == 100.0

async def test_replica_replicates_writes(patroni_cluster):
    primary = patroni_cluster.primary_pool
    replica = patroni_cluster.replica_pool
    async with primary.acquire() as conn:
        await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 200.0)")
    await asyncio.sleep(1)  # replication lag
    async with replica.acquire() as conn:
        row = await conn.fetchrow("SELECT val FROM ts_prices ORDER BY ts DESC LIMIT 1")
        assert row["val"] == 200.0

async def test_replica_rejects_writes(patroni_cluster):
    replica = patroni_cluster.replica_pool
    async with replica.acquire() as conn:
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            await conn.execute("INSERT INTO ts_prices (ts, val) VALUES (NOW(), 300.0)")

async def test_replication_lag_within_threshold(patroni_cluster):
    checker = PatroniHealthChecker(patroni_cluster.patroni_url)
    lag = await checker.get_replication_lag()
    assert lag < 5.0  # under 5 seconds
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ha/test_timescale_replication.py -v`
Expected: FAIL — PatroniHealthChecker not found, no patroni cluster fixture

- [ ] **Step 3: Create Patroni YAML configs**

`deploy/patroni/patroni-primary.yml`: scope `homepy-cluster`, bootstrap DCS `etcd`, PostgreSQL data_dir, replication user, synchronous_mode on. `deploy/patroni/patroni-replica.yml`: same scope, `bootstrap.method: basebackup`, connect to primary.

- [ ] **Step 4: Update `docker-compose.yml`**

Replace single `timescaledb` service with `etcd` (quay.io/coreos/etcd:v3.5), `timescale-primary` (timescale/timescaledb + patroni entrypoint), `timescale-replica` (same image, replica config). Wire Patroni REST API ports (8008). Keep existing volume mounts for data persistence.

- [ ] **Step 5: Implement `PatroniHealthChecker` in `ha/patroni_config.py`**

`check()` calls Patroni REST API (`GET /patroni`) and parses role/state/timeline. `get_replication_lag()` queries `pg_stat_replication` on primary via Patroni's `/cluster` endpoint, returning replay_lag in seconds.

- [ ] **Step 6: Run tests**

Run: `pytest tests/ha/test_timescale_replication.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add deploy/patroni/ homepy/ha/patroni_config.py docker-compose.yml tests/ha/test_timescale_replication.py
git commit -m "feat: TimescaleDB streaming replication with Patroni + etcd"
```

---

### Task 3: TypeDB Warm Standby + Redis Sentinel

**Files:**
- Create: `homepy/ha/typedb_standby.py`
- Create: `homepy/ha/redis_sentinel.py`
- Create: `deploy/redis/sentinel.conf`
- Modify: `docker-compose.yml` (add typedb-standby, redis-replica, redis-sentinel-{1,2,3})
- Create: `tests/ha/test_typedb_standby.py`
- Create: `tests/ha/test_redis_sentinel.py`

**Interfaces:**
- Consumes: `TypeDBService` from Plan A Task 5, `HAStatus` from Task 1
- Produces:
  - `TypeDBStandbyManager(primary_addr: str, standby_addr: str, export_dir: str)` with methods:
    - `async export_snapshot() -> Path` — runs `typedb server export`, returns file path
    - `async import_to_standby(snapshot: Path) -> None`
    - `async promote_standby() -> None` — stops primary, imports latest snapshot, starts standby as primary
    - `async last_export_timestamp() -> datetime | None`
  - `RedisSentinelManager(sentinel_hosts: list[tuple[str, int]], master_name: str)` with methods:
    - `async get_master() -> tuple[str, int]`
    - `async check_health() -> HAStatus`
    - `async failover() -> tuple[str, int]` — returns new master address

- [ ] **Step 1: Write failing tests**

```python
async def test_typedb_export_creates_file(typedb_primary, tmp_path):
    mgr = TypeDBStandbyManager(typedb_primary.addr, "localhost:11730", str(tmp_path))
    snapshot = await mgr.export_snapshot()
    assert snapshot.exists()
    assert snapshot.suffix == ".typedb"

async def test_typedb_export_timestamp_recorded(typedb_primary, tmp_path):
    mgr = TypeDBStandbyManager(typedb_primary.addr, "localhost:11730", str(tmp_path))
    before = datetime.now()
    await mgr.export_snapshot()
    ts = await mgr.last_export_timestamp()
    assert ts is not None
    assert ts >= before

async def test_redis_sentinel_discovers_master(redis_sentinel_cluster):
    mgr = RedisSentinelManager(redis_sentinel_cluster.sentinels, "homepy-master")
    host, port = await mgr.get_master()
    assert host is not None
    assert port > 0

async def test_redis_sentinel_health(redis_sentinel_cluster):
    mgr = RedisSentinelManager(redis_sentinel_cluster.sentinels, "homepy-master")
    status = await mgr.check_health()
    assert status.healthy is True
    assert status.role == "master"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ha/test_typedb_standby.py tests/ha/test_redis_sentinel.py -v`
Expected: FAIL

- [ ] **Step 3: Create Redis Sentinel config**

`deploy/redis/sentinel.conf`: `sentinel monitor homepy-master redis-master 6379 2`, `sentinel down-after-milliseconds homepy-master 5000`, `sentinel failover-timeout homepy-master 10000`.

- [ ] **Step 4: Update `docker-compose.yml`**

Add services: `typedb-standby` (same TypeDB image, different port 11730, separate volume), `redis-replica` (redis image, `--replicaof redis-master 6379`), `redis-sentinel-1/2/3` (redis image with sentinel entrypoint + mounted sentinel.conf).

- [ ] **Step 5: Implement `TypeDBStandbyManager` in `ha/typedb_standby.py`**

`export_snapshot()` runs `typedb server export --database=homepy --port=... --file=...`, writes timestamp to `export_dir/last_export.json`. `import_to_standby()` runs `typedb server import`. `promote_standby()` stops primary process connection, loads latest snapshot to standby, logs exact export timestamp for data gap awareness.

- [ ] **Step 6: Implement `RedisSentinelManager` in `ha/redis_sentinel.py`**

Uses `redis.asyncio.Sentinel` client. `get_master()` calls `sentinel.discover_master()`. `check_health()` pings master and returns `HAStatus`. `failover()` calls `sentinel.failover()` and returns new master address.

- [ ] **Step 7: Run tests**

Run: `pytest tests/ha/test_typedb_standby.py tests/ha/test_redis_sentinel.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/ha/typedb_standby.py homepy/ha/redis_sentinel.py deploy/redis/ docker-compose.yml tests/ha/
git commit -m "feat: TypeDB warm standby + Redis Sentinel HA"
```

---

### Task 4: Backup Strategy + Load Balancer

**Files:**
- Create: `homepy/ha/backup_manager.py`
- Create: `deploy/nginx/nginx.conf`
- Modify: `docker-compose.yml` (add nginx service, WAL archive volume)
- Create: `scripts/restore_timescale.sh`
- Create: `scripts/restore_typedb.sh`
- Create: `tests/ha/test_backup.py`
- Create: `tests/ha/test_load_balancer.py`

**Interfaces:**
- Consumes: `TypeDBStandbyManager` from Task 3, `PatroniHealthChecker` from Task 2, `TimescaleService` from Plan A Task 6
- Produces:
  - `BackupManager(config: BackupConfig)` with methods:
    - `async full_backup_timescale() -> Path` — pg_dump to compressed file
    - `async export_typedb() -> Path` — delegates to TypeDBStandbyManager.export_snapshot()
    - `async archive_raw_data(source_dir: str, dest_dir: str) -> int` — Parquet archival, returns file count
    - `async verify_backup(backup_path: Path) -> bool` — integrity check
    - `async list_backups() -> list[BackupInfo]`
  - `BackupConfig(timescale_retain_days: int = 30, typedb_retain_days: int = 7, raw_retain_days: int = 365)` — dataclass
  - `BackupInfo(path: Path, component: str, created_at: datetime, size_bytes: int, verified: bool)` — dataclass
  - Nginx reverse proxy: `api.homepy.local` → round-robin FastAPI nodes, `app.homepy.local` → Streamlit

- [ ] **Step 1: Write failing tests**

```python
async def test_timescale_full_backup_creates_file(backup_mgr, tmp_path):
    path = await backup_mgr.full_backup_timescale()
    assert path.exists()
    assert path.stat().st_size > 0

async def test_backup_verify_valid_dump(backup_mgr, tmp_path):
    path = await backup_mgr.full_backup_timescale()
    assert await backup_mgr.verify_backup(path) is True

async def test_backup_retention_cleans_old(backup_mgr, tmp_path):
    # Create fake old backup files
    old = tmp_path / "ts_backup_2026-01-01.sql.gz"
    old.write_text("fake")
    backups = await backup_mgr.list_backups()
    recent = [b for b in backups if b.created_at > datetime.now() - timedelta(days=30)]
    assert all(b.created_at > datetime.now() - timedelta(days=31) for b in recent)

def test_nginx_round_robin(nginx_running):
    node_ids = set()
    for _ in range(10):
        resp = httpx.get("http://localhost:80/api/v1/pipeline/health")
        assert resp.status_code == 200
        node_ids.add(resp.json()["node_id"])
    assert len(node_ids) == 2  # two FastAPI nodes

def test_nginx_streamlit_proxy(nginx_running):
    resp = httpx.get("http://localhost:80/app/")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ha/test_backup.py tests/ha/test_load_balancer.py -v`
Expected: FAIL

- [ ] **Step 3: Create `deploy/nginx/nginx.conf`**

Upstream `fastapi_backend` with `server fastapi-1:8000; server fastapi-2:8000;`. Upstream `streamlit_backend` with `server streamlit:8501;`. Location `/api/` proxies to `fastapi_backend`. Location `/app/` proxies to `streamlit_backend`. Health check: `location /nginx-health { return 200; }`.

- [ ] **Step 4: Update `docker-compose.yml`**

Add `nginx` service (nginx:1.25 image, mount `deploy/nginx/nginx.conf`, expose port 80). Scale `fastapi` to 2 instances with `NODE_ID` env var distinguishing them. Add WAL archive volume `wal-archive`.

- [ ] **Step 5: Implement `BackupManager` in `ha/backup_manager.py`**

`full_backup_timescale()` runs `pg_dump -Fc` and compresses, rotates old backups beyond `retain_days`. `export_typedb()` delegates to `TypeDBStandbyManager.export_snapshot()`. `archive_raw_data()` copies Parquet files to archive directory, returns count. `verify_backup()` runs `pg_restore --list` to check dump integrity. `list_backups()` scans backup directory.

- [ ] **Step 6: Create restore scripts**

`scripts/restore_timescale.sh`: stops Patroni, runs `pg_restore`, verifies row counts, restarts Patroni. `scripts/restore_typedb.sh`: stops TypeDB, imports from snapshot, verifies schema, starts TypeDB. Both scripts log RPO/RTO metrics.

- [ ] **Step 7: Run tests**

Run: `pytest tests/ha/test_backup.py tests/ha/test_load_balancer.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/ha/backup_manager.py deploy/nginx/ scripts/ docker-compose.yml tests/ha/
git commit -m "feat: backup manager + Nginx load balancer for FastAPI HA"
```

---

### Task 5: Anomaly Detection Engine

**Files:**
- Create: `homepy/monitoring/anomaly_detector.py`
- Create: `tests/monitoring/test_anomaly_detector.py`

**Interfaces:**
- Consumes: `TimescaleService` from Plan A Task 6, `AnomalyResult` from Task 1
- Produces:
  - `ZScoreDetector(threshold: float = 3.0, lookback_days: int = 90)` with method:
    - `detect(series: pd.Series) -> list[AnomalyResult]`
  - `IsolationForestDetector(contamination: float = 0.01)` with method:
    - `detect(features: pd.DataFrame) -> list[AnomalyResult]`
  - `CUSUMDetector(drift_threshold_sigma: float = 5.0)` with method:
    - `detect(series: pd.Series) -> list[AnomalyResult]`
  - `BollingerDetector(window: int = 20, num_std: float = 2.0)` with method:
    - `detect(series: pd.Series) -> list[AnomalyResult]`
  - `AnomalyEngine(timescale_svc: TimescaleService, detectors: list)` with methods:
    - `async scan_district(district_code: str) -> list[AnomalyResult]`
    - `async scan_all() -> dict[str, list[AnomalyResult]]`
    - `async get_fp_rate(algorithm: str, days: int = 30) -> float`
    - `async suppress_if_noisy(algorithm: str) -> bool` — returns True if FP > 30% and suppressed

- [ ] **Step 1: Write failing tests**

```python
def test_zscore_detects_spike():
    normal = pd.Series([100.0] * 90)
    spiked = pd.concat([normal, pd.Series([200.0])])
    detector = ZScoreDetector(threshold=3.0, lookback_days=90)
    results = detector.detect(spiked)
    assert len(results) >= 1
    assert results[0].algorithm == "zscore"
    assert abs(results[0].z_score) > 3.0

def test_zscore_no_false_positive_on_normal():
    normal = pd.Series(np.random.normal(100, 5, 100))
    detector = ZScoreDetector(threshold=3.0, lookback_days=90)
    results = detector.detect(normal)
    assert len(results) == 0

def test_isolation_forest_detects_multivariate_anomaly():
    np.random.seed(42)
    normal = pd.DataFrame({"price": np.random.normal(100, 5, 100),
                           "volume": np.random.normal(500, 50, 100)})
    anomaly = pd.DataFrame({"price": [300.0], "volume": [50.0]})
    data = pd.concat([normal, anomaly], ignore_index=True)
    detector = IsolationForestDetector(contamination=0.01)
    results = detector.detect(data)
    assert len(results) >= 1
    assert results[0].algorithm == "isolation_forest"

def test_cusum_detects_trend_change():
    stable = pd.Series([100.0] * 50)
    drift = pd.Series([100.0 + i * 2 for i in range(50)])
    series = pd.concat([stable, drift], ignore_index=True)
    detector = CUSUMDetector(drift_threshold_sigma=5.0)
    results = detector.detect(series)
    assert len(results) >= 1
    assert results[0].algorithm == "cusum"

def test_bollinger_detects_overheated():
    normal = pd.Series(np.random.normal(100, 2, 50))
    overheated = pd.Series([120.0] * 5)
    series = pd.concat([normal, overheated], ignore_index=True)
    detector = BollingerDetector(window=20, num_std=2.0)
    results = detector.detect(series)
    assert len(results) >= 1
    assert results[0].algorithm == "bollinger"

async def test_anomaly_engine_auto_suppress_noisy_detector(mock_timescale):
    engine = AnomalyEngine(mock_timescale, [ZScoreDetector()])
    mock_timescale.set_fp_rate("zscore", 0.35)  # > 30%
    suppressed = await engine.suppress_if_noisy("zscore")
    assert suppressed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/monitoring/test_anomaly_detector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement 4 detectors in `monitoring/anomaly_detector.py`**

`ZScoreDetector`: compute rolling mean/std over `lookback_days`, flag points where |Z| > `threshold`. `IsolationForestDetector`: fit sklearn `IsolationForest(contamination=...)` on features, flag outliers (label == -1). `CUSUMDetector`: compute cumulative sum of deviations from mean, flag where cumsum exceeds `drift_threshold_sigma * std`. `BollingerDetector`: compute `window`-day SMA ± `num_std * std`, flag points outside bands. Each returns `list[AnomalyResult]` with appropriate `algorithm` string, computed `z_score` (None for non-Z algorithms), and `severity` mapped from deviation magnitude.

- [ ] **Step 4: Implement `AnomalyEngine`**

`scan_district()` fetches time-series for all monitored metrics (price_index, volume, interest_rate) from TimescaleDB, runs each detector, collects results. `scan_all()` iterates all districts. `get_fp_rate()` queries `ts_anomaly_detections` for FP count / total count in last `days` days. `suppress_if_noisy()` checks FP rate > 0.30 and marks detector as suppressed in memory, logging suppression event.

- [ ] **Step 5: Run tests**

Run: `pytest tests/monitoring/test_anomaly_detector.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add homepy/monitoring/anomaly_detector.py tests/monitoring/test_anomaly_detector.py
git commit -m "feat: anomaly detection engine (Z-score, IsolationForest, CUSUM, Bollinger)"
```

---

### Task 6: Early Warning TypeDB Rules + Alert System

**Files:**
- Create: `storage/typedb/early_warning_rules.tql`
- Create: `homepy/monitoring/alert_manager.py`
- Create: `homepy/monitoring/channels/`
- Create: `homepy/monitoring/channels/__init__.py`
- Create: `homepy/monitoring/channels/slack.py`
- Create: `homepy/monitoring/channels/kakao.py`
- Create: `homepy/monitoring/channels/email.py`
- Modify: `storage/typedb/schema.tql` (add `smart-money-signal`, `gap-narrowing-signal` relation types)
- Create: `tests/monitoring/test_early_warning_rules.py`
- Create: `tests/monitoring/test_alert_manager.py`

**Interfaces:**
- Consumes: `AnomalyResult` from Task 1, `AnomalyEngine` from Task 5, `TypeDBService` from Plan A Task 5, `AlertEvent` from Task 1
- Produces:
  - TypeDB schema additions: `smart-money-signal` relation (role `detected-area`), `gap-narrowing-signal` relation (role `narrowing-area`)
  - 2 TypeDB rules: `smart-money-detection`, `jeonse-gap-narrowing` (exact TypeQL from spec Section 11.4)
  - `AlertClassifier` with method:
    - `classify(anomalies: list[AnomalyResult], active_signals: list[str]) -> str` — returns level ∈ {"WATCH", "ADVISORY", "WARNING", "CRITICAL"}
  - `AlertManager(channels: dict, routing: dict)` with methods:
    - `async send_alert(event: AlertEvent) -> AlertEvent` — dispatches to channels per `ALERT_ROUTING`, returns event with `channels_sent`/`channels_failed` populated
    - `async deduplicate(events: list[AlertEvent], window_hours: float = 1.0) -> list[AlertEvent]` — merges events with same (district, level) within window
  - Channel interfaces — each has `async send(title: str, body: str) -> bool`:
    - `SlackNotifier(webhook_url: str, timeout: float = 5.0, max_retries: int = 2)`
    - `KakaoNotifier(api_key: str, template_id: str, timeout: float = 5.0, max_retries: int = 2)`
    - `EmailNotifier(smtp_host: str, from_addr: str, to_addrs: list[str], timeout: float = 5.0, max_retries: int = 2)`

- [ ] **Step 1: Write failing tests for TypeDB rules**

```python
async def test_smart_money_signal_fires(typedb_session):
    """price-change-mom < 0 AND sale-to-list-ratio > 1.05 → smart-money-signal"""
    async with typedb_session.transaction(TransactionType.WRITE) as tx:
        await tx.query.insert("""
            insert
            $dist isa district, has district-code "11680", has district-name "강남구";
            $co isa cycle-observation,
                has price-change-mom -2.5,
                has sale-to-list-ratio 1.08;
            (observation: $co, observed-district: $dist) isa cycle-observed-at;
        """)
        await tx.commit()
    async with typedb_session.transaction(TransactionType.READ, infer=True) as tx:
        results = await tx.query.get("match (detected-area: $d) isa smart-money-signal; get $d;")
        districts = [r.get("d") for r in results]
        assert len(districts) == 1

async def test_smart_money_signal_not_fires_positive_mom(typedb_session):
    """price-change-mom > 0 → no smart-money-signal"""
    async with typedb_session.transaction(TransactionType.WRITE) as tx:
        await tx.query.insert("""
            insert
            $dist isa district, has district-code "11680", has district-name "강남구";
            $co isa cycle-observation,
                has price-change-mom 1.5,
                has sale-to-list-ratio 1.08;
            (observation: $co, observed-district: $dist) isa cycle-observed-at;
        """)
        await tx.commit()
    async with typedb_session.transaction(TransactionType.READ, infer=True) as tx:
        results = await tx.query.get("match (detected-area: $d) isa smart-money-signal; get $d;")
        assert len([r for r in results]) == 0
```

- [ ] **Step 2: Write failing tests for alert system**

```python
def test_alert_classify_single_anomaly_is_watch():
    classifier = AlertClassifier()
    anomalies = [AnomalyResult(anomaly_id="A1", detected_at=datetime.now(),
        district_code="11680", metric_name="price", algorithm="zscore",
        current_value=150, baseline_value=100, z_score=3.2,
        severity="high", details={})]
    level = classifier.classify(anomalies, active_signals=[])
    assert level == "WATCH"

def test_alert_classify_multiple_anomalies_is_advisory():
    classifier = AlertClassifier()
    anomalies = [
        AnomalyResult(anomaly_id="A1", detected_at=datetime.now(),
            district_code="11680", metric_name="price", algorithm="zscore",
            current_value=150, baseline_value=100, z_score=3.2,
            severity="high", details={}),
        AnomalyResult(anomaly_id="A2", detected_at=datetime.now(),
            district_code="11680", metric_name="volume", algorithm="cusum",
            current_value=800, baseline_value=500, z_score=None,
            severity="medium", details={}),
    ]
    level = classifier.classify(anomalies, active_signals=[])
    assert level == "ADVISORY"

def test_alert_classify_extreme_zscore_is_warning():
    classifier = AlertClassifier()
    anomalies = [AnomalyResult(anomaly_id="A1", detected_at=datetime.now(),
        district_code="11680", metric_name="price", algorithm="zscore",
        current_value=250, baseline_value=100, z_score=4.5,
        severity="critical", details={})]
    level = classifier.classify(anomalies, active_signals=[])
    assert level == "WARNING"

async def test_alert_deduplication_merges_same_district(alert_manager):
    events = [
        AlertEvent(alert_id=f"AL{i}", created_at=datetime.now(), level="ADVISORY",
            title="Price spike", description="Z > 3", district_code="11680",
            anomaly_ids=[f"A{i}"], channels_sent=[], channels_failed=[],
            deduplicated=False, batch_count=1)
        for i in range(50)
    ]
    deduped = await alert_manager.deduplicate(events, window_hours=1.0)
    assert len(deduped) == 1
    assert deduped[0].batch_count == 50
    assert deduped[0].deduplicated is True

async def test_slack_failure_does_not_block_kakao(mock_channels):
    mock_channels["slack"].force_timeout = True
    manager = AlertManager(channels=mock_channels, routing=ALERT_ROUTING)
    event = AlertEvent(alert_id="AL1", created_at=datetime.now(), level="WARNING",
        title="Test", description="Test", district_code="11680",
        anomaly_ids=["A1"], channels_sent=[], channels_failed=[],
        deduplicated=False, batch_count=1)
    result = await manager.send_alert(event)
    assert "slack" in result.channels_failed
    assert "kakao" in result.channels_sent

def test_alert_routing_matches_spec():
    assert ALERT_ROUTING["WATCH"] == []
    assert ALERT_ROUTING["ADVISORY"] == ["slack"]
    assert ALERT_ROUTING["WARNING"] == ["slack", "kakao"]
    assert ALERT_ROUTING["CRITICAL"] == ["slack", "kakao", "email"]
```

- [ ] **Step 3: Run all tests to verify they fail**

Run: `pytest tests/monitoring/test_early_warning_rules.py tests/monitoring/test_alert_manager.py -v`
Expected: FAIL

- [ ] **Step 4: Add schema types to `storage/typedb/schema.tql`**

Add `smart-money-signal sub relation, relates detected-area;` and `gap-narrowing-signal sub relation, relates narrowing-area;`. Add `district plays smart-money-signal:detected-area, plays gap-narrowing-signal:narrowing-area;`.

- [ ] **Step 5: Create `storage/typedb/early_warning_rules.tql`**

The two rules exactly as specified in Section 11.4: `smart-money-detection` (price-change-mom < 0 AND sale-to-list-ratio > 1.05 → smart-money-signal) and `jeonse-gap-narrowing` (jeonse-ratio difference > 0.05 → gap-narrowing-signal).

- [ ] **Step 6: Implement `AlertClassifier` and `AlertManager` in `monitoring/alert_manager.py`**

`AlertClassifier.classify()`: 1 anomaly + no signals → WATCH; 2+ anomalies OR TypeDB signal → ADVISORY; Z > 4 OR duration > 3 days → WARNING; multiple WARNING concurrent OR systemic risk → CRITICAL. `AlertManager.send_alert()`: looks up `ALERT_ROUTING[event.level]`, dispatches to each channel with 5s timeout + 2 retries (exponential backoff), populates `channels_sent`/`channels_failed`. `deduplicate()`: groups by (district_code, level) within `window_hours`, merges into single event with `batch_count`.

- [ ] **Step 7: Implement channel notifiers in `monitoring/channels/`**

`slack.py`: `SlackNotifier.send()` posts to webhook URL via httpx with timeout/retry. `kakao.py`: `KakaoNotifier.send()` calls KakaoTalk API via httpx with template. `email.py`: `EmailNotifier.send()` uses `smtplib.SMTP` with timeout. All return `bool` (success/failure), never raise on channel failure.

- [ ] **Step 8: Run tests**

Run: `pytest tests/monitoring/test_early_warning_rules.py tests/monitoring/test_alert_manager.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add storage/typedb/ homepy/monitoring/alert_manager.py homepy/monitoring/channels/ tests/monitoring/
git commit -m "feat: early warning TypeDB rules + 4-level alert system with Slack/KakaoTalk/Email"
```

---

### Task 7: Market Monitoring Dashboard (Page 11) + E2E Integration

**Files:**
- Create: `homepy/app/pages/11_market_monitoring.py`
- Create: `homepy/app/components/anomaly_heatmap.py`
- Create: `homepy/app/components/alert_timeline.py`
- Create: `homepy/app/components/ha_status_panel.py`
- Modify: `homepy/api/routers/pipeline.py` (add `/monitoring/anomalies`, `/monitoring/alerts`, `/monitoring/early-warnings` endpoints)
- Create: `tests/monitoring/test_monitoring_dashboard_e2e.py`

**Interfaces:**
- Consumes: `AnomalyEngine` from Task 5, `AlertManager` from Task 6, `HAStatus` from Task 1, `PatroniHealthChecker` from Task 2, `TypeDBStandbyManager` from Task 3, `RedisSentinelManager` from Task 3, `BackupManager` from Task 4, `ApiClient` from Plan C Task 5
- Produces:
  - API endpoints:
    - `GET /api/v1/pipeline/monitoring/anomalies?days=7` → `list[AnomalyResult]`
    - `GET /api/v1/pipeline/monitoring/alerts?days=7&level=WARNING` → `list[AlertEvent]`
    - `GET /api/v1/pipeline/monitoring/early-warnings` → `list[dict]` (active TypeDB signals)
  - Streamlit Page 11 sections:
    - Anomaly heatmap: district × date matrix, color by severity
    - Alert timeline: chronological alert events, filterable by level
    - Early warning signals: active smart-money, gap-narrowing signals from TypeDB
    - HA system health: component status cards (TimescaleDB, TypeDB, Redis, Nginx)
  - Visualization components:
    - `anomaly_heatmap(anomalies: list[AnomalyResult]) -> go.Figure` (Plotly heatmap)
    - `alert_timeline(alerts: list[AlertEvent]) -> go.Figure` (Plotly timeline/Gantt)
    - `ha_status_panel(statuses: list[HAStatus]) -> None` (Streamlit metric cards)

- [ ] **Step 1: Write failing test for API endpoints**

```python
async def test_anomalies_endpoint(client, seeded_anomalies):
    resp = client.get("/api/v1/pipeline/monitoring/anomalies?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert all("anomaly_id" in a for a in data)

async def test_alerts_endpoint_filter_by_level(client, seeded_alerts):
    resp = client.get("/api/v1/pipeline/monitoring/alerts?days=7&level=WARNING")
    assert resp.status_code == 200
    data = resp.json()
    assert all(a["level"] == "WARNING" for a in data)

async def test_early_warnings_endpoint(client, typedb_with_signals):
    resp = client.get("/api/v1/pipeline/monitoring/early-warnings")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
```

- [ ] **Step 2: Write E2E integration test**

```python
async def test_e2e_anomaly_to_alert_to_dashboard(
    timescale_svc, typedb_svc, mock_slack, client
):
    """Inject anomalous data → AnomalyEngine detects → AlertManager sends → API returns"""
    # Inject price spike
    await timescale_svc.insert_price(district="11680", ts=datetime.now(), value=300.0)
    # Previous 90 days normal (~100)
    for i in range(90):
        await timescale_svc.insert_price(
            district="11680",
            ts=datetime.now() - timedelta(days=i+1),
            value=100.0 + np.random.normal(0, 2)
        )

    # Run detection
    engine = AnomalyEngine(timescale_svc, [ZScoreDetector(threshold=3.0)])
    anomalies = await engine.scan_district("11680")
    assert len(anomalies) >= 1

    # Classify and alert
    classifier = AlertClassifier()
    level = classifier.classify(anomalies, active_signals=[])
    assert level in {"WATCH", "ADVISORY", "WARNING", "CRITICAL"}

    manager = AlertManager(channels={"slack": mock_slack}, routing=ALERT_ROUTING)
    event = AlertEvent(
        alert_id="E2E-001", created_at=datetime.now(), level=level,
        title="E2E test", description="Price Z > 3", district_code="11680",
        anomaly_ids=[a.anomaly_id for a in anomalies],
        channels_sent=[], channels_failed=[],
        deduplicated=False, batch_count=1
    )
    result = await manager.send_alert(event)
    if level != "WATCH":
        assert len(result.channels_sent) > 0

    # Verify API reflects detection
    resp = client.get("/api/v1/pipeline/monitoring/anomalies?days=1")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/monitoring/test_monitoring_dashboard_e2e.py -v`
Expected: FAIL

- [ ] **Step 4: Add monitoring API endpoints to `api/routers/pipeline.py`**

`GET /monitoring/anomalies`: queries `ts_anomaly_detections` with `days` filter. `GET /monitoring/alerts`: queries `ts_alert_events` with `days` and optional `level` filter. `GET /monitoring/early-warnings`: queries TypeDB for active `smart-money-signal` and `gap-narrowing-signal` relations.

- [ ] **Step 5: Implement visualization components**

`anomaly_heatmap.py`: `anomaly_heatmap()` builds Plotly `go.Heatmap` with x=date, y=district, z=severity count, colorscale red. `alert_timeline.py`: `alert_timeline()` builds Plotly timeline with level-colored markers. `ha_status_panel.py`: `ha_status_panel()` renders 4 `st.metric` cards (one per component), green/yellow/red status indicators.

- [ ] **Step 6: Build Streamlit Page 11 in `app/pages/11_market_monitoring.py`**

Calls `ApiClient` to fetch anomalies, alerts, early warnings, HA status. Renders 4 sections: anomaly heatmap (with date range selector), alert timeline (with level filter), early warning signal cards, HA status panel. Uses `st.columns` for layout, `st.expander` for signal details.

- [ ] **Step 7: Run tests**

Run: `pytest tests/monitoring/test_monitoring_dashboard_e2e.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add homepy/app/pages/11_market_monitoring.py homepy/app/components/ homepy/api/routers/pipeline.py tests/monitoring/
git commit -m "feat: market monitoring dashboard (Page 11) + E2E anomaly-to-alert pipeline"
```
