"""Tests for orchestrator evaluation integration (FEAT-004)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.pipeline.orchestrator import PipelineOrchestrator


@pytest.fixture
def orch():
    ws = AsyncMock()
    llm = MagicMock()
    session = AsyncMock()
    return PipelineOrchestrator(
        ws=ws,
        session_id="test-123",
        llm_client=llm,
        session_manager=session,
        eval_api_key="test-key",
    )


def test_evaluation_started_flag_default(orch):
    assert orch._evaluation_started is False
    assert orch._evaluation_task is None


@pytest.mark.asyncio
async def test_on_session_end_sets_flag(orch):
    """on_session_end should set _evaluation_started and create task."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    await orch.on_session_end("test-123", orch._ws, redis)
    assert orch._evaluation_started is True
    assert orch._evaluation_task is not None


@pytest.mark.asyncio
async def test_on_session_end_idempotent(orch):
    """Second call to on_session_end should be a no-op."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    await orch.on_session_end("test-123", orch._ws, redis)
    task1 = orch._evaluation_task
    await orch.on_session_end("test-123", orch._ws, redis)
    task2 = orch._evaluation_task
    assert task1 is task2


@pytest.mark.asyncio
async def test_teardown_does_not_cancel_evaluation(orch):
    """teardown() must NOT cancel _evaluation_task."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    await orch.on_session_end("test-123", orch._ws, redis)
    eval_task = orch._evaluation_task
    await orch.teardown()
    # eval_task should not be cancelled by teardown
    assert eval_task is not None
    assert eval_task not in orch._background_tasks
