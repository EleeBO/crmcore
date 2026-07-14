"""WebSocket handler for real-time audio streaming."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from fastapi.websockets import WebSocket
from starlette.websockets import WebSocketDisconnect

from backend.config import Settings
from backend.logger import logger
from backend.pipeline.audio import (
    FrameType,
    deinterleave_stereo,
    parse_frame,
)
from backend.pipeline.audio_buffer import AudioBuffer
from backend.pipeline.llm import LLMClient
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.stt import create_stt_client
from backend.pipeline.types import Transcript
from backend.session.manager import SessionManager

_MSG_IDLE_WARNING = "Речь не обнаружена"
_MSG_IDLE_TIMEOUT = "Сессия завершена"

# ── Test mode synthetic conversation ──────────────────────────────────────

_TEST_CONVERSATION = [
    ("rep", "Добрый день! Меня зовут Алексей."),
    ("client", "Расскажите подробнее о продукте."),
    ("rep", "Наше решение увеличивает конверсию."),
    ("client", "Сколько стоит? Слишком дорого."),
    ("rep", "Давайте посмотрим на ROI."),
    ("client", "У нас уже есть решение."),
    ("rep", "Мы интегрируемся с любыми CRM."),
    ("client", "Какие гарантии?"),
]


async def _run_test_conversation(
    orchestrator: PipelineOrchestrator,
    ws: WebSocket,
) -> None:
    """Feed synthetic transcripts into the pipeline with realistic timing."""
    logger.info("Test mode: starting conversation")
    utt_n: dict[str, int] = {"rep": 0, "client": 0}

    for speaker, text in _TEST_CONVERSATION:
        utt_n[speaker] += 1

        # Simulate STT partials
        words = text.split()
        for i in range(len(words)):
            partial = " ".join(words[: i + 1])
            if i < len(words) - 1 and i % 3 == 2:
                t = Transcript(
                    speaker=speaker,
                    text=partial,
                    is_final=False,
                )
                await orchestrator.handle_transcript(t)
                await asyncio.sleep(0.3)

        # Final transcript
        t = Transcript(
            speaker=speaker,
            text=text,
            is_final=True,
            utterance_id=f"{speaker}-{utt_n[speaker]}",
        )
        await orchestrator.handle_transcript(t)
        logger.info(f"Test: [{speaker}] {text[:50]}")

        # Let LLM generate hint
        await asyncio.sleep(10.0)

    logger.info("Test mode: conversation complete")
    try:
        eval_token = await orchestrator.on_session_end(
            orchestrator._session_id,
            ws,
            None,  # redis handled inside orchestrator
        )
        await ws.send_json(
            {
                "type": "evaluation_started",
                "session_id": orchestrator._session_id,
                "eval_token": eval_token,
            }
        )
    except Exception as exc:
        logger.warning(f"Test mode: session_end failed: {exc!r}")


class WebSocketHandler:
    """Handle real-time audio streaming from Chrome extension."""

    def __init__(
        self,
        cfg: Settings,
        redis: Any | None,
    ) -> None:
        self._cfg = cfg
        self._redis = redis

    async def run(  # noqa: C901, PLR0912, PLR0915
        self,
        websocket: WebSocket,
    ) -> None:
        """Accept connection and process the message loop."""
        await websocket.accept()

        cfg = self._cfg
        redis_client = self._redis

        stt: Any = None
        orchestrator: PipelineOrchestrator | None = None
        audio_buffer: AudioBuffer | None = None
        session_id: str | None = None
        last_transcript_time: float = 0.0
        idle_warning_sent: bool = False
        stt_failed: bool = False
        session_init_deadline = time.monotonic() + 30.0

        logger.info("WebSocket connection opened")

        try:
            while True:
                if stt_failed:
                    break

                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=30.0)
                except TimeoutError:
                    if last_transcript_time > 0:
                        idle_s = time.monotonic() - last_transcript_time
                        remaining = cfg.session_idle_timeout_s - idle_s

                        if remaining <= 60 and not idle_warning_sent:
                            idle_warning_sent = True
                            with contextlib.suppress(Exception):
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "code": "SESSION_IDLE_WARNING",
                                        "message": _MSG_IDLE_WARNING,
                                    }
                                )

                        if idle_s >= cfg.session_idle_timeout_s:
                            logger.info(
                                f"Session idle timeout ({idle_s:.0f}s): {session_id}"
                            )
                            with contextlib.suppress(Exception):
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "code": "SESSION_IDLE_TIMEOUT",
                                        "message": _MSG_IDLE_TIMEOUT,
                                    }
                                )
                            break

                    if (
                        orchestrator is None
                        and time.monotonic() > session_init_deadline
                    ):
                        logger.warning("No session_start received within 30s")
                        break

                    continue
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: session={session_id}")
                    break
                except Exception as exc:
                    logger.warning(f"WebSocket receive error: {exc}")
                    break

                raw: bytes | None = message.get("bytes")
                if raw is None:
                    text = message.get("text", "")
                    if text:
                        try:
                            data = json.loads(text)
                            if data.get("type") == "session_end":
                                logger.info(f"Session end (text): {session_id}")
                                # Flush pending STT finals before evaluation
                                if stt is not None:
                                    logger.info("Flushing STT for pending finals...")
                                    await stt.flush(timeout=5.0)
                                    stt = None  # prevent double-close in finally
                                eval_token = ""
                                if orchestrator is not None:
                                    eval_token = await orchestrator.on_session_end(
                                        session_id,
                                        websocket,
                                        redis_client,
                                        audio_buffer=audio_buffer,
                                    )
                                await websocket.send_json(
                                    {
                                        "type": "evaluation_started",
                                        "session_id": session_id,
                                        "eval_token": eval_token,
                                    }
                                )
                                break
                        except Exception:
                            pass
                    continue

                try:
                    frame = parse_frame(raw)
                except ValueError as exc:
                    logger.warning(f"Bad WS frame: {exc}")
                    continue

                if frame.frame_type == FrameType.CONTROL:
                    try:
                        ctrl = json.loads(frame.payload)
                    except Exception:
                        logger.warning("Bad control JSON, skipping")
                        continue

                    ctrl_type = ctrl.get("type")

                    if ctrl_type == "session_start":
                        session_id = ctrl.get("session_id", "ws-anon")
                        kb_id: str = ctrl.get("kb_id", "")
                        stt_provider: str | None = ctrl.get("stt_provider")
                        test_mode: bool = ctrl.get("test_mode", False)

                        try:
                            # Defensive cleanup
                            if redis_client is not None:
                                cleanup_mgr = SessionManager(redis=redis_client)
                                await cleanup_mgr.cleanup_session(
                                    session_id, kb_id=kb_id
                                )

                            scenario_text = ""
                            if not kb_id:
                                logger.warning("session_start without kb_id")
                            elif redis_client is not None:
                                raw_scenario = await redis_client.get(
                                    f"kb:{kb_id}:scenario"
                                )
                                if raw_scenario:
                                    scenario_text = (
                                        raw_scenario.decode()
                                        if isinstance(raw_scenario, bytes)
                                        else raw_scenario
                                    )
                                else:
                                    logger.warning(f"No scenario for kb={kb_id}")

                            llm = LLMClient(
                                primary_model=cfg.llm_primary_model,
                                fallback_model=cfg.llm_fallback_model,
                                api_key=cfg.openrouter_api_key,
                                primary_timeout_ms=cfg.llm_primary_timeout_ms,
                                fallback_timeout_ms=cfg.llm_fallback_timeout_ms,
                            )
                            session_mgr = SessionManager(
                                redis=redis_client,
                            )
                            orchestrator = PipelineOrchestrator(
                                ws=websocket,
                                session_id=session_id,
                                llm_client=llm,
                                session_manager=session_mgr,
                                scenario_text=scenario_text,
                                kb_id=kb_id,
                                eval_api_key=cfg.openrouter_api_key,
                                enable_post_call_diarization=cfg.enable_post_call_diarization,
                                yandex_api_key=cfg.yandex_speechkit_api_key,
                                hint_context_utterances=cfg.hint_context_utterances,
                            )

                            if test_mode:
                                # Test mode: no STT, no audio
                                last_transcript_time = time.monotonic()
                                logger.info(f"Test session: id={session_id}")
                                asyncio.create_task(
                                    _run_test_conversation(
                                        orchestrator,
                                        websocket,
                                    )
                                )
                            else:
                                # Normal mode: set up STT
                                if cfg.enable_post_call_diarization:
                                    audio_buffer = AudioBuffer()

                                stt = create_stt_client(
                                    cfg,
                                    provider=stt_provider,
                                )
                                _orch = orchestrator

                                async def _on_transcript(
                                    t: Any,
                                    _o: Any = _orch,
                                ) -> None:
                                    nonlocal last_transcript_time
                                    nonlocal idle_warning_sent
                                    last_transcript_time = time.monotonic()
                                    idle_warning_sent = False
                                    await _o.handle_transcript(t)

                                stt.on_transcript = _on_transcript

                                async def _on_stt_error(
                                    code: str,
                                    message: str,
                                ) -> None:
                                    nonlocal stt_failed
                                    permanent = code in (
                                        "STT_BALANCE_EXHAUSTED",
                                        "STT_AUTH_FAILED",
                                        "STT_UNAVAILABLE",
                                    )
                                    if permanent:
                                        stt_failed = True
                                    try:
                                        await websocket.send_json(
                                            {
                                                "type": "error",
                                                "code": code,
                                                "message": message,
                                            }
                                        )
                                    except Exception as ws_exc:
                                        logger.debug(f"STT error WS: {ws_exc!r}")

                                stt.on_error = _on_stt_error
                                await stt.start_session(session_id)
                                last_transcript_time = time.monotonic()
                                slen = len(scenario_text)
                                logger.info(
                                    f"Session: id={session_id} kb={kb_id} len={slen}"
                                )
                        except Exception as exc:
                            logger.error(f"Session start failed: {exc!r}")
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "code": "SESSION_START_FAILED",
                                    "message": str(exc)[:100],
                                }
                            )

                    elif ctrl_type == "session_end":
                        logger.info(f"Session end: {session_id}")
                        # Flush pending STT finals before evaluation
                        if stt is not None:
                            logger.info("Flushing STT for pending finals...")
                            await stt.flush(timeout=5.0)
                            stt = None  # prevent double-close in finally
                        eval_token = ""
                        if orchestrator is not None:
                            eval_token = await orchestrator.on_session_end(
                                session_id,
                                websocket,
                                redis_client,
                                audio_buffer=audio_buffer,
                            )
                        await websocket.send_json(
                            {
                                "type": "evaluation_started",
                                "session_id": session_id,
                                "eval_token": eval_token,
                            }
                        )
                        break

                elif frame.frame_type == FrameType.AUDIO and orchestrator is not None:
                    try:
                        left, right = deinterleave_stereo(frame.payload)
                    except ValueError as exc:
                        logger.warning(f"Deinterleave error: {exc}")
                        continue

                    if stt is not None:
                        await stt.send_audio(left, "rep")
                        await stt.send_audio(right, "client")
                    if audio_buffer is not None:
                        audio_buffer.append("rep", left)
                        audio_buffer.append("client", right)

        finally:
            if orchestrator is not None:
                await orchestrator.teardown()
                if orchestrator._evaluation_task is not None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await asyncio.wait_for(
                            orchestrator._evaluation_task,
                            timeout=150.0,
                        )
            if stt is not None:
                await stt.close()
            if audio_buffer is not None:
                audio_buffer.clear()
            logger.info(f"WebSocket cleanup done: session={session_id}")
