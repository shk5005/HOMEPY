"""Statistical anomaly detection: Z-score, IsolationForest, CUSUM, Bollinger."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from homepy.monitoring.models import AnomalyResult

logger = logging.getLogger(__name__)

MONITORED_METRICS = ("price_index", "volume", "interest_rate")
FP_SUPPRESSION_THRESHOLD = 0.30


def severity_from_sigma(deviation: float) -> str:
    """Map deviation magnitude (in sigmas) to a severity label."""
    d = abs(deviation)
    if d >= 4.0:
        return "critical"
    if d >= 3.0:
        return "high"
    if d >= 2.0:
        return "medium"
    return "low"


def severity_from_iforest_score(score: float) -> str:
    """Map IsolationForest decision_function score (more negative = worse)."""
    if score < -0.6:
        return "critical"
    if score < -0.5:
        return "high"
    if score < -0.4:
        return "medium"
    return "low"


def _make_result(
    algorithm: str,
    district_code: str,
    metric_name: str,
    current_value: float,
    baseline_value: float,
    z_score: float | None,
    severity: str,
    details: dict[str, Any] | None = None,
) -> AnomalyResult:
    return AnomalyResult(
        anomaly_id=f"{algorithm}_{uuid4().hex[:8]}",
        detected_at=datetime.now(timezone.utc),
        district_code=district_code,
        metric_name=metric_name,
        algorithm=algorithm,
        current_value=float(current_value),
        baseline_value=float(baseline_value),
        z_score=None if z_score is None else float(z_score),
        severity=severity,
        details=details or {},
    )


def _safe_std(std: float, mean: float) -> float:
    """Floor a zero std so constant baselines yield a large finite Z."""
    return std if std > 1e-12 else max(abs(mean) * 1e-6, 1e-12)


class ZScoreDetector:
    algorithm = "zscore"

    def __init__(self, threshold: float = 3.0, lookback_days: int = 90) -> None:
        self.threshold = threshold
        self.lookback_days = lookback_days

    def detect(
        self,
        series: pd.Series,
        district_code: str = "unknown",
        metric_name: str = "value",
    ) -> list[AnomalyResult]:
        values = pd.Series(series).dropna().astype(float)
        if len(values) < 3:
            return []
        current = values.iloc[-1]
        baseline = values.iloc[:-1].tail(self.lookback_days)
        mean = float(baseline.mean())
        std = _safe_std(float(baseline.std(ddof=1)) if len(baseline) > 1 else 0.0, mean)
        z = (current - mean) / std
        if abs(z) <= self.threshold:
            return []
        return [
            _make_result(
                self.algorithm, district_code, metric_name, current, mean, z,
                severity_from_sigma(z),
                {"threshold": self.threshold, "lookback_days": self.lookback_days,
                 "baseline_std": std},
            )
        ]


class IsolationForestDetector:
    algorithm = "isolation_forest"

    def __init__(self, contamination: float = 0.01) -> None:
        self.contamination = contamination

    def detect(
        self,
        features: pd.DataFrame,
        district_code: str = "unknown",
        metric_name: str = "multivariate",
    ) -> list[AnomalyResult]:
        data = features.dropna()
        if len(data) < 2:
            return []
        model = IsolationForest(contamination=self.contamination, random_state=42)
        labels = model.fit_predict(data.values)
        scores = model.decision_function(data.values)
        means = data.mean()
        first_col = data.columns[0]
        results: list[AnomalyResult] = []
        for pos in np.where(labels == -1)[0]:
            score = float(scores[pos])
            row = data.iloc[pos]
            results.append(
                _make_result(
                    self.algorithm, district_code, metric_name,
                    row[first_col], means[first_col], None,
                    severity_from_iforest_score(score),
                    {"anomaly_score": score, "index": data.index[pos],
                     "features": {c: float(row[c]) for c in data.columns}},
                )
            )
        return results


class CUSUMDetector:
    algorithm = "cusum"

    def __init__(self, drift_threshold_sigma: float = 5.0) -> None:
        self.drift_threshold_sigma = drift_threshold_sigma

    def detect(
        self,
        series: pd.Series,
        district_code: str = "unknown",
        metric_name: str = "value",
    ) -> list[AnomalyResult]:
        values = pd.Series(series).dropna().astype(float).reset_index(drop=True)
        if len(values) < 3:
            return []
        mean = float(values.mean())
        std = float(values.std(ddof=1))
        if std <= 1e-12:
            return []
        cumsum = (values - mean).cumsum()
        limit = self.drift_threshold_sigma * std
        exceeded = np.where(cumsum.abs() > limit)[0]
        if len(exceeded) == 0:
            return []
        pos = int(exceeded[0])  # first change point
        ratio = abs(float(cumsum.iloc[pos])) / std
        return [
            _make_result(
                self.algorithm, district_code, metric_name,
                values.iloc[pos], mean, float(cumsum.iloc[pos]) / std,
                severity_from_sigma(ratio / max(self.drift_threshold_sigma, 1e-9) * 2.0),
                {"cusum": float(cumsum.iloc[pos]), "limit": limit, "index": pos,
                 "drift_threshold_sigma": self.drift_threshold_sigma},
            )
        ]


class BollingerDetector:
    algorithm = "bollinger"

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        self.window = window
        self.num_std = num_std

    def detect(
        self,
        series: pd.Series,
        district_code: str = "unknown",
        metric_name: str = "value",
    ) -> list[AnomalyResult]:
        values = pd.Series(series).dropna().astype(float).reset_index(drop=True)
        if len(values) <= self.window:
            return []
        # Bands from the preceding window so a point never inflates its own band.
        sma = values.rolling(self.window).mean().shift(1)
        std = values.rolling(self.window).std(ddof=1).shift(1)
        results: list[AnomalyResult] = []
        for i in range(self.window, len(values)):
            mean = float(sma.iloc[i])
            s = _safe_std(float(std.iloc[i]), mean)
            z = (float(values.iloc[i]) - mean) / s
            if abs(z) > self.num_std:
                results.append(
                    _make_result(
                        self.algorithm, district_code, metric_name,
                        values.iloc[i], mean, z, severity_from_sigma(z),
                        {"upper_band": mean + self.num_std * s,
                         "lower_band": mean - self.num_std * s,
                         "window": self.window, "index": i},
                    )
                )
        return results


class AnomalyEngine:
    """Runs detectors over TimescaleDB series; tracks noisy-detector suppression."""

    def __init__(self, timescale_svc: Any, detectors: list) -> None:
        self.timescale = timescale_svc
        self.detectors = detectors
        self.suppressed: set[str] = set()

    async def _fetch_series(self, district_code: str, metric: str) -> pd.Series:
        # Placeholder query pattern (project convention).
        rows = await self.timescale.execute(
            "SELECT time, value FROM ts_market_metrics "
            "WHERE district_code = $1 AND metric_name = $2 "
            "ORDER BY time ASC",
            district_code, metric,
        )
        if not rows:
            return pd.Series(dtype=float)
        return pd.Series([float(r["value"]) for r in rows])

    async def scan_district(self, district_code: str) -> list[AnomalyResult]:
        results: list[AnomalyResult] = []
        frames: dict[str, pd.Series] = {}
        for metric in MONITORED_METRICS:
            series = await self._fetch_series(district_code, metric)
            if series.empty:
                continue
            frames[metric] = series
            for det in self.detectors:
                if det.algorithm in self.suppressed or det.algorithm == "isolation_forest":
                    continue
                results.extend(det.detect(series, district_code, metric))
        for det in self.detectors:
            if det.algorithm == "isolation_forest" and det.algorithm not in self.suppressed \
                    and len(frames) >= 2:
                df = pd.DataFrame(frames).dropna()
                if not df.empty:
                    results.extend(det.detect(df, district_code, "multivariate"))
        return results

    async def scan_all(self) -> dict[str, list[AnomalyResult]]:
        rows = await self.timescale.execute(
            "SELECT DISTINCT district_code FROM ts_market_metrics"
        )
        out: dict[str, list[AnomalyResult]] = {}
        for row in rows:
            code = row["district_code"]
            found = await self.scan_district(code)
            if found:
                out[code] = found
        return out

    async def get_fp_rate(self, algorithm: str, days: int = 30) -> float:
        rows = await self.timescale.execute(
            "SELECT COUNT(*) FILTER (WHERE is_false_positive) AS fp, COUNT(*) AS total "
            "FROM ts_anomaly_detections "
            "WHERE algorithm = $1 AND detected_at > NOW() - make_interval(days => $2)",
            algorithm, days,
        )
        if not rows:
            return 0.0
        total = rows[0].get("total", 0) or 0
        if total == 0:
            return 0.0
        return float(rows[0].get("fp", 0) or 0) / float(total)

    async def suppress_if_noisy(self, algorithm: str) -> bool:
        rate = await self.get_fp_rate(algorithm)
        if rate > FP_SUPPRESSION_THRESHOLD:
            self.suppressed.add(algorithm)
            logger.warning("Suppressed noisy detector %s (FP rate %.2f)", algorithm, rate)
            return True
        return False
