#!/usr/bin/env bash
# Restore TimescaleDB from a pg_dump -Fc backup. Logs RPO/RTO metrics.
set -euo pipefail

BACKUP="${1:?usage: restore_timescale.sh <backup.dump> [dsn]}"
DSN="${2:-postgresql://homepy:homepy@localhost:5432/homepy}"
PATRONI_CONTAINER="${PATRONI_CONTAINER:-homepy-timescale-primary}"
START=$(date +%s)

echo "[restore] backup mtime (RPO reference): $(date -r "$BACKUP" -Iseconds)"
echo "[restore] pausing Patroni failover"
docker exec "$PATRONI_CONTAINER" patronictl pause || true

pg_restore --list "$BACKUP" >/dev/null
pg_restore --clean --if-exists --no-owner -d "$DSN" "$BACKUP"

echo "[restore] verifying row counts"
psql "$DSN" -At -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"

echo "[restore] resuming Patroni"
docker exec "$PATRONI_CONTAINER" patronictl resume || true

END=$(date +%s)
echo "[restore] RTO: $((END - START)) seconds"
