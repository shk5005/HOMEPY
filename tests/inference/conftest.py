import pytest


class _MockBase:
    """Canned responses keyed by query substring.

    ``set_response(rows)`` overrides every query; ``set_response_for(sub, rows)``
    overrides one factor's query. Each factor query contains a ``factor:<name>`` tag.
    """

    def __init__(self, responses: dict[str, list]):
        self.responses = dict(responses)
        self._override: list | None = None
        self.calls: list[str] = []
        self.call_args: list[tuple] = []

    def set_response(self, rows: list) -> None:
        self._override = rows

    def set_response_for(self, substring: str, rows: list) -> None:
        self.responses[substring] = rows

    def _lookup(self, query: str, args: tuple = ()) -> list:
        self.calls.append(query)
        self.call_args.append(args)
        if self._override is not None:
            return self._override
        for sub, rows in self.responses.items():
            if sub in query:
                return rows
        return []


class MockTypeDBService(_MockBase):
    """Synchronous, like the real TypeDBService."""

    def execute_read(self, db: str, query: str, infer: bool = False) -> list[dict]:
        return self._lookup(query)


class MockTimescaleService(_MockBase):
    """Async, like the real TimescaleService."""

    async def execute(self, query: str, *args):
        return self._lookup(query, args)


TYPEDB_DEFAULTS = {
    "factor:valuation_gap": [{"price_per_sqm": 17_000_000, "district_avg_price": 20_000_000}],
    "factor:transport_access": [{"nearest_station_m": 450, "line_count": 2}],
    "factor:development_upside": [{"stage_weight": 0.5}, {"stage_weight": 0.8}],
    "factor:regulation_impact": [{"severity": 1}],
    "factor:tax_burden": [{"effective_tax_rate": 5.0}],
}

TIMESCALE_DEFAULTS = {
    "factor:price_momentum": [{"price_change_pct_12m": 4.0}],
    "factor:jeonse_ratio_trend": [{"jeonse_ratio_change_pp": 2.0, "jeonse_ratio": 62.0}],
    "factor:interest_rate_cycle": [{"rate_change_bp_6m": -20}],
    "factor:liquidity_trend": [{"volume_change_pct": 10.0}],
    "factor:supply_demand_gap": [{"demand_households": 12000, "supply_units": 9000}],
    "factor:unsold_risk": [{"unsold_ratio_pct": 2.0}],
    "factor:migration_momentum": [{"net_migration_pct": 0.3}],
    "factor:cycle_position": [{"phase": "recovery"}],
    "factor:sentiment_composite": [
        {"sentiment_divergence": 0.2, "fear_greed_index": 55, "search_trend_change_pct": 8.0}
    ],
}


@pytest.fixture
def mock_typedb():
    return MockTypeDBService(TYPEDB_DEFAULTS)


@pytest.fixture
def mock_timescale():
    return MockTimescaleService(TIMESCALE_DEFAULTS)


# ---- Simulator fixtures -------------------------------------------------
import copy
from datetime import datetime, timezone

from homepy.inference.scorer import FACTOR_WEIGHTS, FactorScore, InvestmentScore, grade_for, minmax
from homepy.inference.simulator import FACTOR_RANGES

MOCK_RAW_VALUES = {
    "supply_demand_gap": 25.0,
    "valuation_gap": 15.0,
    "interest_rate_cycle": -20.0,
    "transport_access": 450.0,
    "price_momentum": 4.0,
}


class MockInvestmentScorer:
    """Returns a configurable InvestmentScore; hands out a fresh copy per call.

    ``overrides`` maps factor name -> raw value. Factors with known ranges are
    normalized like the real scorer, others get 50. Total is the weighted sum,
    so changing a raw value changes total_score predictably.
    """

    def __init__(self, overrides: dict[str, float] | None = None):
        self.raw = dict(MOCK_RAW_VALUES)
        if overrides:
            self.raw.update(overrides)
        self.calls: list[str] = []
        self.missing_factors = 0

    def set_sparse_data(self, missing_factors: int) -> None:
        """Mark the first N factors as having no data in their evidence."""
        self.missing_factors = missing_factors

    async def score(self, complex_id: str) -> InvestmentScore:
        self.calls.append(complex_id)
        factors = []
        for i, (name, w) in enumerate(FACTOR_WEIGHTS.items()):
            if name in FACTOR_RANGES:
                lo, hi, inv = FACTOR_RANGES[name]
                raw = self.raw.get(name, (lo + hi) / 2)
                norm = minmax(raw, lo, hi, invert=inv)
            else:
                raw, norm = 0.0, 50.0
            ev = f"no data for {name}" if i < self.missing_factors else f"mock {name}"
            factors.append(FactorScore(name, raw, norm, w, norm * w, [ev]))
        total = round(sum(f.weighted_score for f in factors), 4)
        return copy.deepcopy(
            InvestmentScore(complex_id, total, grade_for(total), factors, datetime.now(timezone.utc))
        )


@pytest.fixture
def mock_scorer():
    return MockInvestmentScorer()
