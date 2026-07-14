"""Tests for AudioBuffer — in-memory PCM buffer with WAV export."""

import io
import time
import wave

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
        buf._buffers["rep"] = bytearray(50 * 1024 * 1024)
        buf.append("rep", b"\x00\x01" * 100)
        assert len(buf._buffers["rep"]) == 50 * 1024 * 1024

    def test_append_unknown_channel_creates_it(self) -> None:
        buf = AudioBuffer()
        buf.append("other", b"\x00\x01" * 10)
        assert buf.duration_s("other") > 0


class TestAudioBufferWav:
    def test_get_wav_returns_valid_wav(self) -> None:
        buf = AudioBuffer()
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
        buf.append("rep", b"\x00\x00" * 16000)
        assert buf.duration_s("rep") == pytest.approx(1.0)

    def test_duration_s_empty_channel(self) -> None:
        buf = AudioBuffer()
        assert buf.duration_s("rep") == 0.0

    def test_estimated_memory_mb(self) -> None:
        buf = AudioBuffer()
        buf._buffers["rep"] = bytearray(1024 * 1024)
        buf._buffers["client"] = bytearray(2 * 1024 * 1024)
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
        buf._start_ts["client"] = 100.2
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
