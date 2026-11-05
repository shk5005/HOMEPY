"""HOMEPY FastAPI application (port 8000)."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from homepy.auth import JWTHandler
from homepy.auth.rbac import RBACMiddleware
from homepy.api.routers import analysis, market, ontology, pipeline, portfolio, simulation

PREFIXES = {
    "ontology": "/api/v1/ontology",
    "analysis": "/api/v1/analysis",
    "simulation": "/api/v1/simulation",
    "market": "/api/v1/market",
    "portfolio": "/api/v1/portfolio",
    "pipeline": "/api/v1/pipeline",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from homepy.storage.timescale_service import TimescaleService
    from homepy.storage.typedb_service import TypeDBService

    typedb = TypeDBService(os.environ.get("TYPEDB_ADDRESS", "localhost:1729"))
    timescale = TimescaleService(
        os.environ.get("TIMESCALE_DSN", "postgresql://homepy:homepy@localhost:5432/homepy")
    )
    await asyncio.to_thread(typedb.connect)
    await timescale.connect()
    app.state.typedb, app.state.timescale = typedb, timescale
    try:
        yield
    finally:
        await timescale.close()
        await asyncio.to_thread(typedb.close)


def create_app(use_lifespan: bool = True) -> FastAPI:
    """Build the app. ``use_lifespan=False`` skips DB connections (tests)."""
    import time as _time

    app = FastAPI(title="HOMEPY", version="0.1.0", lifespan=lifespan if use_lifespan else None)
    app.state.startup_time = _time.monotonic()
    issuer = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8080/realms/homepy")
    app.state.jwt_handler = JWTHandler(
        jwks_url=os.environ.get("KEYCLOAK_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
        audience=os.environ.get("JWT_AUDIENCE", "homepy-api"),
        issuer=issuer,
    )
    app.add_middleware(RBACMiddleware)
    for module, name in [(ontology, "ontology"), (analysis, "analysis"),
                         (simulation, "simulation"), (market, "market"),
                         (portfolio, "portfolio"), (pipeline, "pipeline")]:
        app.include_router(module.router, prefix=PREFIXES[name], tags=[name])
    return app


app = create_app()
