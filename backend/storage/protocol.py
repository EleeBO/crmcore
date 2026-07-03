"""SessionStore Protocol — typed abstraction over Redis."""

from __future__ import annotations

from typing import Protocol


class SessionStore(Protocol):
    """Typed interface for session storage operations."""

    async def get(self, key: str) -> bytes | str | None: ...

    async def set(
        self, key: str, value: str | bytes, ex: int | None = None
    ) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def delete_many(self, *keys: str) -> None: ...

    async def lrange(self, key: str, start: int, stop: int) -> list[bytes]: ...

    async def rpush(self, key: str, *values: str) -> int: ...

    async def expire(self, key: str, ttl: int) -> None: ...

    async def add_utterance(self, session_id: str, speaker: str, text: str) -> None: ...

    async def store_eval_transcript(
        self, session_id: str, items: list[str], ttl: int
    ) -> None: ...
