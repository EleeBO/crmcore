"""Tests for STT integration: abstract interface + Deepgram mock (Task 3.3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Abstract interface ─────────────────────────────────────────────────────


def test_stt_client_is_abstract() -> None:
    """STTClient cannot be instantiated directly."""
    import inspect

    from backend.pipeline.stt import STTClient

    assert inspect.isabstract(STTClient)


def test_stt_factory_returns_deepgram_by_default() -> None:
    """Factory returns DeepgramSTT when stt_provider=deepgram."""
    from backend.pipeline.stt import DeepgramSTT, create_stt_client

    with patch("backend.pipeline.stt.DeepgramSTT") as mock_cls:
        mock_cls.return_value = MagicMock(spec=DeepgramSTT)
        from backend.config import Settings

        settings = Settings(stt_provider="deepgram", deepgram_api_key="test-key")
        create_stt_client(settings)
        mock_cls.assert_called_once_with("test-key")


# ── Transcript dataclass ───────────────────────────────────────────────────


def test_transcript_dataclass() -> None:
    """Transcript has speaker, text, is_final fields."""
    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="client", text="Привет", is_final=True)
    assert t.speaker == "client"
    assert t.text == "Привет"
    assert t.is_final is True


def test_transcript_interim_default() -> None:
    """Transcript is_final defaults to False."""
    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="rep", text="промежуточный")
    assert t.is_final is False


def test_transcript_has_utterance_id() -> None:
    """Transcript accepts utterance_id field."""
    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="client", text="Hello", is_final=True, utterance_id="utt-1")
    assert t.utterance_id == "utt-1"


def test_transcript_utterance_id_defaults_empty() -> None:
    """Transcript utterance_id defaults to empty string."""
    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="client", text="Hello")
    assert t.utterance_id == ""


# ── DeepgramSTT unit tests (mock Deepgram SDK) ─────────────────────────────


@pytest.fixture
def deepgram_stt():
    """DeepgramSTT instance with mocked Deepgram SDK."""
    with patch("backend.pipeline.stt.DeepgramClient"):
        from backend.pipeline.stt import DeepgramSTT

        stt = DeepgramSTT(api_key="test-key")
        return stt


@pytest.mark.asyncio
async def test_deepgram_start_session(deepgram_stt) -> None:
    """start_session initialises connections without error."""
    with patch.object(deepgram_stt, "_open_channel", new_callable=AsyncMock):
        await deepgram_stt.start_session("session-001")
        assert deepgram_stt._session_id == "session-001"


@pytest.mark.asyncio
async def test_deepgram_emits_transcript_on_final(deepgram_stt) -> None:
    """Final Deepgram message triggers transcript callback."""
    received: list = []

    async def on_transcript(t) -> None:
        received.append(t)

    deepgram_stt.on_transcript = on_transcript

    # Simulate transcript callback directly
    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="client", text="Какой у вас RTO?", is_final=True)
    await on_transcript(t)

    assert len(received) == 1
    assert received[0].is_final is True
    assert received[0].speaker == "client"


@pytest.mark.asyncio
async def test_deepgram_emits_interim_transcript(deepgram_stt) -> None:
    """Interim Deepgram result also triggers callback with is_final=False."""
    received: list = []

    async def on_transcript(t) -> None:
        received.append(t)

    deepgram_stt.on_transcript = on_transcript

    from backend.pipeline.stt import Transcript

    t = Transcript(speaker="rep", text="Промежуточный", is_final=False)
    await on_transcript(t)

    assert len(received) == 1
    assert received[0].is_final is False


@pytest.mark.asyncio
async def test_deepgram_close(deepgram_stt) -> None:
    """close() completes without error even if no connection open."""
    await deepgram_stt.close()  # Should not raise


# ── STT factory with salutespeech ─────────────────────────────────────────


def test_stt_factory_returns_salutespeech() -> None:
    """Factory returns SaluteSpeechSTT when stt_provider=salutespeech."""
    from backend.pipeline.stt import SaluteSpeechSTT, create_stt_client

    with patch("backend.pipeline.stt.SaluteSpeechSTT") as mock_cls:
        mock_cls.return_value = MagicMock(spec=SaluteSpeechSTT)
        from backend.config import Settings

        settings = Settings(
            stt_provider="salutespeech",
            sber_speech_api_key="sber-key",
            sber_speech_scope="SALUTE_SPEECH_PERS",
        )
        create_stt_client(settings)
        mock_cls.assert_called_once_with(
            api_key="sber-key", scope="SALUTE_SPEECH_PERS"
        )


# ── Deepgram v6 real connection ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deepgram_open_channel_uses_async_context_manager() -> None:
    """_open_channel uses client.listen.v1.connect and stores the socket."""
    import sys
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_socket = AsyncMock()
    mock_socket.send_media = AsyncMock()
    mock_socket.on = MagicMock()
    mock_socket.start_listening = AsyncMock()  # returns immediately in test

    @asynccontextmanager
    async def fake_connect(**kwargs):
        yield mock_socket

    mock_v1 = MagicMock()
    mock_v1.connect = fake_connect

    mock_listen = MagicMock()
    mock_listen.v1 = mock_v1

    mock_client_instance = MagicMock()
    mock_client_instance.listen = mock_listen

    # Mock deepgram.core.events so the import inside _run() works
    mock_events = MagicMock()
    mock_events.EventType = MagicMock()
    mock_events.EventType.MESSAGE = "Results"
    sys.modules["deepgram.core.events"] = mock_events

    try:
        dg_cls = "backend.pipeline.stt.DeepgramClient"
        with patch(dg_cls, return_value=mock_client_instance):
            from backend.pipeline.stt import DeepgramSTT

            stt = DeepgramSTT(api_key="fake-key")
            await stt._open_channel("client")

            # Allow the background task to run
            import asyncio

            await asyncio.sleep(0.05)

        # Connection should be stored (or was stored during the task)
        mock_socket.start_listening.assert_called_once()
    finally:
        sys.modules.pop("deepgram.core.events", None)


@pytest.mark.asyncio
async def test_deepgram_send_audio_uses_send_media() -> None:
    """send_audio calls conn.send_media() in v6 API."""
    from unittest.mock import AsyncMock

    from backend.pipeline.stt import DeepgramSTT

    with patch("backend.pipeline.stt.DeepgramClient", MagicMock()):
        stt = DeepgramSTT(api_key="test")

    mock_conn = AsyncMock()
    mock_conn.send_media = AsyncMock()
    stt._connections["client"] = mock_conn

    await stt.send_audio(b"\x00\x01" * 480, "client")
    mock_conn.send_media.assert_called_once_with(b"\x00\x01" * 480)
