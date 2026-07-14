"""Tests for shared DTO types extracted to backend.pipeline.types."""

from __future__ import annotations

import json


def test_hint_context_importable_from_types() -> None:
    """HintContext can be imported from backend.pipeline.types."""
    from backend.pipeline.types import HintContext

    ctx = HintContext(
        utterance="test",
        speaker="client",
        rag_context=["doc1"],
        session_summary="summary",
    )
    assert ctx.utterance == "test"
    assert ctx.speaker == "client"
    assert ctx.rag_context == ["doc1"]
    assert ctx.session_summary == "summary"


def test_hint_response_importable_from_types() -> None:
    """HintResponse can be imported from backend.pipeline.types."""
    from backend.pipeline.types import HintResponse

    resp = HintResponse(
        hint="test hint",
        source="doc.pdf",
        sentiment="neutral",
        color="blue",
    )
    assert resp.hint == "test hint"
    assert resp.source == "doc.pdf"
    assert resp.coaching == ""
    assert resp.relevance == "on_topic"
    assert resp.reasoning == ""


def test_hint_response_from_json() -> None:
    """HintResponse.from_json works after extraction."""
    from backend.pipeline.types import HintResponse

    raw = json.dumps(
        {
            "hint": "подсказка",
            "source": "файл.pdf",
            "sentiment": "positive",
            "color": "green",
            "coaching": "совет",
            "relevance": "on_topic",
            "reasoning": "тема",
        }
    )
    resp = HintResponse.from_json(raw)
    assert resp.hint == "подсказка"
    assert resp.color == "green"


def test_transcript_importable_from_types() -> None:
    """Transcript can be imported from backend.pipeline.types."""
    from backend.pipeline.types import Transcript

    t = Transcript(speaker="rep", text="привет", is_final=True)
    assert t.speaker == "rep"
    assert t.text == "привет"
    assert t.is_final is True
    assert t.confidence == 1.0
    assert t.utterance_id == ""


def test_call_analytics_importable_from_types() -> None:
    """CallAnalytics can be imported from backend.pipeline.types."""
    from backend.pipeline.types import CallAnalytics

    a = CallAnalytics(
        total_duration_s=120.0,
        rep_talk_time_s=60.0,
        client_talk_time_s=60.0,
        rep_talk_ratio=0.5,
        rep_speech_rate_wpm=120.0,
        client_speech_rate_wpm=100.0,
        rep_word_count=200,
        client_word_count=180,
        interruptions_by_rep=2,
        interruptions_by_client=1,
        avg_rep_pause_before_response_s=1.5,
    )
    assert a.total_duration_s == 120.0
    assert a.utterances == []


def test_call_analytics_no_redis_methods() -> None:
    """CallAnalytics should NOT have to_redis_json / from_redis_json after extraction."""
    from backend.pipeline.types import CallAnalytics

    assert not hasattr(CallAnalytics, "to_redis_json")
    assert not hasattr(CallAnalytics, "from_redis_json")


def test_diarized_utterance_importable_from_types() -> None:
    """DiarizedUtterance can be imported from backend.pipeline.types."""
    from backend.pipeline.types import DiarizedUtterance

    u = DiarizedUtterance(speaker="rep", text="привет", start_ms=0, end_ms=1000)
    assert u.speaker == "rep"
    assert u.start_ms == 0
    assert u.end_ms == 1000


def test_call_analytics_wire_contract() -> None:
    """CallAnalytics JSON serialization field names must match CallAnalyticsWire."""
    from backend.pipeline.types import CallAnalytics

    a = CallAnalytics(
        total_duration_s=120.0,
        rep_talk_time_s=60.0,
        client_talk_time_s=60.0,
        rep_talk_ratio=0.5,
        rep_speech_rate_wpm=120.0,
        client_speech_rate_wpm=100.0,
        rep_word_count=200,
        client_word_count=180,
        interruptions_by_rep=2,
        interruptions_by_client=1,
        avg_rep_pause_before_response_s=1.5,
    )
    # The wire contract: these exact keys must appear in serialized JSON
    expected_keys = {
        "total_duration_s",
        "rep_talk_ratio",
        "rep_talk_time_s",
        "client_talk_time_s",
        "rep_speech_rate_wpm",
        "client_speech_rate_wpm",
        "interruptions_by_rep",
        "interruptions_by_client",
        "avg_rep_pause_before_response_s",
        "rep_word_count",
        "client_word_count",
    }
    # Use the standalone serialization helper
    from backend.pipeline.types import call_analytics_to_wire_json

    serialized = json.loads(call_analytics_to_wire_json(a))
    assert set(serialized.keys()) == expected_keys


def test_backward_compat_llm_imports() -> None:
    """Old import paths from backend.pipeline.llm still work."""
    from backend.pipeline.llm import HintContext, HintResponse

    assert HintContext is not None
    assert HintResponse is not None


def test_backward_compat_stt_imports() -> None:
    """Old import paths from backend.pipeline.stt still work."""
    from backend.pipeline.stt import Transcript

    assert Transcript is not None


def test_backward_compat_post_call_imports() -> None:
    """Old import paths from backend.pipeline.post_call still work."""
    from backend.pipeline.post_call import CallAnalytics, DiarizedUtterance

    assert CallAnalytics is not None
    assert DiarizedUtterance is not None
