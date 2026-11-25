"""POST /nlp/query — natural language to (read-only) Cypher, executed on Neo4j."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from homepy.api.dependencies import get_neo4j
from homepy.auth.rbac import require_roles
from homepy.nlp.query_generator import NLPQueryResult, RateLimitError, CypherGenerator

router = APIRouter()

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "storage" / "neo4j" / "schema.cypher"
NEO4J_DATABASE = "homepy"
_generator: CypherGenerator | None = None


class NLPQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class NLPQueryResponse(BaseModel):
    original_query: str
    generated_cypher: str
    results: list[dict]
    execution_time_ms: float


def get_generator() -> CypherGenerator:
    global _generator
    if _generator is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=503, detail="NLP service not configured")
        _generator = CypherGenerator(api_key, SCHEMA_PATH.read_text(encoding="utf-8"))
    return _generator


@router.post("/query", response_model=NLPQueryResponse,
             dependencies=[require_roles("analyst", "admin")])
async def nlp_query(body: NLPQueryRequest, request: Request,
                    generator: CypherGenerator = Depends(get_generator),
                    neo4j=Depends(get_neo4j)):
    start = time.perf_counter()
    try:
        cypher = await generator.generate(body.query)
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = neo4j.execute_read(NEO4J_DATABASE, cypher)
    result = NLPQueryResult(body.query, cypher, rows, (time.perf_counter() - start) * 1000)
    return asdict(result)
