"""Tests for the self-healing engine."""
from __future__ import annotations

import json

import pytest

from homepy.verification.self_healer import DEFAULT_POLICIES, SelfHealer


class MockService:
    pass


class MockDeps:
    def __init__(self) -> None:
        self.timescale = MockService()
        self.typedb = MockService()
        self._permanent: set[str] = set()
        self.retry_calls: list[str] = []

    def set_permanent_failure(self, component: str) -> None:
        self._permanent.add(component)

    async def retry(self, component: str) -> bool:
        self.retry_calls.append(component)
        return component not in self._permanent


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def mock_deps() -> MockDeps:
    return MockDeps()


def _healer(deps: MockDeps, path) -> SelfHealer:
    return SelfHealer(
        deps.timescale, deps.typedb, path, retry_fn=deps.retry, sleep_fn=_no_sleep
    )


async def test_api_error_retries_with_backoff(mock_deps, tmp_path):
    healer = _healer(mock_deps, tmp_path / "recovery.jsonl")
    event = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("timeout"))
    assert event.auto_action == "retry"
    assert event.success


async def test_max_retries_escalates_to_human(mock_deps, tmp_path):
    mock_deps.set_permanent_failure("bok_ecos")
    healer = _healer(mock_deps, tmp_path / "recovery.jsonl")
    event = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("down"))
    assert event.human_escalated is True
    assert event.success is False
    assert len(mock_deps.retry_calls) == DEFAULT_POLICIES["api_error"].max_retries


async def test_recovery_log_persists(mock_deps, tmp_path):
    log_path = tmp_path / "recovery.jsonl"
    healer = _healer(mock_deps, log_path)
    await healer.handle_failure("api_error", "test", ConnectionError("test"))
    history = healer.get_recovery_history(hours=1)
    assert len(history) == 1
    assert log_path.exists()
    assert json.loads(log_path.read_text().splitlines()[0])["component"] == "test"


async def test_cooldown_prevents_rapid_retries(mock_deps, tmp_path):
    healer = _healer(mock_deps, tmp_path / "recovery.jsonl")
    await healer.handle_failure("api_error", "bok_ecos", ConnectionError("err"))
    e2 = await healer.handle_failure("api_error", "bok_ecos", ConnectionError("err"))
    assert e2.auto_action == "cooldown_active"
    assert len(mock_deps.retry_calls) == 1


async def test_quality_gate_fail_escalates_immediately(mock_deps, tmp_path):
    healer = _healer(mock_deps, tmp_path / "recovery.jsonl")
    event = await healer.handle_failure("quality_gate_fail", "pipeline", RuntimeError("x"))
    assert event.human_escalated is True
    assert mock_deps.retry_calls == []
