"""Tests for WebSocket /ws endpoint."""

from __future__ import annotations

import json
import struct
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient


def make_control_frame(payload: dict, seq: int = 1) -> bytes:
    """Binary control frame (channel=1)."""
    header = struct.pack("<IB", seq, 1)
    return header + json.dumps(payload).encode()


def make_audio_frame(pcm_bytes: bytes, seq: int = 2) -> bytes:
    """Binary audio frame (channel=0)."""
    header = struct.pack("<IB", seq, 0)
    return header + pcm_bytes


def make_silent_stereo(n_pairs: int = 480) -> bytes:
    """Silent interleaved stereo PCM16 (L=0, R=0 for each pair)."""
    return struct.pack(f"<{n_pairs * 2}h", *([0] * n_pairs * 2))


@pytest.fixture
def ws_app(mock_redis):
    from backend.main import create_app

    app = create_app()
    app.state.redis = mock_redis
    return app


def test_websocket_session_start_and_end(ws_app):
    """Full session: start → audio frame → end — no crash."""
    silent = make_silent_stereo()

    with (
        patch(
            "backend.pipeline.vad.SileroVAD.detect_speech",
            new=AsyncMock(return_value=False),
        ),
        patch("backend.pipeline.stt.SaluteSpeechSTT.start_session", new=AsyncMock()),
        patch("backend.pipeline.stt.SaluteSpeechSTT.send_audio", new=AsyncMock()),
        patch("backend.pipeline.stt.SaluteSpeechSTT.close", new=AsyncMock()),
        patch(
            "backend.pipeline.orchestrator.PipelineOrchestrator.teardown",
            new=AsyncMock(),
        ),
    ):
        client = TestClient(ws_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_bytes(
                make_control_frame(
                    {"type": "session_start", "session_id": "s1", "kb_id": "kb1"}
                )
            )
            ws.send_bytes(make_audio_frame(silent))
            ws.send_bytes(make_control_frame({"type": "session_end"}, seq=3))


def test_websocket_speech_routes_to_stt(ws_app):
    """When VAD returns True, audio is forwarded to STT."""
    speech = [int(32767 * 0.3)] * 480
    stereo = struct.pack(
        f"<{480 * 2}h",
        *[s for pair in zip(speech, [0] * 480, strict=True) for s in pair],
    )

    mock_send_audio = AsyncMock()
    with (
        patch(
            "backend.pipeline.vad.SileroVAD.detect_speech",
            new=AsyncMock(return_value=True),
        ),
        patch("backend.pipeline.stt.SaluteSpeechSTT.start_session", new=AsyncMock()),
        patch("backend.pipeline.stt.SaluteSpeechSTT.send_audio", mock_send_audio),
        patch("backend.pipeline.stt.SaluteSpeechSTT.close", new=AsyncMock()),
        patch(
            "backend.pipeline.orchestrator.PipelineOrchestrator.teardown",
            new=AsyncMock(),
        ),
    ):
        client = TestClient(ws_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_bytes(
                make_control_frame(
                    {"type": "session_start", "session_id": "s2", "kb_id": "kb2"}
                )
            )
            ws.send_bytes(make_audio_frame(stereo))
            ws.send_bytes(make_control_frame({"type": "session_end"}, seq=3))

    assert mock_send_audio.call_count >= 1


def test_websocket_audio_before_session_start_is_ignored(ws_app):
    """Audio frames before session_start do not crash the handler."""
    silent = make_silent_stereo()
    with (
        patch(
            "backend.pipeline.vad.SileroVAD.detect_speech",
            new=AsyncMock(return_value=False),
        ),
        patch("backend.pipeline.stt.SaluteSpeechSTT.close", new=AsyncMock()),
    ):
        client = TestClient(ws_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_bytes(make_audio_frame(silent))
            ws.send_bytes(make_control_frame({"type": "session_end"}))


def test_websocket_disconnect_calls_teardown(ws_app):
    """Abrupt disconnect still calls orchestrator.teardown and stt.close."""
    mock_teardown = AsyncMock()
    mock_close = AsyncMock()
    with (
        patch(
            "backend.pipeline.vad.SileroVAD.detect_speech",
            new=AsyncMock(return_value=False),
        ),
        patch("backend.pipeline.stt.SaluteSpeechSTT.start_session", new=AsyncMock()),
        patch("backend.pipeline.stt.SaluteSpeechSTT.close", mock_close),
        patch(
            "backend.pipeline.orchestrator.PipelineOrchestrator.teardown",
            mock_teardown,
        ),
    ):
        client = TestClient(ws_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_bytes(
                make_control_frame(
                    {"type": "session_start", "session_id": "s3", "kb_id": "kb3"}
                )
            )
            # Disconnect without session_end

    mock_teardown.assert_called_once()
    mock_close.assert_called_once()


def test_websocket_loads_scenario_from_redis(ws_app, mock_redis):
    """session_start reads scenario from Redis and passes to orchestrator."""
    scenario_json = '{"portrait": {}, "key_facts": [{"fact": "test"}]}'
    mock_redis.get = AsyncMock(return_value=scenario_json.encode())

    captured_kwargs = {}

    class CapturingOrchestrator:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self._background_tasks = set()
            self._evaluation_task = None

        async def handle_transcript(self, t):
            pass

        async def teardown(self):
            pass

        async def on_session_end(self, session_id, ws, redis, **kwargs):
            pass

    with (
        patch(
            "backend.pipeline.vad.SileroVAD.detect_speech",
            new=AsyncMock(return_value=False),
        ),
        patch("backend.pipeline.stt.SaluteSpeechSTT.start_session", new=AsyncMock()),
        patch("backend.pipeline.stt.SaluteSpeechSTT.close", new=AsyncMock()),
        patch(
            "backend.ws.handler.PipelineOrchestrator",
            CapturingOrchestrator,
        ),
    ):
        client = TestClient(ws_app)
        with client.websocket_connect("/ws") as ws:
            ws.send_bytes(
                make_control_frame(
                    {"type": "session_start", "session_id": "s4", "kb_id": "kb4"}
                )
            )
            ws.send_bytes(make_control_frame({"type": "session_end"}, seq=3))

    assert "scenario_text" in captured_kwargs
    assert captured_kwargs["scenario_text"] == scenario_json
    mock_redis.get.assert_called()
