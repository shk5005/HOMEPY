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
