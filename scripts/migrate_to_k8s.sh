#!/usr/bin/env bash
# Migrate HOMEPY from Docker Compose to Kubernetes (Helm). Idempotent.
set -euo pipefail

NAMESPACE="${NAMESPACE:-homepy}"
RELEASE="${RELEASE:-homepy}"
CHART_DIR="${CHART_DIR:-./charts/homepy}"
VALUES_FILE="${VALUES_FILE:-$CHART_DIR/values-prod.yaml}"
HEALTH_URL="${HEALTH_URL:-}"
TIMEOUT="${TIMEOUT:-600s}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[migrate_to_k8s] $*"; }
die() { echo "[migrate_to_k8s] ERROR: $*" >&2; exit 1; }

check_prerequisites() {
  local missing=0
  for bin in kubectl helm docker curl; do
    if ! command -v "$bin" >/dev/null 2>&1; then
      echo "missing prerequisite: $bin" >&2; missing=1
    fi
  done
  [ "$missing" -eq 0 ] || die "install missing tools and retry"
  [ -d "$CHART_DIR" ] || die "chart not found: $CHART_DIR"
  [ -f "$VALUES_FILE" ] || die "values file not found: $VALUES_FILE"
  kubectl cluster-info >/dev/null 2>&1 || die "cannot reach Kubernetes cluster"
}

ensure_namespace() {
  if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    log "namespace $NAMESPACE exists, skipping"
  else
    log "creating namespace $NAMESPACE"
    kubectl create namespace "$NAMESPACE"
  fi
}

migrate_data() {
  log "migrating volumes"
  NAMESPACE="$NAMESPACE" RELEASE="$RELEASE" bash "$SCRIPT_DIR/migrate_volumes.sh"
}

install_chart() {
  if helm status "$RELEASE" -n "$NAMESPACE" >/dev/null 2>&1; then
    log "release $RELEASE exists, upgrading"
  else
    log "installing release $RELEASE"
  fi
  # upgrade --install is idempotent; secrets must be supplied via env/-f, never committed.
  helm upgrade --install "$RELEASE" "$CHART_DIR" -n "$NAMESPACE" -f "$VALUES_FILE" --wait --timeout "$TIMEOUT"
}

wait_ready() {
  log "waiting for pods to be ready"
  kubectl -n "$NAMESPACE" wait --for=condition=Ready pod --all --timeout="$TIMEOUT" \
    || die "pods did not become ready"
}

smoke_test() {
  local pf_pid="" url="$HEALTH_URL"
  if [ -z "$url" ]; then
    kubectl -n "$NAMESPACE" port-forward "svc/${RELEASE}-fastapi" 18000:8000 >/dev/null 2>&1 &
    pf_pid=$!
    sleep 3
    url="http://localhost:18000/health"
  fi
  local rc=0
  curl -fsS --retry 5 --retry-delay 3 "$url" >/dev/null || rc=$?
  if [ -n "$pf_pid" ]; then kill "$pf_pid" >/dev/null 2>&1 || true; fi
  [ "$rc" -eq 0 ] || die "smoke test failed: $url"
  log "smoke test passed: $url"
}

check_prerequisites
ensure_namespace
migrate_data
install_chart
wait_ready
smoke_test
log "migration complete"
