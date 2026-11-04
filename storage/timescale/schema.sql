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
