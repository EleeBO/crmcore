"""Protocol interfaces for pipeline components (Task 3.1, H2 fix)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from backend.pipeline.types import HintContext


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Protocol for LLM hint generation clients."""

    def _cancel_current(self) -> None: ...

    def generate_hint_stream(
        self,
        ctx: HintContext,
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class SessionManagerProtocol(Protocol):
    """Protocol for session state management."""

    async def add_utterance(self, session_id: str, speaker: str, text: str) -> None: ...

    async def get_context(self, session_id: str) -> Any: ...


@runtime_checkable
class AsyncRecognizerProtocol(Protocol):
    """Protocol for async speech recognition."""

    async def recognize(self, audio_data: bytes, **kwargs: Any) -> list[str]: ...


@runtime_checkable
class DocumentParserProtocol(Protocol):
    """Protocol for document parsing."""

    def parse(self, content: bytes, filename: str) -> list[Any]: ...
