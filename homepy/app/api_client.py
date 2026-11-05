"""Thin async httpx wrapper over the HOMEPY FastAPI service."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

API_PREFIX = "/api/v1"


class ApiError(RuntimeError):
    """Raised when the API is unreachable or returns an error status."""


class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000", *,
                 timeout: float = 10.0, retries: int = 2, backoff: float = 0.3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    async def _request(self, method: str, path: str, json: Any = None) -> Any:
        url = f"{self.base_url}{API_PREFIX}{path}"
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(method, url, json=json)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError as exc:
                    raise ApiError(f"Non-JSON response from {url}") from exc
            except httpx.HTTPStatusError as exc:
                raise ApiError(f"{exc.response.status_code} from {url}: {exc.response.text[:200]}") from exc
            except httpx.TransportError as exc:  # connect/timeout/network: retry
                last = exc
                if attempt < self.retries:
                    await asyncio.sleep(self.backoff * (2 ** attempt))
        raise ApiError(f"API unreachable at {self.base_url}: {last!r}") from last

    # market
    async def get_macro_summary(self) -> dict:
        return await self._request("GET", "/market/macro/summary")

    async def get_cycle(self, district_code: str) -> dict:
        return await self._request("GET", f"/market/cycle/{district_code}")

    # analysis
    async def post_score(self, complex_ids: list[str]) -> list[dict]:
        return await self._request("POST", "/analysis/score", {"complex_ids": complex_ids})

    async def post_verdict(self, complex_id: str) -> dict:
        return await self._request("POST", f"/analysis/verdict/{complex_id}")

    # simulation
    async def post_scenario(self, complex_id: str) -> dict:
        return await self._request("POST", f"/simulation/scenario/{complex_id}")

    async def post_tax(self, payload: dict) -> dict:
        return await self._request("POST", "/simulation/tax", payload)

    async def post_loan(self, payload: dict) -> dict:
        return await self._request("POST", "/simulation/loan", payload)

    async def post_policy(self, policy_type: str, parameters: dict) -> dict:
        return await self._request("POST", "/simulation/policy",
                                   {"policy_type": policy_type, "parameters": parameters})

    async def post_policy_backtest(self, policy_name: str, policy_date: str,
                                   changes: dict | None = None) -> dict:
        return await self._request("POST", "/simulation/policy/backtest", {
            "policy_name": policy_name, "policy_date": policy_date, "changes": changes or {}})

    # nlp / reports
    async def post_nlp_query(self, query: str) -> dict:
        return await self._request("POST", "/nlp/query", {"query": query})

    async def post_report_generate(self, complex_id: str, fmt: str = "html",
                                   include_debate: bool = False) -> bytes:
        """Return raw report bytes (HTML or PDF)."""
        url = f"{self.base_url}{API_PREFIX}/reports/generate"
        payload = {"complex_id": complex_id, "format": fmt, "include_debate": include_debate}
        try:
            async with httpx.AsyncClient(timeout=max(self.timeout, 120.0)) as client:
                resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ApiError(f"{exc.response.status_code} from {url}: {exc.response.text[:200]}") from exc
        except httpx.TransportError as exc:
            raise ApiError(f"API unreachable at {self.base_url}: {exc!r}") from exc
        return resp.content

    async def post_debate(self, complex_id: str) -> dict:
        return await self._request("POST", "/reports/debate", {"complex_id": complex_id})

    # ontology
    async def get_graph(self, complex_id: str) -> dict:
        return await self._request("GET", f"/ontology/graph/{complex_id}")

    async def get_entities(self, entity_type: str, limit: int = 50) -> dict:
        return await self._request("GET", f"/ontology/entity/{entity_type}?limit={limit}")

    # portfolio
    async def post_rank(self, complex_ids: list[str]) -> list[dict]:
        return await self._request("POST", "/portfolio/rank", {"complex_ids": complex_ids})

    # pipeline
    async def get_pipeline_status(self) -> dict:
        return await self._request("GET", "/pipeline/status")

    # verification
    async def get_verification_accuracy(self) -> dict:
        return await self._request("GET", "/pipeline/verification/accuracy")

    async def get_verification_proposals(self) -> list[dict]:
        return await self._request("GET", "/pipeline/verification/proposals")

    async def approve_proposal(self, proposal_id: str) -> dict:
        return await self._request("POST", f"/pipeline/verification/proposals/{proposal_id}/approve")

    async def get_verification_health(self) -> dict:
        return await self._request("GET", "/pipeline/verification/health")

    # monitoring
    async def get_monitoring_anomalies(self, days: int = 7) -> list[dict]:
        return await self._request("GET", f"/pipeline/monitoring/anomalies?days={days}")

    async def get_monitoring_alerts(self, days: int = 7, level: str | None = None) -> list[dict]:
        path = f"/pipeline/monitoring/alerts?days={days}"
        if level:
            path += f"&level={level}"
        return await self._request("GET", path)

    async def get_early_warnings(self) -> list[dict]:
        return await self._request("GET", "/pipeline/monitoring/early-warnings")

    async def get_ha_status(self) -> list[dict]:
        return await self._request("GET", "/pipeline/ha/status")


def run(coro):
    """Run an ApiClient coroutine from synchronous Streamlit code."""
    return asyncio.run(coro)
