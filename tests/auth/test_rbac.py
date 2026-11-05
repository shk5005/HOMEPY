"""RBAC tests: token roles vs endpoint permissions (no live services needed)."""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest
from jose import jwt

from homepy.api.main import create_app
from homepy.auth.jwt_handler import JWTHandler
from homepy.auth.rbac import ENDPOINT_PERMISSIONS, required_roles_for
from tests.auth.test_jwt_handler import (
    AUDIENCE, ISSUER, JWKS_URL, KID, _jwk, _new_key, _pem,
)


@pytest.fixture(scope="module")
def key():
    return _new_key()


def _token(key, roles: list[str]) -> str:
    now = int(time.time())
    claims = {
        "sub": "u1", "email": "u@example.com", "iss": ISSUER, "aud": AUDIENCE,
        "iat": now, "exp": now + 900, "jti": str(uuid.uuid4()),
        "realm_access": {"roles": roles},
    }
    return jwt.encode(claims, _pem(key), algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def viewer_token(key): return _token(key, ["viewer"])
@pytest.fixture
def analyst_token(key): return _token(key, ["analyst"])
@pytest.fixture
def operator_token(key): return _token(key, ["pipeline_operator"])
@pytest.fixture
def admin_token(key): return _token(key, ["admin"])


@pytest.fixture
async def test_client(key):
    app = create_app(use_lifespan=False)
    jwks = {"keys": [_jwk(key)]}
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=json.dumps(jwks)))
    )
    app.state.jwt_handler = JWTHandler(JWKS_URL, AUDIENCE, ISSUER, http_client=http)
    # No DB in tests: handlers may 500; we only assert on authorization outcome.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _h(t): return {"Authorization": f"Bearer {t}"}


async def test_viewer_can_access_market(test_client, viewer_token):
    resp = await test_client.get("/api/v1/market/cycle/11680", headers=_h(viewer_token))
    assert resp.status_code != 403


async def test_viewer_cannot_access_analysis(test_client, viewer_token):
    resp = await test_client.get("/api/v1/analysis/score/test-complex", headers=_h(viewer_token))
    assert resp.status_code == 403


async def test_analyst_can_access_analysis(test_client, analyst_token):
    resp = await test_client.get("/api/v1/analysis/score/test-complex", headers=_h(analyst_token))
    assert resp.status_code not in (401, 403)


async def test_pipeline_operator_cannot_approve_proposal(test_client, operator_token):
    resp = await test_client.post(
        "/api/v1/pipeline/verification/proposals/P001/approve", headers=_h(operator_token)
    )
    assert resp.status_code == 403


async def test_admin_can_approve_proposal(test_client, admin_token):
    resp = await test_client.post(
        "/api/v1/pipeline/verification/proposals/P001/approve", headers=_h(admin_token)
    )
    assert resp.status_code not in (401, 403)


async def test_pipeline_operator_can_access_pipeline(test_client, operator_token):
    resp = await test_client.get("/api/v1/pipeline/status", headers=_h(operator_token))
    assert resp.status_code not in (401, 403)


async def test_analyst_cannot_access_pipeline(test_client, analyst_token):
    resp = await test_client.get("/api/v1/pipeline/status", headers=_h(analyst_token))
    assert resp.status_code == 403


async def test_missing_token_is_401(test_client):
    resp = await test_client.get("/api/v1/market/cycle/11680")
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/pipeline/health", "/api/v1/pipeline/ha/status"])
async def test_health_probes_exempt(test_client, path):
    resp = await test_client.get(path)
    assert resp.status_code not in (401, 403)


async def test_openapi_exempt(test_client):
    assert (await test_client.get("/openapi.json")).status_code == 200


def test_most_specific_pattern_wins():
    assert required_roles_for("/api/v1/pipeline/verification/proposals/P1/approve") == ["admin"]
    assert required_roles_for("/api/v1/pipeline/status") == ["pipeline_operator", "admin"]
    assert required_roles_for("/other") is None
    assert set(ENDPOINT_PERMISSIONS) >= {"/api/v1/market/*"}
