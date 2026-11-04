"""Data models for backtesting, calibration, improvement and recovery tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class BacktestRecord:
    verdict_id: str
    complex_id: str
    verdict_date: date | datetime
    predicted_verdict: str
    predicted_score: float
    predicted_scenarios: dict[str, Any] = field(default_factory=dict)
    actual_price_change_3m: float | None = None
    actual_price_change_6m: float | None = None
    actual_price_change_12m: float | None = None
    direction_correct: bool | None = None
    scenario_hit: bool | None = None
    factor_contributions: dict[str, float] = field(default_factory=dict)
    bias_warnings_issued: int = 0
    bias_warnings_valid: int = 0


@dataclass
class CalibrationProposal:
    proposal_id: str
    created_at: datetime
    category: str
    current_values: dict[str, Any]
    proposed_values: dict[str, Any]
    rationale: str
    backtest_evidence: dict[str, Any] = field(default_factory=dict)
    expected_improvement: str = ""
    risk_assessment: str = ""
    rollback_plan: str = ""
    status: str = "proposed"


@dataclass
class ImprovementRecord:
    record_id: str
    timestamp: datetime
    category: str
    component: str
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    trigger: str
    evidence: dict[str, Any] = field(default_factory=dict)
    impact_metrics: dict[str, float] = field(default_factory=dict)
    approved_by: str | None = None
    rollback_possible: bool = True


@dataclass
class RecoveryEvent:
    event_id: str
    timestamp: datetime
    failure_type: str
    component: str
    auto_action: str
    success: bool
    human_escalated: bool = False
    resolution_time_seconds: float | None = None
