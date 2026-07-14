"""Tests for orchestrator post-call diarization integration."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.audio_buffer import AudioBuffer
from backend.pipeline.post_call import CallAnalytics
from backend.pipeline.types import call_analytics_to_wire_json


def _make_analytics() -> CallAnalytics:
    return CallAnalytics(
        total_duration_s=120.0,
        rep_talk_time_s=50.0,
        client_talk_time_s=60.0,
        rep_talk_ratio=0.45,
        rep_speech_rate_wpm=130,
        client_speech_rate_wpm=110,
        rep_word_count=200,
        client_word_count=180,
        interruptions_by_rep=2,
        interruptions_by_client=1,
        avg_rep_pause_before_response_s=1.3,
    )


class TestOrchestratorOnSessionEndWithDiarization:
    @pytest.mark.asyncio
    async def test_calls_post_call_processor_when_buffer_provided(self) -> None:
        """on_session_end should run diarization before evaluation when buffer given."""
        from backend.pipeline.orchestrator import PipelineOrchestrator

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hello"}).encode()
        ])
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=AsyncMock())

        orch = PipelineOrchestrator(
            ws=mock_ws,
            session_id="test-session",
            llm_client=MagicMock(),
            session_manager=MagicMock(),
            eval_api_key="test-key",
        )

        buf = AudioBuffer()
        buf.append("rep", b"\x00\x00" * 16000)  # 1s
        buf.append("client", b"\x00\x00" * 16000)

        with patch("backend.pipeline.post_call.PostCallProcessor") as MockPCP:
            mock_processor = AsyncMock()
            mock_processor.process = AsyncMock(return_value=None)
            MockPCP.return_value = mock_processor

            await orch.on_session_end("test-session", mock_ws, mock_redis, audio_buffer=buf)

            # Wait for the task to run
            if orch._evaluation_task:
                await asyncio.wait_for(orch._evaluation_task, timeout=5.0)

    @pytest.mark.asyncio
    async def test_skips_diarization_when_buffer_none(self) -> None:
        """on_session_end should skip diarization when buffer is None."""
        from backend.pipeline.orchestrator import PipelineOrchestrator

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hello"}).encode()
        ])
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        orch = PipelineOrchestrator(
            ws=mock_ws,
            session_id="test-session",
            llm_client=MagicMock(),
            session_manager=MagicMock(),
            eval_api_key="test-key",
        )

        with patch("backend.pipeline.post_call.PostCallProcessor") as MockPCP:
            await orch.on_session_end("test-session", mock_ws, mock_redis)
            if orch._evaluation_task:
                await asyncio.wait_for(orch._evaluation_task, timeout=5.0)
            MockPCP.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_message_includes_analytics(self) -> None:
        """WS evaluation_result message includes analytics when present."""
        from backend.pipeline.evaluation_runner import EvaluationRunner
        from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hello"}).encode(),
        ])
        mock_redis.set = AsyncMock()

        analytics = _make_analytics()
        analytics_json = call_analytics_to_wire_json(analytics)
        config_json = DEFAULT_CONFIG.model_dump_json()

        async def _redis_get(key: str):
            if "eval_analytics" in key:
                return analytics_json.encode()
            if "eval_config" in key:
                return config_json.encode()
            return None

        mock_redis.get = AsyncMock(side_effect=_redis_get)

        runner = EvaluationRunner(
            session_id="sess",
            eval_api_key="k",
            scenario_text="",
            redis=mock_redis,
        )

        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call",
        ) as mock_eval:
            from backend.pipeline.evaluator import CallEvaluation

            mock_eval.return_value = CallEvaluation(
                call_summary="ok",
                criteria_results=[],
                overall_score=7.0,
                verdict="good",
                strengths=["a", "b"],
                growth_areas=["a", "b"],
                action_plan=["a", "b", "c"],
            )

            await runner.run(mock_ws, "tok")

        # Find the evaluation_result call
        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_result"
        ]
        assert len(sent) == 1
        msg = sent[0]
        assert "analytics" in msg
        assert msg["analytics"]["rep_talk_ratio"] == 0.45
        assert msg["analytics"]["total_duration_s"] == 120.0

    @pytest.mark.asyncio
    async def test_ws_message_omits_analytics_when_absent(
        self,
    ) -> None:
        """WS evaluation_result omits analytics key when none."""
        from backend.pipeline.evaluation_runner import EvaluationRunner

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hi"}).encode(),
        ])
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        runner = EvaluationRunner(
            session_id="s2",
            eval_api_key="k",
            scenario_text="",
            redis=mock_redis,
        )

        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call",
        ) as mock_eval:
            from backend.pipeline.evaluator import CallEvaluation

            mock_eval.return_value = CallEvaluation(
                call_summary="ok",
                criteria_results=[],
                overall_score=5.0,
                verdict="satisfactory",
                strengths=["a", "b"],
                growth_areas=["a", "b"],
                action_plan=["a", "b", "c"],
            )

            await runner.run(mock_ws, "tok2")

        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_result"
        ]
        assert len(sent) == 1
        assert "analytics" not in sent[0]
