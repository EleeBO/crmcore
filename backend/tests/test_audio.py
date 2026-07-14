"""Tests for backend audio processing: binary frame parsing, VAD (Task 3.2)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Frame parsing ──────────────────────────────────────────────────────────


def test_parse_audio_frame(audio_frame: bytes) -> None:
    """Audio frame parsed: seq=1, channel=0, payload=PCM16."""
    from backend.pipeline.audio import FrameType, parse_frame

    frame = parse_frame(audio_frame)
    assert frame.frame_type == FrameType.AUDIO
    assert frame.seq == 1
    assert frame.channel == 0
    assert len(frame.payload) > 0


def test_parse_control_frame(control_frame: bytes) -> None:
    """Control frame parsed: seq=1, channel=1, valid JSON payload."""
    import json

    from backend.pipeline.audio import FrameType, parse_frame

    frame = parse_frame(control_frame)
    assert frame.frame_type == FrameType.CONTROL
    assert frame.channel == 1
    data = json.loads(frame.payload)
    assert data["type"] == "session_start"


def test_parse_frame_too_short() -> None:
    """Frame shorter than 5 bytes raises ValueError."""
    from backend.pipeline.audio import parse_frame

    with pytest.raises(ValueError, match="too short"):
        parse_frame(b"\x01\x02")


def test_deinterleave_stereo(stereo_pcm16: bytes) -> None:
    """Stereo PCM16 deinterleaved into separate L and R channels."""
    from backend.pipeline.audio import deinterleave_stereo

    left, right = deinterleave_stereo(stereo_pcm16)
    # Each channel should have half the total bytes
    assert len(left) == len(stereo_pcm16) // 2
    assert len(right) == len(stereo_pcm16) // 2


def test_deinterleave_stereo_odd_length() -> None:
    """Odd-length input raises ValueError."""
    from backend.pipeline.audio import deinterleave_stereo

    with pytest.raises(ValueError, match="even"):
        deinterleave_stereo(b"\x00\x00\x00")


# ── VAD tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vad_speech_detected(speech_pcm16: bytes) -> None:
    """Speech audio triggers VAD to return True."""
    from backend.pipeline.vad import SileroVAD

    with patch("backend.pipeline.vad._run_inference", return_value=0.9):
        vad = SileroVAD(threshold=0.5)
        result = await vad.detect_speech(speech_pcm16, channel="client")
    assert result is True


@pytest.mark.asyncio
async def test_vad_silence_detected(silence_pcm16: bytes) -> None:
    """Silence audio triggers VAD to return False."""
    from backend.pipeline.vad import SileroVAD

    with patch("backend.pipeline.vad._run_inference", return_value=0.1):
        vad = SileroVAD(threshold=0.5)
        result = await vad.detect_speech(silence_pcm16, channel="client")
    assert result is False


@pytest.mark.asyncio
async def test_vad_runs_in_executor(speech_pcm16: bytes) -> None:
    """VAD uses run_in_executor to avoid blocking the event loop."""
    import asyncio

    from backend.pipeline.vad import SileroVAD

    loop_mock = MagicMock(spec=asyncio.AbstractEventLoop)
    future = asyncio.get_event_loop().run_in_executor(None, lambda: 0.9)
    loop_mock.run_in_executor = AsyncMock(return_value=0.9)

    with patch("backend.pipeline.vad._run_inference", return_value=0.9):
        with patch("asyncio.get_event_loop", return_value=loop_mock):
            vad = SileroVAD(threshold=0.5)
            await vad.detect_speech(speech_pcm16, channel="client")

    loop_mock.run_in_executor.assert_called_once()


@pytest.mark.asyncio
async def test_vad_per_channel_state(speech_pcm16: bytes) -> None:
    """VAD maintains separate state per channel."""
    from backend.pipeline.vad import SileroVAD

    with patch("backend.pipeline.vad._run_inference", return_value=0.9):
        vad = SileroVAD(threshold=0.5)
        await vad.detect_speech(speech_pcm16, channel="client")
        await vad.detect_speech(speech_pcm16, channel="rep")
        assert "client" in vad._states
        assert "rep" in vad._states
        assert vad._states["client"] is not vad._states["rep"]
