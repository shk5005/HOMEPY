from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from homepy.api.dependencies import get_policy_simulator, get_simulator, get_tax_engine
from homepy.api.models.schemas import (
    COMPLEX_ID_PATTERN,
    LoanSimulationRequest, LoanSimulationResponse, ScenarioResultResponse,
    TaxSimulationRequest, TaxSimulationResponse,
)

router = APIRouter()

# (LTV, DSR) limits by area type; simplified policy values.
LOAN_LIMITS = {"regulated": (0.40, 0.40), "non_regulated": (0.70, 0.40)}
FIRST_TIME_LTV = 0.70


@router.post("/scenario/{complex_id}", response_model=ScenarioResultResponse)
async def scenario(
    complex_id: Annotated[str, Path(pattern=COMPLEX_ID_PATTERN)],
    simulator=Depends(get_simulator),
):
    try:
        return await simulator.simulate(complex_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tax", response_model=TaxSimulationResponse)
async def tax(body: TaxSimulationRequest, engine=Depends(get_tax_engine)):
    acq = await engine.calc_acquisition_tax(
        body.price, body.buyer_type, body.owner_count, body.area_type)
    cgt = None
    if body.sale_price is not None:
        cgt = await engine.calc_capital_gains_tax(
            body.price, body.sale_price, body.holding_years, body.area_type, body.owner_count)
    comp = None
    if body.assessed_values:
        comp = await engine.calc_comprehensive_tax(body.assessed_values, body.owner_count)
    total = acq["total"] + (cgt["total"] if cgt else 0) + (comp["total"] if comp else 0)
    return TaxSimulationResponse(
        complex_id=body.complex_id, acquisition_tax=acq, capital_gains_tax=cgt,
        comprehensive_tax=comp, total_tax=total)


@router.post("/loan", response_model=LoanSimulationResponse)
async def loan(body: LoanSimulationRequest):
    ltv, dsr = LOAN_LIMITS.get(body.area_type, LOAN_LIMITS["non_regulated"])
    if body.first_time_buyer:
        ltv = max(ltv, FIRST_TIME_LTV)
    ltv_cap = int(body.price * ltv)
    # Annuity factor: annual payment per KRW borrowed.
    r, n = body.interest_rate / 12, body.term_years * 12
    monthly_factor = r / (1 - (1 + r) ** -n)
    annual_budget = body.income * dsr - body.existing_debt
    dsr_cap = max(0, int(annual_budget / (monthly_factor * 12)))
    maximum = min(ltv_cap, dsr_cap)
    return LoanSimulationResponse(
        max_borrowable=maximum,
        binding_constraint="LTV" if ltv_cap <= dsr_cap else "DSR",
        ltv_limit=ltv, dsr_limit=dsr, ltv_cap_amount=ltv_cap, dsr_cap_amount=dsr_cap,
        monthly_payment=int(maximum * monthly_factor))


class PolicyRequest(BaseModel):
    policy_type: str = Field(pattern="^(tax|regulation|interest_rate|supply_shock)$")
    parameters: dict[str, Any] = Field(default_factory=dict)


class PolicyBacktestRequest(BaseModel):
    policy_name: str
    policy_date: date
    changes: dict[str, Any] = Field(default_factory=dict)


@router.post("/policy")
async def policy(body: PolicyRequest, sim=Depends(get_policy_simulator)):
    p = body.parameters
    try:
        if body.policy_type == "tax":
            result = await sim.simulate_tax_change(p)
        elif body.policy_type == "regulation":
            result = await sim.simulate_regulation(
                p["district_code"], p["regulation_type"], p["action"])
        elif body.policy_type == "interest_rate":
            result = await sim.simulate_interest_rate(p["rate_path"])
        else:
            result = await sim.simulate_supply_shock(p["district_code"], int(p["units"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid parameters: {exc}") from exc
    return asdict(result)


@router.post("/policy/backtest")
async def policy_backtest(body: PolicyBacktestRequest, sim=Depends(get_policy_simulator)):
    result = await sim.backtest_policy(body.policy_name, body.policy_date, body.changes)
    return asdict(result)
