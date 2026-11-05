import pytest


class MockTypeDB:
    def __init__(self):
        self.results: dict[str, list[dict]] = {}
        self.queries: list[str] = []

    def set_query_result(self, key, result):
        self.results[key] = result

    def execute_read(self, db, query, infer=False):
        self.queries.append(query)
        for key, res in self.results.items():
            if key in query:
                return res
        return []


class MockTimescale:
    def __init__(self):
        self.executed_queries: list[str] = []
        self.executed_args: list[tuple] = []

    async def execute(self, query, *args):
        self.executed_queries.append(query)
        self.executed_args.append(args)
        if "FROM ts_real_trade" in query and "AVG(price_krw)" in query:
            return [{"month": i, "avg_price": 1_000_000_000 + 10_000_000 * (12 - i)} for i in range(12)]
        if "COUNT(*)" in query:
            return [{"month": 1, "volume": 12.0}, {"month": 0, "volume": 10.0}]
        if "FROM ts_interest_rate" in query:
            return [{"ts": i, "base_rate": 3.0 + 0.25 * i} for i in range(4)]
        if "jeonse_ratio" in query:
            return [{"ts": i, "jeonse_ratio": 60.0 - i} for i in range(6)]
        if "search_trend" in query:
            return [{"ts": i, "search_trend": 50.0 + (i % 5)} for i in range(30)]
        return []


@pytest.fixture
def mock_typedb():
    return MockTypeDB()


@pytest.fixture
def mock_timescale():
    return MockTimescale()
