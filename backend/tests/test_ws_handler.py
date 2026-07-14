"""Tests for WebSocketHandler (Task 2.2: extract WS logic from main.py)."""

from __future__ import annotations

import json
import struct
from unittest.mock import AsyncMock, patch

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.config import Settings
from backend.ws.handler import WebSocketHandler

_TEST_CFG = Settings(
    stt_provider="deepgram",
    deepgram_api_key="test-key",
    openrouter_api_key="test-or-key",
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_control_frame(payload: dict) -> bytes:
    """Build a binary WS frame with channel=1 (control) and JSON payload."""
    body = json.dumps(payload).encode()
    header = struct.pack("<IB", 0, 1)  # seq=0, channel=1 (CONTROL)
    return header + body


def _make_audio_frame(pcm: bytes, seq: int = 1) -> bytes:
    """Build a binary WS frame with channel=0 (audio)."""
    header = struct.pack("<IB", seq, 0)  # channel=0 (AUDIO)
    return header + pcm


def _sent_json_types(ws: AsyncMock) -> list[str]:
    """Extract the 'type' field from all send_json calls on a mock websocket."""
    return [c.args[0].get("type") for c in ws.send_json.call_args_list]


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def ws_mock() -> AsyncMock:
    """Pre-configured websocket mock with accept stubbed."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    return ws


@pytest.fixture()
def handler() -> WebSocketHandler:
    """Handler with no Redis (simplest setup)."""
    return WebSocketHandler(cfg=_TEST_CFG, redis=None)


@pytest.fixture()
def handler_with_redis() -> tuple[WebSocketHandler, AsyncMock]:
    """Handler with a mocked Redis client."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    return WebSocketHandler(cfg=_TEST_CFG, redis=redis_mock), redis_mock


# ── Instantiation ────────────────────────────────────────────────────────────


class TestWebSocketHandlerInit:
    def test_stores_cfg_and_redis(self) -> None:
        redis = AsyncMock()
        h = WebSocketHandler(cfg=_TEST_CFG, redis=redis)
        assert h._cfg is _TEST_CFG
        assert h._redis is redis

    def test_redis_none_accepted(self, handler: WebSocketHandler) -> None:
        assert handler._redis is None


# ── Disconnect handling ──────────────────────────────────────────────────────


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_immediate_disconnect_no_crash(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Handler gracefully exits on immediate WebSocketDisconnect."""
        ws_mock.receive = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
        await handler.run(ws_mock)
        ws_mock.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_exception_exits_cleanly(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Handler exits on unexpected receive error without raising."""
        ws_mock.receive = AsyncMock(side_effect=RuntimeError("connection lost"))
        await handler.run(ws_mock)
        ws_mock.accept.assert_called_once()


# ── Session lifecycle ────────────────────────────────────────────────────────


class TestSessionEnd:
    @pytest.mark.asyncio
    async def test_text_session_end_sends_evaluation_started(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Text-based session_end triggers evaluation_started response."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"text": json.dumps({"type": "session_end"})},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)

        assert "evaluation_started" in _sent_json_types(ws_mock)

    @pytest.mark.asyncio
    async def test_control_session_end_sends_evaluation_started(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Binary control session_end triggers evaluation_started response."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": _make_control_frame({"type": "session_end"})},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)

        assert "evaluation_started" in _sent_json_types(ws_mock)


class TestSessionStart:
    @pytest.mark.asyncio
    async def test_session_start_creates_orchestrator(
        self,
        handler_with_redis: tuple[WebSocketHandler, AsyncMock],
        ws_mock: AsyncMock,
    ) -> None:
        """session_start control frame initializes orchestrator and STT."""
        h, _ = handler_with_redis

        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": _make_control_frame({
                "type": "session_start",
                "session_id": "test-123",
                "kb_id": "kb-1",
            })},
            {"bytes": _make_control_frame({"type": "session_end"})},
            WebSocketDisconnect(1000),
        ])

        with patch("backend.ws.handler.create_stt_client") as mock_stt_factory, \
             patch("backend.ws.handler.LLMClient"):
            mock_stt = AsyncMock()
            mock_stt_factory.return_value = mock_stt

            await h.run(ws_mock)

            mock_stt_factory.assert_called_once()
            mock_stt.start_session.assert_called_once_with("test-123")
            assert "evaluation_started" in _sent_json_types(ws_mock)

    @pytest.mark.asyncio
    async def test_session_start_failure_sends_error(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """If session_start setup fails, handler sends SESSION_START_FAILED."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": _make_control_frame({
                "type": "session_start",
                "session_id": "test-err",
                "kb_id": "kb-1",
            })},
            WebSocketDisconnect(1000),
        ])

        with patch(
            "backend.ws.handler.create_stt_client",
            side_effect=RuntimeError("STT init failed"),
        ):
            await handler.run(ws_mock)

        calls = ws_mock.send_json.call_args_list
        error_calls = [
            c for c in calls
            if c.args[0].get("code") == "SESSION_START_FAILED"
        ]
        assert len(error_calls) == 1
        assert "STT init failed" in error_calls[0].args[0]["message"]


# ── Audio routing ────────────────────────────────────────────────────────────


class TestAudioRouting:
    @pytest.mark.asyncio
    async def test_audio_frame_sent_to_stt(
        self,
        handler_with_redis: tuple[WebSocketHandler, AsyncMock],
        ws_mock: AsyncMock,
    ) -> None:
        """Audio frames are deinterleaved and forwarded to STT client."""
        h, _ = handler_with_redis

        # Stereo interleaved PCM: 4 samples (L R L R), 2 bytes each
        stereo_pcm = struct.pack("<4h", 100, 200, 300, 400)

        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": _make_control_frame({
                "type": "session_start",
                "session_id": "audio-test",
                "kb_id": "",
            })},
            {"bytes": _make_audio_frame(stereo_pcm, seq=1)},
            {"bytes": _make_control_frame({"type": "session_end"})},
            WebSocketDisconnect(1000),
        ])

        with patch("backend.ws.handler.create_stt_client") as mock_stt_factory, \
             patch("backend.ws.handler.LLMClient"):
            mock_stt = AsyncMock()
            mock_stt_factory.return_value = mock_stt

            await h.run(ws_mock)

            assert mock_stt.send_audio.call_count == 2
            assert mock_stt.send_audio.call_args_list[0].args[1] == "rep"
            assert mock_stt.send_audio.call_args_list[1].args[1] == "client"

    @pytest.mark.asyncio
    async def test_audio_before_session_start_ignored(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Audio frames received before session_start are silently dropped."""
        stereo_pcm = struct.pack("<4h", 1, 2, 3, 4)

        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": _make_audio_frame(stereo_pcm)},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)
        ws_mock.accept.assert_called_once()


# ── Text message handling ────────────────────────────────────────────────────


class TestTextMessages:
    @pytest.mark.asyncio
    async def test_non_session_end_text_ignored(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Text messages that aren't session_end are silently skipped."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"text": json.dumps({"type": "ping"})},
            {"text": "not json at all"},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)
        ws_mock.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_text_message_ignored(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Empty text messages are skipped without error."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"text": ""},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)
        ws_mock.send_json.assert_not_called()


# ── Malformed frames ────────────────────────────────────────────────────────


class TestMalformedFrames:
    @pytest.mark.asyncio
    async def test_short_binary_frame_skipped(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Binary frame shorter than 5 bytes is logged and skipped."""
        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": b"\x00\x01"},  # too short
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)
        ws_mock.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_bad_control_json_skipped(
        self, handler: WebSocketHandler, ws_mock: AsyncMock
    ) -> None:
        """Control frame with invalid JSON is skipped, not crashed."""
        header = struct.pack("<IB", 0, 1)
        bad_frame = header + b"not json {"

        ws_mock.receive = AsyncMock(side_effect=[
            {"bytes": bad_frame},
            WebSocketDisconnect(1000),
        ])

        await handler.run(ws_mock)
        ws_mock.accept.assert_called_once()
