"""Shared DTO types for the pipeline.

Extracted from infrastructure modules (llm.py, stt.py, post_call.py)
so that importers don't pull in heavy dependencies (gRPC, Redis, httpx).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class HintContext:
    """Context passed to the LLM for hint generation."""

    utterance: str
    speaker: str
    rag_context: list[str]
    session_summary: str = ""
    conversation_history: list[dict[str, str]] = field(default_factory=list)


@dataclass
class HintResponse:
    """Structured hint returned by the LLM."""

    hint: str
    source: str
    sentiment: str
    color: str
    coaching: str = ""
    relevance: str = "on_topic"
    reasoning: str = ""

    @classmethod
    def from_json(cls, raw: str) -> HintResponse:
        """Parse a JSON string, stripping markdown code fences if present."""
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        hint = cls(
            hint=data["hint"],
            source=data.get("source", ""),
            sentiment=data.get("sentiment", "neutral"),
            color=data.get("color", "blue"),
            coaching=data.get("coaching", ""),
            relevance=data.get("relevance", "on_topic")
            if data.get("relevance") in ("on_topic", "off_topic")
            else "on_topic",
            reasoning=data.get("reasoning", ""),
        )
        # Enforce: off_topic always uses red
        if hint.relevance == "off_topic":
            hint.color = "red"
        return hint


@dataclass
class Transcript:
    """Single transcription result from STT provider."""

    speaker: str
    text: str
    is_final: bool = False
    confidence: float = 1.0
    utterance_id: str = ""


@dataclass
class DiarizedUtterance:
    """Utterance with speaker label and timing."""

    speaker: str
    text: str
    start_ms: int
    end_ms: int


@dataclass
class CallAnalytics:
    """Objective metrics computed from utterance timings.

    NOTE: Redis serialization methods (to_redis_json / from_redis_json)
    have been moved to PostCallProcessor._store_results() as local helpers.
    Use call_analytics_to_wire_json() for JSON serialization.
    """

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


def call_analytics_to_wire_json(analytics: CallAnalytics) -> str:
    """Serialize CallAnalytics to JSON for the wire contract.

    Field names are byte-for-byte identical to the original
    to_redis_json output and the CallAnalyticsWire TS interface.
    Does NOT include utterances (stored separately in Redis list).
    """
    d = {
        "total_duration_s": analytics.total_duration_s,
        "rep_talk_time_s": analytics.rep_talk_time_s,
        "client_talk_time_s": analytics.client_talk_time_s,
        "rep_talk_ratio": analytics.rep_talk_ratio,
        "rep_speech_rate_wpm": analytics.rep_speech_rate_wpm,
        "client_speech_rate_wpm": analytics.client_speech_rate_wpm,
        "rep_word_count": analytics.rep_word_count,
        "client_word_count": analytics.client_word_count,
        "interruptions_by_rep": analytics.interruptions_by_rep,
        "interruptions_by_client": analytics.interruptions_by_client,
        "avg_rep_pause_before_response_s": analytics.avg_rep_pause_before_response_s,
    }
    return json.dumps(d)


def call_analytics_from_wire_json(data: str) -> CallAnalytics:
    """Deserialize from wire JSON (utterances will be empty)."""
    d = json.loads(data)
    return CallAnalytics(utterances=[], **d)
