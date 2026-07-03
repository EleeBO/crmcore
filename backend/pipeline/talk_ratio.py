"""Real-time talk ratio tracker with waveform ring buffer.

Replaces frontend word-counting (sidepanel.ts updateTalkRatio).
Sends data via WS for TalkRatioBar visualization.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, Field


class WaveSegment(BaseModel):
    """Single waveform bar in the visualization."""

    speaker: Literal["manager", "client"]
    amplitude: float = Field(ge=0.0, le=1.0)


class TalkRatioTracker:
    """Tracks speaking balance and builds waveform ring buffer."""

    BUFFER_SIZE: int = 60
    NORMALIZATION_MAX: int = 30  # fixed max words for amplitude

    def __init__(self) -> None:
        self._manager_words: int = 0
        self._client_words: int = 0
        self._waveform: deque[WaveSegment] = deque(maxlen=self.BUFFER_SIZE)

    def on_utterance(self, speaker: str, text: str, *, is_final: bool) -> None:
        """Update word counts and waveform on final utterances only.

        Interim utterances are ignored entirely — STT sends expanding
        partial text (3 → 7 → 10 words) for the same utterance, so
        counting interims would double/triple the real word count.
        """
        if not is_final:
            return

        word_count = len(text.split())
        mapped_speaker: Literal["manager", "client"] = (
            "manager" if speaker == "rep" else "client"
        )

        if mapped_speaker == "manager":
            self._manager_words += word_count
        else:
            self._client_words += word_count

        amplitude = min(word_count / self.NORMALIZATION_MAX, 1.0)
        self._waveform.append(WaveSegment(speaker=mapped_speaker, amplitude=amplitude))

    def get_state(self) -> dict[str, Any]:
        """Return serializable state for WS message."""
        total = self._manager_words + self._client_words
        if total == 0:
            return {
                "managerPercent": 0,
                "clientPercent": 0,
                "waveform": [],
            }
        manager_pct = round(self._manager_words / total * 100)
        return {
            "managerPercent": manager_pct,
            "clientPercent": 100 - manager_pct,
            "waveform": [seg.model_dump() for seg in self._waveform],
        }
