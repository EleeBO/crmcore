"""Tests for Protocol interfaces (Task 3.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.pipeline.protocols import (
    AsyncRecognizerProtocol,
    DocumentParserProtocol,
    LLMClientProtocol,
    SessionManagerProtocol,
)

# ── LLMClientProtocol ────────────────────────────────────────────────────────


class TestLLMClientProtocol:
    def test_real_llm_client_satisfies_protocol(self) -> None:
        """LLMClient instance must pass isinstance check against Protocol."""
        from backend.pipeline.llm import LLMClient

        client = LLMClient(
            primary_model="test",
            fallback_model="test",
            api_key="fake",
        )
        assert isinstance(client, LLMClientProtocol)

    def test_incomplete_class_does_not_satisfy(self) -> None:
        """A class missing _cancel_current must NOT satisfy the protocol."""

        class Incomplete:
            def generate_hint_stream(self, ctx: Any) -> AsyncIterator[str]: ...

        assert not isinstance(Incomplete(), LLMClientProtocol)

    def test_protocol_requires_generate_hint_stream(self) -> None:
        """A class missing generate_hint_stream must NOT satisfy the protocol."""

        class NoStream:
            def _cancel_current(self) -> None: ...

        assert not isinstance(NoStream(), LLMClientProtocol)


# ── SessionManagerProtocol ───────────────────────────────────────────────────


class TestSessionManagerProtocol:
    def test_real_session_manager_satisfies_protocol(self) -> None:
        """SessionManager instance must pass isinstance check."""
        from backend.session.manager import SessionManager

        mgr = SessionManager(redis=MagicMock())
        assert isinstance(mgr, SessionManagerProtocol)

    def test_incomplete_class_does_not_satisfy(self) -> None:
        """A class with only add_utterance must NOT satisfy the protocol."""

        class Incomplete:
            async def add_utterance(
                self, session_id: str, speaker: str, text: str
            ) -> None: ...

        assert not isinstance(Incomplete(), SessionManagerProtocol)

    @pytest.mark.asyncio
    async def test_add_utterance_callable(self) -> None:
        """SessionManager.add_utterance is async-callable with correct args."""
        from backend.session.manager import SessionManager

        # redis.pipeline() is sync, returns object with sync chain + async execute
        pipe_mock = MagicMock()
        pipe_mock.execute = AsyncMock(return_value=[])
        redis_mock = MagicMock()
        redis_mock.pipeline = MagicMock(return_value=pipe_mock)
        mgr = SessionManager(redis=redis_mock)
        # Should not raise — verifies the method signature matches protocol
        await mgr.add_utterance("sess-1", "client", "hello")
        pipe_mock.rpush.assert_called()
        pipe_mock.execute.assert_awaited_once()


# ── AsyncRecognizerProtocol ──────────────────────────────────────────────────


class TestAsyncRecognizerProtocol:
    def test_conforming_class_satisfies_protocol(self) -> None:
        """A class with async recognize(bytes, **kwargs) -> list[str] satisfies."""

        class FakeRecognizer:
            async def recognize(
                self, audio_data: bytes, **kwargs: Any
            ) -> list[str]:
                return ["hello"]

        assert isinstance(FakeRecognizer(), AsyncRecognizerProtocol)

    def test_missing_recognize_does_not_satisfy(self) -> None:
        """A class without recognize method must NOT satisfy."""

        class NoRecognize:
            pass

        assert not isinstance(NoRecognize(), AsyncRecognizerProtocol)


# ── DocumentParserProtocol ───────────────────────────────────────────────────


class TestDocumentParserProtocol:
    def test_conforming_class_satisfies_protocol(self) -> None:
        """A class with parse(bytes, str) -> list[Any] satisfies."""

        class FakeParser:
            def parse(self, content: bytes, filename: str) -> list[Any]:
                return []

        assert isinstance(FakeParser(), DocumentParserProtocol)

    def test_missing_parse_does_not_satisfy(self) -> None:
        """A class without parse method must NOT satisfy."""

        class NoParser:
            pass

        assert not isinstance(NoParser(), DocumentParserProtocol)
