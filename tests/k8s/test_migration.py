"""Migration script tests: syntax and key behaviours (scripts are not executed)."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
NAMES = ["migrate_to_k8s.sh", "migrate_volumes.sh"]


@pytest.mark.parametrize("name", NAMES)
def test_script_syntax(name):
    r = subprocess.run(["bash", "-n", str(SCRIPTS / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("name", NAMES)
def test_script_strict_and_executable(name):
    p = SCRIPTS / name
    assert p.read_text().startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in p.read_text()
    assert os.access(p, os.X_OK)


def test_migrate_to_k8s_steps():
    t = (SCRIPTS / "migrate_to_k8s.sh").read_text()
    for needle in ("kubectl", "helm", "docker", "create namespace", "migrate_volumes.sh",
                   "values-prod.yaml", "/health", "upgrade --install"):
        assert needle in t


def test_migrate_volumes_steps():
    t = (SCRIPTS / "migrate_volumes.sh").read_text()
    for needle in ("pg_dump", "typedb server export", "typedb server import",
                   "PersistentVolumeClaim", "pg_restore", "kubectl"):
        assert needle in t
