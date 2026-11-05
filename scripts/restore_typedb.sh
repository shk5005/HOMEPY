#!/usr/bin/env bash
# Restore TypeDB from an exported snapshot. Logs RPO/RTO metrics.
set -euo pipefail

SNAPSHOT="${1:?usage: restore_typedb.sh <snapshot.typedb> [address]}"
ADDR="${2:-localhost:1729}"
DB="${TYPEDB_DATABASE:-homepy}"
CONTAINER="${TYPEDB_CONTAINER:-homepy-typedb}"
SCHEMA="${SNAPSHOT%.typedb}.schema.tql"
START=$(date +%s)

echo "[restore] snapshot mtime (RPO reference): $(date -r "$SNAPSHOT" -Iseconds)"
docker stop "$CONTAINER" || true
docker start "$CONTAINER"
sleep 5

typedb console --address="$ADDR" --command "database delete $DB" || true
typedb console --address="$ADDR" --command "database import $DB $SCHEMA $SNAPSHOT"

echo "[restore] verifying schema"
typedb console --address="$ADDR" --command "database schema $DB" | head -20

END=$(date +%s)
echo "[restore] RTO: $((END - START)) seconds"
