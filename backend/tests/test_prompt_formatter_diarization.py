"""Tests for diarization-related prompt formatting functions."""


from backend.pipeline.post_call import CallAnalytics
from backend.pipeline.prompt_formatter import (
    _ms_to_timestamp,
    format_analytics,
    format_diarized_transcript,
    format_plain_transcript,
)


class TestMsToTimestamp:
    def test_zero(self) -> None:
        assert _ms_to_timestamp(0) == "00:00"

    def test_12400ms(self) -> None:
        assert _ms_to_timestamp(12400) == "00:12"  # truncation not rounding

    def test_90000ms(self) -> None:
        assert _ms_to_timestamp(90000) == "01:30"

    def test_3661000ms(self) -> None:
        assert _ms_to_timestamp(3661000) == "61:01"  # > 60 min is fine


class TestFormatDiarizedTranscript:
    def test_formats_with_timestamps(self) -> None:
        utts = [
            {"speaker": "rep", "text": "Добрый день", "start_ms": 12400},
            {"speaker": "client", "text": "Здравствуйте", "start_ms": 28000},
        ]
        result = format_diarized_transcript(utts)
        assert "[00:12] Менеджер: Добрый день" in result
        assert "[00:28] Клиент: Здравствуйте" in result

    def test_empty_list(self) -> None:
        assert format_diarized_transcript([]) == ""


class TestFormatPlainTranscript:
    def test_formats_without_timestamps(self) -> None:
        utts = [
            {"speaker": "rep", "text": "Привет"},
            {"speaker": "client", "text": "Привет"},
        ]
        result = format_plain_transcript(utts)
        assert "Менеджер: Привет" in result
        assert "Клиент: Привет" in result


class TestFormatAnalytics:
    def test_formats_all_fields(self) -> None:
        a = CallAnalytics(
            total_duration_s=754.0, rep_talk_time_s=324.0,
            client_talk_time_s=430.0, rep_talk_ratio=0.43,
            rep_speech_rate_wpm=142.0, client_speech_rate_wpm=118.0,
            rep_word_count=768, client_word_count=847,
            interruptions_by_rep=2, interruptions_by_client=1,
            avg_rep_pause_before_response_s=1.8, utterances=[],
        )
        result = format_analytics(a)
        assert "АНАЛИТИКА ЗВОНКА" in result
        assert "43%" in result
        assert "142" in result
        assert "Перебивания менеджером: 2" in result

    def test_none_returns_empty(self) -> None:
        assert format_analytics(None) == ""
