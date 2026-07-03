"""Pipeline Orchestrator: STT → Scenario → LLM → streaming hint delivery (FEAT-001)."""

from __future__ import annotations

import asyncio
import contextlib
import secrets as _secrets
import time
from typing import TYPE_CHECKING, Any

from backend.logger import logger
from backend.pipeline.evaluation_runner import EvaluationRunner
from backend.pipeline.llm import HintContext
from backend.pipeline.prompt_formatter import format_scenario_for_hints
from backend.pipeline.protocols import LLMClientProtocol, SessionManagerProtocol
from backend.pipeline.scenario import Scenario
from backend.pipeline.schemas import HintResponseV2
from backend.pipeline.talk_ratio import TalkRatioTracker
from backend.storage.keys import EVAL_TTL
from backend.storage.keys import eval_token as eval_token_key

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from backend.pipeline.stt import Transcript

_HINT_COOLDOWN_S = 8.0  # Minimum gap between hints (seconds)
_HINT_GENERATION_TIMEOUT_S = 20.0  # Max time for LLM to generate a hint


class PipelineOrchestrator:
    """Coordinates the full pipeline for one WebSocket session."""

    def __init__(
        self,
        ws: WebSocket,
        session_id: str,
        llm_client: LLMClientProtocol,
        session_manager: SessionManagerProtocol,
        scenario_text: str = "",
        kb_id: str = "",
        eval_api_key: str = "",
        *,
        enable_post_call_diarization: bool = False,
        yandex_api_key: str = "",
        hint_context_utterances: int = 50,
    ) -> None:
        self._ws = ws
        self._session_id = session_id
        self._llm = llm_client
        self._session = session_manager
        self._scenario_text = scenario_text
        self._formatted_scenario = self._format_scenario(scenario_text)
        self._kb_id = kb_id or session_id
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._last_hint_time: float = 0.0
        self._eval_api_key = eval_api_key
        self._enable_post_call_diarization = enable_post_call_diarization
        self._yandex_api_key = yandex_api_key
        self._hint_context_utterances = hint_context_utterances
        self._evaluation_task: asyncio.Task | None = None
        self._evaluation_started: bool = False
        self._eval_lock = asyncio.Lock()
        self._talk_ratio = TalkRatioTracker()
        self._seen_utterance_ids: set[str] = set()  # dedup final_refinement

    @staticmethod
    def _format_scenario(raw_json: str) -> str:
        """Parse raw scenario JSON and format for LLM prompts."""
        if not raw_json:
            return ""
        try:
            scenario = Scenario.model_validate_json(raw_json)
            return format_scenario_for_hints(scenario)
        except Exception:
            # Fallback: use raw text if parsing fails
            return raw_json

    # ── Public API ─────────────────────────────────────────────────────────

    async def handle_transcript(self, transcript: Transcript) -> None:
        """Forward transcript to extension and route final client speech to pipeline."""
        # Dedup: Yandex sends final + final_refinement with the same utterance_id.
        # Only process the FIRST final per utterance_id; skip the refinement duplicate.
        if transcript.is_final and transcript.utterance_id:
            if transcript.utterance_id in self._seen_utterance_ids:
                logger.debug(
                    "Skipping duplicate final (refinement): utt_id={}",
                    transcript.utterance_id,
                )
                # Still forward to frontend so it can update text (refinement may
                # have better capitalization), but do NOT save or run pipeline again.
                with contextlib.suppress(Exception):
                    await self._ws.send_json(
                        {
                            "type": "transcript",
                            "speaker": transcript.speaker,
                            "text": transcript.text,
                            "is_final": transcript.is_final,
                            "utterance_id": transcript.utterance_id,
                        }
                    )
                return
            self._seen_utterance_ids.add(transcript.utterance_id)

        # Forward every transcript to extension widget
        try:
            await self._ws.send_json(
                {
                    "type": "transcript",
                    "speaker": transcript.speaker,
                    "text": transcript.text,
                    "is_final": transcript.is_final,
                    "utterance_id": transcript.utterance_id,
                }
            )
        except Exception as exc:
            logger.warning("Не удалось переслать транскрипт: {!r}", exc)

        # Update talk ratio tracker (word counts only on final)
        self._talk_ratio.on_utterance(
            transcript.speaker, transcript.text, is_final=transcript.is_final
        )
        # Send talk_ratio on every transcript (interim + final) for responsive UI
        try:
            await self._ws.send_json(
                {"type": "talk_ratio", **self._talk_ratio.get_state()}
            )
        except Exception as exc:
            logger.warning("Failed to send talk_ratio: {!r}", exc)

        # Save utterance and run pipeline only on final transcripts
        if transcript.is_final:
            try:
                await self._session.add_utterance(
                    self._session_id, transcript.speaker, transcript.text
                )
            except Exception as exc:
                logger.warning("Не удалось сохранить реплику: {!r}", exc)
            await self._run_pipeline(transcript.text, transcript.speaker)

    async def teardown(self) -> None:
        """Cancel all in-flight background tasks and await their completion."""
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        if self._background_tasks:
            await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

    async def on_session_end(
        self,
        session_id: str,
        ws: Any,
        redis: Any,
        *,
        audio_buffer: Any | None = None,
    ) -> str:
        """Trigger evaluation as a separate asyncio.Task.

        Returns the eval_token so the caller can include it in
        the ``evaluation_started`` WS message. Returns ``""`` if
        evaluation was already started (idempotent).
        """
        async with self._eval_lock:
            if self._evaluation_started:
                return ""
            self._evaluation_started = True

        # Defense-in-depth: skip evaluation if Redis is unavailable
        if redis is None:
            logger.warning(
                f"Redis unavailable, skipping evaluation for session {session_id}"
            )
            return ""

        # Generate token early so the client can poll the REST API
        # before the evaluation completes.
        eval_token = _secrets.token_urlsafe(16)
        await redis.set(eval_token_key(session_id), eval_token, ex=EVAL_TTL)

        runner = EvaluationRunner(
            session_id=session_id,
            eval_api_key=self._eval_api_key,
            scenario_text=self._scenario_text,
            redis=redis,
            enable_post_call_diarization=self._enable_post_call_diarization,
            yandex_api_key=self._yandex_api_key,
        )
        self._evaluation_task = asyncio.create_task(
            runner.run(ws, eval_token, audio_buffer)
        )
        return eval_token

    # ── Internal pipeline stages ────────────────────────────────────────────

    async def _run_pipeline(self, query: str, speaker: str = "client") -> None:
        """Execute Scenario → LLM → streaming delivery for a final transcript."""
        # Cooldown: skip if last hint was less than 15s ago
        now = time.monotonic()
        elapsed = now - self._last_hint_time
        if elapsed < _HINT_COOLDOWN_S:
            logger.debug(
                f"Cooldown: skipping hint, last was {elapsed:.1f}s ago "
                f"(cooldown={_HINT_COOLDOWN_S:.0f}s)"
            )
            return
        # [FEAT-005] Log pipeline start
        logger.info(f"Пайплайн запущен: session={self._session_id} query={query[:80]}")

        try:
            history = await self._session.get_conversation_history(
                self._session_id,
                limit=self._hint_context_utterances,
                exclude_last=True,
            )
        except Exception:
            history = []

        hint_ctx = HintContext(
            utterance=query,
            speaker=speaker,
            rag_context=[self._formatted_scenario] if self._formatted_scenario else [],
            conversation_history=history,
        )

        # [FEAT-005] Proper error handling instead of suppress
        try:
            await self._generate_hint_silent(hint_ctx)
        except Exception as exc:
            logger.error(
                f"Ошибка пайплайна подсказок: {exc!r} (сессия={self._session_id})"
            )
            try:
                await self._ws.send_json(
                    {
                        "type": "error",
                        "code": "HINT_PIPELINE_FAILED",
                        "message": str(exc)[:200],
                    }
                )
            except Exception as ws_exc:
                logger.debug(f"Could not send error to WS: {ws_exc!r}")

    async def _generate_hint_silent(self, ctx: HintContext) -> None:
        """Generate hint silently with timeout."""
        self._llm._cancel_current()

        try:
            await asyncio.wait_for(
                self._collect_and_send_hint(ctx),
                timeout=_HINT_GENERATION_TIMEOUT_S,
            )
        except TimeoutError:
            logger.warning(
                f"Hint generation timed out after {_HINT_GENERATION_TIMEOUT_S:.0f}s "
                f"(session={self._session_id})"
            )

    async def _collect_and_send_hint(self, ctx: HintContext) -> None:
        """Collect all LLM tokens and send a single hint_end v2."""
        logger.info(
            "Hint generation started (session={}, speaker={})",
            self._session_id,
            ctx.speaker,
        )
        tokens: list[str] = []
        logger.debug(
            f"LLM stream start: speaker={ctx.speaker}, "
            f"utterance={ctx.utterance[:60]!r}, "
            f"rag_len={len(ctx.rag_context)}, "
            f"history_len={len(ctx.conversation_history)}"
        )
        try:
            async for token in self._llm.generate_hint_stream(ctx):
                tokens.append(token)
        except Exception as exc:
            logger.warning(
                f"LLM stream failed after {len(tokens)} tokens: {exc!r} "
                f"(session={self._session_id})"
            )
            if not tokens:
                return

        if not tokens:
            logger.warning(f"LLM returned 0 tokens (session={self._session_id})")
            return

        full_json = "".join(tokens).strip()
        logger.info(
            f"LLM raw response ({len(tokens)} tokens, {len(full_json)} chars): "
            f"{full_json[:200]}"
        )
        # Strip markdown code fences (```json ... ```) that some models add
        if full_json.startswith("```"):
            first_nl = full_json.index("\n") + 1
            full_json = full_json[first_nl:]
        if full_json.endswith("```"):
            full_json = full_json[:-3].strip()
        try:
            resp = HintResponseV2.model_validate_json(full_json)
            logger.info(
                "Hint sent: type={} headline={:.60} (session={})",
                resp.hint_type,
                resp.headline,
                self._session_id,
            )
            await self._ws.send_json(
                {
                    "type": "hint_end",
                    "v": 2,
                    "hint_type": resp.hint_type,
                    "headline": resp.headline,
                    "detail": resp.detail,
                    "coaching": resp.coaching,
                    "source": resp.source,
                }
            )
            self._last_hint_time = time.monotonic()
        except Exception as exc:
            logger.warning(
                f"Failed to parse/send hint_end v2: {exc!r} "
                f"json={full_json[:200]} (session={self._session_id})"
            )
