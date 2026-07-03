"""STT abstraction layer: abstract STTClient + Deepgram/SaluteSpeech implementations."""

from __future__ import annotations

import asyncio
import pathlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from backend.logger import logger

# Re-export Transcript for backward compatibility — importers can still use
# `from backend.pipeline.stt import Transcript`
from backend.pipeline.types import Transcript  # noqa: F401

# Russian Trusted Root CA — required for SaluteSpeech gRPC (smartspeech.sber.ru)
_CERTS_DIR = pathlib.Path(__file__).parent.parent / "certs"
_ROOT_CA_PATH = _CERTS_DIR / "russian_trusted_root_ca.pem"


def _load_root_ca() -> bytes | None:
    """Load Russian Trusted Root CA for SaluteSpeech gRPC SSL.

    Returns None if the cert file is missing (e.g. system CA bundle
    already includes it), letting gRPC fall back to defaults.
    """
    if _ROOT_CA_PATH.exists():
        return _ROOT_CA_PATH.read_bytes()
    logger.warning(
        f"Russian Trusted Root CA not found at {_ROOT_CA_PATH} — using system defaults"
    )
    return None


if TYPE_CHECKING:
    from backend.config import Settings

# Lazy import — Deepgram SDK may not be installed in all environments
try:
    from deepgram import DeepgramClient  # type: ignore[import]
except ImportError:
    DeepgramClient = None  # type: ignore[assignment,misc]


TranscriptCallback = Callable[[Transcript], Coroutine[Any, Any, None]]
ErrorCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class STTClient(ABC):
    """Abstract Speech-to-Text client."""

    @abstractmethod
    async def start_session(self, session_id: str) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes, channel: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def flush(self, timeout: float = 5.0) -> None:
        """Signal end-of-audio and wait for pending finals.

        Half-closes the streams so the server sends remaining finals,
        then waits up to *timeout* seconds for them to arrive.
        Default implementation delegates to ``close()``.
        """
        await self.close()

    # Injected callbacks — set after construction
    on_transcript: TranscriptCallback | None = None
    on_error: ErrorCallback | None = None


# ---------------------------------------------------------------------------
# DualChannelSTT — shared base for two-channel STT providers
# ---------------------------------------------------------------------------


class DualChannelSTT(STTClient):
    """Base for STT providers running two parallel channels (client + rep).

    Provides shared state management, error deduplication, queue-based
    audio routing, and lifecycle management so providers only implement
    ``_open_channel()`` with their protocol-specific logic.
    """

    def __init__(self) -> None:
        self.on_transcript: TranscriptCallback | None = None
        self.on_error: ErrorCallback | None = None

        # Shared state — not duplicated per provider
        self._closing: bool = False
        self._error_reported: bool = False
        self._permanent_error: bool = False
        self._queues: dict[str, asyncio.Queue[bytes | None] | None] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._session_id: str = ""

    async def report_error(self, code: str, message: str) -> None:
        """Thread-safe (asyncio) error reporting with deduplication.

        Called from any channel — guarantees a single ``on_error`` invocation.
        """
        if self._error_reported or self._closing or not self.on_error:
            return
        self._error_reported = True
        self._permanent_error = True
        await self.on_error(code, message)

    async def start_session(self, session_id: str) -> None:
        self._session_id = session_id
        self._closing = False
        self._error_reported = False
        self._permanent_error = False
        for channel in ("client", "rep"):
            await self._open_channel(channel)

    @abstractmethod
    async def _open_channel(self, channel: str) -> None:
        """Provider-specific: open gRPC/WS stream for a channel."""
        ...

    async def send_audio(self, chunk: bytes, channel: str) -> None:
        q = self._queues.get(channel)
        if q is not None:
            await q.put(chunk)

    async def flush(self, timeout: float = 5.0) -> None:
        """Half-close streams and wait for pending finals.

        Sends ``None`` to each queue so the gRPC request generator
        finishes (half-close).  The server then sends any buffered
        finals before closing its side.  We wait up to *timeout*
        seconds for the background tasks to finish naturally.
        """
        self._closing = True
        # Signal end-of-audio to each channel
        for q in self._queues.values():
            if q is not None:
                await q.put(None)
        # Wait for tasks to finish (server sends remaining finals)
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks.values(),
                timeout=timeout,
            )
            # Cancel anything still running after the grace period
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                logger.info(
                    f"STT flush: {len(done)} channels finished, "
                    f"{len(pending)} timed out after {timeout}s"
                )
            else:
                logger.info(
                    f"STT flush: all {len(done)} channels finished within {timeout}s"
                )
        self._tasks.clear()
        self._queues.clear()

    async def close(self) -> None:
        self._closing = True
        for q in self._queues.values():
            if q is not None:
                await q.put(None)
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._queues.clear()


# ---------------------------------------------------------------------------
# DeepgramSTT
# ---------------------------------------------------------------------------


class DeepgramSTT(DualChannelSTT):
    """Deepgram Nova-3 WebSocket streaming STT."""

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._connections: dict[str, Any] = {}

        if DeepgramClient is not None:
            self._client = DeepgramClient(api_key=api_key)
        else:
            self._client = None

    async def start_session(self, session_id: str) -> None:
        await super().start_session(session_id)
        logger.info(f"Deepgram STT session started: {session_id}")

    async def _open_channel(self, channel: str) -> None:
        """Open a Deepgram WebSocket connection for the given channel."""
        if self._client is None:
            logger.warning(
                f"Deepgram SDK not available; channel {channel} produces no transcripts"
            )
            self._connections[channel] = None
            return

        speaker = "client" if channel == "client" else "rep"

        async def _run() -> None:
            try:
                async with self._client.listen.v1.connect(
                    model="nova-3",
                    language="ru",
                    interim_results="true",
                    endpointing="300",
                    encoding="linear16",
                    sample_rate="16000",
                ) as conn:
                    self._connections[channel] = conn
                    logger.info(f"Deepgram channel connected: {channel}")

                    from deepgram.core.events import EventType

                    async def _on_message(msg: Any) -> None:
                        try:
                            # ListenV1Results has .channel.alternatives[0].transcript
                            alts = msg.channel.alternatives
                            text: str = alts[0].transcript if alts else ""
                            is_final: bool = bool(getattr(msg, "is_final", False))
                            if text and self.on_transcript is not None:
                                t = Transcript(
                                    speaker=speaker, text=text, is_final=is_final
                                )
                                await self.on_transcript(t)
                        except Exception as exc:
                            logger.debug(f"Deepgram msg parse [{channel}]: {exc!r}")

                    conn.on(EventType.MESSAGE, _on_message)
                    await conn.start_listening()

            except Exception as exc:
                logger.error(f"Deepgram channel [{channel}] error: {exc!r}")
            finally:
                self._connections[channel] = None
                logger.debug(f"Deepgram channel closed: {channel}")

        task: asyncio.Task[None] = asyncio.create_task(_run())
        self._tasks[channel] = task

    async def send_audio(self, chunk: bytes, channel: str) -> None:
        """Override: send directly to Deepgram connection (not via queue)."""
        conn = self._connections.get(channel)
        if conn is None:
            return
        try:
            await conn.send_media(chunk)
        except Exception as exc:
            logger.warning(f"Deepgram send_audio failed [{channel}]: {exc}")

    async def close(self) -> None:
        self._closing = True
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._connections.clear()
        logger.info(f"Deepgram STT closed: {self._session_id}")


# ---------------------------------------------------------------------------
# SaluteSpeech helpers
# ---------------------------------------------------------------------------


class _PermanentSTTError(Exception):
    """Non-retryable STT error (e.g. balance exhausted, auth failure)."""


def _classify_grpc_error(exc: Exception) -> str | None:
    """Return an error code if the gRPC error is permanent, else None."""
    try:
        import grpc
    except ImportError:
        return None

    if not isinstance(exc, grpc.RpcError):
        return None

    code = exc.code()  # type: ignore[union-attr]
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return "STT_BALANCE_EXHAUSTED"
    if code in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
        return "STT_AUTH_FAILED"
    return None


# Maximum reconnect attempts per channel before giving up
_MAX_RECONNECT_ATTEMPTS = 5
_RECONNECT_DELAY_S = 2.0
# no_speech_timeout: wait up to 20s of silence before server sends EOU
_NO_SPEECH_TIMEOUT_S = 20
# Maximum retries for HTTP 429 rate limiting during token refresh
_MAX_TOKEN_RETRIES = 3


# ---------------------------------------------------------------------------
# SaluteSpeechSTT
# ---------------------------------------------------------------------------


class SaluteSpeechSTT(DualChannelSTT):
    """SaluteSpeech gRPC streaming STT — real implementation with auto-reconnect."""

    TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GRPC_HOST = "smartspeech.sber.ru:443"

    def __init__(self, api_key: str, scope: str = "SALUTE_SPEECH_PERS") -> None:
        super().__init__()
        self._api_key = api_key
        self._scope = scope
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_token(self) -> str:
        """Obtain or refresh OAuth access token (30-minute TTL).

        Uses ``asyncio.Lock`` to prevent concurrent token refresh from
        both channels (avoids duplicate HTTP requests and potential 429).
        Handles HTTP 429 as transient rate-limit (retry), not as balance error.
        """
        import uuid

        import httpx

        async with self._token_lock:
            # Check cache again — another task may have refreshed while waiting
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token

            # ngw.devices.sberbank.ru is signed by the Russian Trusted Root CA;
            # use the bundled PEM rather than disabling verification.
            verify: str | bool = str(_ROOT_CA_PATH) if _ROOT_CA_PATH.exists() else True

            for _attempt in range(_MAX_TOKEN_RETRIES):
                async with httpx.AsyncClient(verify=verify) as client:
                    resp = await client.post(
                        self.TOKEN_URL,
                        headers={
                            "Authorization": f"Basic {self._api_key}",
                            "RqUID": str(uuid.uuid4()),
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={"scope": self._scope},
                        timeout=10.0,
                    )

                    if resp.status_code == 402:
                        # Permanent — balance exhausted
                        msg = "SaluteSpeech: баланс исчерпан"
                        logger.error(msg)
                        await self.report_error("STT_BALANCE_EXHAUSTED", msg)
                        raise _PermanentSTTError(msg)

                    if resp.status_code == 429:
                        # Transient — rate limit, retry after delay
                        retry_after = int(resp.headers.get("Retry-After", "5"))
                        logger.warning(
                            f"SaluteSpeech rate limited, retry in {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if resp.status_code in (401, 403):
                        # Permanent — auth failure
                        msg = f"SaluteSpeech auth failed: HTTP {resp.status_code}"
                        logger.error(msg)
                        await self.report_error("STT_AUTH_FAILED", msg)
                        raise _PermanentSTTError(msg)

                    resp.raise_for_status()
                    data = resp.json()
                    self._token = data["access_token"]
                    self._token_expires_at = data["expires_at"] / 1000.0
                    logger.info("SaluteSpeech token acquired")
                    return self._token

            # Exhausted retries on 429
            msg = "SaluteSpeech: rate limited after retries"
            logger.error(msg)
            raise _PermanentSTTError(msg)

    async def start_session(self, session_id: str) -> None:
        # Pre-fetch token to fail fast on auth/balance errors
        await self._get_token()
        await super().start_session(session_id)
        logger.info(f"SaluteSpeech STT session started: {session_id}")

    async def _open_channel(self, channel: str) -> None:
        """Start a background task that maintains a gRPC streaming connection.

        Auto-reconnects on DEADLINE_EXCEEDED or other transient errors.
        """
        import grpc
        import grpc.aio
        from google.protobuf import duration_pb2

        from backend.pipeline.salutespeech import recognition_pb2, recognition_pb2_grpc

        speaker = channel

        async def _run() -> None:
            attempt = 0
            max_a = _MAX_RECONNECT_ATTEMPTS
            while attempt < max_a and not self._closing and not self._permanent_error:
                q: asyncio.Queue[bytes | None] = asyncio.Queue()
                self._queues[channel] = q
                try:
                    # Refresh token if needed (may have expired since session start)
                    current_token = await self._get_token()

                    root_ca = _load_root_ca()
                    ssl_cred = grpc.ssl_channel_credentials(root_certificates=root_ca)
                    token_cred = grpc.access_token_call_credentials(current_token)
                    cred = grpc.composite_channel_credentials(ssl_cred, token_cred)

                    async with grpc.aio.secure_channel(self.GRPC_HOST, cred) as ch:
                        stub = recognition_pb2_grpc.SmartSpeechStub(ch)

                        # Set generous no_speech_timeout so the server doesn't
                        # kill the stream during silence gaps in conversation
                        nst = duration_pb2.Duration(seconds=_NO_SPEECH_TIMEOUT_S)

                        async def _requests(
                            _nst: Any = nst,
                            _q: Any = q,
                        ) -> Any:
                            yield recognition_pb2.RecognitionRequest(
                                options=recognition_pb2.RecognitionOptions(
                                    audio_encoding=recognition_pb2.RecognitionOptions.PCM_S16LE,
                                    sample_rate=16000,
                                    language="ru-RU",
                                    enable_partial_results=True,
                                    enable_multi_utterance=True,
                                    no_speech_timeout=_nst,
                                )
                            )
                            while True:
                                chunk = await _q.get()
                                if chunk is None:
                                    return
                                yield recognition_pb2.RecognitionRequest(
                                    audio_chunk=chunk
                                )

                        if attempt > 0:
                            n = attempt + 1
                            logger.info(
                                f"SaluteSpeech [{channel}] reconnect attempt {n}"
                            )
                        else:
                            logger.info(f"SaluteSpeech channel [{channel}] connected")

                        async for resp in stub.Recognize(_requests()):
                            # Reset attempt counter on successful response
                            attempt = 0
                            is_final: bool = resp.eou
                            text: str = resp.results[0].text if resp.results else ""
                            if text and self.on_transcript is not None:
                                t = Transcript(
                                    speaker=speaker,
                                    text=text,
                                    is_final=is_final,
                                )
                                await self.on_transcript(t)

                except asyncio.CancelledError:
                    logger.debug(f"SaluteSpeech channel [{channel}] cancelled")
                    break
                except _PermanentSTTError:
                    # Already reported via report_error callback, don't retry
                    break
                except Exception as exc:
                    attempt += 1
                    if self._closing:
                        break

                    # Detect permanent gRPC errors
                    error_code = _classify_grpc_error(exc)
                    if error_code:
                        logger.error(
                            f"SaluteSpeech [{channel}] permanent error: {exc!r}"
                        )
                        await self.report_error(error_code, str(exc)[:200])
                        break

                    logger.warning(
                        f"SaluteSpeech [{channel}] error ({attempt}/{max_a}): {exc!r}"
                    )
                    if attempt < max_a:
                        await asyncio.sleep(_RECONNECT_DELAY_S)
                finally:
                    self._queues[channel] = None

            if attempt >= max_a:
                logger.error(f"SaluteSpeech [{channel}] gave up after {max_a} attempts")
                await self.report_error(
                    "STT_UNAVAILABLE",
                    f"SaluteSpeech: не удалось подключиться после {max_a} попыток",
                )

        task: asyncio.Task[None] = asyncio.create_task(_run())
        self._tasks[channel] = task

    async def close(self) -> None:
        await super().close()
        logger.info(f"SaluteSpeech STT closed: {self._session_id}")


# ---------------------------------------------------------------------------
# YandexSpeechKitSTT
# ---------------------------------------------------------------------------

# Yandex SpeechKit session limit: 5 min. Reconnect at 4.5 min.
_YANDEX_SESSION_MAX_S = 270


class YandexSpeechKitSTT(DualChannelSTT):
    """Yandex SpeechKit v3 gRPC streaming STT with auto-reconnect.

    Key differences from SaluteSpeech:
    - Auth: API key directly in gRPC metadata (no OAuth token).
    - SSL: standard certificates (no Russian Trusted Root CA).
    - Session limit: 5 minutes — auto-reconnect every 4.5 min.
    """

    GRPC_HOST = "stt.api.cloud.yandex.net:443"

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._utterance_counters: dict[str, int] = {}

    async def start_session(self, session_id: str) -> None:
        await super().start_session(session_id)
        logger.info(f"Yandex STT session started: {session_id}")

    async def _open_channel(self, channel: str) -> None:
        """Start a background task for gRPC streaming with session rotation."""
        import grpc
        import grpc.aio

        from backend.pipeline.yandexstt import stt_pb2, stt_pb2_grpc

        speaker = channel

        async def _run() -> None:
            attempt = 0
            max_a = _MAX_RECONNECT_ATTEMPTS
            while attempt < max_a and not self._closing and not self._permanent_error:
                q: asyncio.Queue[bytes | None] = asyncio.Queue()
                self._queues[channel] = q
                try:
                    ssl_cred = grpc.ssl_channel_credentials()
                    metadata = (("authorization", f"Api-Key {self._api_key}"),)

                    async with grpc.aio.secure_channel(self.GRPC_HOST, ssl_cred) as ch:
                        stub = stt_pb2_grpc.RecognizerStub(ch)
                        session_start = time.monotonic()

                        async def _requests(
                            _q: asyncio.Queue[bytes | None] = q,
                        ) -> Any:
                            # First message: session options
                            yield stt_pb2.StreamingRequest(
                                session_options=stt_pb2.StreamingOptions(
                                    recognition_model=stt_pb2.RecognitionModelOptions(
                                        model="general:rc",
                                        audio_format=stt_pb2.AudioFormatOptions(
                                            raw_audio=stt_pb2.RawAudio(
                                                audio_encoding=stt_pb2.LINEAR16_PCM,
                                                sample_rate_hertz=16000,
                                                audio_channel_count=1,
                                            )
                                        ),
                                        language_restriction=stt_pb2.LanguageRestrictionOptions(
                                            restriction_type=stt_pb2.LanguageRestrictionOptions.WHITELIST,
                                            language_code=["ru-RU"],
                                        ),
                                        audio_processing_type=stt_pb2.REAL_TIME,
                                    ),
                                )
                            )
                            # Audio chunks
                            while True:
                                chunk = await _q.get()
                                if chunk is None:
                                    return
                                yield stt_pb2.StreamingRequest(
                                    chunk=stt_pb2.AudioChunk(data=chunk)
                                )

                        if attempt > 0:
                            logger.info(
                                f"Yandex [{channel}] reconnect attempt {attempt + 1}"
                            )
                        else:
                            logger.info(f"Yandex channel [{channel}] connected")

                        call = stub.RecognizeStreaming(_requests(), metadata=metadata)
                        async for resp in call:
                            attempt = 0
                            event = resp.WhichOneof("Event")

                            if event == "partial":
                                alts = resp.partial.alternatives
                                text = alts[0].text if alts else ""
                                if text and self.on_transcript:
                                    await self.on_transcript(
                                        Transcript(
                                            speaker=speaker,
                                            text=text,
                                            is_final=False,
                                        )
                                    )
                            elif event == "final":
                                alts = resp.final.alternatives
                                text = alts[0].text if alts else ""
                                if text and self.on_transcript:
                                    self._utterance_counters[channel] = (
                                        self._utterance_counters.get(channel, 0) + 1
                                    )
                                    utt_id = (
                                        f"{channel}-{self._utterance_counters[channel]}"
                                    )
                                    await self.on_transcript(
                                        Transcript(
                                            speaker=speaker,
                                            text=text,
                                            is_final=True,
                                            utterance_id=utt_id,
                                        )
                                    )
                            elif event == "final_refinement":
                                update = resp.final_refinement.normalized_text
                                alts = update.alternatives
                                text = alts[0].text if alts else ""
                                if text and self.on_transcript:
                                    cnt = self._utterance_counters.get(channel, 0)
                                    utt_id = f"{channel}-{cnt}"
                                    await self.on_transcript(
                                        Transcript(
                                            speaker=speaker,
                                            text=text,
                                            is_final=True,
                                            utterance_id=utt_id,
                                        )
                                    )

                            # Session rotation before 5-min limit
                            elapsed = time.monotonic() - session_start
                            if elapsed >= _YANDEX_SESSION_MAX_S:
                                logger.info(
                                    f"Yandex [{channel}] session "
                                    f"rotation ({elapsed:.0f}s)"
                                )
                                break

                except asyncio.CancelledError:
                    logger.debug(f"Yandex channel [{channel}] cancelled")
                    break
                except Exception as exc:
                    attempt += 1
                    if self._closing:
                        break

                    error_code = _classify_grpc_error(exc)
                    if error_code:
                        logger.error(f"Yandex [{channel}] permanent error: {exc!r}")
                        await self.report_error(error_code, str(exc)[:200])
                        break

                    logger.warning(
                        f"Yandex [{channel}] error ({attempt}/{max_a}): {exc!r}"
                    )
                    if attempt < max_a:
                        await asyncio.sleep(_RECONNECT_DELAY_S)
                finally:
                    self._queues[channel] = None

            if attempt >= max_a:
                logger.error(f"Yandex [{channel}] gave up after {max_a} attempts")
                await self.report_error(
                    "STT_UNAVAILABLE",
                    f"Yandex SpeechKit: не удалось подключиться после {max_a} попыток",
                )

        task: asyncio.Task[None] = asyncio.create_task(_run())
        self._tasks[channel] = task

    async def close(self) -> None:
        await super().close()
        logger.info(f"Yandex STT closed: {self._session_id}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_stt_client(settings: Settings, provider: str | None = None) -> STTClient:
    """Factory: create the correct STT client based on settings.

    Args:
        settings: Application settings.
        provider: Override ``settings.stt_provider`` (e.g. from session_start).
    """
    p = provider or settings.stt_provider
    if p == "salutespeech":
        return SaluteSpeechSTT(
            api_key=settings.sber_speech_api_key,
            scope=settings.sber_speech_scope,
        )
    if p == "yandex":
        return YandexSpeechKitSTT(
            api_key=settings.yandex_speechkit_api_key,
        )
    return DeepgramSTT(settings.deepgram_api_key)
