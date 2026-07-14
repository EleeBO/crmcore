"""Tests for PostCallProcessor — merge, analytics computation, Redis storage."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.pipeline.post_call import (
    CallAnalytics,
    DiarizedUtterance,
    PostCallProcessor,
)
from backend.pipeline.types import (
    call_analytics_from_wire_json,
    call_analytics_to_wire_json,
)
from backend.pipeline.yandex_async import AsyncRecognitionResult, TimedUtterance


class TestDiarizedUtterance:
    def test_fields(self) -> None:
        u = DiarizedUtterance(speaker="rep", text="hello", start_ms=100, end_ms=500)
        assert u.speaker == "rep"
        assert u.start_ms == 100


class TestCallAnalytics:
    def test_to_redis_json_excludes_utterances(self) -> None:
        a = CallAnalytics(
            total_duration_s=60.0,
            rep_talk_time_s=30.0,
            client_talk_time_s=30.0,
            rep_talk_ratio=0.5,
            rep_speech_rate_wpm=140.0,
            client_speech_rate_wpm=120.0,
            rep_word_count=70,
            client_word_count=60,
            interruptions_by_rep=1,
            interruptions_by_client=0,
            avg_rep_pause_before_response_s=1.5,
            utterances=[DiarizedUtterance("rep", "hi", 0, 100)],
        )
        data = json.loads(call_analytics_to_wire_json(a))
        assert "utterances" not in data
        assert data["rep_talk_ratio"] == 0.5

    def test_from_wire_json(self) -> None:
        j = json.dumps({"total_duration_s": 60.0, "rep_talk_time_s": 30.0,
                         "client_talk_time_s": 30.0, "rep_talk_ratio": 0.5,
                         "rep_speech_rate_wpm": 140.0, "client_speech_rate_wpm": 120.0,
                         "rep_word_count": 70, "client_word_count": 60,
                         "interruptions_by_rep": 1, "interruptions_by_client": 0,
                         "avg_rep_pause_before_response_s": 1.5})
        a = call_analytics_from_wire_json(j)
        assert a.rep_talk_ratio == 0.5
        assert a.utterances == []


class TestPostCallProcessorMerge:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(),
            redis=AsyncMock(),
            session_id="test-session",
        )

    def test_merge_sorts_by_start_ms(self) -> None:
        proc = self._make_processor()
        rep = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="rep1", start_ms=100, end_ms=500, confidence=0.9),
            TimedUtterance(text="rep2", start_ms=1000, end_ms=1500, confidence=0.9),
        ])
        client = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="client1", start_ms=600, end_ms=900, confidence=0.9),
        ])
        merged = proc._merge(rep, client, offset_ms=0)
        assert [u.speaker for u in merged] == ["rep", "client", "rep"]
        assert merged[0].text == "rep1"
        assert merged[1].text == "client1"

    def test_merge_applies_offset(self) -> None:
        proc = self._make_processor()
        rep = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="rep1", start_ms=0, end_ms=500, confidence=0.9),
        ])
        client = AsyncRecognitionResult(utterances=[
            TimedUtterance(text="client1", start_ms=0, end_ms=400, confidence=0.9),
        ])
        # client started 200ms after rep
        merged = proc._merge(rep, client, offset_ms=200)
        assert merged[0].speaker == "rep"  # starts at 0
        assert merged[1].speaker == "client"  # starts at 0+200=200
        assert merged[1].start_ms == 200


class TestPostCallProcessorInterruptions:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_no_overlap_no_interruptions(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "hi", 0, 1000),
            DiarizedUtterance("rep", "hello", 1100, 2000),
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0
        assert by_client == 0

    def test_overlap_above_threshold(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "talking", 0, 1000),
            DiarizedUtterance("rep", "interrupts", 600, 1500),  # 400ms overlap
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 1  # rep started later → rep interrupted
        assert by_client == 0

    def test_overlap_below_threshold_ignored(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "hi", 0, 1000),
            DiarizedUtterance("rep", "hello", 800, 1500),  # 200ms overlap < 300ms
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0

    def test_client_interrupts_rep(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("rep", "talking", 0, 1000),
            DiarizedUtterance("client", "interrupts", 600, 1500),  # 400ms overlap
        ]
        by_rep, by_client = proc._count_interruptions(utts)
        assert by_rep == 0
        assert by_client == 1  # client started later → client interrupted


class TestPostCallProcessorPause:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_avg_pause_before_response(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "question1", 0, 1000),
            DiarizedUtterance("rep", "answer1", 2000, 3000),  # 1s pause
            DiarizedUtterance("client", "question2", 4000, 5000),
            DiarizedUtterance("rep", "answer2", 7000, 8000),  # 2s pause
        ]
        avg = proc._avg_pause_before_response(utts)
        assert avg == pytest.approx(1.5, abs=0.01)

    def test_pause_over_10s_excluded(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("client", "q", 0, 1000),
            DiarizedUtterance("rep", "a", 12000, 13000),  # 11s gap — excluded
        ]
        avg = proc._avg_pause_before_response(utts)
        assert avg == 0.0

    def test_no_client_rep_pairs(self) -> None:
        proc = self._make_processor()
        utts = [DiarizedUtterance("rep", "a", 0, 1000)]
        avg = proc._avg_pause_before_response(utts)
        assert avg == 0.0


class TestPostCallProcessorAnalytics:
    def _make_processor(self) -> PostCallProcessor:
        return PostCallProcessor(
            recognizer=MagicMock(), redis=AsyncMock(), session_id="s",
        )

    def test_compute_analytics(self) -> None:
        proc = self._make_processor()
        utts = [
            DiarizedUtterance("rep", "one two three", 0, 3000),      # 3s, 3 words
            DiarizedUtterance("client", "four five", 3500, 5500),     # 2s, 2 words
            DiarizedUtterance("rep", "six seven eight nine", 6000, 10000),  # 4s, 4 words
        ]
        a = proc._compute_analytics(utts)
        assert a.rep_talk_time_s == pytest.approx(7.0, abs=0.01)
        assert a.client_talk_time_s == pytest.approx(2.0, abs=0.01)
        assert a.rep_word_count == 7
        assert a.client_word_count == 2
        assert a.rep_talk_ratio == pytest.approx(7.0 / 9.0, abs=0.01)
        # speech rate: 7 words / (7/60 min) = 60 wpm
        assert a.rep_speech_rate_wpm == pytest.approx(60.0, abs=0.1)
