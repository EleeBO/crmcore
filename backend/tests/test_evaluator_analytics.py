"""Tests for evaluator integration with CallAnalytics."""

import json

from backend.pipeline.evaluator import (
    _SYSTEM_PROMPT,
    _USER_TEMPLATE,
    _truncate_transcript,
)


class TestUserTemplateHasAnalyticsPlaceholder:
    def test_analytics_section_in_template(self) -> None:
        assert "{analytics_section}" in _USER_TEMPLATE


class TestSystemPromptHasAnalyticsInstructions:
    def test_analytics_instructions(self) -> None:
        assert "АНАЛИТИКА ЗВОНКА" in _SYSTEM_PROMPT
        assert "43/57" in _SYSTEM_PROMPT


class TestTruncateTranscriptDiarized:
    def test_diarized_format_with_timestamps(self) -> None:
        lines = [
            json.dumps({"speaker": "rep", "text": "hello", "start_ms": 100, "end_ms": 500}),
            json.dumps({"speaker": "client", "text": "hi", "start_ms": 600, "end_ms": 900}),
        ]
        result = _truncate_transcript(lines)
        assert "[00:00] Менеджер: hello" in result
        assert "[00:00] Клиент: hi" in result

    def test_plain_format_without_timestamps(self) -> None:
        lines = [
            json.dumps({"speaker": "rep", "text": "hello"}),
            json.dumps({"speaker": "client", "text": "hi"}),
        ]
        result = _truncate_transcript(lines)
        assert "Менеджер: hello" in result
        assert "[" not in result  # no timestamps
