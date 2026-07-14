"""Standalone Yandex SpeechKit test — records 5s from mic, sends to STT.

Usage:
    YANDEX_SPEECHKIT_API_KEY=<key> uv run python backend/tests/test_yandex_mic.py
"""

import asyncio
import struct


async def main() -> None:
    import numpy as np
    import sounddevice as sd

    from backend.config import Settings
    from backend.pipeline.stt import Transcript, YandexSpeechKitSTT

    SAMPLE_RATE = 16000
    RECORD_SECONDS = 5
    CHUNK_SAMPLES = 128

    cfg = Settings()
    api_key = cfg.yandex_speechkit_api_key
    if not api_key:
        print("ERROR: set YANDEX_SPEECHKIT_API_KEY env var")
        return
    print(f"API key: ***{api_key[-6:]}")

    transcripts: list[Transcript] = []

    async def on_transcript(t: Transcript) -> None:
        transcripts.append(t)
        marker = "FINAL" if t.is_final else "partial"
        print(f"  [{marker}] [{t.speaker}]: {t.text}")

    async def on_error(code: str, msg: str) -> None:
        print(f"  ERROR: {code}: {msg}")

    print(f"Recording {RECORD_SECONDS}s — say something in Russian...")
    audio = sd.rec(
        int(SAMPLE_RATE * RECORD_SECONDS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocking=True,
    )
    n = len(audio)
    dur = n / SAMPLE_RATE
    print(f"Recorded {n} samples ({dur:.1f}s)")

    rms = float(np.sqrt(np.mean(audio.astype(float) ** 2)))
    print(f"RMS level: {rms:.0f} (silence ~50, speech ~1000+)")
    if rms < 100:
        print("WARNING: very low audio level")

    stt = YandexSpeechKitSTT(api_key=api_key)
    stt.on_transcript = on_transcript
    stt.on_error = on_error

    print("Connecting to Yandex SpeechKit...")
    await stt.start_session("mic-test")

    print("Sending audio...")
    flat = audio.flatten()
    for off in range(0, len(flat), CHUNK_SAMPLES):
        chunk = flat[off : off + CHUNK_SAMPLES]
        pcm = struct.pack(f"<{len(chunk)}h", *chunk)
        await stt.send_audio(pcm, "client")
        await asyncio.sleep(0.002)

    sent = len(flat) // CHUNK_SAMPLES
    print(f"Sent {sent} chunks, waiting 5s for results...")
    await asyncio.sleep(5)
    await stt.close()

    print(f"\n{'='*50}")
    print(f"TRANSCRIPTS: {len(transcripts)}")
    if transcripts:
        print("Yandex SpeechKit is working!")
        for t in transcripts:
            tag = "FINAL" if t.is_final else "partial"
            print(f"  [{tag}] {t.text}")
    else:
        print("No transcripts received.")
        print("  - Mic silent / too quiet?")
        print("  - Speech not recognized?")


if __name__ == "__main__":
    asyncio.run(main())
