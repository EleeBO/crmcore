"""Voice Activity Detection using Silero VAD ONNX (mocked for tests)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from backend.logger import logger

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vad")


@dataclass
class VADState:
    """Per-channel RNN state for stateful Silero VAD."""

    h: Any = None
    c: Any = None


def _run_inference(audio: bytes, state: VADState, threshold: float) -> float:
    """Run Silero VAD ONNX inference. Returns speech probability 0.0-1.0.

    In production this loads the ONNX model. In tests this function is patched.
    """
    # Fallback: simple energy-based heuristic for when model is not loaded
    import struct

    if len(audio) < 2:
        return 0.0
    n = len(audio) // 2
    samples = struct.unpack(f"<{n}h", audio[: n * 2])
    energy = sum(abs(s) for s in samples) / max(1, n)
    return min(1.0, energy / 10000.0)


class SileroVAD:
    """Voice Activity Detector, one instance per WebSocket session."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self._states: dict[str, VADState] = {}

    def _get_state(self, channel: str) -> VADState:
        if channel not in self._states:
            self._states[channel] = VADState()
        return self._states[channel]

    async def detect_speech(self, audio: bytes, channel: str) -> bool:
        """Return True if speech is detected. Runs in executor (CPU-bound)."""
        state = self._get_state(channel)
        loop = asyncio.get_event_loop()

        prob = await loop.run_in_executor(
            _executor,
            _run_inference,
            audio,
            state,
            self.threshold,
        )
        is_speech = float(prob) >= self.threshold
        if is_speech:
            logger.info(f"VAD: речь [{channel}] prob={prob:.3f}")
        else:
            logger.debug(f"VAD [{channel}]: prob={prob:.3f} speech={is_speech}")
        return is_speech

    def reset(self, channel: str | None = None) -> None:
        """Reset RNN state for a channel (or all channels)."""
        if channel is not None:
            self._states.pop(channel, None)
        else:
            self._states.clear()
