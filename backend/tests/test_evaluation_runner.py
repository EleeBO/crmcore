"""Tests for EvaluationRunner — extracted evaluation logic (Task 2.1)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.evaluation_runner import EvaluationRunner

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis with common defaults."""
    r = AsyncMock()
    r.lrange = AsyncMock(return_value=[
        json.dumps({"speaker": "rep", "text": "Добрый день"}).encode(),
        json.dumps({"speaker": "client", "text": "Здравствуйте"}).encode(),
    ])
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    return r


@pytest.fixture
def mock_ws() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def runner(mock_redis: AsyncMock) -> EvaluationRunner:
    return EvaluationRunner(
        session_id="sess-1",
        eval_api_key="test-key",
        scenario_text="some scenario",
        redis=mock_redis,
        enable_post_call_diarization=False,
        yandex_api_key="",
    )


# ── Test: constructor ─────────────────────────────────────────────────────


class TestEvaluationRunnerInit:
    def test_stores_session_id(self, runner: EvaluationRunner) -> None:
        assert runner._session_id == "sess-1"

    def test_stores_eval_api_key(self, runner: EvaluationRunner) -> None:
        assert runner._eval_api_key == "test-key"

    def test_stores_scenario_text(self, runner: EvaluationRunner) -> None:
        assert runner._scenario_text == "some scenario"

    def test_stores_diarization_settings(self) -> None:
        r = EvaluationRunner(
            session_id="s",
            eval_api_key="k",
            scenario_text="",
            redis=AsyncMock(),
            enable_post_call_diarization=True,
            yandex_api_key="yandex-key",
        )
        assert r._enable_post_call_diarization is True
        assert r._yandex_api_key == "yandex-key"


# ── Test: None guard ─────────────────────────────────────────────────────


class TestEvaluationRunnerNoneGuard:
    @pytest.mark.asyncio
    async def test_run_with_none_redis_sends_error(self, mock_ws: AsyncMock) -> None:
        """When redis is None, run() sends evaluation_error and returns early."""
        runner = EvaluationRunner(
            session_id="s",
            eval_api_key="k",
            scenario_text="",
            redis=None,
            enable_post_call_diarization=False,
            yandex_api_key="",
        )
        await runner.run(mock_ws, "tok")
        mock_ws.send_json.assert_called_once()
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "evaluation_error"
        assert "EVAL_NO_REDIS" in msg["code"]


# ── Test: diarization step ───────────────────────────────────────────────


class TestEvaluationRunnerDiarization:
    @pytest.mark.asyncio
    async def test_skips_diarization_when_disabled(
        self, runner: EvaluationRunner, mock_ws: AsyncMock
    ) -> None:
        """When enable_post_call_diarization=False, PostCallProcessor is not called."""
        with patch(
            "backend.pipeline.evaluation_runner.PostCallProcessor"
        ) as MockPCP, patch(
            "backend.pipeline.evaluation_runner.evaluate_call"
        ) as mock_eval:
            from backend.pipeline.evaluation_schemas import CallEvaluation

            mock_eval.return_value = CallEvaluation(
                call_summary="ok",
                criteria_results=[],
                overall_score=5.0,
                verdict="satisfactory",
                strengths=["a", "b"],
                growth_areas=["a", "b"],
                action_plan=["a", "b", "c"],
            )
            mock_buffer = MagicMock()
            await runner.run(mock_ws, "tok", audio_buffer=mock_buffer)
            MockPCP.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_diarization_when_enabled_with_buffer(
        self, mock_redis: AsyncMock, mock_ws: AsyncMock
    ) -> None:
        """When enabled and buffer provided, PostCallProcessor is invoked."""
        runner = EvaluationRunner(
            session_id="sess",
            eval_api_key="k",
            scenario_text="",
            redis=mock_redis,
            enable_post_call_diarization=True,
            yandex_api_key="yandex-key",
        )
        mock_buffer = MagicMock()
        mock_buffer.clear = MagicMock()

        with patch(
            "backend.pipeline.evaluation_runner.YandexAsyncRecognizer"
        ), patch(
            "backend.pipeline.evaluation_runner.PostCallProcessor"
        ) as MockPCP, patch(
            "backend.pipeline.evaluation_runner.evaluate_call"
        ) as mock_eval:
            from backend.pipeline.evaluation_schemas import CallEvaluation

            mock_processor = AsyncMock()
            mock_processor.process = AsyncMock(return_value=None)
            MockPCP.return_value = mock_processor
            mock_eval.return_value = CallEvaluation(
                call_summary="ok",
                criteria_results=[],
                overall_score=5.0,
                verdict="satisfactory",
                strengths=["a", "b"],
                growth_areas=["a", "b"],
                action_plan=["a", "b", "c"],
            )
            await runner.run(mock_ws, "tok", audio_buffer=mock_buffer)
            MockPCP.assert_called_once()


# ── Test: transcript loading ─────────────────────────────────────────────


class TestEvaluationRunnerTranscript:
    @pytest.mark.asyncio
    async def test_empty_transcript_sends_error(
        self, mock_ws: AsyncMock
    ) -> None:
        """When transcript is empty, sends EVAL_EMPTY_TRANSCRIPT error."""
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[])
        mock_redis.get = AsyncMock(return_value=None)

        runner = EvaluationRunner(
            session_id="s",
            eval_api_key="k",
            scenario_text="",
            redis=mock_redis,
            enable_post_call_diarization=False,
            yandex_api_key="",
        )
        await runner.run(mock_ws, "tok")
        msg = mock_ws.send_json.call_args[0][0]
        assert msg["type"] == "evaluation_error"
        assert msg["code"] == "EVAL_EMPTY_TRANSCRIPT"


# ── Test: full success path ──────────────────────────────────────────────


class TestEvaluationRunnerSuccess:
    @pytest.mark.asyncio
    async def test_full_run_sends_evaluation_result(
        self,
        runner: EvaluationRunner,
        mock_redis: AsyncMock,
        mock_ws: AsyncMock,
    ) -> None:
        """Full run calls evaluate_call and sends evaluation_result via WS."""
        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call"
        ) as mock_eval:
            from backend.pipeline.evaluation_schemas import CallEvaluation

            mock_eval.return_value = CallEvaluation(
                call_summary="ok",
                criteria_results=[],
                overall_score=7.0,
                verdict="good",
                strengths=["a", "b"],
                growth_areas=["a", "b"],
                action_plan=["a", "b", "c"],
            )
            await runner.run(mock_ws, "tok-1")

        # Check evaluation_result WS message
        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_result"
        ]
        assert len(sent) == 1
        msg = sent[0]
        assert msg["eval_token"] == "tok-1"
        assert msg["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_stores_result_in_redis(
        self,
        runner: EvaluationRunner,
        mock_redis: AsyncMock,
        mock_ws: AsyncMock,
    ) -> None:
        """run() stores evaluation result in Redis with eval: key."""
        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call"
        ) as mock_eval:
            from backend.pipeline.evaluation_schemas import CallEvaluation

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

        # Check redis.set was called with eval:sess-1 key
        set_calls = mock_redis.set.call_args_list
        eval_keys = [c for c in set_calls if "eval:sess-1" in str(c)]
        assert len(eval_keys) >= 1


# ── Test: error handling ─────────────────────────────────────────────────


class TestEvaluationRunnerErrors:
    @pytest.mark.asyncio
    async def test_eval_timeout_sends_error_code(
        self,
        runner: EvaluationRunner,
        mock_ws: AsyncMock,
    ) -> None:
        """EvalLLMTimeoutError results in EVAL_LLM_TIMEOUT message."""
        from backend.pipeline.evaluator_llm import EvalLLMTimeoutError

        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call",
            side_effect=EvalLLMTimeoutError("timeout"),
        ):
            await runner.run(mock_ws, "tok")

        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_error"
        ]
        assert len(sent) == 1
        assert sent[0]["code"] == "EVAL_LLM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_eval_unavailable_sends_error_code(
        self,
        runner: EvaluationRunner,
        mock_ws: AsyncMock,
    ) -> None:
        """EvalLLMUnavailableError results in EVAL_LLM_UNAVAILABLE message."""
        from backend.pipeline.evaluator_llm import EvalLLMUnavailableError

        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call",
            side_effect=EvalLLMUnavailableError("down"),
        ):
            await runner.run(mock_ws, "tok")

        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_error"
        ]
        assert len(sent) == 1
        assert sent[0]["code"] == "EVAL_LLM_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_eval_parse_failed_sends_error_code(
        self,
        runner: EvaluationRunner,
        mock_ws: AsyncMock,
    ) -> None:
        """EvalParseFailedError results in EVAL_PARSE_FAILED message."""
        from backend.pipeline.evaluator import EvalParseFailedError

        with patch(
            "backend.pipeline.evaluation_runner.evaluate_call",
            side_effect=EvalParseFailedError("bad json"),
        ):
            await runner.run(mock_ws, "tok")

        sent = [
            c.args[0]
            for c in mock_ws.send_json.call_args_list
            if isinstance(c.args[0], dict)
            and c.args[0].get("type") == "evaluation_error"
        ]
        assert len(sent) == 1
        assert sent[0]["code"] == "EVAL_PARSE_FAILED"


# ── Test: no get_settings() call ─────────────────────────────────────────


class TestEvaluationRunnerDI:
    def test_no_get_settings_import(self) -> None:
        """evaluation_runner.py must NOT import or call get_settings."""
        import ast
        from pathlib import Path

        src = Path(__file__).parent.parent / "pipeline" / "evaluation_runner.py"
        tree = ast.parse(src.read_text())
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.names:
                for alias in node.names:
                    names.append(alias.name)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "get_settings":
                    names.append("get_settings")
        assert "get_settings" not in names, (
            "EvaluationRunner must not import/call get_settings() — "
            "settings are passed via constructor (DI)"
        )
