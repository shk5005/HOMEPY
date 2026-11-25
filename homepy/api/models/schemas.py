"""Pydantic v2 response/request models mirroring the inference dataclasses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

COMPLEX_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
ComplexId = Annotated[str, Field(pattern=COMPLEX_ID_PATTERN)]
BuyerType = Literal["individual", "corporate"]
AreaType = Literal["regulated", "non_regulated"]


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FactorScoreResponse(_ORM):
    name: str
    raw_value: float
    normalized: float
    weight: float
    weighted_score: float
    evidence: list[str] = Field(default_factory=list)


class InvestmentScoreResponse(_ORM):
    complex_id: str
    total_score: float
    grade: str
    factors: list[FactorScoreResponse]
    computed_at: datetime


class ScoreRequest(BaseModel):
    complex_ids: list[ComplexId] = Field(min_length=1, max_length=50)


class BiasWarningResponse(_ORM):
    bias_type: str
    description: str
    severity: str
    evidence: str
    mitigation: str


class InvestmentVerdictResponse(_ORM):
    core_facts: list[str]
    strongest_bull_case: str
    strongest_bear_case: str
    hidden_variable: str
    primary_risk: str
    verdict: str
    confidence: str
    kill_switch: str
    watchlist_data: list[str]
    bias_warnings: list[BiasWarningResponse] = Field(default_factory=list)
    scenario_summary: str = ""
    evidence_chain: list[str] = Field(default_factory=list)


class ScenarioResponse(_ORM):
    name: str
    conditions: list[str]
    key_variables: dict[str, float]
    expected_outcome: str
    leading_indicators: list[str]
    invalidation_conditions: list[str]
    probability: float


class SensitivityResponse(_ORM):
    variable: str
    base_value: float
    perturbations: list[float]
    score_impacts: list[float]


class ScenarioResultResponse(_ORM):
    complex_id: str
    scenarios: list[ScenarioResponse]
    sensitivity: list[SensitivityResponse] = Field(default_factory=list)


class MacroSummaryResponse(_ORM):
    as_of: datetime | None = None
    base_rate: float | None = None
    mortgage_rate: float | None = None
    usd_krw: float | None = None
    m2_change_yoy_pct: float | None = None
    cpi_change_yoy_pct: float | None = None
    gdp_growth: float | None = None
    unemployment: float | None = None


class CycleStatusResponse(_ORM):
    district_code: str
    phase: str | None = None
    indicators: dict[str, float | None] = Field(default_factory=dict)


class TaxSimulationRequest(BaseModel):
    complex_id: str | None = None
    price: int = Field(gt=0, description="KRW purchase price")
    sale_price: int | None = Field(default=None, gt=0)
    holding_years: float = Field(default=0, ge=0)
    buyer_type: BuyerType = "individual"
    owner_count: int = Field(default=1, ge=1)
    area_type: AreaType = "non_regulated"
    assessed_values: list[int] = Field(default_factory=list)


class TaxSimulationResponse(_ORM):
    complex_id: str | None = None
    acquisition_tax: dict
    capital_gains_tax: dict | None = None
    comprehensive_tax: dict | None = None
    total_tax: int


class LoanSimulationRequest(BaseModel):
    price: int = Field(gt=0)
    income: int = Field(gt=0, description="Annual income, KRW")
    existing_debt: int = Field(default=0, ge=0, description="Annual debt service on existing loans, KRW")
    area_type: AreaType = "non_regulated"
    interest_rate: float = Field(default=0.045, gt=0, lt=1)
    term_years: int = Field(default=30, ge=1, le=50)
    first_time_buyer: bool = False


class LoanSimulationResponse(_ORM):
    max_borrowable: int
    binding_constraint: str
    ltv_limit: float
    dsr_limit: float
    ltv_cap_amount: int
    dsr_cap_amount: int
    monthly_payment: int


class GraphNode(_ORM):
    id: str
    type: str
    label: str
    attributes: dict = Field(default_factory=dict)


class GraphEdge(_ORM):
    source: str
    target: str
    relation: str


class OntologyGraphResponse(_ORM):
    complex_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class EntityListResponse(_ORM):
    entity_type: str
    count: int
    entities: list[dict]


class PipelineStatusResponse(_ORM):
    collectors: list[dict]
    total_rows: int
    latest_ts: datetime | None = None


class BacktestSummaryResponse(_ORM):
    direction_accuracy: float
    signal_hit_rate: float
    total_verdicts: int
    computed_at: datetime


class CalibrationProposalResponse(_ORM):
    proposal_id: str
    created_at: datetime
    category: str
    current_values: dict
    proposed_values: dict
    rationale: str
    status: str


class SystemHealthResponse(_ORM):
    components: list[dict]  # each: {name, status, latency_p95}
    data_quality_alerts: int
    recovery_events_24h: int


class ImprovementRecordResponse(_ORM):
    record_id: str
    timestamp: datetime
    category: str
    component: str
    trigger: str
    impact_metrics: dict[str, float] | None = None
