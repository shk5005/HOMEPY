from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from homepy.api.dependencies import get_neo4j
from homepy.api.models.schemas import EntityListResponse, GraphEdge, GraphNode, OntologyGraphResponse

router = APIRouter()
NEO4J_DB = "homepy"
NODE_LABELS = {"Region", "District", "Dong", "Complex", "UnitType", "LoanProduct",
               "Policy", "Infrastructure", "DevelopmentProject"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/entity/{entity_type}", response_model=EntityListResponse)
async def list_entities(entity_type: str, limit: int = Query(50, ge=1, le=500),
                        neo4j=Depends(get_neo4j)):
    if entity_type not in NODE_LABELS:
        raise HTTPException(status_code=404, detail=f"unknown entity type: {entity_type}")
    rows = neo4j.execute_read(
        NEO4J_DB,
        f"MATCH (e:{entity_type}) RETURN e LIMIT $limit",
        limit=limit)
    return EntityListResponse(entity_type=entity_type, count=len(rows), entities=list(rows))


@router.get("/graph/{complex_id}", response_model=OntologyGraphResponse)
async def graph(complex_id: str, neo4j=Depends(get_neo4j)):
    if not _ID_RE.fullmatch(complex_id):
        raise HTTPException(status_code=422, detail="invalid complex_id")
    rows = neo4j.execute_read(
        NEO4J_DB,
        "MATCH (c:Complex {complexId: $cid})-[r]-(o) "
        "RETURN labels(o)[0] AS otype, type(r) AS rel, "
        "coalesce(o.complexId, o.districtCode, o.regionCode, id(o)) AS oid "
        "LIMIT 200",
        cid=complex_id)
    nodes = {complex_id: GraphNode(id=complex_id, type="Complex", label=complex_id)}
    edges: list[GraphEdge] = []
    for i, row in enumerate(rows):
        oid = str(row.get("oid") or f"node-{i}")
        otype = str(row.get("otype") or "Node")
        nodes.setdefault(oid, GraphNode(id=oid, type=otype, label=oid))
        edges.append(GraphEdge(source=complex_id, target=oid, relation=str(row.get("rel") or "RELATED")))
    return OntologyGraphResponse(complex_id=complex_id, nodes=list(nodes.values()), edges=edges)
