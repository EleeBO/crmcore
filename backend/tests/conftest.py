"""Shared pytest fixtures for AI Sales Copilot tests."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

# ── Settings override ──────────────────────────────────────────────────────


@pytest.fixture
def test_settings():
    """Return Settings with test defaults (no real services required)."""
    from backend.config import Settings

    return Settings(
        stt_provider="deepgram",
        deepgram_api_key="test-deepgram-key",
        openrouter_api_key="test-openrouter-key",
        redis_url="redis://localhost:6379",
        log_level="DEBUG",
    )


# ── Redis mock ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_redis():
    """Mock Redis client that doesn't require a real Redis server."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.rpush = AsyncMock(return_value=1)
    mock.lrange = AsyncMock(return_value=[])
    mock.ltrim = AsyncMock(return_value=True)
    mock.expire = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=0)
    mock.close = AsyncMock()
    return mock


# ── FastAPI test client ────────────────────────────────────────────────────


@pytest.fixture
async def app_with_mocks(mock_redis):
    """FastAPI app with all external services mocked."""
    from backend.main import create_app

    app = create_app()
    app.state.redis = mock_redis
    return app


@pytest.fixture
async def client(app_with_mocks) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with mocked services."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as ac:
        yield ac


# ── Audio fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def silence_pcm16() -> bytes:
    """256 samples of silence as PCM16 little-endian bytes."""
    return b"\x00\x00" * 256


@pytest.fixture
def speech_pcm16() -> bytes:
    """Simulate speech-like PCM16 data (non-zero amplitude)."""
    import struct

    samples = [int(32767 * 0.3) for _ in range(480)]  # 30ms at 16kHz
    return struct.pack(f"<{len(samples)}h", *samples)


@pytest.fixture
def stereo_pcm16(speech_pcm16: bytes, silence_pcm16: bytes) -> bytes:
    """Interleaved stereo: L=speech (mic), R=silence (tab)."""
    import struct

    mic_samples = list(struct.unpack("<480h", speech_pcm16[:960]))
    tab_samples = [0] * 480
    interleaved = []
    for m, t in zip(mic_samples, tab_samples, strict=True):
        interleaved.extend([m, t])
    return struct.pack(f"<{len(interleaved)}h", *interleaved)


# ── WebSocket binary frame fixtures ───────────────────────────────────────


@pytest.fixture
def audio_frame(speech_pcm16: bytes) -> bytes:
    """Binary audio frame: 5-byte header (seq=1, channel=0) + PCM16."""
    import struct

    header = struct.pack("<IB", 1, 0)  # seq=1, channel=0 (audio)
    return header + speech_pcm16


@pytest.fixture
def control_frame() -> bytes:
    """Binary control frame: 5-byte header (seq=1, channel=1) + JSON."""
    import json
    import struct

    payload = json.dumps(
        {
            "type": "session_start",
            "session_id": "test-session-id",
            "kb_id": "test-kb-id",
        }
    ).encode()
    header = struct.pack("<IB", 1, 1)  # seq=1, channel=1 (control)
    return header + payload
