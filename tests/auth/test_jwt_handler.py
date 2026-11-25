"""JWT handler tests using in-memory RSA keys and a mocked JWKS endpoint."""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from jose.backends.cryptography_backend import CryptographyRSAKey

from homepy.auth.jwt_handler import AuthenticationError, JWTHandler

ISSUER = "http://keycloak.test/realms/homepy"
AUDIENCE = "homepy-api"
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"
KID = "test-key-1"


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _jwk(key: rsa.RSAPrivateKey) -> dict:
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    jwk = CryptographyRSAKey(pub, "RS256").to_dict()
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {k: (v.decode() if isinstance(v, bytes) else v) for k, v in jwk.items()}


def _make_token(key, *, exp_delta=900, jti=None, kid=KID) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-uuid-001",
        "email": "a@example.com",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + exp_delta,
        "jti": jti or str(uuid.uuid4()),
        "realm_access": {"roles": ["analyst"]},
    }
    return jwt.encode(claims, _pem(key), algorithm="RS256", headers={"kid": kid})


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, tuple[object, int | None]] = {}

    async def set(self, name, value, ex=None):
        self.store[name] = (value, ex)
        return True

    async def exists(self, *names):
        return sum(1 for n in names if n in self.store)


@pytest.fixture(scope="module")
def signing_key():
    return _new_key()


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def jwt_handler(signing_key, fake_redis):
    jwks = {"keys": [_jwk(signing_key)]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, content=json.dumps(jwks))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JWTHandler(JWKS_URL, AUDIENCE, ISSUER, redis=fake_redis, http_client=client)


@pytest.fixture
def token_jti():
    return "jti-fixed-001"


@pytest.fixture
def valid_token(signing_key, token_jti):
    return _make_token(signing_key, jti=token_jti)


@pytest.fixture
def expired_token(signing_key):
    return _make_token(signing_key, exp_delta=-60)


@pytest.fixture
def wrong_key_token():
    return _make_token(_new_key())


async def test_valid_token_returns_payload(jwt_handler, valid_token):
    payload = await jwt_handler.verify_token(valid_token)
    assert payload.sub == "user-uuid-001"
    assert "analyst" in payload.roles
    assert payload.email == "a@example.com"


async def test_expired_token_raises(jwt_handler, expired_token):
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(expired_token)


async def test_wrong_key_token_raises(jwt_handler, wrong_key_token):
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(wrong_key_token)


async def test_blacklisted_token_rejected(jwt_handler, valid_token, token_jti):
    await jwt_handler.blacklist_token(token_jti, exp=int(time.time()) + 900)
    assert await jwt_handler.is_blacklisted(token_jti)
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(valid_token)


async def test_blacklist_sets_ttl(jwt_handler, fake_redis):
    await jwt_handler.blacklist_token("abc", exp=int(time.time()) + 100)
    _, ex = fake_redis.store["jti:abc"]
    assert 95 <= ex <= 100


async def test_wrong_audience_raises(signing_key):
    jwks = {"keys": [_jwk(signing_key)]}
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=jwks))
    )
    h = JWTHandler(JWKS_URL, "other-aud", ISSUER, http_client=client)
    with pytest.raises(AuthenticationError):
        await h.verify_token(_make_token(signing_key))


async def test_hs256_token_rejected(jwt_handler):
    token = jwt.encode(
        {"sub": "x", "exp": int(time.time()) + 60}, "secret", algorithm="HS256",
        headers={"kid": KID},
    )
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token(token)


async def test_garbage_token_raises(jwt_handler):
    with pytest.raises(AuthenticationError):
        await jwt_handler.verify_token("not-a-jwt")


@pytest.mark.skip(reason="requires live FastAPI with auth middleware")
async def test_no_token_returns_401(test_client):
    resp = await test_client.get("/api/v1/analysis/score/test-complex")
    assert resp.status_code == 401
