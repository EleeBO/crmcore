"""Binary WebSocket frame parsing and stereo PCM de-interleaving."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum


class FrameType(IntEnum):
    AUDIO = 0
    CONTROL = 1


@dataclass
class Frame:
    frame_type: FrameType
    seq: int
    channel: int
    payload: bytes


def parse_frame(data: bytes) -> Frame:
    """Parse 5-byte header (uint32 LE seq + uint8 channel) + payload."""
    if len(data) < 5:
        raise ValueError(f"Frame too short: {len(data)} bytes (minimum 5)")
    seq, channel = struct.unpack_from("<IB", data, 0)
    payload = data[5:]
    frame_type = FrameType.CONTROL if channel == 1 else FrameType.AUDIO
    return Frame(frame_type=frame_type, seq=seq, channel=channel, payload=payload)


def deinterleave_stereo(pcm16: bytes) -> tuple[bytes, bytes]:
    """Split interleaved PCM16 stereo into separate L (mic) and R (tab) channels.

    Input: L0 R0 L1 R1 L2 R2 ...  (2 bytes per sample, interleaved)
    Output: (L_bytes, R_bytes)
    """
    if len(pcm16) % 2 != 0:
        raise ValueError(f"PCM16 data must have even byte count, got {len(pcm16)}")

    num_samples = len(pcm16) // 2
    if num_samples % 2 != 0:
        # Pad with one silent sample to make pairs
        pcm16 = pcm16 + b"\x00\x00"
        num_samples += 1

    samples = struct.unpack(f"<{num_samples}h", pcm16)
    left = struct.pack(f"<{num_samples // 2}h", *samples[0::2])
    right = struct.pack(f"<{num_samples // 2}h", *samples[1::2])
    return left, right
