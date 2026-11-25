#!/usr/bin/env bash
# Restore Neo4j from a dump file. Logs RPO/RTO metrics.
set -euo pipefail

SNAPSHOT="${1:?usage: restore_neo4j.sh <snapshot.dump> [container]}"
CONTAINER="${2:-homepy-neo4j}"
DB="${NEO4J_DATABASE:-homepy}"
START=$(date +%s)

echo "[restore] snapshot mtime (RPO reference): $(date -r "$SNAPSHOT" -Iseconds)"
docker stop "$CONTAINER" || true

docker run --rm \
  -v "$(dirname "$SNAPSHOT"):/dumps" \
  -v "homepy_neo4j_data:/data" \
  neo4j:5-community \
  neo4j-admin database load "$DB" --from-path=/dumps --overwrite-destination=true

docker start "$CONTAINER"
sleep 5

echo "[restore] verifying node count"
docker exec "$CONTAINER" cypher-shell -u neo4j -p homepy "MATCH (n) RETURN count(n) AS nodeCount;"

END=$(date +%s)
echo "[restore] RTO: $((END - START)) seconds"
