from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.skip(reason="requires live Nginx")


def test_nginx_round_robin(nginx_running):
    node_ids = set()
    for _ in range(10):
        resp = httpx.get("http://localhost:80/api/v1/pipeline/health")
        assert resp.status_code == 200
        node_ids.add(resp.json()["node_id"])
    assert len(node_ids) == 2


def test_nginx_streamlit_proxy(nginx_running):
    resp = httpx.get("http://localhost:80/app/")
    assert resp.status_code == 200
