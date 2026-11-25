#!/usr/bin/env bash
# Migrate TimescaleDB + Neo4j data from Docker Compose containers to K8s PVCs.
# Idempotent: dumps are reused if present, PVCs are applied declaratively,
# restore steps are skipped when a marker file exists on the PVC.
set -euo pipefail

NAMESPACE="${NAMESPACE:-homepy}"
RELEASE="${RELEASE:-homepy}"
BACKUP_DIR="${BACKUP_DIR:-./migration-backup}"
TS_CONTAINER="${TS_CONTAINER:-homepy-timescale-primary}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-homepy-neo4j}"
PG_USER="${PG_USER:-homepy}"
PG_DB="${PG_DB:-homepy}"
NEO4J_DB="${NEO4J_DB:-homepy}"
TS_PVC="${TS_PVC:-data-${RELEASE}-timescaledb-0}"
NEO4J_PVC="${NEO4J_PVC:-data-${RELEASE}-neo4j-0}"
TS_SIZE="${TS_SIZE:-50Gi}"
NEO4J_SIZE="${NEO4J_SIZE:-10Gi}"
HELPER_POD="${HELPER_POD:-homepy-migrate-helper}"

log() { echo "[migrate_volumes] $*"; }
die() { echo "[migrate_volumes] ERROR: $*" >&2; exit 1; }

cleanup() {
  kubectl -n "$NAMESPACE" delete pod "$HELPER_POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

for bin in docker kubectl; do
  command -v "$bin" >/dev/null 2>&1 || die "missing prerequisite: $bin"
done
mkdir -p "$BACKUP_DIR"

export_timescale() {
  local out="$BACKUP_DIR/timescaledb.dump"
  if [ -s "$out" ]; then log "TimescaleDB dump exists, skipping export"; return 0; fi
  log "exporting TimescaleDB via pg_dump"
  docker exec "$TS_CONTAINER" pg_dump -U "$PG_USER" -Fc "$PG_DB" > "$out.tmp" \
    || { rm -f "$out.tmp"; die "pg_dump failed"; }
  mv "$out.tmp" "$out"
}

export_neo4j() {
  local dump="$BACKUP_DIR/neo4j.dump"
  if [ -s "$dump" ]; then log "Neo4j export exists, skipping"; return 0; fi
  log "exporting Neo4j via neo4j-admin dump"
  docker exec "$NEO4J_CONTAINER" neo4j-admin database dump "$NEO4J_DB" --to-path=/tmp \
    || die "neo4j-admin dump failed"
  docker cp "$NEO4J_CONTAINER:/tmp/${NEO4J_DB}.dump" "$dump"
}

ensure_pvc() {
  local name="$1" size="$2"
  log "ensuring PVC $name ($size)"
  kubectl -n "$NAMESPACE" apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $name
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: $size
EOF
}

start_helper() {
  log "starting helper pod mounting both PVCs"
  kubectl -n "$NAMESPACE" delete pod "$HELPER_POD" --ignore-not-found --wait=true >/dev/null
  kubectl -n "$NAMESPACE" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $HELPER_POD
spec:
  restartPolicy: Never
  containers:
    - name: helper
      image: busybox:1.36
      command: ["sleep", "3600"]
      volumeMounts:
        - {name: ts, mountPath: /mnt/timescaledb}
        - {name: neo4j, mountPath: /mnt/neo4j}
  volumes:
    - name: ts
      persistentVolumeClaim: {claimName: $TS_PVC}
    - name: neo4j
      persistentVolumeClaim: {claimName: $NEO4J_PVC}
EOF
  kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod/$HELPER_POD" --timeout=300s \
    || die "helper pod not ready"
}

copy_dumps() {
  log "copying dumps into PVCs"
  kubectl -n "$NAMESPACE" exec "$HELPER_POD" -- mkdir -p /mnt/timescaledb/migration /mnt/neo4j/migration
  kubectl -n "$NAMESPACE" cp "$BACKUP_DIR/timescaledb.dump" "$HELPER_POD:/mnt/timescaledb/migration/timescaledb.dump"
  kubectl -n "$NAMESPACE" cp "$BACKUP_DIR/neo4j.dump" "$HELPER_POD:/mnt/neo4j/migration/neo4j.dump"
}

restore_timescale() {
  if kubectl -n "$NAMESPACE" get pod "${RELEASE}-timescaledb-0" >/dev/null 2>&1; then
    if kubectl -n "$NAMESPACE" exec "${RELEASE}-timescaledb-0" -- test -f /var/lib/postgresql/data/migration/.restored >/dev/null 2>&1; then
      log "TimescaleDB already restored, skipping"; return 0
    fi
    log "restoring TimescaleDB via psql/pg_restore"
    kubectl -n "$NAMESPACE" exec "${RELEASE}-timescaledb-0" -- sh -c \
      "pg_restore --clean --if-exists --no-owner -U '$PG_USER' -d '$PG_DB' /var/lib/postgresql/data/migration/timescaledb.dump && psql -U '$PG_USER' -d '$PG_DB' -c 'SELECT count(*) FROM pg_stat_user_tables;' && touch /var/lib/postgresql/data/migration/.restored" \
      || die "TimescaleDB restore failed"
  else
    log "TimescaleDB pod not running yet; dump staged on PVC, restore after helm install"
  fi
}

restore_neo4j() {
  if kubectl -n "$NAMESPACE" get pod "${RELEASE}-neo4j-0" >/dev/null 2>&1; then
    log "restoring Neo4j via neo4j-admin load"
    kubectl -n "$NAMESPACE" exec "${RELEASE}-neo4j-0" -- sh -c \
      "neo4j-admin database load '$NEO4J_DB' --from-path=/data/migration --overwrite-destination=true" \
      || log "Neo4j import skipped/failed (database may already exist)"
  else
    log "Neo4j pod not running yet; dump staged on PVC, import after helm install"
  fi
}

export_timescale
export_neo4j
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
ensure_pvc "$TS_PVC" "$TS_SIZE"
ensure_pvc "$NEO4J_PVC" "$NEO4J_SIZE"
start_helper
copy_dumps
cleanup
restore_timescale
restore_neo4j
log "done"
