-- HOMEPY hypertables, compression, continuous aggregate (idempotent). Requires schema.sql.
-- Each statement ends with ';' at end of line; no DO blocks (the test splits on it).
-- The continuous aggregate cannot run inside a transaction block: use psql -f (autocommit).

SELECT create_hypertable('ts_real_trade', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_real_trade SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_real_trade', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_price_index', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_price_index SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_price_index', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_interest_rate', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_interest_rate SET (timescaledb.compress);
SELECT add_compression_policy('ts_interest_rate', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_exchange_rate', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_exchange_rate SET (timescaledb.compress);
SELECT add_compression_policy('ts_exchange_rate', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_liquidity', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_liquidity SET (timescaledb.compress);
SELECT add_compression_policy('ts_liquidity', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_macro_index', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_macro_index SET (timescaledb.compress);
SELECT add_compression_policy('ts_macro_index', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_population', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_population SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_population', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_migration', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_migration SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_migration', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_income', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_income SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_income', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_supply', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_supply SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_supply', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_unsold', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_unsold SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_unsold', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_sentiment', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_sentiment SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_sentiment', INTERVAL '90 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_signals', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_signals SET (timescaledb.compress, timescaledb.compress_segmentby = 'signal_type');
SELECT add_compression_policy('ts_signals', INTERVAL '90 days', if_not_exists => TRUE);

-- Monthly average price per district
CREATE MATERIALIZED VIEW IF NOT EXISTS ts_real_trade_monthly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket(INTERVAL '1 month', ts) AS bucket,
    district_code,
    AVG(price_krw) AS avg_price_krw,
    AVG(price_per_pyeong) AS avg_price_per_pyeong,
    COUNT(*) AS trade_count
FROM ts_real_trade
WHERE is_cancelled = FALSE
GROUP BY bucket, district_code
WITH NO DATA;

SELECT add_continuous_aggregate_policy('ts_real_trade_monthly',
    start_offset => INTERVAL '3 months',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- Plan D: verification & improvement hypertables
SELECT create_hypertable('ts_backtest_results', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_backtest_results SET (timescaledb.compress, timescaledb.compress_segmentby = 'complex_id');
SELECT add_compression_policy('ts_backtest_results', INTERVAL '180 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_calibration_log', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_calibration_log SET (timescaledb.compress, timescaledb.compress_segmentby = 'category');
SELECT add_compression_policy('ts_calibration_log', INTERVAL '180 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_system_metrics', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_system_metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'component');
SELECT add_compression_policy('ts_system_metrics', INTERVAL '180 days', if_not_exists => TRUE);

-- Plan E: HA/DR monitoring hypertables
SELECT create_hypertable('ts_anomaly_detections', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_anomaly_detections SET (timescaledb.compress, timescaledb.compress_segmentby = 'district_code');
SELECT add_compression_policy('ts_anomaly_detections', INTERVAL '365 days', if_not_exists => TRUE);

SELECT create_hypertable('ts_alert_events', 'ts', if_not_exists => TRUE);
ALTER TABLE ts_alert_events SET (timescaledb.compress, timescaledb.compress_segmentby = 'level');
SELECT add_compression_policy('ts_alert_events', INTERVAL '365 days', if_not_exists => TRUE);

-- Plan F Task 3: per-user hypertables (RLS policies defined in schema.sql)
SELECT create_hypertable('ts_portfolio', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('ts_watchlist', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('ts_verdict_history', 'ts', if_not_exists => TRUE);
