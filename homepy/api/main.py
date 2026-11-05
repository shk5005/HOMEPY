"""HOMEPY FastAPI application (port 8000)."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from homepy.auth import JWTHandler
from homepy.auth.rbac import RBACMiddleware
from homepy.auth.tenant import TenantMiddleware
from homepy.realtime.ws_server import signal_stream
from homepy.api.routers import (analysis, market, nlp, ontology, pipeline, portfolio, reports,
                                 simulation)

PREFIXES = {
    "ontology": "/api/v1/ontology",
    "analysis": "/api/v1/analysis",
    "simulation": "/api/v1/simulation",
    "market": "/api/v1/market",
    "portfolio": "/api/v1/portfolio",
    "pipeline": "/api/v1/pipeline",
    "nlp": "/api/v1/nlp",
    "reports": "/api/v1/reports",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging

    log = logging.getLogger("homepy.startup")
    from homepy.storage.timescale_service import TimescaleService
    from homepy.storage.typedb_service import TypeDBService

    typedb = TypeDBService(os.environ.get("TYPEDB_ADDRESS", "localhost:1729"))
    timescale = TimescaleService(
        os.environ.get("TIMESCALE_DSN", "postgresql://homepy:homepy@localhost:5432/homepy")
    )
    try:
        await asyncio.to_thread(typedb.connect)
        log.info("TypeDB connected")
    except Exception as exc:
        log.warning("TypeDB unavailable (%s) — ontology endpoints will fail", exc)
        typedb = None
    try:
        await timescale.connect()
        log.info("TimescaleDB connected")
    except Exception as exc:
        log.warning("TimescaleDB unavailable (%s) — time-series endpoints will fail", exc)
        timescale = None
    app.state.typedb, app.state.timescale = typedb, timescale
    try:
        yield
    finally:
        if timescale is not None:
            await timescale.close()
        if typedb is not None:
            await asyncio.to_thread(typedb.close)


def create_app(use_lifespan: bool = True) -> FastAPI:
    """Build the app. ``use_lifespan=False`` skips DB connections (tests)."""
    import time as _time

    app = FastAPI(title="도깨비", version="0.1.0", lifespan=lifespan if use_lifespan else None)
    app.state.startup_time = _time.monotonic()
    issuer = os.environ.get("KEYCLOAK_ISSUER", "http://localhost:8080/realms/homepy")
    app.state.jwt_handler = JWTHandler(
        jwks_url=os.environ.get("KEYCLOAK_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"),
        audience=os.environ.get("JWT_AUDIENCE", "homepy-api"),
        issuer=issuer,
    )
    # Starlette runs the last-added middleware first: RBAC (sets request.state.user) -> Tenant.
    app.add_middleware(TenantMiddleware)
    app.add_middleware(RBACMiddleware)
    for module, name in [(ontology, "ontology"), (analysis, "analysis"),
                         (simulation, "simulation"), (market, "market"),
                         (portfolio, "portfolio"), (pipeline, "pipeline"),
                         (nlp, "nlp"), (reports, "reports")]:
        app.include_router(module.router, prefix=PREFIXES[name], tags=[name])
    # WebSocket route is intentionally outside the /api/v1 router prefixes.
    app.add_api_websocket_route("/ws/signals/{district_code}", signal_stream)
    return app


app = create_app()
