from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from homepy.api.dependencies import get_scorer
from homepy.api.models.schemas import InvestmentScoreResponse, ScoreRequest

router = APIRouter()


@router.post("/rank", response_model=list[InvestmentScoreResponse])
async def rank(body: ScoreRequest, scorer=Depends(get_scorer)):
    """Score the given complexes and return them ranked best-first."""
    try:
        scores = [await scorer.score(cid) for cid in body.complex_ids]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return sorted(scores, key=lambda s: s.total_score, reverse=True)
