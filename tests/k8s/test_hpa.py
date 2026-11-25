"""HPA spec tests (design Section 13.1)."""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.k8s.test_helm_chart import CHART, pseudo_render

HPA = CHART / "templates" / "hpa.yaml"


def _values():
    return yaml.safe_load((CHART / "values.yaml").read_text())["autoscaling"]


def _hpa():
    return next(d for d in pseudo_render(HPA) if d["kind"] == "HorizontalPodAutoscaler")


def test_hpa_api_version():
    assert _hpa()["apiVersion"] == "autoscaling/v2"


def test_hpa_values_match_design():
    v = _values()
    assert v["enabled"] is True
    assert v["minReplicas"] == 2
    assert v["maxReplicas"] == 10
    assert v["targetCPUUtilizationPercentage"] == 70


def test_hpa_template_wires_values_and_target():
    text = HPA.read_text()
    assert ".Values.autoscaling.minReplicas" in text
    assert ".Values.autoscaling.maxReplicas" in text
    assert ".Values.autoscaling.targetCPUUtilizationPercentage" in text
    spec = _hpa()["spec"]
    assert spec["scaleTargetRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": "PLACEHOLDER-fastapi"}
    cpu = next(m for m in spec["metrics"] if m["resource"]["name"] == "cpu")
    assert cpu["resource"]["target"]["type"] == "Utilization"


@pytest.mark.skipif(shutil.which("helm") is None, reason="requires helm CLI")
def test_hpa_spec_matches_design_helm():
    result = subprocess.run(["helm", "template", "homepy", str(CHART)],
                            capture_output=True, text=True, check=True)
    docs = [d for d in yaml.safe_load_all(result.stdout)
            if d and d.get("kind") == "HorizontalPodAutoscaler"]
    assert docs
    spec = docs[0]["spec"]
    assert spec["minReplicas"] == 2
    assert spec["maxReplicas"] == 10
    cpu = next(m for m in spec["metrics"] if m["resource"]["name"] == "cpu")
    assert cpu["resource"]["target"]["averageUtilization"] == 70
    assert spec["scaleTargetRef"]["name"] == "homepy-fastapi"
