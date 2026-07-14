"""Tests for orchestrator edge cases (Task 3.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.pipeline.orchestrator import PipelineOrchestrator


@pytest.fixture()
def orchestrator() -> PipelineOrchestrator:
    """Minimal PipelineOrchestrator for edge-case tests."""
    return PipelineOrchestrator(
        ws=AsyncMock(),
        session_id="test",
        llm_client=MagicMock(),
        session_manager=MagicMock(),
        eval_api_key="key",
    )


class TestOnSessionEndRedisNone:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_redis_none(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """on_session_end with redis=None returns '' without raising."""
        result = await orchestrator.on_session_end("test", AsyncMock(), None)
        assert result == ""

    @pytest.mark.asyncio
    async def test_no_evaluation_task_when_redis_none(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """on_session_end with redis=None does not create evaluation task."""
        await orchestrator.on_session_end("test", AsyncMock(), None)
        assert orchestrator._evaluation_task is None


class TestBackgroundTasksCleanup:
    def test_background_tasks_initialized_empty(
        self, orchestrator: PipelineOrchestrator
    ) -> None:
        """_background_tasks is initialized as empty set."""
        assert orchestrator._background_tasks == set()


class TestCallSummaryNoneGuard:
    @pytest.mark.asyncio
    async def test_generate_summary_raises_on_redis_none(self) -> None:
        """generate_summary raises ValueError when redis is None."""
        from backend.summarize.call_summary import generate_summary

        with pytest.raises(ValueError, match="Redis unavailable"):
            await generate_summary("s1", None, "key", "model")
