"""Synthetic WebSocket test: TTS audio → WS → check transcripts & hints.

Usage:
    PYTHONPATH=. backend/.venv/bin/python backend/tests/test_ws_synthetic.py
"""

from __future__ import annotations

import asyncio
import json
import struct
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

SAMPLE_RATE = 16000
WS_URL = "ws://localhost:8000/ws"
KB_ID = "cdacbd3d-1e71-4136-b9c6-13c611aacbef"


# ── Audio generation ──────────────────────────────────────────────────────


def generate_tts_audio(text: str) -> bytes:
    """Generate speech via macOS 'say' → PCM S16LE 16kHz mono."""
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            ["say", "-v", "Milena", "-o", str(tmp_path), text],
            check=True,
            capture_output=True,
        )
        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(str(tmp_path), dtype="int16")
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1).astype(np.int16)
        if sr != SAMPLE_RATE:
            from scipy import signal

            n_samples = int(len(audio) * SAMPLE_RATE / sr)
            audio = signal.resample(audio, n_samples).astype(np.int16)
        return audio.tobytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def interleave_stereo(left: bytes, right: bytes) -> bytes:
    """Interleave two mono PCM16 channels into stereo."""
    n = min(len(left), len(right)) // 2
    left_samples = struct.unpack(f"<{n}h", left[: n * 2])
    right_samples = struct.unpack(f"<{n}h", right[: n * 2])
    interleaved = []
    for l, r in zip(left_samples, right_samples):
        interleaved.extend([l, r])
    return struct.pack(f"<{n * 2}h", *interleaved)


def make_ws_frame(payload: bytes, channel: int, seq: int) -> bytes:
    """Build binary WS frame: 4-byte seq (LE) + 1-byte channel + payload."""
    header = struct.pack("<IB", seq, channel)
    return header + payload


# ── Phrases to send ──────────────────────────────────────────────────────

CLIENT_PHRASES = [
    "Здравствуйте, меня зовут Иван. Расскажите подробнее о вашем продукте.",
    "Сколько это стоит? Мне кажется, это слишком дорого.",
    "У нас уже есть похожее решение от другого поставщика.",
    "Какие гарантии вы предоставляете?",
]

REP_PHRASES = [
    "Добрый день, Иван! Рад знакомству. Давайте я расскажу о нашем решении.",
    "Понимаю ваш вопрос о цене. Давайте посмотрим на экономический эффект.",
    "Отличный вопрос! Наше решение интегрируется с существующими системами.",
    "Мы предоставляем полную гарантию и бесплатную поддержку на год.",
]


# ── Main test ─────────────────────────────────────────────────────────────


async def run_test() -> int:
    import websockets

    session_id = str(uuid.uuid4())
    print(f"Session: {session_id}")
    print(f"KB: {KB_ID}")
    print(f"WS: {WS_URL}")
    print()

    transcripts_received: list[dict] = []
    hints_received: list[dict] = []
    errors_received: list[dict] = []
    eval_result: dict | None = None

    async with websockets.connect(WS_URL) as ws:
        # ── Send session_start as control frame ──
        ctrl = json.dumps({
            "type": "session_start",
            "session_id": session_id,
            "kb_id": KB_ID,
            "stt_provider": "yandex",
        }).encode()
        frame = make_ws_frame(ctrl, channel=1, seq=0)
        await ws.send(frame)
        print("[SENT] session_start")

        # Wait for session to initialize
        await asyncio.sleep(2)

        # ── Reader task ──
        stop_event = asyncio.Event()

        async def reader():
            try:
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except TimeoutError:
                        continue
                    except Exception:
                        break

                    if isinstance(msg, str):
                        data = json.loads(msg)
                        msg_type = data.get("type", "")

                        if msg_type == "transcript":
                            is_final = data.get("is_final", False)
                            marker = "FINAL" if is_final else "partial"
                            speaker = data.get("speaker", "?")
                            text = data.get("text", "")
                            print(f"  [{marker}] {speaker}: {text[:80]}")
                            transcripts_received.append(data)
                        elif msg_type == "hint_end":
                            print(f"  [HINT] color={data.get('color')} → {data.get('hint', '')[:80]}")
                            hints_received.append(data)
                        elif msg_type == "error":
                            print(f"  [ERROR] {data.get('code')}: {data.get('message', '')[:80]}")
                            errors_received.append(data)
                        elif msg_type == "evaluation_started":
                            print(f"  [EVAL] started, token={data.get('eval_token', '')[:16]}...")
                        elif msg_type == "evaluation_result":
                            print("  [EVAL] result received")
                            nonlocal eval_result
                            eval_result = data
                        elif msg_type == "evaluation_error":
                            print(f"  [EVAL ERROR] {data.get('code')}: {data.get('message', '')[:80]}")
                        else:
                            print(f"  [MSG] {msg_type}: {str(data)[:100]}")
            except asyncio.CancelledError:
                pass

        reader_task = asyncio.create_task(reader())

        # ── Send audio phrases ──
        seq = 1
        silence_mono = b"\x00\x00" * (SAMPLE_RATE // 2)  # 0.5s silence

        for i, (client_text, rep_text) in enumerate(zip(CLIENT_PHRASES, REP_PHRASES)):
            # Generate REP audio (left channel = rep, right channel = client)
            print(f"\n[PHRASE {i+1}] Rep: {rep_text[:60]}...")
            rep_audio = generate_tts_audio(rep_text)
            # Rep speaks: left=rep audio, right=silence
            silence_for_rep = b"\x00\x00" * (len(rep_audio) // 2)
            stereo = interleave_stereo(rep_audio, silence_for_rep)

            # Send in chunks (200ms each = 6400 stereo samples = 25600 bytes)
            chunk_bytes = SAMPLE_RATE * 2 * 2 * 200 // 1000  # 200ms of stereo PCM16
            for offset in range(0, len(stereo), chunk_bytes):
                chunk = stereo[offset : offset + chunk_bytes]
                frame = make_ws_frame(chunk, channel=0, seq=seq)
                await ws.send(frame)
                seq += 1
                await asyncio.sleep(0.18)  # ~real-time pace

            # Gap between speakers
            await asyncio.sleep(1.0)

            # Generate CLIENT audio
            print(f"[PHRASE {i+1}] Client: {client_text[:60]}...")
            client_audio = generate_tts_audio(client_text)
            silence_for_client = b"\x00\x00" * (len(client_audio) // 2)
            stereo = interleave_stereo(silence_for_client, client_audio)

            for offset in range(0, len(stereo), chunk_bytes):
                chunk = stereo[offset : offset + chunk_bytes]
                frame = make_ws_frame(chunk, channel=0, seq=seq)
                await ws.send(frame)
                seq += 1
                await asyncio.sleep(0.18)

            # Wait for potential hints
            print("[WAIT] Waiting for hint processing...")
            await asyncio.sleep(5.0)

        # ── Send session_end ──
        print("\n[SENT] session_end")
        ctrl = json.dumps({"type": "session_end"}).encode()
        frame = make_ws_frame(ctrl, channel=1, seq=seq)
        await ws.send(frame)

        # Wait for evaluation
        print("[WAIT] Waiting for evaluation (up to 30s)...")
        await asyncio.sleep(15)

        stop_event.set()
        reader_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reader_task

    # ── Report ──
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    final_transcripts = [t for t in transcripts_received if t.get("is_final")]
    partial_transcripts = [t for t in transcripts_received if not t.get("is_final")]
    print(f"Transcripts: {len(transcripts_received)} total")
    print(f"  Final: {len(final_transcripts)}")
    print(f"  Partial: {len(partial_transcripts)}")
    print(f"Hints: {len(hints_received)}")
    print(f"Errors: {len(errors_received)}")
    for e in errors_received:
        print(f"  {e.get('code')}: {e.get('message', '')[:100]}")
    if eval_result:
        ev = eval_result.get("evaluation", {})
        print(f"Evaluation: score={ev.get('overall_score')}, verdict={ev.get('verdict')}")
    else:
        print("Evaluation: not received")

    if hints_received:
        print("\nHints detail:")
        for h in hints_received:
            print(f"  [{h.get('color')}] {h.get('hint', '')[:100]}")

    print()
    if len(final_transcripts) > 0 and len(hints_received) > 0:
        print("SUCCESS: Pipeline works end-to-end!")
        return 0
    elif len(final_transcripts) > 0 and len(hints_received) == 0:
        print("PARTIAL: Transcripts work but NO hints generated (LLM issue)")
        return 1
    elif len(final_transcripts) == 0:
        print("FAIL: No final transcripts received (STT issue)")
        return 2
    return 1


if __name__ == "__main__":
    import contextlib

    sys.exit(asyncio.run(run_test()))
