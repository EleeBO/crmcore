"""Evaluation pipeline runner — extracted from orchestrator (Task 2.1, H3).

This module contains the full evaluation flow that was previously inlined
in PipelineOrchestrator._run_evaluation(). It addresses the H3 finding
(feature envy) by separating evaluation logic from real-time hint generation.

Direct dependency: AudioBuffer (from pipeline/audio_buffer.py) is a concrete
data holder, not an infrastructure service. This coupling is accepted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from backend.logger import logger
from backend.pipeline.audio_buffer import AudioBuffer
from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, EvaluationConfig
from backend.pipeline.evaluator import (
    EvalParseFailedError,
    evaluate_call,
    generate_follow_up,
)
from backend.pipeline.evaluator_llm import (
    EvalLLMTimeoutError,
    EvalLLMUnavailableError,
    EvaluatorLLMClient,
)
from backend.pipeline.post_call import PostCallProcessor
from backend.pipeline.types import call_analytics_from_wire_json
from backend.pipeline.yandex_async import YandexAsyncRecognizer
from backend.storage.keys import (
    EVAL_TTL,
    eval_analytics,
    eval_config,
    eval_result,
    eval_transcript,
)


class EvaluationRunner:
    """Run the full post-call evaluation pipeline.

    Receives all dependencies via constructor (DI). Does NOT call
    get_settings() — the caller passes enable_post_call_diarization
    and yandex_api_key explicitly.
    """

    def __init__(
        self,
        session_id: str,
        eval_api_key: str,
        scenario_text: str,
        redis: Any | None,
        *,
        enable_post_call_diarization: bool = False,
        yandex_api_key: str = "",
    ) -> None:
        self._session_id = session_id
        self._eval_api_key = eval_api_key
        self._scenario_text = scenario_text
        self._redis = redis
        self._enable_post_call_diarization = enable_post_call_diarization
        self._yandex_api_key = yandex_api_key

    async def run(
        self,
        ws: Any,
        eval_token: str,
        audio_buffer: AudioBuffer | None = None,
    ) -> None:
        """Execute the full evaluation pipeline.

        Steps:
        1. Post-call diarization (best-effort, if enabled)
        2. Load transcript from Redis
        3. Load evaluation config
        4. Call evaluate_call()
        5. Store result in Redis
        6. Notify client via WebSocket
        """
        logger.info(f"Evaluation started for session {self._session_id}")

        # None guard: if Redis is unavailable, notify and bail out
        if self._redis is None:
            logger.warning("Redis unavailable — cannot run evaluation")
            with contextlib.suppress(Exception):
                await ws.send_json(
                    {
                        "type": "evaluation_error",
                        "session_id": self._session_id,
                        "code": "EVAL_NO_REDIS",
                        "message": "Redis недоступен для оценки",
                    }
                )
            return

        error_code = "EVAL_INTERNAL_ERROR"

        # STEP A: Post-call diarization (best-effort)
        analytics = await self._run_diarization(audio_buffer)
        logger.debug(f"Diarization result: {'has analytics' if analytics else 'None'}")

        # STEP B: Load analytics from Redis if diarization didn't produce any
        if analytics is None:
            analytics = await self._load_analytics_from_redis()
            logger.debug(
                f"Analytics from Redis: {'has analytics' if analytics else 'None'}"
            )

        try:
            # Load transcript from eval-specific key
            transcript_key = eval_transcript(self._session_id)
            transcript_raw: list[bytes] = await self._redis.lrange(
                transcript_key,
                0,
                3999,
            )
            logger.info(
                f"Loaded transcript: {len(transcript_raw)} entries "
                f"from key={transcript_key}"
            )
            if not transcript_raw:
                logger.warning(
                    f"Empty transcript for session {self._session_id} — cannot evaluate"
                )
                with contextlib.suppress(Exception):
                    await ws.send_json(
                        {
                            "type": "evaluation_error",
                            "session_id": self._session_id,
                            "code": "EVAL_EMPTY_TRANSCRIPT",
                            "message": "Транскрипт пуст",
                        }
                    )
                return

            # Load config
            raw_config = await self._redis.get(eval_config())
            if raw_config:
                config = EvaluationConfig.model_validate(json.loads(raw_config))
            else:
                config = DEFAULT_CONFIG

            # Get briefing from scenario
            briefing = self._scenario_text or ""

            # Use API key passed at construction time
            eval_llm = EvaluatorLLMClient(api_key=self._eval_api_key)
            follow_up_llm = EvaluatorLLMClient(api_key=self._eval_api_key)

            logger.info(
                f"Starting parallel evaluation: "
                f"transcript={len(transcript_raw)}, "
                f"briefing={len(briefing)}, "
                f"criteria={len(config.criteria)}"
            )

            # ── Parallel execution: follow-up (fast) + evaluation (slow) ──

            async def _follow_up_and_notify() -> Any:
                """Generate follow-up and send immediately via WS."""
                try:
                    fu_result = await generate_follow_up(
                        llm_client=follow_up_llm,
                        transcript_raw=transcript_raw,
                        briefing=briefing,
                    )
                    logger.info("Follow-up generated, sending via WS")
                    fu_msg = {
                        "type": "follow_up_ready",
                        "session_id": self._session_id,
                        "follow_up_email": (fu_result.follow_up_email.model_dump()),
                        "crm_note": (fu_result.crm_note.model_dump()),
                    }
                    with contextlib.suppress(Exception):
                        await ws.send_json(fu_msg)
                    return fu_result
                except Exception as fu_exc:
                    logger.warning(f"Follow-up generation failed: {fu_exc!r}")
                    return None

            follow_up_task = asyncio.create_task(_follow_up_and_notify())

            result = await evaluate_call(
                llm_client=eval_llm,
                transcript_raw=transcript_raw,
                config=config,
                briefing=briefing,
                analytics=analytics,
            )

            # Collect follow-up result and merge into evaluation
            follow_up = await follow_up_task
            if follow_up is not None:
                result.follow_up_email = follow_up.follow_up_email
                result.crm_note = follow_up.crm_note

            logger.info(
                f"Evaluation complete: overall_score={result.overall_score}, "
                f"verdict={result.verdict}, "
                f"has_email={result.follow_up_email is not None}, "
                f"has_crm_note={result.crm_note is not None}"
            )

            # Save result to Redis
            result_json = result.model_dump_json()
            await self._redis.set(
                eval_result(self._session_id),
                result_json,
                ex=EVAL_TTL,
            )
            logger.debug(
                f"Evaluation result saved to Redis: {eval_result(self._session_id)}"
            )

            # Send to client
            analytics_payload = self._build_analytics_payload(analytics)

            # Include diarized transcript (with timestamps if available)
            transcript_entries = self._parse_transcript(transcript_raw)

            msg: dict[str, Any] = {
                "type": "evaluation_result",
                "session_id": self._session_id,
                "eval_token": eval_token,
                "evaluation": result.model_dump(),
            }
            if analytics_payload is not None:
                msg["analytics"] = analytics_payload
            if transcript_entries:
                msg["transcript"] = transcript_entries

            try:
                await ws.send_json(msg)
                logger.info(
                    f"Evaluation result sent via WS for session {self._session_id}"
                )
            except Exception as ws_exc:
                logger.warning(f"WS send failed (result saved to Redis): {ws_exc!r}")
            return  # success — skip error sending below

        except EvalLLMTimeoutError:
            error_code = "EVAL_LLM_TIMEOUT"
        except EvalLLMUnavailableError:
            error_code = "EVAL_LLM_UNAVAILABLE"
        except EvalParseFailedError:
            error_code = "EVAL_PARSE_FAILED"
        except Exception:
            error_code = "EVAL_INTERNAL_ERROR"

        logger.exception(
            f"Evaluation failed ({error_code}) for session {self._session_id}"
        )
        with contextlib.suppress(Exception):
            await ws.send_json(
                {
                    "type": "evaluation_error",
                    "session_id": self._session_id,
                    "code": error_code,
                    "message": "Не удалось оценить звонок",
                }
            )

    # ── Private helpers ───────────────────────────────────────────────────

    async def _run_diarization(self, audio_buffer: AudioBuffer | None) -> Any | None:
        """Run post-call diarization if enabled and buffer provided."""
        if audio_buffer is None:
            return None

        try:
            if self._enable_post_call_diarization and self._yandex_api_key:
                recognizer = YandexAsyncRecognizer(
                    api_key=self._yandex_api_key,
                )
                processor = PostCallProcessor(
                    recognizer=recognizer,
                    redis=self._redis,
                    session_id=self._session_id,
                )
                analytics = await processor.process(audio_buffer)
                if analytics:
                    ratio = analytics.rep_talk_ratio
                    logger.info(
                        f"Post-call diarization complete: talk_ratio={ratio:.2f}"
                    )
                return analytics
            else:
                audio_buffer.clear()
                return None
        except Exception as exc:
            logger.exception(f"Post-call diarization failed: {exc!r}")
            if audio_buffer is not None:
                audio_buffer.clear()
            return None

    async def _load_analytics_from_redis(self) -> Any | None:
        """Try to load pre-computed analytics from Redis."""
        try:
            raw_analytics = await self._redis.get(
                eval_analytics(self._session_id),
            )
            if raw_analytics:
                data = (
                    raw_analytics.decode()
                    if isinstance(raw_analytics, bytes)
                    else raw_analytics
                )
                return call_analytics_from_wire_json(data)
        except Exception as exc:
            logger.warning(f"Failed to load analytics from Redis: {exc!r}")
        return None

    @staticmethod
    def _parse_transcript(raw_entries: list[bytes]) -> list[dict[str, Any]]:
        """Parse Redis transcript entries into dicts for the WS message."""
        result: list[dict[str, Any]] = []
        for entry in raw_entries:
            try:
                text = entry.decode() if isinstance(entry, bytes) else entry
                data = json.loads(text)
                result.append(data)
            except Exception:
                continue
        return result

    @staticmethod
    def _build_analytics_payload(analytics: Any | None) -> dict[str, Any] | None:
        """Build analytics dict for WS message, or None if no analytics."""
        if analytics is None:
            return None
        return {
            "total_duration_s": analytics.total_duration_s,
            "rep_talk_ratio": analytics.rep_talk_ratio,
            "rep_talk_time_s": analytics.rep_talk_time_s,
            "client_talk_time_s": analytics.client_talk_time_s,
            "rep_speech_rate_wpm": analytics.rep_speech_rate_wpm,
            "client_speech_rate_wpm": analytics.client_speech_rate_wpm,
            "interruptions_by_rep": analytics.interruptions_by_rep,
            "interruptions_by_client": analytics.interruptions_by_client,
            "avg_rep_pause_before_response_s": (
                analytics.avg_rep_pause_before_response_s
            ),
            "rep_word_count": analytics.rep_word_count,
            "client_word_count": analytics.client_word_count,
        }
