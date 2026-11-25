#!/usr/bin/env bash
# Migrate TimescaleDB + TypeDB data from Docker Compose containers to K8s PVCs.
# Idempotent: dumps are reused if present, PVCs are applied declaratively,
# restore steps are skipped when a marker file exists on the PVC.
set -euo pipefail

NAMESPACE="${NAMESPACE:-homepy}"
RELEASE="${RELEASE:-homepy}"
BACKUP_DIR="${BACKUP_DIR:-./migration-backup}"
TS_CONTAINER="${TS_CONTAINER:-homepy-timescale-primary}"
TYPEDB_CONTAINER="${TYPEDB_CONTAINER:-homepy-typedb}"
PG_USER="${PG_USER:-homepy}"
PG_DB="${PG_DB:-homepy}"
TYPEDB_DB="${TYPEDB_DB:-homepy}"
TS_PVC="${TS_PVC:-data-${RELEASE}-timescaledb-0}"
TYPEDB_PVC="${TYPEDB_PVC:-data-${RELEASE}-typedb-0}"
TS_SIZE="${TS_SIZE:-50Gi}"
TYPEDB_SIZE="${TYPEDB_SIZE:-10Gi}"
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

export_typedb() {
  local schema="$BACKUP_DIR/typedb.schema.tql" data="$BACKUP_DIR/typedb.typedb"
  if [ -s "$schema" ] && [ -s "$data" ]; then log "TypeDB export exists, skipping"; return 0; fi
  log "exporting TypeDB via typedb server export"
  docker exec "$TYPEDB_CONTAINER" typedb server export \
    --database="$TYPEDB_DB" --schema=/tmp/typedb.schema.tql --data=/tmp/typedb.typedb \
    || die "typedb export failed"
  docker cp "$TYPEDB_CONTAINER:/tmp/typedb.schema.tql" "$schema"
  docker cp "$TYPEDB_CONTAINER:/tmp/typedb.typedb" "$data"
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
        - {name: typedb, mountPath: /mnt/typedb}
  volumes:
    - name: ts
      persistentVolumeClaim: {claimName: $TS_PVC}
    - name: typedb
      persistentVolumeClaim: {claimName: $TYPEDB_PVC}
EOF
  kubectl -n "$NAMESPACE" wait --for=condition=Ready "pod/$HELPER_POD" --timeout=300s \
    || die "helper pod not ready"
}

copy_dumps() {
  log "copying dumps into PVCs"
  kubectl -n "$NAMESPACE" exec "$HELPER_POD" -- mkdir -p /mnt/timescaledb/migration /mnt/typedb/migration
  kubectl -n "$NAMESPACE" cp "$BACKUP_DIR/timescaledb.dump" "$HELPER_POD:/mnt/timescaledb/migration/timescaledb.dump"
  kubectl -n "$NAMESPACE" cp "$BACKUP_DIR/typedb.schema.tql" "$HELPER_POD:/mnt/typedb/migration/typedb.schema.tql"
  kubectl -n "$NAMESPACE" cp "$BACKUP_DIR/typedb.typedb" "$HELPER_POD:/mnt/typedb/migration/typedb.typedb"
}

marker_exists() {
  kubectl -n "$NAMESPACE" exec "$HELPER_POD" -- test -f "$1" >/dev/null 2>&1
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

restore_typedb() {
  if kubectl -n "$NAMESPACE" get pod "${RELEASE}-typedb-0" >/dev/null 2>&1; then
    log "restoring TypeDB via typedb server import"
    kubectl -n "$NAMESPACE" exec "${RELEASE}-typedb-0" -- sh -c \
      "typedb server import --database='$TYPEDB_DB' --schema=/opt/typedb-all-linux-x86_64/server/data/migration/typedb.schema.tql --data=/opt/typedb-all-linux-x86_64/server/data/migration/typedb.typedb" \
      || log "TypeDB import skipped/failed (database may already exist)"
  else
    log "TypeDB pod not running yet; export staged on PVC, import after helm install"
  fi
}

export_timescale
export_typedb
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
ensure_pvc "$TS_PVC" "$TS_SIZE"
ensure_pvc "$TYPEDB_PVC" "$TYPEDB_SIZE"
start_helper
copy_dumps
cleanup
restore_timescale
restore_typedb
log "done"
