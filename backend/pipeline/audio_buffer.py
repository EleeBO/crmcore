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
        self._buffers: dict[str, bytearray] = {
            "rep": bytearray(),
            "client": bytearray(),
        }
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
                mb_limit = _MAX_CHANNEL_BYTES // (1024 * 1024)
                logger.warning(
                    f"AudioBuffer [{channel}] hit {mb_limit} MB limit, "
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
