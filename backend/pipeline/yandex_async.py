"""Yandex SpeechKit v3 async file recognition via gRPC."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.logger import logger

_MAX_CONTENT_BYTES = 50 * 1024 * 1024  # 50 MB

# Proto stubs have internal cross-imports (e.g. yandex.cloud.ai.stt.v3).
# Add yandexstt_async to sys.path so those imports resolve.
_PROTO_DIR = str(Path(__file__).parent / "yandexstt_async")
if _PROTO_DIR not in sys.path:
    sys.path.insert(0, _PROTO_DIR)


@dataclass
class TimedUtterance:
    """Single utterance with timing information from async recognition."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float = 1.0


@dataclass
class AsyncRecognitionResult:
    """Result of async file recognition for one channel."""

    utterances: list[TimedUtterance] = field(default_factory=list)


class YandexAsyncRecognizer:
    """Yandex SpeechKit v3 async file recognition via gRPC.

    Sends a WAV file to AsyncRecognizer.RecognizeFile, polls for result,
    and parses utterances with timestamps.
    """

    GRPC_HOST = "stt.api.cloud.yandex.net:443"
    POLL_BACKOFF = [1, 2, 4, 8, 8, 8, 8, 8, 8]  # sum = 55s
    MAX_CONTENT_BYTES = _MAX_CONTENT_BYTES

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def recognize(self, wav_bytes: bytes) -> AsyncRecognitionResult:
        """Send WAV to Yandex async API, poll for result, parse utterances.

        Raises ValueError if content exceeds 50 MB.
        """
        if len(wav_bytes) > _MAX_CONTENT_BYTES:
            msg = f"Content size {len(wav_bytes)} exceeds {_MAX_CONTENT_BYTES} limit"
            raise ValueError(msg)

        import grpc
        import grpc.aio

        from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import (
            stt_pb2 as async_stt_pb2,
        )
        from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import (
            stt_service_pb2_grpc as async_stt_grpc,
        )

        ssl_cred = grpc.ssl_channel_credentials()
        options = [("grpc.max_send_message_length", 55 * 1024 * 1024)]
        metadata = (("authorization", f"Api-Key {self._api_key}"),)

        async with grpc.aio.secure_channel(
            self.GRPC_HOST, ssl_cred, options=options
        ) as channel:
            stub = async_stt_grpc.AsyncRecognizerStub(channel)

            request = async_stt_pb2.RecognizeFileRequest(
                content=wav_bytes,
                recognition_model=async_stt_pb2.RecognitionModelOptions(
                    model="general",
                    audio_format=async_stt_pb2.AudioFormatOptions(
                        container_audio=async_stt_pb2.ContainerAudio(
                            container_audio_type=async_stt_pb2.ContainerAudio.WAV
                        )
                    ),
                    audio_processing_type=async_stt_pb2.RecognitionModelOptions.FULL_DATA,
                    language_restriction=async_stt_pb2.LanguageRestrictionOptions(
                        restriction_type=async_stt_pb2.LanguageRestrictionOptions.WHITELIST,
                        language_code=["ru-RU"],
                    ),
                ),
            )

            operation = await stub.RecognizeFile(request, metadata=metadata)
            logger.info(f"Yandex async recognition started: operation={operation.id}")

            chunks = await self._poll_operation(stub, operation.id, metadata)
            return self._parse_chunks(chunks)

    async def _poll_operation(
        self,
        stub: Any,
        operation_id: str,
        metadata: tuple[tuple[str, str], ...],
    ) -> list[Any]:
        """Poll GetRecognition until done or timeout."""
        from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import (
            stt_pb2 as async_stt_pb2,
        )

        for delay in self.POLL_BACKOFF:
            await asyncio.sleep(delay)
            request = async_stt_pb2.GetRecognitionRequest(operation_id=operation_id)
            try:
                response = stub.GetRecognition(request, metadata=metadata)
                chunks: list[Any] = []
                async for chunk in response:
                    chunks.append(chunk)
                if chunks:
                    logger.info(f"Yandex async recognition done: {len(chunks)} chunks")
                    return chunks
            except Exception as exc:
                logger.warning(f"Yandex async poll error: {exc!r}")
                continue

        logger.error(f"Yandex async polling timed out for operation {operation_id}")
        return []

    def _parse_chunks(self, chunks: list[Any]) -> AsyncRecognitionResult:
        """Parse recognition response chunks into TimedUtterance list."""
        utterances: list[TimedUtterance] = []
        for chunk in chunks:
            event = chunk.WhichOneof("Event")
            if event in ("final", "final_refinement"):
                final = getattr(chunk, event)
                if event == "final_refinement":
                    final = final.normalized_text
                for alt in final.alternatives[:1]:
                    text = alt.text
                    if not text:
                        continue
                    words = (
                        list(alt.words) if hasattr(alt, "words") and alt.words else []
                    )
                    if words:
                        start_ms = int(words[0].start_time_ms)
                        end_ms = int(words[-1].end_time_ms)
                    else:
                        start_ms = 0
                        end_ms = 0
                    confidence = (
                        float(alt.confidence) if hasattr(alt, "confidence") else 1.0
                    )
                    utterances.append(
                        TimedUtterance(
                            text=text,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            confidence=confidence,
                        )
                    )
        return AsyncRecognitionResult(utterances=utterances)
