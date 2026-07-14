"""Tests for Task 7.1: End-to-end integration + edge cases."""

from __future__ import annotations

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case handling for the full pipeline."""

    # E1: Cross-talk — both channels have speech, prioritise client
    @pytest.mark.asyncio
    async def test_crosstalk_both_speakers_trigger_pipeline(self):
        """Both rep and client speech trigger the hint pipeline."""
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.stt import Transcript

        ws = AsyncMock()
        ws.send_json = AsyncMock()
        llm = AsyncMock()
        llm._cancel_current = MagicMock()
        llm.generate_hint_stream = AsyncMock(return_value=_async_iter([]))
        session = AsyncMock()
        session.add_utterance = AsyncMock()
        session.get_context = AsyncMock(
            return_value=MagicMock(utterances=[], summary="")
        )

        orch = PipelineOrchestrator(
            ws=ws,
            session_id="sess1",
            llm_client=llm,
            session_manager=session,
            scenario_text="test scenario",
        )

        # Rep transcript — triggers hint pipeline (coaching)
        await orch.handle_transcript(
            Transcript(
                speaker="rep",
                text="Наш продукт самый лучший",
                is_final=True,
            )
        )
        assert llm.generate_hint_stream.call_count == 1

        # Reset cooldown timer so next transcript isn't skipped
        orch._last_hint_time = 0.0

        # Client transcript — also triggers hint pipeline (analysis)
        await orch.handle_transcript(
            Transcript(
                speaker="client",
                text="Сколько стоит?",
                is_final=True,
            )
        )
        assert llm.generate_hint_stream.call_count >= 2

    # E2: Empty scenario — pipeline still works
    @pytest.mark.asyncio
    async def test_empty_scenario_no_crash(self):
        """Pipeline works with empty scenario text."""
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.stt import Transcript

        ws = AsyncMock()
        ws.send_json = AsyncMock()
        llm = AsyncMock()
        llm._cancel_current = MagicMock()
        llm.generate_hint_stream = AsyncMock(return_value=_async_iter([]))
        session = AsyncMock()
        session.add_utterance = AsyncMock()
        session.get_context = AsyncMock(
            return_value=MagicMock(utterances=[], summary="")
        )

        orch = PipelineOrchestrator(
            ws=ws,
            session_id="sess-empty",
            llm_client=llm,
            session_manager=session,
            scenario_text="",
        )

        # Should not raise with empty scenario
        await orch.handle_transcript(
            Transcript(
                speaker="client",
                text="Вопрос вне базы",
                is_final=True,
            )
        )

    # E4: WebSocket disconnect → teardown doesn't crash
    @pytest.mark.asyncio
    async def test_ws_disconnect_teardown_graceful(self):
        """Orchestrator teardown cancels background tasks gracefully."""
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.stt import Transcript

        ws = AsyncMock()
        ws.send_json = AsyncMock()
        llm = AsyncMock()
        llm._cancel_current = MagicMock()
        llm.generate_hint_stream = AsyncMock(return_value=_async_iter([]))
        session = AsyncMock()
        session.add_utterance = AsyncMock()
        session.get_context = AsyncMock(
            return_value=MagicMock(utterances=[], summary="")
        )

        orch = PipelineOrchestrator(
            ws=ws,
            session_id="sess-disc",
            llm_client=llm,
            session_manager=session,
            scenario_text="test",
        )

        await orch.handle_transcript(
            Transcript(
                speaker="client",
                text="Interim query",
                is_final=False,
            )
        )

        # Teardown should not raise
        await orch.teardown()

    # E9: Corrupt file handling in upload
    def test_corrupt_file_returns_error(self):
        """Parser returns CopilotError for corrupt files."""
        from backend.errors import CopilotError, ErrorCode
        from backend.ingestion.parser import parse_pdf

        corrupt_bytes = b"This is not a valid PDF"
        with pytest.raises(CopilotError) as exc_info:
            parse_pdf(corrupt_bytes)
        assert exc_info.value.code == ErrorCode.FILE_CORRUPT

    # E10: LLM timeout fallback with badge
    @pytest.mark.asyncio
    async def test_llm_timeout_returns_fallback(self):
        """LLM timeout results in fallback hint being returned."""
        from backend.pipeline.llm import HintContext, LLMClient

        client = LLMClient(
            primary_model="test-primary",
            fallback_model="test-fallback",
            api_key="test-key",
            primary_timeout_ms=1,
        )

        ctx = HintContext(
            utterance="Слишком дорого",
            speaker="client",
            rag_context=["Тариф Gold: 500 руб/мес"],
        )

        result = await client.generate_hint(ctx)
        assert result.source == "fallback"

    # Binary frame parsing
    def test_binary_frame_header_parse(self):
        """AudioFrame header can be correctly decoded."""
        from backend.pipeline.audio import Frame as AudioFrame
        from backend.pipeline.audio import parse_frame

        payload = b"\xff" * 100
        seq = 42
        channel = 0
        header = struct.pack("<IB", seq, channel)
        frame_bytes = header + payload

        frame = parse_frame(frame_bytes)
        assert isinstance(frame, AudioFrame)
        assert frame.seq == seq
        assert frame.channel == channel
        assert len(frame.payload) == len(payload)

    # Stereo de-interleave
    def test_deinterleave_produces_equal_length_channels(
        self, stereo_pcm16
    ):
        """De-interleaved channels have equal length."""
        from backend.pipeline.audio import deinterleave_stereo

        mic_bytes, tab_bytes = deinterleave_stereo(stereo_pcm16)
        assert len(mic_bytes) == len(tab_bytes)
        mic_samples = struct.unpack(
            f"<{len(mic_bytes) // 2}h", mic_bytes
        )
        assert any(s != 0 for s in mic_samples)


# ── Latency Tests ──────────────────────────────────────────────────────────


class TestLatency:
    """Verify pipeline latency constraints with mocked services."""

    @pytest.mark.asyncio
    async def test_latency_full_pipeline_under_2s(self):
        """Full pipeline (mock STT+LLM) completes within 2000ms."""
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.stt import Transcript

        ws = AsyncMock()
        ws.send_json = AsyncMock()
        llm = AsyncMock()
        llm._cancel_current = MagicMock()
        llm.generate_hint_stream = AsyncMock(return_value=_async_iter([]))
        session = AsyncMock()
        session.add_utterance = AsyncMock()
        session.get_context = AsyncMock(
            return_value=MagicMock(utterances=[], summary="")
        )

        orch = PipelineOrchestrator(
            ws=ws,
            session_id="latency-test",
            llm_client=llm,
            session_manager=session,
            scenario_text="test scenario",
        )

        transcript = Transcript(
            speaker="client", text="Какой у вас SLA?", is_final=True
        )

        await asyncio.wait_for(
            orch.handle_transcript(transcript), timeout=2.0
        )

    @pytest.mark.asyncio
    async def test_latency_rep_speech_triggers_pipeline(self):
        """Rep transcripts trigger hint pipeline (coaching hints)."""
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.stt import Transcript

        ws = AsyncMock()
        ws.send_json = AsyncMock()
        llm = AsyncMock()
        llm._cancel_current = MagicMock()
        llm.generate_hint_stream = AsyncMock(return_value=_async_iter([]))
        session = AsyncMock()
        session.add_utterance = AsyncMock()
        session.get_context = AsyncMock(
            return_value=MagicMock(utterances=[], summary="")
        )

        orch = PipelineOrchestrator(
            ws=ws,
            session_id="silence-test",
            llm_client=llm,
            session_manager=session,
            scenario_text="test",
        )

        await orch.handle_transcript(
            Transcript(
                speaker="rep",
                text="Я понял ваш вопрос",
                is_final=True,
            )
        )

        # Rep speech now triggers hint pipeline (silent generation)
        assert llm.generate_hint_stream.call_count == 1

    @pytest.mark.asyncio
    async def test_latency_llm_fallback_fast(self):
        """LLM fallback responds within 1500ms with mocked delay."""
        from backend.pipeline.llm import HintContext, LLMClient

        client = LLMClient(
            primary_model="test-primary",
            fallback_model="test-fallback",
            api_key="test-key",
            primary_timeout_ms=10,
        )

        ctx = HintContext(
            utterance="Возражение клиента",
            speaker="client",
            rag_context=[],
        )

        result = await asyncio.wait_for(
            client.generate_hint(ctx), timeout=1.5
        )
        assert result.source == "fallback"


# ── Helpers ────────────────────────────────────────────────────────────────


async def _async_iter(items):
    """Helper: create an async iterator from a list."""
    for item in items:
        yield item
