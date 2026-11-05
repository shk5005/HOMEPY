-- HOMEPY TimescaleDB schema (idempotent). Run hypertables.sql afterwards.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Real estate transactions (collect_real_trade)
CREATE TABLE IF NOT EXISTS ts_real_trade (
    ts TIMESTAMPTZ NOT NULL,
    trade_id VARCHAR(40) NOT NULL,
    complex_id VARCHAR(20) NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    price_krw BIGINT NOT NULL,
    area_m2 NUMERIC(8,2),
    floor SMALLINT,
    build_year SMALLINT,
    price_per_pyeong NUMERIC(12,2),
    trade_type VARCHAR(10),
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (ts, complex_id, trade_id)
);

-- Price indices by district (collect_price_index)
CREATE TABLE IF NOT EXISTS ts_price_index (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    index_type VARCHAR(20) NOT NULL DEFAULT 'sale',
    index_value NUMERIC(10,3),
    change_wow_pct NUMERIC(7,3),
    change_mom_pct NUMERIC(7,3),
    change_yoy_pct NUMERIC(7,3),
    trade_volume INTEGER,
    PRIMARY KEY (ts, district_code, index_type)
);

-- Interest rates (collect_interest_rate)
CREATE TABLE IF NOT EXISTS ts_interest_rate (
    ts TIMESTAMPTZ NOT NULL,
    base_rate NUMERIC(6,3),
    cd_rate NUMERIC(6,3),
    treasury_3y NUMERIC(6,3),
    treasury_10y NUMERIC(6,3),
    mortgage_rate NUMERIC(6,3),
    jeonse_loan_rate NUMERIC(6,3),
    cofix NUMERIC(6,3),
    PRIMARY KEY (ts)
);

-- Exchange rates (collect_exchange_rate)
CREATE TABLE IF NOT EXISTS ts_exchange_rate (
    ts TIMESTAMPTZ NOT NULL,
    usd_krw NUMERIC(10,2),
    change_pct NUMERIC(7,3),
    jpy_krw_100 NUMERIC(10,2),
    eur_krw NUMERIC(10,2),
    cny_krw NUMERIC(10,2),
    PRIMARY KEY (ts)
);

-- Money supply and credit (collect_liquidity)
CREATE TABLE IF NOT EXISTS ts_liquidity (
    ts TIMESTAMPTZ NOT NULL,
    m2 NUMERIC(18,2),
    m2_change_yoy_pct NUMERIC(7,3),
    household_credit NUMERIC(18,2),
    mortgage_balance NUMERIC(18,2),
    jeonse_loan_balance NUMERIC(18,2),
    PRIMARY KEY (ts)
);

-- Macro indicators (collect_macro_index)
CREATE TABLE IF NOT EXISTS ts_macro_index (
    ts TIMESTAMPTZ NOT NULL,
    cpi NUMERIC(8,3),
    cpi_change_yoy_pct NUMERIC(7,3),
    gdp_growth NUMERIC(7,3),
    unemployment NUMERIC(6,3),
    leading_index NUMERIC(8,3),
    construction_cost_index NUMERIC(8,3),
    PRIMARY KEY (ts)
);

-- Population by district (collect_population)
CREATE TABLE IF NOT EXISTS ts_population (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    total_pop INTEGER,
    households INTEGER,
    pop_change INTEGER,
    age_20_39_pop INTEGER,
    age_65_plus_pop INTEGER,
    avg_household_size NUMERIC(5,2),
    PRIMARY KEY (ts, district_code)
);

-- Migration by district (collect_migration)
CREATE TABLE IF NOT EXISTS ts_migration (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    net_migration INTEGER,
    in_migration INTEGER,
    out_migration INTEGER,
    PRIMARY KEY (ts, district_code)
);

-- Income by district (collect_income)
CREATE TABLE IF NOT EXISTS ts_income (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    median_income BIGINT,
    avg_income BIGINT,
    pir NUMERIC(6,2),
    growth_rate NUMERIC(7,3),
    PRIMARY KEY (ts, district_code)
);

-- Housing supply by district (collect_supply)
CREATE TABLE IF NOT EXISTS ts_supply (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    permits INTEGER,
    starts INTEGER,
    completions INTEGER,
    planned_supply INTEGER,
    PRIMARY KEY (ts, district_code)
);

-- Unsold inventory by district (collect_unsold)
CREATE TABLE IF NOT EXISTS ts_unsold (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    total_unsold INTEGER,
    unsold_after_completion INTEGER,
    unsold_change INTEGER,
    PRIMARY KEY (ts, district_code)
);

-- Market sentiment by district (collect_sentiment)
CREATE TABLE IF NOT EXISTS ts_sentiment (
    ts TIMESTAMPTZ NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    buyer_sentiment NUMERIC(6,2),
    seller_sentiment NUMERIC(6,2),
    jeonse_ratio NUMERIC(6,2),
    fear_greed NUMERIC(6,2),
    search_trend NUMERIC(8,2),
    PRIMARY KEY (ts, district_code)
);

-- Signals inferred by TypeDB rules, tracked over time
CREATE TABLE IF NOT EXISTS ts_signals (
    ts TIMESTAMPTZ NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(40) NOT NULL,
    target_type VARCHAR(30),
    district_code VARCHAR(10),
    confidence NUMERIC(5,4),
    rule_name VARCHAR(80),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (ts, signal_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_ts_real_trade_district ON ts_real_trade (district_code, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ts_signals_target ON ts_signals (target_id, ts DESC);

-- ===== Plan D: verification & improvement layer =====

-- Backtest results: verdict predictions vs realized price changes
CREATE TABLE IF NOT EXISTS ts_backtest_results (
    ts TIMESTAMPTZ NOT NULL,                -- verdict_date
    verdict_id VARCHAR(60) NOT NULL,
    complex_id VARCHAR(40) NOT NULL,
    predicted_verdict VARCHAR(30),
    predicted_score NUMERIC(6,2),
    predicted_scenarios JSONB NOT NULL DEFAULT '{}'::jsonb,
    actual_price_change_3m NUMERIC(8,4),
    actual_price_change_6m NUMERIC(8,4),
    actual_price_change_12m NUMERIC(8,4),
    direction_correct BOOLEAN,
    scenario_hit BOOLEAN,
    factor_contributions JSONB NOT NULL DEFAULT '{}'::jsonb,
    bias_warnings_issued INTEGER NOT NULL DEFAULT 0,
    bias_warnings_valid INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ts, verdict_id)
);

-- Calibration proposals log
CREATE TABLE IF NOT EXISTS ts_calibration_log (
    ts TIMESTAMPTZ NOT NULL,                -- created_at
    proposal_id VARCHAR(60) NOT NULL,
    category VARCHAR(40) NOT NULL,
    current_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    proposed_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    rationale TEXT,
    backtest_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_improvement TEXT,
    risk_assessment TEXT,
    rollback_plan TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    PRIMARY KEY (ts, proposal_id)
);

-- System performance metrics
CREATE TABLE IF NOT EXISTS ts_system_metrics (
    ts TIMESTAMPTZ NOT NULL,
    component TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION,
    PRIMARY KEY (ts, component, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_ts_backtest_complex ON ts_backtest_results (complex_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ts_system_metrics_component ON ts_system_metrics (component, metric_name, ts DESC);

-- ===== Plan E: HA/DR monitoring layer =====

-- Anomaly detection results
CREATE TABLE IF NOT EXISTS ts_anomaly_detections (
    ts TIMESTAMPTZ NOT NULL,                -- detected_at
    anomaly_id VARCHAR(60) NOT NULL,
    district_code VARCHAR(10) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    algorithm VARCHAR(30) NOT NULL,
    current_value DOUBLE PRECISION,
    baseline_value DOUBLE PRECISION,
    z_score DOUBLE PRECISION,
    severity VARCHAR(20) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (ts, anomaly_id)
);

-- Alert events
CREATE TABLE IF NOT EXISTS ts_alert_events (
    ts TIMESTAMPTZ NOT NULL,                -- created_at
    alert_id VARCHAR(60) NOT NULL,
    level VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    district_code VARCHAR(10),
    anomaly_ids TEXT[] NOT NULL DEFAULT '{}',
    channels_sent TEXT[] NOT NULL DEFAULT '{}',
    channels_failed TEXT[] NOT NULL DEFAULT '{}',
    deduplicated BOOLEAN NOT NULL DEFAULT FALSE,
    batch_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (ts, alert_id)
);

CREATE INDEX IF NOT EXISTS idx_ts_anomaly_district ON ts_anomaly_detections (district_code, ts DESC);
CREATE INDEX IF NOT EXISTS idx_ts_alert_level ON ts_alert_events (level, ts DESC);

-- ============================================================
-- Plan F Task 3: multi-tenancy (users + per-user tables + RLS)
-- ============================================================
CREATE TABLE IF NOT EXISTS ts_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ts_portfolio (
    ts TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL REFERENCES ts_users(user_id),
    complex_id VARCHAR(30) NOT NULL,
    action VARCHAR(20) NOT NULL,
    notes TEXT,
    PRIMARY KEY (ts, user_id, complex_id)
);

CREATE TABLE IF NOT EXISTS ts_watchlist (
    ts TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL REFERENCES ts_users(user_id),
    complex_id VARCHAR(30) NOT NULL,
    PRIMARY KEY (ts, user_id, complex_id)
);

CREATE TABLE IF NOT EXISTS ts_verdict_history (
    ts TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL REFERENCES ts_users(user_id),
    complex_id VARCHAR(30) NOT NULL,
    verdict VARCHAR(20) NOT NULL,
    score DOUBLE PRECISION,
    PRIMARY KEY (ts, user_id, complex_id)
);

-- Plan F Task 4: raw real-time events from collectors
CREATE TABLE IF NOT EXISTS ts_realtime_events (
    ts TIMESTAMPTZ NOT NULL,
    event_id VARCHAR(60) NOT NULL,
    source VARCHAR(30) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    district_code VARCHAR(10),
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (ts, event_id)
);

-- RLS: unset app.current_user_id -> current_setting(..., true) is NULL -> no rows.
-- FORCE applies the policy to the table owner too. USING also serves as WITH CHECK.
ALTER TABLE ts_portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE ts_portfolio FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS portfolio_isolation ON ts_portfolio;
CREATE POLICY portfolio_isolation ON ts_portfolio
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

ALTER TABLE ts_watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE ts_watchlist FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS watchlist_isolation ON ts_watchlist;
CREATE POLICY watchlist_isolation ON ts_watchlist
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);

ALTER TABLE ts_verdict_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE ts_verdict_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS verdict_isolation ON ts_verdict_history;
CREATE POLICY verdict_isolation ON ts_verdict_history
    USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
