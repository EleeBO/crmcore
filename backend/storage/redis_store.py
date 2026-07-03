"""RedisStore — concrete SessionStore implementation wrapping redis.asyncio."""

from __future__ import annotations

import json
from typing import Any

from backend.logger import logger
from backend.storage.keys import (
    EVAL_TTL,
    SESSION_TTL,
    eval_transcript,
    session_utterances,
)

_MAX_UTTERANCES = 10


class RedisStore:
    """Thin wrapper around redis.asyncio that implements SessionStore."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def get(self, key: str) -> bytes | str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str | bytes, ex: int | None = None) -> None:
        await self._redis.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_many(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def lrange(self, key: str, start: int, stop: int) -> list[bytes]:
        return await self._redis.lrange(key, start, stop)

    async def rpush(self, key: str, *values: str) -> int:
        return await self._redis.rpush(key, *values)

    async def expire(self, key: str, ttl: int) -> None:
        await self._redis.expire(key, ttl)

    async def add_utterance(self, session_id: str, speaker: str, text: str) -> None:
        """Append utterance to session list + eval transcript via pipeline."""
        utter_key = session_utterances(session_id)
        eval_key = eval_transcript(session_id)
        payload = json.dumps({"speaker": speaker, "text": text})

        pipe = self._redis.pipeline()
        pipe.rpush(utter_key, payload)
        pipe.ltrim(utter_key, -_MAX_UTTERANCES, -1)
        pipe.expire(utter_key, SESSION_TTL)
        pipe.rpush(eval_key, payload)
        pipe.expire(eval_key, EVAL_TTL)
        await pipe.execute()
        logger.debug(f"Session {session_id}: added utterance from {speaker}")

    async def store_eval_transcript(
        self, session_id: str, items: list[str], ttl: int
    ) -> None:
        """Atomically replace eval transcript using MULTI/EXEC."""
        key = eval_transcript(session_id)
        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(key)
        if items:
            pipe.rpush(key, *items)
        pipe.expire(key, ttl)
        await pipe.execute()
