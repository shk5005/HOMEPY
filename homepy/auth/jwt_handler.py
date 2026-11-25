"""RS256 JWT verification against Keycloak JWKS, with a Redis token blacklist."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from fastapi import HTTPException, Request
from jose import JWTError, jwt

from homepy.auth.models import TokenPayload

if TYPE_CHECKING:
    from collections.abc import Awaitable

JWKS_TTL_SECONDS = 3600
ALGORITHMS = ["RS256"]  # RS256 only; never allow symmetric algorithms
BLACKLIST_PREFIX = "jti:"


class AuthenticationError(Exception):
    """Invalid, expired or revoked credentials (maps to HTTP 401)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BlacklistStore(Protocol):
    """Subset of redis.asyncio.Redis used for the blacklist."""

    def set(self, name: str, value: Any, ex: int | None = None) -> Awaitable[Any]: ...

    def exists(self, *names: str) -> Awaitable[int]: ...


class JWTHandler:
    def __init__(
        self,
        jwks_url: str,
        audience: str,
        issuer: str,
        redis: BlacklistStore | None = None,
        http_client: httpx.AsyncClient | None = None,
        jwks_ttl: int = JWKS_TTL_SECONDS,
    ) -> None:
        self.jwks_url = jwks_url
        self.audience = audience
        self.issuer = issuer
        self._redis = redis
        self._http = http_client
        self._jwks_ttl = jwks_ttl
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at = 0.0

    @classmethod
    async def from_issuer(
        cls, issuer: str, audience: str, **kwargs: Any
    ) -> JWTHandler:
        """Discover jwks_uri from the issuer's OIDC well-known document."""
        url = issuer.rstrip("/") + "/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            jwks_uri = resp.json()["jwks_uri"]
        return cls(jwks_uri, audience, issuer, **kwargs)

    async def _fetch_jwks(self) -> None:
        client = self._http or httpx.AsyncClient(timeout=10)
        try:
            resp = await client.get(self.jwks_url)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError("Unable to fetch signing keys") from exc
        finally:
            if self._http is None:
                await client.aclose()
        self._keys = {k["kid"]: k for k in keys if "kid" in k}
        self._fetched_at = time.monotonic()

    async def _get_key(self, kid: str) -> dict[str, Any]:
        stale = time.monotonic() - self._fetched_at > self._jwks_ttl
        if stale or kid not in self._keys:
            # Refetch on TTL expiry or unknown kid (key rotation)
            await self._fetch_jwks()
        key = self._keys.get(kid)
        if key is None:
            raise AuthenticationError("Unknown signing key")
        return key

    async def verify_token(self, token: str) -> TokenPayload:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise AuthenticationError("Malformed token") from exc
        if header.get("alg") not in ALGORITHMS:
            raise AuthenticationError("Unsupported signing algorithm")
        key = await self._get_key(header.get("kid", ""))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self.audience,
                issuer=self.issuer,
                options={"require_exp": True, "require_iat": True},
            )
        except JWTError as exc:
            raise AuthenticationError(f"Invalid token: {exc}") from exc

        jti = str(claims.get("jti", ""))
        if not jti:
            raise AuthenticationError("Token missing jti")
        if await self.is_blacklisted(jti):
            raise AuthenticationError("Token has been revoked")

        roles = list(claims.get("realm_access", {}).get("roles", []))
        return TokenPayload(
            sub=str(claims["sub"]),
            email=str(claims.get("email", "")),
            roles=roles,
            exp=int(claims["exp"]),
            iat=int(claims["iat"]),
            jti=jti,
        )

    async def blacklist_token(self, jti: str, exp: int) -> None:
        if self._redis is None:
            raise RuntimeError("Redis is required for token blacklist")
        ttl = exp - int(time.time())
        if ttl <= 0:
            return  # already expired; nothing to revoke
        await self._redis.set(f"{BLACKLIST_PREFIX}{jti}", 1, ex=ttl)

    async def is_blacklisted(self, jti: str) -> bool:
        if self._redis is None:
            return False
        return bool(await self._redis.exists(f"{BLACKLIST_PREFIX}{jti}"))


async def get_current_user(request: Request) -> TokenPayload:
    """FastAPI dependency: Bearer token -> TokenPayload, else 401.

    Expects a JWTHandler at ``request.app.state.jwt_handler`` (wired in Task 2).
    """
    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    handler: JWTHandler | None = getattr(request.app.state, "jwt_handler", None)
    if handler is None:
        raise HTTPException(status_code=503, detail="Auth not configured")
    try:
        return await handler.verify_token(token.strip())
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
