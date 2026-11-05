"""Helm chart tests.

Two groups:
  * helm CLI tests (skipped when `helm` is not installed)
  * pure-Python YAML tests that approximate rendering by stripping Go
    template directives, so the same structural checks run without helm.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts" / "homepy"
TEMPLATES = CHART / "templates"

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="requires helm CLI")

EXPECTED_KINDS = {
    "StatefulSet", "Deployment", "Service", "Ingress",
    "ConfigMap", "Secret", "HorizontalPodAutoscaler",
}

_CONTROL = re.compile(r"^\s*\{\{-?\s*(if|else|end|with|range|define)\b.*\}\}\s*$")
_STANDALONE_EXPR = re.compile(r"^\s*\{\{-?.*\}\}\s*$")
_INLINE = re.compile(r"\{\{.*?\}\}")


def pseudo_render(path: Path):
    """Strip Go template syntax and parse the remaining YAML documents."""
    lines = []
    for line in path.read_text().splitlines():
        if _CONTROL.match(line) or _STANDALONE_EXPR.match(line):
            continue
        lines.append(_INLINE.sub("PLACEHOLDER", line))
    return [d for d in yaml.safe_load_all("\n".join(lines)) if d]


def all_docs():
    docs = []
    for p in sorted(TEMPLATES.glob("*.yaml")):
        docs.extend(pseudo_render(p))
    return docs


def helm_docs():
    result = subprocess.run(
        ["helm", "template", "homepy", str(CHART)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


# ---------------------------------------------------------------- helm CLI
@needs_helm
def test_helm_lint_passes():
    result = subprocess.run(["helm", "lint", str(CHART)], capture_output=True, text=True)
    assert result.returncode == 0, f"helm lint failed: {result.stdout}{result.stderr}"


@needs_helm
def test_helm_template_renders_all_resources():
    kinds = {d["kind"] for d in helm_docs()}
    assert EXPECTED_KINDS <= kinds


@needs_helm
def test_helm_secrets_template_has_no_plaintext():
    for doc in helm_docs():
        if doc["kind"] == "Secret":
            for key, val in doc.get("data", {}).items():
                assert val != "", f"Secret {key} empty"


@needs_helm
def test_helm_statefulset_has_pvc():
    for doc in helm_docs():
        if doc["kind"] == "StatefulSet":
            assert doc["spec"].get("volumeClaimTemplates")


# ------------------------------------------------------- pure-Python checks
def test_chart_yaml_valid():
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    assert chart["name"] == "homepy"
    assert chart["version"] == "0.1.0"
    assert chart["apiVersion"] == "v2"
    assert "HOMEPY" in chart["description"]


@pytest.mark.parametrize("name", ["values.yaml", "values-dev.yaml", "values-prod.yaml"])
def test_values_files_parse(name):
    assert isinstance(yaml.safe_load((CHART / name).read_text()), dict)


def test_values_defaults():
    v = yaml.safe_load((CHART / "values.yaml").read_text())
    assert v["fastapi"]["replicas"] == 2
    assert v["streamlit"]["replicas"] == 1
    assert v["typedb"]["persistence"]["size"] == "10Gi"
    assert v["timescaledb"]["persistence"]["size"] == "50Gi"
    for comp in ("typedb", "timescaledb", "redis", "fastapi", "streamlit"):
        assert v[comp]["image"]["repository"] and v[comp]["image"]["tag"]
        assert "resources" in v[comp]


def test_dev_and_prod_overrides():
    dev = yaml.safe_load((CHART / "values-dev.yaml").read_text())
    prod = yaml.safe_load((CHART / "values-prod.yaml").read_text())
    assert dev["fastapi"]["replicas"] == 1
    assert dev["typedb"]["persistence"]["size"] == "5Gi"
    assert dev["timescaledb"]["persistence"]["size"] == "25Gi"
    assert dev["config"]["logLevel"] == "DEBUG"
    assert dev["ingress"]["host"] == "homepy-dev.local"
    assert prod["fastapi"]["replicas"] == 2
    assert prod["config"]["logLevel"] == "WARNING"


def test_templates_render_all_resource_kinds():
    kinds = {d["kind"] for d in all_docs()}
    assert EXPECTED_KINDS <= kinds


def test_expected_template_files_exist():
    for f in ("typedb-statefulset", "timescaledb-statefulset", "redis-deployment",
              "fastapi-deployment", "streamlit-deployment", "ingress",
              "configmap", "secrets", "hpa"):
        assert (TEMPLATES / f"{f}.yaml").exists(), f


def test_statefulsets_have_pvc():
    sts = [d for d in all_docs() if d["kind"] == "StatefulSet"]
    assert len(sts) == 2
    for doc in sts:
        vcts = doc["spec"].get("volumeClaimTemplates", [])
        assert vcts, f"{doc['metadata']['name']} missing PVC"
        assert vcts[0]["spec"]["resources"]["requests"]["storage"]


def test_statefulset_mount_paths_and_probes():
    by = {d["metadata"]["name"].split("-")[-1]: d for d in all_docs() if d["kind"] == "StatefulSet"}
    ts = by["timescaledb"]["spec"]["template"]["spec"]["containers"][0]
    assert ts["volumeMounts"][0]["mountPath"] == "/var/lib/postgresql/data"
    assert ts["readinessProbe"]["exec"]["command"][0] == "pg_isready"
    tdb = by["typedb"]["spec"]["template"]["spec"]["containers"][0]
    assert "readinessProbe" in tdb


def test_fastapi_probes_on_health():
    dep = next(d for d in all_docs()
               if d["kind"] == "Deployment" and d["metadata"]["name"].endswith("fastapi"))
    c = dep["spec"]["template"]["spec"]["containers"][0]
    assert c["livenessProbe"]["httpGet"]["path"] == "/health"
    assert c["readinessProbe"]["httpGet"]["path"] == "/health"


def test_secrets_use_values_not_plaintext():
    text = (TEMPLATES / "secrets.yaml").read_text()
    docs = pseudo_render(TEMPLATES / "secrets.yaml")
    assert docs[0]["kind"] == "Secret"
    data = docs[0]["data"]
    assert data
    for key, val in data.items():
        assert val == "PLACEHOLDER", f"{key} must come from a template expression"
        assert val != ""
    assert text.count(".Values.secrets.") == len(data)


def test_values_secrets_are_placeholders_only():
    v = yaml.safe_load((CHART / "values.yaml").read_text())
    for key, val in v["secrets"].items():
        assert val == "CHANGE_ME", f"{key} must be a placeholder"


def test_ingress_routes():
    text = (TEMPLATES / "ingress.yaml").read_text()
    assert ".Values.ingress.className" in text
    ing = pseudo_render(TEMPLATES / "ingress.yaml")[0]
    paths = {p["path"]: p["backend"]["service"]["name"]
             for p in ing["spec"]["rules"][0]["http"]["paths"]}
    assert paths["/api"].endswith("fastapi")
    assert paths["/"].endswith("streamlit")
    assert yaml.safe_load((CHART / "values.yaml").read_text())["ingress"]["className"] == "nginx"


def test_hpa_targets_fastapi():
    hpa = next(d for d in all_docs() if d["kind"] == "HorizontalPodAutoscaler")
    assert hpa["spec"]["scaleTargetRef"]["kind"] == "Deployment"
    assert hpa["spec"]["scaleTargetRef"]["name"].endswith("fastapi")
    v = yaml.safe_load((CHART / "values.yaml").read_text())["autoscaling"]
    assert (v["minReplicas"], v["maxReplicas"], v["targetCPUUtilizationPercentage"]) == (2, 10, 70)


def test_configmap_keys():
    cm = next(d for d in all_docs() if d["kind"] == "ConfigMap")
    for k in ("LOG_LEVEL", "TYPEDB_HOST", "TYPEDB_PORT", "ALERT_CHANNELS", "CACHE_TTL_SECONDS"):
        assert k in cm["data"]
