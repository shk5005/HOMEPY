"""Auto-calibrator: proposes factor-weight and bias-threshold updates from backtests.

Weight proposals use a 36-month rolling window split 30/6 (train/validation).
Weights are IC-proportional (``max(IC, 0)``) and always sum to 1.0.  If more
than ``OVERFIT_DEGRADED_FACTORS`` factors degrade in validation the proposal
carries an overfit warning.  Approved proposals are written to a JSON config
file; normalization-range refreshes are applied automatically.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homepy.inference import bias_detector
from homepy.inference.scorer import FACTOR_WEIGHTS
from homepy.verification.models import CalibrationProposal, ImprovementRecord

if TYPE_CHECKING:
    from homepy.storage.timescale_service import TimescaleService
    from homepy.verification.backtester import Backtester

ROLLING_WINDOW_MONTHS = 36
TRAIN_MONTHS = 30
VALIDATION_MONTHS = 6
OVERFIT_DEGRADED_FACTORS = 3  # overfit when MORE than this many factors degrade
DEGRADE_TOLERANCE = 0.05  # validation IC must fall below train IC by more than this
MIN_THRESHOLD_SAMPLES = 5

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "calibration.json"

# bias name -> (module constant, warning fires when value >= threshold ("ge") or <= ("le"))
BIAS_THRESHOLDS: dict[str, tuple[str, str]] = {
    "confirmation": ("CONFIRMATION_RATIO", "ge"),
    "anchoring": ("ANCHORING_DIVERGENCE", "ge"),
    "survivorship": ("SURVIVORSHIP_DECLINING_PCT", "ge"),
    "availability": ("AVAILABILITY_PERCENTILE", "ge"),
    "loss_aversion": ("LOSS_AVERSION_DRAWDOWN", "le"),
    "overconfidence": ("OVERCONFIDENCE_MIN_EVIDENCE", "le"),
    "base_rate": ("BASE_RATE_MULTIPLE", "ge"),
    "sunk_cost": ("SUNK_COST_EXPIRED", "ge"),
}
_INT_CONSTANTS = {"OVERCONFIDENCE_MIN_EVIDENCE", "SUNK_COST_EXPIRED"}

# Placeholder queries (accepted project pattern).
_BIAS_OUTCOMES_QUERY = (
    "SELECT metadata FROM ts_signals "
    "WHERE signal_type = 'bias_outcome' AND ts >= NOW() - ($1 || ' months')::interval"
)
_NORMALIZATION_QUERY = (
    "SELECT factor, "
    "percentile_cont(0.05) WITHIN GROUP (ORDER BY value) AS p05, "
    "percentile_cont(0.95) WITHIN GROUP (ORDER BY value) AS p95 "
    "FROM ts_factor_scores WHERE ts >= NOW() - ($1 || ' months')::interval GROUP BY factor"
)


def _f1(tp: int, fp: int, fn: int) -> float:
    denom = 2 * tp + fp + fn
    return 2 * tp / denom if denom else 0.0


class AutoCalibrator:
    def __init__(
        self,
        backtester: "Backtester",
        timescale_svc: "TimescaleService",
        config_path: Path | str | None = None,
    ) -> None:
        self._bt = backtester
        self._ts = timescale_svc
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._proposals: dict[str, CalibrationProposal] = {}
        self.normalization_ranges: dict[str, tuple[float, float]] = {}

    # ---- helpers -------------------------------------------------------
    def _load_config(self) -> dict[str, Any]:
        try:
            return json.loads(self._config_path.read_text())
        except (OSError, ValueError):
            return {}

    def _current_weights(self) -> dict[str, float]:
        return dict(self._load_config().get("weights") or FACTOR_WEIGHTS)

    def _current_thresholds(self) -> dict[str, float]:
        cfg = self._load_config().get("thresholds") or {}
        return {
            c: cfg.get(c, getattr(bias_detector, c)) for c, _ in BIAS_THRESHOLDS.values()
        }

    def _store(self, p: CalibrationProposal) -> CalibrationProposal:
        self._proposals[p.proposal_id] = p
        return p

    # ---- weights -------------------------------------------------------
    async def propose_weight_update(self) -> CalibrationProposal:
        # Train IC: 36-month window excluding last 6 months (30-month train)
        # Validation IC: last 6 months only
        train_ic = await self._bt.factor_ic_analysis(
            ROLLING_WINDOW_MONTHS, skip_recent_months=VALIDATION_MONTHS,
        )
        val_ic = await self._bt.factor_ic_analysis(VALIDATION_MONTHS)

        current = self._current_weights()
        raw = {f: max(train_ic.get(f, 0.0), 0.0) for f in FACTOR_WEIGHTS}
        total = sum(raw.values())
        proposed = {f: v / total for f, v in raw.items()} if total > 0 else dict(current)

        degraded = sorted(
            f for f in FACTOR_WEIGHTS
            if f in train_ic and f in val_ic and val_ic[f] < train_ic[f] - DEGRADE_TOLERANCE
        )
        overfit = len(degraded) > OVERFIT_DEGRADED_FACTORS
        if overfit:
            risk = (
                f"Overfit risk: {len(degraded)} factors degraded in validation "
                f"(> {OVERFIT_DEGRADED_FACTORS}): {', '.join(degraded)}. "
                "Review manually before applying."
            )
        else:
            risk = (
                f"Low overfit risk: {len(degraded)} factor(s) degraded in validation "
                f"(limit {OVERFIT_DEGRADED_FACTORS})."
            )
        if total <= 0:
            risk += " No factor has positive IC; weights left unchanged."

        return self._store(CalibrationProposal(
            proposal_id=f"cal-w-{uuid.uuid4().hex[:12]}",
            created_at=datetime.now(timezone.utc),
            category="weight",
            current_values=current,
            proposed_values=proposed,
            rationale=(
                f"IC-proportional rebalance over a {ROLLING_WINDOW_MONTHS}-month rolling window "
                f"({TRAIN_MONTHS}-month train / {VALIDATION_MONTHS}-month validation); "
                "weight proportional to max(IC, 0), normalized to sum 1.0."
            ),
            backtest_evidence={
                "train_ic": train_ic,
                "validation_ic": val_ic,
                "degraded_factors": degraded,
                "overfit": overfit,
            },
            expected_improvement="Higher weight on factors with positive predictive IC.",
            risk_assessment=risk,
            rollback_plan="Restore previous weights from the ImprovementRecord before_state.",
        ))

    # ---- thresholds ----------------------------------------------------
    async def propose_threshold_update(self) -> CalibrationProposal:
        rows = await self._ts.execute(_BIAS_OUTCOMES_QUERY, str(ROLLING_WINDOW_MONTHS))
        samples: dict[str, list[tuple[float, bool]]] = {b: [] for b in BIAS_THRESHOLDS}
        for r in rows:
            m = r["metadata"]
            if isinstance(m, str):
                m = json.loads(m)
            if m and m.get("bias") in samples and m.get("value") is not None:
                samples[m["bias"]].append((float(m["value"]), bool(m.get("valid"))))

        current = self._current_thresholds()
        proposed = dict(current)
        f1_evidence: dict[str, Any] = {}
        for bias, (const, direction) in BIAS_THRESHOLDS.items():
            data = samples[bias]
            if len(data) < MIN_THRESHOLD_SAMPLES:
                f1_evidence[bias] = {"samples": len(data), "note": "insufficient data"}
                continue

            def f1_at(t: float) -> float:
                tp = fp = fn = 0
                for v, valid in data:
                    warn = v >= t if direction == "ge" else v <= t
                    if warn and valid:
                        tp += 1
                    elif warn:
                        fp += 1
                    elif valid:
                        fn += 1
                return _f1(tp, fp, fn)

            cur = float(current[const])
            best_t, best_f1 = cur, f1_at(cur)
            for t in sorted({v for v, _ in data}):
                score = f1_at(t)
                if score > best_f1 + 1e-12:
                    best_t, best_f1 = t, score
            proposed[const] = int(round(best_t)) if const in _INT_CONSTANTS else best_t
            f1_evidence[bias] = {
                "samples": len(data), "current_f1": f1_at(cur), "proposed_f1": best_f1,
            }

        return self._store(CalibrationProposal(
            proposal_id=f"cal-t-{uuid.uuid4().hex[:12]}",
            created_at=datetime.now(timezone.utc),
            category="threshold",
            current_values=current,
            proposed_values=proposed,
            rationale=(
                "Per-bias threshold maximizing F1 of bias warnings vs. realized outcomes "
                f"over the {ROLLING_WINDOW_MONTHS}-month rolling window."
            ),
            backtest_evidence=f1_evidence,
            expected_improvement="Higher precision/recall of bias warnings.",
            risk_assessment=f"Biases with < {MIN_THRESHOLD_SAMPLES} samples are left unchanged.",
            rollback_plan="Restore previous thresholds from the ImprovementRecord before_state.",
        ))

    # ---- normalization (auto-apply) ------------------------------------
    async def refresh_normalization_ranges(self) -> dict[str, tuple[float, float]]:
        rows = await self._ts.execute(_NORMALIZATION_QUERY, str(ROLLING_WINDOW_MONTHS))
        ranges: dict[str, tuple[float, float]] = {}
        for r in rows:
            lo, hi = float(r["p05"]), float(r["p95"])
            if lo < hi:
                ranges[r["factor"]] = (lo, hi)
        self.normalization_ranges.update(ranges)
        return dict(self.normalization_ranges)

    # ---- lifecycle -----------------------------------------------------
    def _get_open(self, proposal_id: str) -> CalibrationProposal:
        p = self._proposals.get(proposal_id)
        if p is None:
            raise KeyError(f"unknown proposal: {proposal_id}")
        if p.status != "proposed":
            raise ValueError(f"proposal {proposal_id} is {p.status}, not proposed")
        return p

    def list_proposals(self, status: str | None = "proposed") -> list[CalibrationProposal]:
        """Stored proposals, optionally filtered by status (None = all)."""
        return [p for p in self._proposals.values() if status is None or p.status == status]

    async def apply_proposal(self, proposal_id: str) -> ImprovementRecord:
        p = self._get_open(proposal_id)
        cfg = self._load_config()
        section = "weights" if p.category == "weight" else "thresholds"
        before = dict(p.current_values)
        cfg[section] = dict(p.proposed_values)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
        p.status = "applied"
        return ImprovementRecord(
            record_id=f"imp-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            category="calibration",
            component=section,
            before_state=before,
            after_state=dict(p.proposed_values),
            trigger=f"proposal {p.proposal_id}",
            evidence=p.backtest_evidence,
            approved_by="user",
            rollback_possible=True,
        )

    async def reject_proposal(self, proposal_id: str, reason: str) -> None:
        p = self._get_open(proposal_id)
        p.status = "rejected"
        p.backtest_evidence = {**p.backtest_evidence, "rejection_reason": reason}
