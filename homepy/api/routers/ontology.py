from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from homepy.api.dependencies import get_typedb
from homepy.api.models.schemas import EntityListResponse, GraphEdge, GraphNode, OntologyGraphResponse

router = APIRouter()
TYPEDB_DB = "homepy"
ENTITY_TYPES = {"region", "district", "dong", "complex", "unit-type", "loan-product",
                "policy", "infrastructure", "development-project"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/entity/{entity_type}", response_model=EntityListResponse)
async def list_entities(entity_type: str, limit: int = Query(50, ge=1, le=500),
                        typedb=Depends(get_typedb)):
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=404, detail=f"unknown entity type: {entity_type}")
    rows = await asyncio.to_thread(
        typedb.execute_read, TYPEDB_DB,
        f"match $e isa {entity_type}; get $e; limit {limit};")
    return EntityListResponse(entity_type=entity_type, count=len(rows), entities=list(rows))


@router.get("/graph/{complex_id}", response_model=OntologyGraphResponse)
async def graph(complex_id: str, typedb=Depends(get_typedb)):
    if not _ID_RE.fullmatch(complex_id):
        raise HTTPException(status_code=422, detail="invalid complex_id")
    rows = await asyncio.to_thread(
        typedb.execute_read, TYPEDB_DB,
        f'match $c isa complex, has complex-id "{complex_id}"; '
        "$r ($c, $o) isa $rel; $o isa $ot; get $o, $rel, $ot; limit 200;")
    nodes = {complex_id: GraphNode(id=complex_id, type="complex", label=complex_id)}
    edges: list[GraphEdge] = []
    for i, row in enumerate(rows):
        oid = str(row.get("o_id") or row.get("o") or f"node-{i}")
        otype = str(row.get("ot") or "entity")
        nodes.setdefault(oid, GraphNode(id=oid, type=otype, label=oid))
        edges.append(GraphEdge(source=complex_id, target=oid, relation=str(row.get("rel") or "related")))
    return OntologyGraphResponse(complex_id=complex_id, nodes=list(nodes.values()), edges=edges)
