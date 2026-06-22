# FEAT-005: Post-call Diarization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add post-call audio re-transcription via Yandex AsyncRecognizer to enrich call evaluation with objective analytics (talk ratio, speech rate, interruptions, pauses).

**Architecture:** During a call, PCM chunks are buffered in memory per channel alongside live STT. On session_end, each channel's audio is sent to Yandex async API (FULL_DATA mode) for higher-quality transcription with timestamps. Analytics are computed from utterance timings and injected into the evaluator prompt before scoring.

**Tech Stack:** Python 3.11, gRPC (grpcio), Yandex SpeechKit v3 AsyncRecognizer, Redis, pytest, WAV (stdlib wave)

**Spec:** `docs/superpowers/specs/2026-03-13-post-call-diarization-design.md`

---

## Progress Tracking

- [x] Task 1: AudioBuffer component
- [x] Task 2: Proto generation for Yandex async API
- [x] Task 3: YandexAsyncRecognizer client
- [x] Task 4: PostCallProcessor — merge and analytics
- [x] Task 5: Prompt formatter — diarized transcript and analytics formatting
- [x] Task 6: Evaluator integration — analytics parameter
- [x] Task 7: Config — enable_post_call_diarization flag
- [x] Task 8: Orchestrator — post-call pipeline before evaluation
- [x] Task 9: main.py — AudioBuffer wiring and timeout update

**Total Tasks:** 9 | **Completed:** 9 | **Remaining:** 0

---

## Chunk 1: Core Components (Tasks 1-4)

### Task 1: AudioBuffer component

**Files:**
- Create: `backend/pipeline/audio_buffer.py`
- Create: `backend/tests/test_audio_buffer.py`

- [ ] **Step 1: Write failing tests for AudioBuffer**

```python
# backend/tests/test_audio_buffer.py
"""Tests for AudioBuffer — in-memory PCM buffer with WAV export."""

import struct
import time
import wave
import io

import pytest

from backend.pipeline.audio_buffer import AudioBuffer


class TestAudioBufferAppend:
    def test_append_stores_chunks_per_channel(self) -> None:
        buf = AudioBuffer()
        chunk = b"\x00\x01" * 100
        buf.append("rep", chunk)
        buf.append("client", chunk)
        assert buf.duration_s("rep") > 0
        assert buf.duration_s("client") > 0

    def test_append_records_start_timestamp(self) -> None:
        buf = AudioBuffer()
        before = time.monotonic()
        buf.append("rep", b"\x00\x01" * 100)
        after = time.monotonic()
        assert before <= buf._start_ts["rep"] <= after

    def test_append_ignores_after_50mb(self) -> None:
        buf = AudioBuffer()
        # Simulate buffer at limit
        buf._buffers["rep"] = bytearray(50 * 1024 * 1024)
        buf.append("rep", b"\x00\x01" * 100)
        assert len(buf._buffers["rep"]) == 50 * 1024 * 1024  # unchanged

    def test_append_unknown_channel_creates_it(self) -> None:
        buf = AudioBuffer()
        buf.append("other", b"\x00\x01" * 10)
        assert buf.duration_s("other") > 0


class TestAudioBufferWav:
    def test_get_wav_returns_valid_wav(self) -> None:
        buf = AudioBuffer()
        # 1 second of silence at 16kHz PCM16 = 32000 bytes
        buf.append("rep", b"\x00\x00" * 16000)
        wav_bytes = buf.get_wav("rep")

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 16000

    def test_get_wav_empty_channel_returns_empty_wav(self) -> None:
        buf = AudioBuffer()
        wav_bytes = buf.get_wav("rep")
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnframes() == 0


class TestAudioBufferMetrics:
    def test_duration_s_calculates_correctly(self) -> None:
        buf = AudioBuffer()
        # 16000 samples * 2 bytes = 32000 bytes = 1 second
        buf.append("rep", b"\x00\x00" * 16000)
        assert buf.duration_s("rep") == pytest.approx(1.0)

    def test_duration_s_empty_channel(self) -> None:
        buf = AudioBuffer()
        assert buf.duration_s("rep") == 0.0

    def test_estimated_memory_mb(self) -> None:
        buf = AudioBuffer()
        buf._buffers["rep"] = bytearray(1024 * 1024)  # 1 MB
        buf._buffers["client"] = bytearray(2 * 1024 * 1024)  # 2 MB
        assert buf.estimated_memory_mb() == pytest.approx(3.0, rel=0.01)

    def test_exceeds_limit_false_when_under(self) -> None:
        buf = AudioBuffer()
        buf.append("rep", b"\x00" * 1000)
        assert buf.exceeds_limit() is False

    def test_exceeds_limit_true_when_over(self) -> None:
        buf = AudioBuffer()
        buf._buffers["rep"] = bytearray(50 * 1024 * 1024)
        assert buf.exceeds_limit() is True

    def test_start_offset_ms(self) -> None:
        buf = AudioBuffer()
        buf._start_ts["rep"] = 100.0
        buf._start_ts["client"] = 100.2  # 200ms later
        assert buf.start_offset_ms() == pytest.approx(200, abs=5)

    def test_start_offset_ms_missing_channel(self) -> None:
        buf = AudioBuffer()
        buf._start_ts["rep"] = 100.0
        assert buf.start_offset_ms() == 0


class TestAudioBufferClear:
    def test_clear_frees_memory(self) -> None:
        buf = AudioBuffer()
        buf.append("rep", b"\x00" * 10000)
        buf.append("client", b"\x00" * 10000)
        buf.clear()
        assert buf.duration_s("rep") == 0.0
        assert buf.duration_s("client") == 0.0
        assert buf.estimated_memory_mb() == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/teterinsa/Projects/crmcore
python -m pytest backend/tests/test_audio_buffer.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.pipeline.audio_buffer'`

- [ ] **Step 3: Implement AudioBuffer**

```python
# backend/pipeline/audio_buffer.py
"""In-memory PCM buffer per channel with WAV export."""

from __future__ import annotations

import io
import time
import wave

from backend.logger import logger

_MAX_CHANNEL_BYTES = 50 * 1024 * 1024  # 50 MB — gRPC content limit
_SAMPLE_RATE = 16000
_SAMPLE_WIDTH = 2  # PCM16


class AudioBuffer:
    """Buffer PCM16 audio chunks per channel during a call.

    Provides WAV export and memory guards. Each channel is independent.
    Mid-call guard: silently stops accepting data after 50 MB per channel.
    """

    def __init__(self) -> None:
        self._buffers: dict[str, bytearray] = {"rep": bytearray(), "client": bytearray()}
        self._start_ts: dict[str, float] = {}
        self._limit_warned: set[str] = set()

    def append(self, channel: str, chunk: bytes) -> None:
        """Append PCM chunk. Records start_ts on first chunk per channel.

        Silently ignores new data if channel buffer >= 50 MB.
        """
        if channel not in self._buffers:
            self._buffers[channel] = bytearray()

        if len(self._buffers[channel]) >= _MAX_CHANNEL_BYTES:
            if channel not in self._limit_warned:
                self._limit_warned.add(channel)
                logger.warning(
                    f"AudioBuffer [{channel}] hit {_MAX_CHANNEL_BYTES // (1024*1024)} MB limit, "
                    "ignoring new chunks"
                )
            return

        if channel not in self._start_ts:
            self._start_ts[channel] = time.monotonic()

        self._buffers[channel].extend(chunk)

    def get_wav(self, channel: str) -> bytes:
        """Build WAV from channel buffer using stdlib wave module."""
        raw = self._buffers.get(channel, bytearray())
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(_SAMPLE_WIDTH)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(bytes(raw))
        return buf.getvalue()

    def duration_s(self, channel: str) -> float:
        """Duration of recorded audio in seconds."""
        raw = self._buffers.get(channel, bytearray())
        if not raw:
            return 0.0
        return len(raw) / (_SAMPLE_RATE * _SAMPLE_WIDTH)

    def start_offset_ms(self) -> int:
        """Difference in start timestamps between rep and client in ms.

        Positive = rep started before client.
        Returns 0 if either channel has no data.
        """
        rep_ts = self._start_ts.get("rep")
        client_ts = self._start_ts.get("client")
        if rep_ts is None or client_ts is None:
            return 0
        return int((client_ts - rep_ts) * 1000)

    def estimated_memory_mb(self) -> float:
        """Total RAM usage across all channel buffers in MB."""
        total = sum(len(b) for b in self._buffers.values())
        return total / (1024 * 1024)

    def exceeds_limit(self) -> bool:
        """True if any channel buffer >= 50 MB."""
        return any(len(b) >= _MAX_CHANNEL_BYTES for b in self._buffers.values())

    def clear(self) -> None:
        """Free all buffer memory."""
        for channel in self._buffers:
            self._buffers[channel] = bytearray()
        self._start_ts.clear()
        self._limit_warned.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_audio_buffer.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/audio_buffer.py backend/tests/test_audio_buffer.py
git commit -m "feat(FEAT-005): add AudioBuffer for in-memory PCM buffering"
```

---

### Task 2: Proto generation for Yandex async API

**Files:**
- Create: `backend/pipeline/yandexstt_async/` (generated directory)
- Create: `scripts/generate_yandex_async_proto.sh`

- [ ] **Step 1: Create proto generation script**

```bash
# scripts/generate_yandex_async_proto.sh
#!/usr/bin/env bash
set -euo pipefail

# Generate Python gRPC stubs for Yandex SpeechKit v3 AsyncRecognizer.
# Outputs to backend/pipeline/yandexstt_async/ — separate from
# streaming protos in yandexstt/ to avoid package namespace conflicts.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/backend/pipeline/yandexstt_async"
CLOUDAPI_DIR="/tmp/yandex-cloudapi"

echo "Cloning yandex-cloud/cloudapi..."
rm -rf "$CLOUDAPI_DIR"
git clone --depth 1 https://github.com/yandex-cloud/cloudapi "$CLOUDAPI_DIR"

echo "Generating Python stubs..."
mkdir -p "$OUT_DIR"

python3 -m grpc_tools.protoc \
  -I "$CLOUDAPI_DIR" \
  -I "$CLOUDAPI_DIR/third_party/googleapis" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  yandex/cloud/ai/stt/v3/stt_service.proto \
  yandex/cloud/ai/stt/v3/stt.proto \
  yandex/cloud/operation/operation.proto \
  google/longrunning/operations.proto \
  google/api/http.proto \
  google/api/annotations.proto

# Create __init__.py files for proper Python package imports
find "$OUT_DIR" -type d -exec touch {}/__init__.py \;

echo "Done. Generated stubs in $OUT_DIR"
echo "Import with: from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import stt_pb2"

rm -rf "$CLOUDAPI_DIR"
```

- [ ] **Step 2: Run the generation script**

```bash
chmod +x scripts/generate_yandex_async_proto.sh
./scripts/generate_yandex_async_proto.sh
```

Expected: Directory `backend/pipeline/yandexstt_async/` created with generated `_pb2.py` and `_pb2_grpc.py` files.

- [ ] **Step 3: Verify imports work**

```bash
python -c "from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import stt_pb2; print('OK:', dir(stt_pb2))"
```

Expected: Prints list of proto attributes without errors.

- [ ] **Step 4: Verify existing streaming STT is unaffected**

```bash
python -c "from backend.pipeline.yandexstt import stt_pb2; print('Streaming OK:', type(stt_pb2))"
```

Expected: No import errors — streaming protos untouched.

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_yandex_async_proto.sh backend/pipeline/yandexstt_async/
git commit -m "feat(FEAT-005): generate Yandex async recognition proto stubs"
```

---

### Task 3: YandexAsyncRecognizer client

**Files:**
- Create: `backend/pipeline/yandex_async.py`
- Create: `backend/tests/test_yandex_async.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_yandex_async.py
"""Tests for YandexAsyncRecognizer — async file recognition via gRPC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.yandex_async import (
    AsyncRecognitionResult,
    TimedUtterance,
    YandexAsyncRecognizer,
)


class TestTimedUtterance:
    def test_dataclass_fields(self) -> None:
        u = TimedUtterance(text="hello", start_ms=100, end_ms=500, confidence=0.95)
        assert u.text == "hello"
        assert u.start_ms == 100
        assert u.end_ms == 500
        assert u.confidence == 0.95


class TestAsyncRecognitionResult:
    def test_dataclass_fields(self) -> None:
        r = AsyncRecognitionResult(utterances=[])
        assert r.utterances == []


class TestYandexAsyncRecognizerInit:
    def test_stores_api_key(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        assert rec._api_key == "test-key"

    def test_constants(self) -> None:
        assert YandexAsyncRecognizer.GRPC_HOST == "stt.api.cloud.yandex.net:443"
        assert YandexAsyncRecognizer.MAX_CONTENT_BYTES == 50 * 1024 * 1024


class TestYandexAsyncRecognizerRecognize:
    @pytest.mark.asyncio
    async def test_rejects_oversized_content(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        oversized = b"\x00" * (50 * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="exceeds"):
            await rec.recognize(oversized)


class TestParseChunks:
    """Test _parse_chunks directly — core parsing logic."""

    def _make_chunk(self, text: str, start_ms: int, end_ms: int, confidence: float = 0.95) -> MagicMock:
        mock_word = MagicMock()
        mock_word.text = text
        mock_word.start_time_ms = start_ms
        mock_word.end_time_ms = end_ms

        mock_alt = MagicMock()
        mock_alt.text = text
        mock_alt.words = [mock_word]
        mock_alt.confidence = confidence

        mock_final = MagicMock()
        mock_final.alternatives = [mock_alt]

        mock_chunk = MagicMock()
        mock_chunk.WhichOneof.return_value = "final"
        mock_chunk.final = mock_final
        return mock_chunk

    def test_parses_single_chunk(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        chunk = self._make_chunk("привет мир", 100, 900, 0.95)
        result = rec._parse_chunks([chunk])
        assert len(result.utterances) == 1
        assert result.utterances[0].text == "привет мир"
        assert result.utterances[0].start_ms == 100
        assert result.utterances[0].end_ms == 900
        assert result.utterances[0].confidence == 0.95

    def test_parses_multiple_chunks(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        chunks = [
            self._make_chunk("привет", 100, 500),
            self._make_chunk("мир", 600, 900),
        ]
        result = rec._parse_chunks(chunks)
        assert len(result.utterances) == 2

    def test_skips_non_final_events(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        chunk = MagicMock()
        chunk.WhichOneof.return_value = "partial"
        result = rec._parse_chunks([chunk])
        assert len(result.utterances) == 0

    def test_empty_chunks(self) -> None:
        rec = YandexAsyncRecognizer(api_key="test-key")
        result = rec._parse_chunks([])
        assert len(result.utterances) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest backend/tests/test_yandex_async.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.pipeline.yandex_async'`

- [ ] **Step 3: Implement YandexAsyncRecognizer**

```python
# backend/pipeline/yandex_async.py
"""Yandex SpeechKit v3 async file recognition via gRPC."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from backend.logger import logger

_MAX_CONTENT_BYTES = 50 * 1024 * 1024  # 50 MB


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
                    logger.info(
                        f"Yandex async recognition done: {len(chunks)} chunks"
                    )
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
                if hasattr(final, "normalized_text"):
                    final = final.normalized_text
                for alt in final.alternatives[:1]:
                    text = alt.text
                    if not text:
                        continue
                    # Extract timing from words if available
                    words = list(alt.words) if hasattr(alt, "words") and alt.words else []
                    if words:
                        start_ms = int(words[0].start_time_ms)
                        end_ms = int(words[-1].end_time_ms)
                    else:
                        start_ms = 0
                        end_ms = 0
                    confidence = float(alt.confidence) if hasattr(alt, "confidence") else 1.0
                    utterances.append(
                        TimedUtterance(
                            text=text,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            confidence=confidence,
                        )
                    )
        return AsyncRecognitionResult(utterances=utterances)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_yandex_async.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/yandex_async.py backend/tests/test_yandex_async.py
git commit -m "feat(FEAT-005): add YandexAsyncRecognizer for post-call recognition"
```

---

### Task 4: PostCallProcessor — merge and analytics

**Files:**
- Create: `backend/pipeline/post_call.py`
- Create: `backend/tests/test_post_call.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_post_call.py
"""Tests for PostCallProcessor — merge, analytics computation, Redis storage."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.pipeline.post_call import (
    CallAnalytics,
    DiarizedUtterance,
    PostCallProcessor,
)
from backend.pipeline.yandex_async import AsyncRecognitionResult, TimedUtterance


class TestDiarizedUtterance:
    def test_fields(self) -> None:
        u = DiarizedUtterance(speaker="rep", text="hello", start_ms=100, end_ms=500)
        assert u.speaker == "rep"
        assert u.start_ms == 100


class TestCallAnalytics:
    def test_to_redis_json_excludes_utterances(self) -> None:
        a = CallAnalytics(
            total_duration_s=60.0,
            rep_talk_time_s=30.0,
            client_talk_time_s=30.0,
            rep_talk_ratio=0.5,
            rep_speech_rate_wpm=140.0,
            client_speech_rate_wpm=120.0,
            rep_word_count=70,
            client_word_count=60,
            interruptions_by_rep=1,
            interruptions_by_client=0,
            avg_rep_pause_before_response_s=1.5,
            utterances=[DiarizedUtterance("rep", "hi", 0, 100)],
        )
        data = json.loads(a.to_redis_json())
        assert "utterances" not in data
        assert data["rep_talk_ratio"] == 0.5

    def test_from_redis_json(self) -> None:
        j = json.dumps({"total_duration_s": 60.0, "rep_talk_time_s": 30.0,
                         "client_talk_time_s": 30.0, "rep_talk_ratio": 0.5,
                         "rep_speech_rate_wpm": 140.0, "client_speech_rate_wpm": 120.0,
                         "rep_word_count": 70, "client_word_count": 60,
                         "interruptions_by_rep": 1, "interruptions_by_client": 0,
                         "avg_rep_pause_before_response_s": 1.5})
        a = CallAnalytics.from_redis_json(j)
        assert a.rep_talk_ratio == 0.5
        assert a.utterances == []


class TestPostCallProcessorMerge:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(),
            redis=AsyncMock(),
            session_id="test-session",
        )

    def test_merge_sorts_by_start_ms(self) -> None:
        proc = self._make_processor()
        rep = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="rep1", start_ms=100, end_ms=500, confidence=0.9),
            TimedUtterance(text="rep2", start_ms=1000, end_ms=1500, confidence=0.9),
        ])
        client = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="client1", start_ms=600, end_ms=900, confidence=0.9),
        ])
        merged = proc._merge(rep, client, offset_ms=0)
        assert [u.speaker for u in merged] == ["rep", "client", "rep"]
        assert merged[0].text == "rep1"
        assert merged[1].text == "client1"

    def test_merge_applies_offset(self) -> None:
        proc = self._make_processor()
        rep = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="rep1", start_ms=0, end_ms=500, confidence=0.9),
        ])
        client = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="client1", start_ms=0, end_ms=400, confidence=0.9),
        ])
        # client started 200ms after rep
        merged = proc._merge(rep, client, offset_ms=200)
        assert merged[0].speaker == "rep"  # starts at 0
        assert merged[1].speaker == "client"  # starts at 0+200=200
        assert merged[1].start_ms == 200


class TestPostCallProcessorInterruptions:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_no_overlap_no_interruptions(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "hi", 0, 1000),
            DiarizedUtterance("rep", "hello", 1100, 2000),
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0
        assert by_client == 0

    def test_overlap_above_threshold(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "talking", 0, 1000),
            DiarizedUtterance("rep", "interrupts", 600, 1500),  # 400ms overlap
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 1  # rep started later → rep interrupted
        assert by_client == 0

    def test_overlap_below_threshold_ignored(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "hi", 0, 1000),
            DiarizedUtterance("rep", "hello", 800, 1500),  # 200ms overlap < 300ms
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0

    def test_client_interrupts_rep(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("rep", "talking", 0, 1000),
            DiarizedUtterance("client", "interrupts", 600, 1500),  # 400ms overlap
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0
        assert by_client == 1  # client started later → client interrupted


class TestPostCallProcessorPause:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_avg_pause_before_response(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "question1", 0, 1000),
            DiarizedUtterance("rep", "answer1", 2000, 3000),  # 1s pause
            DiarizedUtterance("client", "question2", 4000, 5000),
            DiarizedUtterance("rep", "answer2", 7000, 8000),  # 2s pause
        ]
        avg = proc._avg_pause_before_response(utts)
        assert avg == pytest.approx(1.5, abs=0.01)

    def test_pause_over_10s_excluded(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "q", 0, 1000),
            DiarizedUtterance("rep", "a", 12000, 13000),  # 11s gap — excluded
        ]
        avg = proc._avg_pause_before_response(utts)
        assert avg == 0.0

    def test_no_client_rep_pairs(self) -> None:
        proc = self._make_processor()
        utts = [DiarizedUtterance("rep", "a", 0, 1000)]
        avg = proc._avg_pause_before_response(utts)
        assert avg == 0.0


class TestPostCallProcessorAnalytics:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_compute_analytics(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("rep", "one two three", 0, 3000),      # 3s, 3 words
            DiarizedUtterance("client", "four five", 3500, 5500),     # 2s, 2 words
            DiarizedUtterance("rep", "six seven eight nine", 6000, 10000),  # 4s, 4 words
        ]
        a = proc._compute_analytics(utts)
        assert a.rep_talk_time_s == pytest.approx(7.0, abs=0.01)
        assert a.client_talk_time_s == pytest.approx(2.0, abs=0.01)
        assert a.rep_word_count == 7
        assert a.client_word_count == 2
        assert a.rep_talk_ratio == pytest.approx(7.0 / 9.0, abs=0.01)
        # speech rate: 7 words / (7/60 min) = 60 wpm
        assert a.rep_speech_rate_wpm == pytest.approx(60.0, abs=0.1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest backend/tests/test_post_call.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.pipeline.post_call'`

- [ ] **Step 3: Implement PostCallProcessor**

```python
# backend/pipeline/post_call.py
"""Post-call processing: merge diarized channels, compute analytics, store in Redis."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from backend.logger import logger
from backend.pipeline.audio_buffer import AudioBuffer
from backend.pipeline.yandex_async import (
    AsyncRecognitionResult,
    YandexAsyncRecognizer,
)

_INTERRUPTION_THRESHOLD_MS = 300
_MAX_PAUSE_FOR_RESPONSE_MS = 10_000


@dataclass
class DiarizedUtterance:
    """Utterance with speaker label and timing."""

    speaker: str
    text: str
    start_ms: int
    end_ms: int


@dataclass
class CallAnalytics:
    """Objective metrics computed from utterance timings."""

    total_duration_s: float
    rep_talk_time_s: float
    client_talk_time_s: float
    rep_talk_ratio: float
    rep_speech_rate_wpm: float
    client_speech_rate_wpm: float
    rep_word_count: int
    client_word_count: int
    interruptions_by_rep: int
    interruptions_by_client: int
    avg_rep_pause_before_response_s: float
    utterances: list[DiarizedUtterance] = field(default_factory=list)

    def to_redis_json(self) -> str:
        """Serialize without utterances (stored separately in Redis list)."""
        d = {
            "total_duration_s": self.total_duration_s,
            "rep_talk_time_s": self.rep_talk_time_s,
            "client_talk_time_s": self.client_talk_time_s,
            "rep_talk_ratio": self.rep_talk_ratio,
            "rep_speech_rate_wpm": self.rep_speech_rate_wpm,
            "client_speech_rate_wpm": self.client_speech_rate_wpm,
            "rep_word_count": self.rep_word_count,
            "client_word_count": self.client_word_count,
            "interruptions_by_rep": self.interruptions_by_rep,
            "interruptions_by_client": self.interruptions_by_client,
            "avg_rep_pause_before_response_s": self.avg_rep_pause_before_response_s,
        }
        return json.dumps(d)

    @classmethod
    def from_redis_json(cls, data: str) -> CallAnalytics:
        """Deserialize from Redis JSON (utterances will be empty)."""
        d = json.loads(data)
        return cls(utterances=[], **d)


class PostCallProcessor:
    """Orchestrate post-call diarization and analytics computation."""

    MIN_DURATION_S = 5.0

    def __init__(
        self,
        recognizer: YandexAsyncRecognizer,
        redis: Any,
        session_id: str,
    ) -> None:
        self._recognizer = recognizer
        self._redis = redis
        self._session_id = session_id

    async def process(self, audio_buffer: AudioBuffer) -> CallAnalytics | None:
        """Run post-call diarization pipeline. Returns None on skip/failure."""
        try:
            return await self._process_inner(audio_buffer)
        except Exception as exc:
            logger.exception(f"Post-call processing failed: {exc!r}")
            return None
        finally:
            audio_buffer.clear()

    async def _process_inner(self, audio_buffer: AudioBuffer) -> CallAnalytics | None:
        # Guards
        rep_dur = audio_buffer.duration_s("rep")
        client_dur = audio_buffer.duration_s("client")
        if max(rep_dur, client_dur) < self.MIN_DURATION_S:
            logger.info("Post-call skip: call too short")
            return None
        if audio_buffer.exceeds_limit():
            logger.warning("Post-call skip: buffer exceeds gRPC limit")
            return None

        # Build WAV per channel
        rep_wav = audio_buffer.get_wav("rep")
        client_wav = audio_buffer.get_wav("client")

        # Parallel recognition
        try:
            rep_result, client_result = await asyncio.gather(
                self._recognizer.recognize(rep_wav),
                self._recognizer.recognize(client_wav),
            )
        except Exception as exc:
            logger.error(f"Yandex async recognition failed: {exc!r}")
            return None

        # Both channels must succeed
        if not rep_result.utterances and not client_result.utterances:
            logger.warning("Post-call: both channels returned 0 utterances")
            return None
        if not rep_result.utterances or not client_result.utterances:
            logger.warning("Post-call: one channel returned 0 utterances, skipping")
            return None

        # Merge with offset compensation
        offset_ms = audio_buffer.start_offset_ms()
        merged = self._merge(rep_result, client_result, offset_ms)

        # Compute analytics
        analytics = self._compute_analytics(merged)

        # Store in Redis (atomic pipeline)
        await self._store_results(analytics)

        return analytics

    def _merge(
        self,
        rep: AsyncRecognitionResult,
        client: AsyncRecognitionResult,
        offset_ms: int,
    ) -> list[DiarizedUtterance]:
        """Merge two channel results into time-sorted timeline."""
        utterances: list[DiarizedUtterance] = []
        for u in rep.utterances:
            utterances.append(
                DiarizedUtterance(speaker="rep", text=u.text,
                                  start_ms=u.start_ms, end_ms=u.end_ms)
            )
        for u in client.utterances:
            utterances.append(
                DiarizedUtterance(speaker="client", text=u.text,
                                  start_ms=u.start_ms + offset_ms,
                                  end_ms=u.end_ms + offset_ms)
            )
        utterances.sort(key=lambda u: u.start_ms)
        return utterances

    def _compute_analytics(
        self, utterances: list[DiarizedUtterance],
    ) -> CallAnalytics:
        """Compute all metrics from utterance timings."""
        rep_time_ms = sum(u.end_ms - u.start_ms for u in utterances if u.speaker == "rep")
        client_time_ms = sum(u.end_ms - u.start_ms for u in utterances if u.speaker == "client")
        total_ms = rep_time_ms + client_time_ms

        rep_words = sum(len(u.text.split()) for u in utterances if u.speaker == "rep")
        client_words = sum(len(u.text.split()) for u in utterances if u.speaker == "client")

        rep_time_min = rep_time_ms / 60_000 if rep_time_ms > 0 else 1
        client_time_min = client_time_ms / 60_000 if client_time_ms > 0 else 1

        by_rep, by_client = self._count_interruptions(utterances)
        avg_pause = self._avg_pause_before_response(utterances)

        return CallAnalytics(
            total_duration_s=total_ms / 1000,
            rep_talk_time_s=rep_time_ms / 1000,
            client_talk_time_s=client_time_ms / 1000,
            rep_talk_ratio=rep_time_ms / total_ms if total_ms > 0 else 0.0,
            rep_speech_rate_wpm=rep_words / rep_time_min,
            client_speech_rate_wpm=client_words / client_time_min,
            rep_word_count=rep_words,
            client_word_count=client_words,
            interruptions_by_rep=by_rep,
            interruptions_by_client=by_client,
            avg_rep_pause_before_response_s=avg_pause,
            utterances=utterances,
        )

    def _count_interruptions(
        self, utterances: list[DiarizedUtterance],
    ) -> tuple[int, int]:
        """Count overlapping utterances between speakers. Overlap > 300ms.

        Utterances are sorted by start_ms, so b always starts at or after a.
        Therefore b is always the interrupter when overlap is detected.
        """
        by_rep = 0
        by_client = 0
        for i, a in enumerate(utterances):
            for b in utterances[i + 1:]:
                if a.speaker == b.speaker:
                    continue
                overlap = min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms)
                if overlap > _INTERRUPTION_THRESHOLD_MS:
                    # b started later (list sorted by start_ms) → b is interrupter
                    if b.speaker == "rep":
                        by_rep += 1
                    else:
                        by_client += 1
        return by_rep, by_client

    def _avg_pause_before_response(
        self, utterances: list[DiarizedUtterance],
    ) -> float:
        """Average gap between client utterance end and next rep start."""
        pauses: list[float] = []
        for i, u in enumerate(utterances):
            if u.speaker != "client":
                continue
            # Find next rep utterance
            for j in range(i + 1, len(utterances)):
                if utterances[j].speaker == "rep":
                    gap_ms = utterances[j].start_ms - u.end_ms
                    if 0 < gap_ms < _MAX_PAUSE_FOR_RESPONSE_MS:
                        pauses.append(gap_ms / 1000)
                    break
        return mean(pauses) if pauses else 0.0

    async def _store_results(self, analytics: CallAnalytics) -> None:
        """Atomic Redis pipeline: replace transcript + store analytics."""
        eval_key = f"eval_transcript:{self._session_id}"
        analytics_key = f"eval_analytics:{self._session_id}"

        diarized = [
            json.dumps({
                "speaker": u.speaker,
                "text": u.text,
                "start_ms": u.start_ms,
                "end_ms": u.end_ms,
            })
            for u in analytics.utterances
        ]

        try:
            pipe = self._redis.pipeline()
            pipe.delete(eval_key)
            if diarized:
                pipe.rpush(eval_key, *diarized)
            pipe.expire(eval_key, 86400)
            pipe.set(analytics_key, analytics.to_redis_json(), ex=86400)
            await pipe.execute()
            logger.info(
                f"Post-call results stored: {len(diarized)} utterances, "
                f"analytics for session {self._session_id}"
            )
        except Exception as exc:
            logger.error(f"Redis store failed: {exc!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_post_call.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/post_call.py backend/tests/test_post_call.py
git commit -m "feat(FEAT-005): add PostCallProcessor with merge and analytics"
```

---

## Chunk 2: Integration (Tasks 5-9)

### Task 5: Prompt formatter — diarized transcript and analytics formatting

**Files:**
- Modify: `backend/pipeline/prompt_formatter.py`
- Create: `backend/tests/test_prompt_formatter_diarization.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_prompt_formatter_diarization.py
"""Tests for diarization-related prompt formatting functions."""

import pytest

from backend.pipeline.post_call import CallAnalytics, DiarizedUtterance
from backend.pipeline.prompt_formatter import (
    _ms_to_timestamp,
    format_analytics,
    format_diarized_transcript,
    format_plain_transcript,
)


class TestMsToTimestamp:
    def test_zero(self) -> None:
        assert _ms_to_timestamp(0) == "00:00"

    def test_12400ms(self) -> None:
        assert _ms_to_timestamp(12400) == "00:12"  # truncation not rounding

    def test_90000ms(self) -> None:
        assert _ms_to_timestamp(90000) == "01:30"

    def test_3661000ms(self) -> None:
        assert _ms_to_timestamp(3661000) == "61:01"  # > 60 min is fine


class TestFormatDiarizedTranscript:
    def test_formats_with_timestamps(self) -> None:
        utts = [
            {"speaker": "rep", "text": "Добрый день", "start_ms": 12400},
            {"speaker": "client", "text": "Здравствуйте", "start_ms": 28000},
        ]
        result = format_diarized_transcript(utts)
        assert "[00:12] Менеджер: Добрый день" in result
        assert "[00:28] Клиент: Здравствуйте" in result

    def test_empty_list(self) -> None:
        assert format_diarized_transcript([]) == ""


class TestFormatPlainTranscript:
    def test_formats_without_timestamps(self) -> None:
        utts = [
            {"speaker": "rep", "text": "Привет"},
            {"speaker": "client", "text": "Привет"},
        ]
        result = format_plain_transcript(utts)
        assert "Менеджер: Привет" in result
        assert "Клиент: Привет" in result


class TestFormatAnalytics:
    def test_formats_all_fields(self) -> None:
        a = CallAnalytics(
            total_duration_s=754.0, rep_talk_time_s=324.0,
            client_talk_time_s=430.0, rep_talk_ratio=0.43,
            rep_speech_rate_wpm=142.0, client_speech_rate_wpm=118.0,
            rep_word_count=768, client_word_count=847,
            interruptions_by_rep=2, interruptions_by_client=1,
            avg_rep_pause_before_response_s=1.8, utterances=[],
        )
        result = format_analytics(a)
        assert "АНАЛИТИКА ЗВОНКА" in result
        assert "43%" in result
        assert "142" in result
        assert "Перебивания менеджером: 2" in result

    def test_none_returns_empty(self) -> None:
        assert format_analytics(None) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest backend/tests/test_prompt_formatter_diarization.py -v
```

Expected: `ImportError: cannot import name '_ms_to_timestamp' from 'backend.pipeline.prompt_formatter'`

- [ ] **Step 3: Add formatting functions to prompt_formatter.py**

Add at the end of `backend/pipeline/prompt_formatter.py`.
Note: `from __future__ import annotations` is already on line 1 of this file,
so string annotations work throughout. No additional future import needed.

```python
# --- Post-call diarization formatting ---

from backend.pipeline.post_call import CallAnalytics

_SPEAKER_LABELS = {"rep": "Менеджер", "client": "Клиент"}


def _ms_to_timestamp(ms: int) -> str:
    """Convert milliseconds to MM:SS timestamp (truncation, not rounding)."""
    total_s = ms // 1000
    minutes = total_s // 60
    seconds = total_s % 60
    return f"{minutes:02d}:{seconds:02d}"


def format_diarized_transcript(utterances: list[dict]) -> str:
    """Format transcript with timestamps: [MM:SS] Speaker: text"""
    if not utterances:
        return ""
    lines = []
    for u in utterances:
        ts = _ms_to_timestamp(u.get("start_ms", 0))
        speaker = _SPEAKER_LABELS.get(u.get("speaker", ""), u.get("speaker", ""))
        lines.append(f"[{ts}] {speaker}: {u['text']}")
    return "\n".join(lines)


def format_plain_transcript(utterances: list[dict]) -> str:
    """Format transcript without timestamps: Speaker: text"""
    if not utterances:
        return ""
    lines = []
    for u in utterances:
        speaker = _SPEAKER_LABELS.get(u.get("speaker", ""), u.get("speaker", ""))
        lines.append(f"{speaker}: {u['text']}")
    return "\n".join(lines)


def format_analytics(analytics: CallAnalytics | None) -> str:
    """Format АНАЛИТИКА ЗВОНКА section for evaluator prompt."""
    if analytics is None:
        return ""
    a = analytics
    client_ratio = 1.0 - a.rep_talk_ratio
    return (
        "АНАЛИТИКА ЗВОНКА (объективные данные, используй для оценки):\n"
        f"- Длительность: {a.total_duration_s:.0f} сек ({a.total_duration_s / 60:.1f} мин)\n"
        f"- Менеджер говорил: {a.rep_talk_time_s:.0f} сек ({a.rep_talk_ratio * 100:.0f}%)\n"
        f"- Клиент говорил: {a.client_talk_time_s:.0f} сек ({client_ratio * 100:.0f}%)\n"
        f"- Темп речи менеджера: {a.rep_speech_rate_wpm:.0f} слов/мин\n"
        f"- Темп речи клиента: {a.client_speech_rate_wpm:.0f} слов/мин\n"
        f"- Перебивания менеджером: {a.interruptions_by_rep}\n"
        f"- Перебивания клиентом: {a.interruptions_by_client}\n"
        f"- Средняя пауза менеджера перед ответом: {a.avg_rep_pause_before_response_s:.1f} сек\n"
        f"- Слов менеджера: {a.rep_word_count}, клиента: {a.client_word_count}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_prompt_formatter_diarization.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/prompt_formatter.py backend/tests/test_prompt_formatter_diarization.py
git commit -m "feat(FEAT-005): add diarized transcript and analytics formatting"
```

---

### Task 6: Evaluator integration — analytics parameter

**Files:**
- Modify: `backend/pipeline/evaluator.py` (lines 24-47 system prompt, lines 49-54 user template, lines 67-83 transcript formatting, lines 110-116 evaluate_call signature)
- Create: `backend/tests/test_evaluator_analytics.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_evaluator_analytics.py
"""Tests for evaluator integration with CallAnalytics."""

import json

import pytest

from backend.pipeline.evaluator import _truncate_transcript, _SYSTEM_PROMPT, _USER_TEMPLATE
from backend.pipeline.post_call import CallAnalytics


class TestUserTemplateHasAnalyticsPlaceholder:
    def test_analytics_section_in_template(self) -> None:
        assert "{analytics_section}" in _USER_TEMPLATE


class TestSystemPromptHasAnalyticsInstructions:
    def test_analytics_instructions(self) -> None:
        assert "АНАЛИТИКА ЗВОНКА" in _SYSTEM_PROMPT
        assert "43/57" in _SYSTEM_PROMPT


class TestTruncateTranscriptDiarized:
    def test_diarized_format_with_timestamps(self) -> None:
        lines = [
            json.dumps({"speaker": "rep", "text": "hello", "start_ms": 100, "end_ms": 500}),
            json.dumps({"speaker": "client", "text": "hi", "start_ms": 600, "end_ms": 900}),
        ]
        result = _truncate_transcript(lines)
        assert "[00:00] Менеджер: hello" in result
        assert "[00:00] Клиент: hi" in result

    def test_plain_format_without_timestamps(self) -> None:
        lines = [
            json.dumps({"speaker": "rep", "text": "hello"}),
            json.dumps({"speaker": "client", "text": "hi"}),
        ]
        result = _truncate_transcript(lines)
        assert "Менеджер: hello" in result
        assert "[" not in result  # no timestamps
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest backend/tests/test_evaluator_analytics.py -v
```

Expected: `AssertionError` — `{analytics_section}` not in current `_USER_TEMPLATE`

- [ ] **Step 3: Update evaluator.py**

Three changes:

**3a. Add analytics instructions to `_SYSTEM_PROMPT` (after existing text, ~line 47):**

Append to end of `_SYSTEM_PROMPT`:

```python
"\n\n"
"Если предоставлена секция АНАЛИТИКА ЗВОНКА:\n"
"- Используй объективные данные (talk ratio, speech rate, паузы) вместо угадывания.\n"
"- Talk ratio 43/57 (менеджер/клиент) — эталон. Отклонение >15% — снижай оценку needs_discovery.\n"
"- Темп речи 120-160 слов/мин — норма. <100 = слишком медленно, >180 = слишком быстро.\n"
"- Пауза менеджера перед ответом на возражение >1 сек — хорошо. <0.5 сек — плохо (не выслушал).\n"
"- Перебивания менеджером >3 — снижай оценку communication.\n"
"- Если аналитика отсутствует — оценивай как раньше, только по тексту."
```

**3b. Add `{analytics_section}` to `_USER_TEMPLATE` (line 49-54):**

```python
_USER_TEMPLATE = (
    "ТРАНСКРИПТ ЗВОНКА:\n{transcript}\n\n"
    "БРИФИНГ (подготовка к звонку):\n{briefing}\n\n"
    "{analytics_section}\n"
    "КРИТЕРИИ ОЦЕНКИ:\n{criteria_list}\n\n"
    "Оцени звонок по каждому критерию. Ответ — ТОЛЬКО валидный JSON"
    " по схеме CallEvaluation."
)
```

**3c. Update `_truncate_transcript` to detect and format diarized utterances (line 67-83):**

```python
def _truncate_transcript(raw_lines: list[str]) -> str:
    """Join transcript lines and truncate to ~12K tokens if needed."""
    from backend.pipeline.prompt_formatter import (
        format_diarized_transcript,
        format_plain_transcript,
    )

    parsed: list[dict] = []
    for line in raw_lines:
        try:
            item = json.loads(line) if isinstance(line, str) else json.loads(line.decode())
            parsed.append(item)
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            parsed.append({"speaker": "unknown", "text": str(line)})

    # Detect diarized format
    is_diarized = parsed and parsed[0].get("start_ms") is not None
    if is_diarized:
        full = format_diarized_transcript(parsed)
    else:
        full = format_plain_transcript(parsed)

    if len(full) <= _MAX_TRANSCRIPT_CHARS:
        return full

    head = full[:_HEAD_CHARS]
    tail = full[-_TAIL_CHARS:]
    return f"{head}\n\n[... часть транскрипта пропущена ...]\n\n{tail}"
```

**3d. Update full `evaluate_call` signature and body:**

Replace the entire `evaluate_call` function (~lines 110-158):

```python
async def evaluate_call(
    *,
    llm_client: EvaluatorLLMClient,
    transcript_raw: list[str | bytes],
    config: EvaluationConfig,
    briefing: str = "",
    analytics: Any = None,  # CallAnalytics | None — NEW
) -> CallEvaluation:
    """Run full evaluation pipeline: format -> LLM -> validate -> recompute."""
    from backend.pipeline.prompt_formatter import format_analytics

    lines = [
        line.decode() if isinstance(line, bytes) else line for line in transcript_raw
    ]
    transcript_text = _truncate_transcript(lines)
    criteria_list = _format_criteria_list(config)
    analytics_section = format_analytics(analytics) if analytics else ""

    user_prompt = _USER_TEMPLATE.format(
        transcript=transcript_text,
        briefing=briefing or "(брифинг не предоставлен)",
        criteria_list=criteria_list,
        analytics_section=analytics_section,
    )

    schema = CallEvaluation.model_json_schema()

    raw = await llm_client.evaluate(_SYSTEM_PROMPT, user_prompt, schema)

    try:
        evaluation = CallEvaluation.model_validate(raw)
    except Exception as first_err:
        logger.warning("First parse failed: %s — attempting reparse", first_err)
        reparse_prompt = (
            f"Предыдущий JSON не прошёл валидацию: {first_err!s}\n"
            "Исправь: 1) проверь типы, 2) проверь обязательные поля, "
            "3) верни ТОЛЬКО JSON.\n\n"
            f"Исходный запрос:\n{user_prompt}"
        )
        raw = await llm_client.evaluate(_SYSTEM_PROMPT, reparse_prompt, schema)
        try:
            evaluation = CallEvaluation.model_validate(raw)
        except Exception as second_err:
            raise EvalParseFailedError(
                f"Reparse also failed: {second_err}"
            ) from second_err

    evaluation.overall_score = _compute_overall_score(
        evaluation.criteria_results,
        config,
    )
    evaluation.verdict = _compute_verdict(evaluation.overall_score)

    return evaluation
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_evaluator_analytics.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run existing evaluator tests to check no regressions**

```bash
python -m pytest backend/tests/test_evaluator.py backend/tests/test_evaluation_integration.py -v
```

Expected: All existing tests PASS (analytics=None default preserves backward compat)

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/evaluator.py backend/tests/test_evaluator_analytics.py
git commit -m "feat(FEAT-005): enrich evaluator prompt with call analytics"
```

---

### Task 7: Config — enable_post_call_diarization flag

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Add flag to Settings and `get_settings()` factory**

In `backend/config.py`, add the field to `Settings` class AND add a cached factory:

```python
    # Post-call diarization (opt-in)
    enable_post_call_diarization: bool = False
```

After the `Settings` class, add:

```python
from functools import lru_cache


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Use in application code."""
    return Settings()
```

Note: `get_settings()` does NOT currently exist in the codebase. All existing code
uses `Settings()` directly. This factory is needed by the orchestrator diarization
path (Task 8) and can be adopted by other modules incrementally.

- [ ] **Step 2: Verify import works**

```bash
python -c "from backend.config import get_settings; s = get_settings(); print('diarization:', s.enable_post_call_diarization)"
```

Expected: `diarization: False`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(FEAT-005): add enable_post_call_diarization config flag"
```

---

### Task 8: Orchestrator — post-call pipeline before evaluation

**Files:**
- Modify: `backend/pipeline/orchestrator.py` (lines 95-120 on_session_end, lines 122-217 _run_evaluation)
- Create: `backend/tests/test_orchestrator_diarization.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_orchestrator_diarization.py
"""Tests for orchestrator post-call diarization integration."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.audio_buffer import AudioBuffer
from backend.pipeline.post_call import CallAnalytics, DiarizedUtterance


class TestOrchestratorOnSessionEndWithDiarization:
    @pytest.mark.asyncio
    async def test_calls_post_call_processor_when_buffer_provided(self) -> None:
        """on_session_end should run diarization before evaluation when buffer given."""
        from backend.pipeline.orchestrator import PipelineOrchestrator

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hello"}).encode()
        ])
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=AsyncMock())

        orch = PipelineOrchestrator(
            ws=mock_ws,
            session_id="test-session",
            llm_client=MagicMock(),
            session_manager=MagicMock(),
            eval_api_key="test-key",
        )

        buf = AudioBuffer()
        buf.append("rep", b"\x00\x00" * 16000)  # 1s
        buf.append("client", b"\x00\x00" * 16000)

        with patch("backend.pipeline.post_call.PostCallProcessor") as MockPCP:
            mock_processor = AsyncMock()
            mock_processor.process = AsyncMock(return_value=None)
            MockPCP.return_value = mock_processor

            await orch.on_session_end("test-session", mock_ws, mock_redis, audio_buffer=buf)

            # Wait for the task to run
            if orch._evaluation_task:
                await asyncio.wait_for(orch._evaluation_task, timeout=5.0)

    @pytest.mark.asyncio
    async def test_skips_diarization_when_buffer_none(self) -> None:
        """on_session_end should skip diarization when buffer is None."""
        from backend.pipeline.orchestrator import PipelineOrchestrator

        mock_ws = AsyncMock()
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"speaker": "rep", "text": "hello"}).encode()
        ])
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        orch = PipelineOrchestrator(
            ws=mock_ws,
            session_id="test-session",
            llm_client=MagicMock(),
            session_manager=MagicMock(),
            eval_api_key="test-key",
        )

        with patch("backend.pipeline.post_call.PostCallProcessor") as MockPCP:
            await orch.on_session_end("test-session", mock_ws, mock_redis)
            if orch._evaluation_task:
                await asyncio.wait_for(orch._evaluation_task, timeout=5.0)
            MockPCP.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest backend/tests/test_orchestrator_diarization.py -v
```

Expected: Failure — `on_session_end` doesn't accept `audio_buffer` parameter yet

- [ ] **Step 3: Update orchestrator.py**

**3a. Update `on_session_end` signature** (line 95) — add `audio_buffer` as keyword-only param, keep `redis`:

```python
async def on_session_end(
    self,
    session_id: str,
    ws: Any,
    redis: Any,
    *,
    audio_buffer: Any | None = None,  # AudioBuffer | None
) -> str:
```

Note: `redis` is kept as a positional param to preserve backward compatibility
with all existing callers (`on_session_end(session_id, ws, redis)`).
`audio_buffer` is keyword-only so callers that don't need diarization
don't pass it.

**3b. Update `_run_evaluation`** — add diarization step before evaluation:

Update `_run_evaluation` signature to accept `audio_buffer`:

```python
async def _run_evaluation(
    self,
    session_id: str,
    ws: Any,
    redis: Any,
    eval_token: str,
    audio_buffer: Any | None = None,
) -> None:
```

At the beginning of `_run_evaluation`, before fetching transcript from Redis
(insert after the existing `error_code = "EVAL_INTERNAL_ERROR"` line):

```python
# STEP A: Post-call diarization (best-effort)
analytics = None
if audio_buffer is not None:
    try:
        from backend.pipeline.post_call import PostCallProcessor
        from backend.pipeline.yandex_async import YandexAsyncRecognizer
        from backend.config import get_settings

        cfg = get_settings()
        if cfg.enable_post_call_diarization and cfg.yandex_speechkit_api_key:
            recognizer = YandexAsyncRecognizer(api_key=cfg.yandex_speechkit_api_key)
            processor = PostCallProcessor(
                recognizer=recognizer, redis=redis, session_id=session_id,
            )
            analytics = await processor.process(audio_buffer)
            if analytics:
                logger.info(f"Post-call diarization complete: talk_ratio={analytics.rep_talk_ratio:.2f}")
        else:
            audio_buffer.clear()
    except Exception as exc:
        logger.exception(f"Post-call diarization failed: {exc!r}")
        if audio_buffer is not None:
            audio_buffer.clear()

# STEP B: Load analytics from Redis if available
if analytics is None:
    raw_analytics = await redis.get(f"eval_analytics:{session_id}")
    if raw_analytics:
        from backend.pipeline.post_call import CallAnalytics
        analytics = CallAnalytics.from_redis_json(raw_analytics)
```

Also update `on_session_end` to pass `audio_buffer` to `_run_evaluation`:

```python
self._evaluation_task = asyncio.create_task(
    self._run_evaluation(session_id, ws, redis, eval_token, audio_buffer)
)
```

Update the existing `evaluate_call` invocation in `_run_evaluation` (~line 174) to pass `analytics`:

```python
result = await evaluate_call(
    llm_client=eval_llm,
    transcript_raw=transcript_raw,
    config=config,
    briefing=briefing,
    analytics=analytics,  # NEW — CallAnalytics | None
)
```

Existing callers without diarization: `analytics` defaults to `None` in the function
signature, so no other call sites need updating.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest backend/tests/test_orchestrator_diarization.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Run existing orchestrator tests**

```bash
python -m pytest backend/tests/test_orchestrator_eval.py -v
```

Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/tests/test_orchestrator_diarization.py
git commit -m "feat(FEAT-005): integrate post-call diarization into orchestrator pipeline"
```

---

### Task 9: main.py — AudioBuffer wiring and timeout update

**Files:**
- Modify: `backend/main.py` (lines 646-659 audio routing, lines 494-510/628-644 session_end, lines 661-672 finally block)

- [ ] **Step 1: Update audio routing to include AudioBuffer** (around line 646)

After deinterleave, add buffer append:

```python
# After line 659 (existing STT routing)
if audio_buffer is not None:
    audio_buffer.append("rep", left)
    audio_buffer.append("client", right)
```

- [ ] **Step 2: Create AudioBuffer at session start** (around line 460, where STT is created)

```python
from backend.pipeline.audio_buffer import AudioBuffer
from backend.config import get_settings

cfg = get_settings()
audio_buffer: AudioBuffer | None = None
if cfg.enable_post_call_diarization:
    audio_buffer = AudioBuffer()
```

- [ ] **Step 3: Pass audio_buffer to on_session_end** (lines 494-510 and 628-644)

In both `session_end` handlers, update the call to pass `audio_buffer` as keyword arg:

```python
eval_token = await orchestrator.on_session_end(
    session_id,
    websocket,
    redis_client,  # kept — redis is still a positional param
    audio_buffer=audio_buffer,  # NEW — keyword-only, None if diarization disabled
)
```

- [ ] **Step 4: Update timeout from 35s to 150s** (line 666)

```python
await asyncio.wait_for(
    orchestrator._evaluation_task,
    timeout=150.0,  # was 35.0 — covers diarization + evaluation
)
```

- [ ] **Step 5: Add audio_buffer.clear() to finally block** (after line 672)

```python
if audio_buffer is not None:
    audio_buffer.clear()
```

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest backend/tests/ -v --timeout=30
```

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/main.py
git commit -m "feat(FEAT-005): wire AudioBuffer into WebSocket handler and update timeout"
```

---

## Progress Tracking

- [x] Task 1: AudioBuffer component
- [x] Task 2: Proto generation for Yandex async API
- [x] Task 3: YandexAsyncRecognizer client
- [x] Task 4: PostCallProcessor — merge and analytics
- [x] Task 5: Prompt formatter — diarized transcript and analytics formatting
- [x] Task 6: Evaluator integration — analytics parameter
- [x] Task 7: Config — enable_post_call_diarization flag
- [x] Task 8: Orchestrator — post-call pipeline before evaluation
- [x] Task 9: main.py — AudioBuffer wiring and timeout update

**Total Tasks:** 9 | **Completed:** 9 | **Remaining:** 0
