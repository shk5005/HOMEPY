"""POST /reports/generate — build an HTML/PDF investment report for a complex."""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from homepy.api.dependencies import get_scorer, get_simulator, get_verdict_builder
from homepy.api.models.schemas import COMPLEX_ID_PATTERN
from homepy.auth.rbac import require_roles
from homepy.reports.generator import ReportGenerator

router = APIRouter()


class ReportRequest(BaseModel):
    complex_id: Annotated[str, Field(pattern=COMPLEX_ID_PATTERN)]
    format: Literal["html", "pdf"] = "html"
    include_debate: bool = False


def get_report_generator() -> ReportGenerator:
    return ReportGenerator()


async def _run_debate(complex_id: str, score) -> object | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="Debate service not configured")
    from homepy.agents import (BearAgent, BehavioralAgent, BullAgent, DebateOrchestrator,
                               PolicyAgent)
    from homepy.agents.base import RateLimiter

    limiter = RateLimiter()
    agents = [cls(api_key, rate_limiter=limiter)
              for cls in (BullAgent, BearAgent, BehavioralAgent, PolicyAgent)]
    data = {"score": score.total_score, "grade": score.grade,
            "factors": {f.name: f.normalized for f in score.factors}}
    return await DebateOrchestrator(agents).run_debate(complex_id, data)


@router.post("/generate", dependencies=[require_roles("analyst", "admin")])
async def generate(
    body: ReportRequest,
    scorer=Depends(get_scorer),
    simulator=Depends(get_simulator),
    builder=Depends(get_verdict_builder),
    generator: ReportGenerator = Depends(get_report_generator),
):
    try:
        score, scenarios, verdict = await asyncio.gather(
            scorer.score(body.complex_id),
            simulator.simulate(body.complex_id),
            builder.build(body.complex_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    debate = await _run_debate(body.complex_id, score) if body.include_debate else None
    kwargs = dict(score=score, scenarios=scenarios, complex_id=body.complex_id)
    if body.format == "pdf":
        pdf = await asyncio.to_thread(generator.generate_pdf, verdict, debate, **kwargs)
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="report_{body.complex_id}.pdf"'})
    return HTMLResponse(generator.generate_html(verdict, debate, **kwargs))


class DebateRequest(BaseModel):
    complex_id: Annotated[str, Field(pattern=COMPLEX_ID_PATTERN)]


@router.post("/debate", dependencies=[require_roles("analyst", "admin")])
async def debate(body: DebateRequest, scorer=Depends(get_scorer)):
    """Run the multi-agent debate and return the structured DebateResult."""
    from dataclasses import asdict

    try:
        score = await scorer.score(body.complex_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await _run_debate(body.complex_id, score)
    out = asdict(result)
    out.pop("investment_verdict", None)
    return out
