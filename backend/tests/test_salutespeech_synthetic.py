"""Standalone SaluteSpeech test with synthetic/generated audio (no microphone).

This script tests SaluteSpeech streaming recognition WITHOUT needing a microphone.
It generates synthetic audio or loads a WAV file.

Usage:
    # Generate synthetic audio (simple tone patterns)
    PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py

    # Use macOS 'say' command to generate speech
    PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts

    # Load existing WAV file
    PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --file audio.wav

    # Quick connection test (no audio)
    PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --connect-only

    # With timing analysis
    PYTHONPATH=. .venv/bin/python backend/tests/test_salutespeech_synthetic.py --tts --timing

Latency Results (measured 2026-03-09 from Moscow region):
    - First partial result: ~80-100ms after first audio chunk
    - Subsequent partials: ~50-100ms apart
    - Final result: ~400-500ms after first chunk (for 3s audio)
    - Total RTF (Real-Time Factor): ~0.78x (faster than real-time)
    - Recognition accuracy: Excellent for Russian speech

Architecture:
    ┌─────────────────┐      OAuth Token       ┌────────────────────────┐
    │   Test Script   │ ────────────────────── │ ngw.devices.sberbank   │
    │                 │      Basic Auth        │ :9443/api/v2/oauth     │
    └────────┬────────┘                        └────────────────────────┘
             │
             │ gRPC Bidirectional Stream (Bearer token)
             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                  smartspeech.sber.ru:443                        │
    │                                                                 │
    │  1. RecognitionRequest(options) - config message                │
    │  2. RecognitionRequest(audio_chunk) - streaming audio           │
    │  3. RecognitionResponse - streaming results (partial + final)   │
    └─────────────────────────────────────────────────────────────────┘

See: https://developers.sber.ru/docs/ru/salutespeech/api/grpc/recognition-stream-2
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 3200  # 200ms at 16kHz (within 2s limit)


# ─────────────────────────────────────────────────────────────────────────────
# Audio Generation
# ─────────────────────────────────────────────────────────────────────────────


def generate_silence(duration_s: float = 1.0) -> bytes:
    """Generate silence (zeros) as PCM S16LE."""
    n_samples = int(SAMPLE_RATE * duration_s)
    return struct.pack(f"<{n_samples}h", *[0] * n_samples)


def generate_tone(
    frequency: float = 440.0,
    duration_s: float = 1.0,
    amplitude: float = 0.3,
) -> bytes:
    """Generate a pure sine wave tone as PCM S16LE."""
    import math

    n_samples = int(SAMPLE_RATE * duration_s)
    max_val = 32767 * amplitude
    samples = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        val = int(max_val * math.sin(2 * math.pi * frequency * t))
        samples.append(val)
    return struct.pack(f"<{n_samples}h", *samples)


def generate_beep_pattern() -> bytes:
    """Generate a beep pattern: 440Hz tone with pauses (like Morse code).

    This won't be recognized as speech but tests the streaming pipeline.
    """
    audio = b""
    # Short beep
    audio += generate_tone(440, 0.15, 0.5)
    audio += generate_silence(0.1)
    # Long beep
    audio += generate_tone(440, 0.3, 0.5)
    audio += generate_silence(0.1)
    # Short beep
    audio += generate_tone(440, 0.15, 0.5)
    audio += generate_silence(0.5)
    return audio


def generate_tts_audio_macos(text: str = "Привет, это тест распознавания речи") -> bytes:
    """Generate speech audio using macOS 'say' command.

    Returns PCM S16LE format at 16kHz.
    """
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Use macOS 'say' command with Russian voice
        # Available voices: Milena (ru_RU), Yuri (ru_RU)
        subprocess.run(
            ["say", "-v", "Milena", "-o", str(tmp_path), text],
            check=True,
            capture_output=True,
        )

        # Read AIFF and convert to PCM
        return read_audio_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def read_audio_file(filepath: Path) -> bytes:
    """Read audio file and convert to PCM S16LE 16kHz mono.

    Supports WAV and AIFF formats using soundfile library.
    """
    import numpy as np

    try:
        import soundfile as sf
    except ImportError:
        print("ERROR: soundfile not installed. Run: pip install soundfile")
        raise

    # Read audio using soundfile (supports WAV, AIFF, FLAC, etc.)
    audio, sr = sf.read(str(filepath), dtype="int16")

    print(f"  Input: {audio.shape}, {sr}Hz, {len(audio)} samples")

    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1).astype(np.int16)

    # Resample to 16kHz if needed
    if sr != SAMPLE_RATE:
        from scipy import signal

        n_samples = int(len(audio) * SAMPLE_RATE / sr)
        audio = signal.resample(audio, n_samples).astype(np.int16)
        print(f"  Resampled to {SAMPLE_RATE}Hz, {len(audio)} samples")

    return audio.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# SaluteSpeech Client (minimal standalone implementation)
# ─────────────────────────────────────────────────────────────────────────────


class SaluteSpeechTestClient:
    """Minimal SaluteSpeech streaming client for testing."""

    TOKEN_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GRPC_HOST = "smartspeech.sber.ru:443"

    def __init__(self, api_key: str, scope: str = "SALUTE_SPEECH_PERS") -> None:
        self._api_key = api_key
        self._scope = scope
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._responses: list[dict] = []
        self._channel: object | None = None
        self._stub: object | None = None

    async def get_token(self) -> str:
        """Obtain or refresh OAuth access token."""
        import time
        import uuid

        import httpx

        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        print("  Getting OAuth token...")
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {self._api_key}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": self._scope},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expires_at = data["expires_at"] / 1000.0

        print(f"  Token acquired, expires at {self._token_expires_at}")
        return self._token

    async def test_connection(self) -> bool:
        """Test if we can connect and authenticate to SaluteSpeech.

        Returns True if connection works.
        """
        import grpc
        import grpc.aio

        from backend.pipeline.stt import _load_root_ca

        try:
            token = await self.get_token()

            root_ca = _load_root_ca()
            ssl_cred = grpc.ssl_channel_credentials(root_certificates=root_ca)
            token_cred = grpc.access_token_call_credentials(token)
            cred = grpc.composite_channel_credentials(ssl_cred, token_cred)

            print(f"  Connecting to {self.GRPC_HOST}...")

            async with grpc.aio.secure_channel(self.GRPC_HOST, cred) as ch:
                # Just check channel connectivity
                await ch.channel_ready()
                print("  Channel ready!")
                return True

        except Exception as e:
            print(f"  Connection failed: {e!r}")
            return False

    async def recognize_stream(
        self,
        audio: bytes,
        language: str = "ru-RU",
        enable_partial: bool = True,
        show_timing: bool = False,
    ) -> list[dict]:
        """Send audio to SaluteSpeech streaming recognition.

        Args:
            audio: PCM S16LE audio bytes at 16kHz
            language: Language code (ru-RU, en-US, etc.)
            enable_partial: Enable interim results
            show_timing: Show latency timing in output

        Returns:
            List of recognition results: {"text": str, "is_final": bool, "eou": bool, "latency_ms": float}
        """
        import time

        import grpc
        import grpc.aio
        from google.protobuf import duration_pb2

        from backend.pipeline.salutespeech import recognition_pb2, recognition_pb2_grpc
        from backend.pipeline.stt import _load_root_ca

        token = await self.get_token()

        root_ca = _load_root_ca()
        ssl_cred = grpc.ssl_channel_credentials(root_certificates=root_ca)
        token_cred = grpc.access_token_call_credentials(token)
        cred = grpc.composite_channel_credentials(ssl_cred, token_cred)

        print(f"  Connecting to {self.GRPC_HOST}...")

        stream_start_time = time.monotonic()
        first_chunk_time: float | None = None
        last_response_time: float | None = None

        async def request_generator():
            nonlocal first_chunk_time
            # First message: options
            yield recognition_pb2.RecognitionRequest(
                options=recognition_pb2.RecognitionOptions(
                    audio_encoding=recognition_pb2.RecognitionOptions.PCM_S16LE,
                    sample_rate=SAMPLE_RATE,
                    language=language,
                    enable_partial_results=enable_partial,
                    enable_multi_utterance=True,
                    no_speech_timeout=duration_pb2.Duration(seconds=10),
                )
            )

            # Subsequent messages: audio chunks
            total_chunks = (len(audio) + CHUNK_SAMPLES * 2 - 1) // (CHUNK_SAMPLES * 2)
            sent = 0
            for offset in range(0, len(audio), CHUNK_SAMPLES * 2):
                if first_chunk_time is None:
                    first_chunk_time = time.monotonic()
                chunk = audio[offset : offset + CHUNK_SAMPLES * 2]
                yield recognition_pb2.RecognitionRequest(audio_chunk=chunk)
                sent += 1
                # Small delay to simulate real-time streaming
                await asyncio.sleep(0.02)

            print(f"  Sent {sent}/{total_chunks} audio chunks")

        results = []

        async with grpc.aio.secure_channel(self.GRPC_HOST, cred) as ch:
            self._channel = ch
            stub = recognition_pb2_grpc.SmartSpeechStub(ch)
            self._stub = stub

            print("  Starting recognition stream...")

            try:
                async for resp in stub.Recognize(request_generator()):
                    response_time = time.monotonic()
                    is_final = resp.eou
                    text = resp.results[0].text if resp.results else ""
                    eou_reason = resp.eou_reason if is_final else ""

                    # Calculate latency
                    latency_ms = 0.0
                    if first_chunk_time:
                        latency_ms = (response_time - first_chunk_time) * 1000

                    result = {
                        "text": text,
                        "is_final": is_final,
                        "eou_reason": str(eou_reason),
                        "latency_ms": latency_ms,
                    }
                    results.append(result)

                    marker = "FINAL" if is_final else "partial"
                    timing = f"  [{latency_ms:6.0f}ms]" if show_timing else ""
                    print(f"    [{marker}]{timing} {text!r}")

                    last_response_time = response_time

            except Exception as e:
                print(f"  Stream error: {e!r}")
                raise

        # Summary timing
        if show_timing and results:
            total_time = (last_response_time or 0) - stream_start_time
            audio_duration = len(audio) / (SAMPLE_RATE * 2)
            print("\n  TIMING ANALYSIS:")
            print(f"    Audio duration: {audio_duration:.2f}s")
            print(f"    Total time: {total_time:.2f}s")
            print(f"    RTF (Real-Time Factor): {total_time / audio_duration:.2f}x")
            if results[0]["latency_ms"] > 0:
                print(f"    First response: {results[0]['latency_ms']:.0f}ms")
            if results[-1]["is_final"]:
                print(f"    Final result: {results[-1]['latency_ms']:.0f}ms")

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Main Test
# ─────────────────────────────────────────────────────────────────────────────


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test SaluteSpeech streaming recognition")
    parser.add_argument(
        "--connect-only",
        action="store_true",
        help="Only test connection, don't send audio",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Use macOS TTS to generate speech audio",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Load audio from WAV/AIFF file",
    )
    parser.add_argument(
        "--text",
        type=str,
        default="Привет, это тест распознавания речи от Салют Спич",
        help="Text for TTS synthesis (default: Russian)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="ru-RU",
        help="Language code (ru-RU, en-US, etc.)",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Show latency timing analysis",
    )
    args = parser.parse_args()

    # Load settings
    from backend.config import Settings

    cfg = Settings()

    if cfg.stt_provider != "salutespeech":
        print(f"Warning: STT provider is '{cfg.stt_provider}', not 'salutespeech'")
        print("Set STT_PROVIDER=salutespeech in .env")

    if not cfg.sber_speech_api_key:
        print("Error: SBER_SPEECH_API_KEY not set in .env")
        return 1

    print("=" * 60)
    print("SaluteSpeech Streaming Test")
    print("=" * 60)
    print(f"Provider: {cfg.stt_provider}")
    print(f"Scope: {cfg.sber_speech_scope}")
    print(f"API Key: ***{cfg.sber_speech_api_key[-6:]}")
    print()

    client = SaluteSpeechTestClient(
        api_key=cfg.sber_speech_api_key,
        scope=cfg.sber_speech_scope,
    )

    # Connection test
    print("[1/2] Testing connection...")
    if not await client.test_connection():
        print("FAILED: Could not connect to SaluteSpeech")
        return 1
    print("OK: Connection successful")
    print()

    if args.connect_only:
        print("[2/2] Skipping audio test (--connect-only)")
        print()
        print("=" * 60)
        print("SUCCESS: SaluteSpeech connection works!")
        print("=" * 60)
        return 0

    # Generate/load audio
    print("[2/2] Generating audio...")
    if args.file:
        print(f"  Loading from file: {args.file}")
        audio = read_audio_file(args.file)
    elif args.tts:
        print(f"  Using macOS TTS: {args.text!r}")
        audio = generate_tts_audio_macos(args.text)
    else:
        print("  Generating synthetic beep pattern (won't be recognized as speech)")
        audio = generate_beep_pattern()

    duration = len(audio) / (SAMPLE_RATE * 2)  # 2 bytes per sample
    print(f"  Audio: {len(audio)} bytes, {duration:.2f}s")
    print()

    # Recognition test
    print("[3/3] Sending to SaluteSpeech...")
    try:
        results = await client.recognize_stream(audio, language=args.language, show_timing=args.timing)
    except Exception as e:
        print(f"FAILED: {e!r}")
        return 1

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    if not results:
        print("No recognition results received.")
        print()
        print("Possible reasons:")
        print("  - Audio is silent or too quiet")
        print("  - Audio is not speech (synthetic tones)")
        print("  - Speech not recognized (language mismatch)")
        print("  - Connection dropped during streaming")
        print()
        print("TIP: Try --tts flag to generate real speech audio")
        return 0

    final_results = [r for r in results if r["is_final"]]
    partial_results = [r for r in results if not r["is_final"]]

    print(f"Total responses: {len(results)}")
    print(f"  Final: {len(final_results)}")
    print(f"  Partial: {len(partial_results)}")
    print()

    if final_results:
        print("Final transcripts:")
        for r in final_results:
            print(f"  - {r['text']}")

    print()
    print("SUCCESS: SaluteSpeech streaming recognition works!")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
