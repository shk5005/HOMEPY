"""POST /nlp/query — natural language to (read-only) TypeQL, executed on TypeDB."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from homepy.api.dependencies import get_typedb
from homepy.auth.rbac import require_roles
from homepy.nlp.query_generator import NLPQueryResult, RateLimitError, TypeQLGenerator

router = APIRouter()

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "storage" / "typedb" / "schema.tql"
TYPEDB_DATABASE = "homepy"
_generator: TypeQLGenerator | None = None


class NLPQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class NLPQueryResponse(BaseModel):
    original_query: str
    generated_typeql: str
    results: list[dict]
    execution_time_ms: float


def get_generator() -> TypeQLGenerator:
    global _generator
    if _generator is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="NLP service not configured")
        _generator = TypeQLGenerator(api_key, SCHEMA_PATH.read_text(encoding="utf-8"))
    return _generator


@router.post("/query", response_model=NLPQueryResponse,
             dependencies=[require_roles("analyst", "admin")])
async def nlp_query(body: NLPQueryRequest, request: Request,
                    generator: TypeQLGenerator = Depends(get_generator),
                    typedb=Depends(get_typedb)):
    start = time.perf_counter()
    try:
        typeql = await generator.generate(body.query)
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = await asyncio.to_thread(typedb.execute_read, TYPEDB_DATABASE, typeql, True)
    result = NLPQueryResult(body.query, typeql, rows, (time.perf_counter() - start) * 1000)
    return asdict(result)
