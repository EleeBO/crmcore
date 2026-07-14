# backend/tests/test_yandex_async.py
"""Tests for YandexAsyncRecognizer — async file recognition via gRPC."""

from __future__ import annotations

from unittest.mock import MagicMock

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
