from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from homepy.api.dependencies import get_scorer, get_verdict_builder
from homepy.api.models.schemas import (
    COMPLEX_ID_PATTERN,
    InvestmentScoreResponse, InvestmentVerdictResponse, ScoreRequest,
)

router = APIRouter()


@router.post("/score", response_model=list[InvestmentScoreResponse])
async def score(body: ScoreRequest, scorer=Depends(get_scorer)):
    try:
        return [await scorer.score(cid) for cid in body.complex_ids]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/verdict/{complex_id}", response_model=InvestmentVerdictResponse)
async def verdict(
    complex_id: Annotated[str, Path(pattern=COMPLEX_ID_PATTERN)],
    builder=Depends(get_verdict_builder),
):
    try:
        return await builder.build(complex_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
