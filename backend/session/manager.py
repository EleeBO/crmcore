"""Session state management: utterance buffer + rolling summary (Task 4.2)."""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from backend.logger import logger
from backend.storage.keys import (
    EVAL_TTL,
    SESSION_TTL,
    briefing_cache,
    eval_analytics,
    eval_result,
    eval_token,
    eval_transcript,
    session_kb_id,
    session_summary,
    session_utterances,
)

_MAX_UTTERANCES = 10

SummariseFn = Callable[[str], Coroutine[Any, Any, str]]


@dataclass
class SessionContext:
    """Aggregated context for a session, passed to the LLM."""

    utterances: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    portrait: str = ""
    strategy: str = ""


class SessionManager:
    """Manages per-session state in Redis."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    # ── public API ────────────────────────────────────────────────────────

    async def cleanup_session(self, session_id: str, kb_id: str = "") -> None:
        """Delete all session-scoped Redis keys for a clean start.

        Should be called before starting a new session to prevent stale data
        from a previous call leaking into the new one.
        """
        if self._redis is None:
            return
        keys = [
            session_utterances(session_id),
            session_summary(session_id),
            session_kb_id(session_id),
            eval_transcript(session_id),
            eval_token(session_id),
            eval_result(session_id),
            eval_analytics(session_id),
        ]
        if kb_id:
            keys.append(briefing_cache(session_id, kb_id))
        await self._redis.delete(*keys)
        logger.info(f"Session {session_id}: cleaned up {len(keys)} Redis keys")

    async def add_utterance(self, session_id: str, speaker: str, text: str) -> None:
        """Append utterance to Redis list, keeping last _MAX_UTTERANCES.

        Also writes to eval_transcript:{session_id} (no trim) for evaluation.
        """
        if self._redis is None:
            return
        utter_key = session_utterances(session_id)
        eval_key = eval_transcript(session_id)
        payload = json.dumps({"speaker": speaker, "text": text})

        pipe = self._redis.pipeline()
        pipe.rpush(utter_key, payload)
        pipe.ltrim(utter_key, -_MAX_UTTERANCES, -1)
        pipe.expire(utter_key, SESSION_TTL)
        pipe.rpush(eval_key, payload)  # no ltrim for eval
        pipe.expire(eval_key, EVAL_TTL)
        await pipe.execute()
        logger.debug(f"Session {session_id}: added utterance from {speaker}")

    async def get_context(self, session_id: str) -> SessionContext:
        """Return SessionContext with utterances and summary from Redis."""
        if self._redis is None:
            return SessionContext()
        raw_items: list[bytes] = await self._redis.lrange(
            session_utterances(session_id), 0, -1
        )
        utterances: list[dict[str, str]] = []
        for item in raw_items:
            try:
                utterances.append(json.loads(item))
            except json.JSONDecodeError:
                logger.warning(f"Session {session_id}: corrupt utterance skipped")

        raw_summary = await self._redis.get(session_summary(session_id))
        summary = raw_summary.decode() if raw_summary else ""

        return SessionContext(utterances=utterances, summary=summary)

    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 0,
        *,
        exclude_last: bool = False,
    ) -> list[dict[str, str]]:
        """Read conversation history from eval_transcript (full, untrimmed).

        Args:
            session_id: Session identifier.
            limit: Max utterances to return. 0 = all.
            exclude_last: If True, exclude the last entry to avoid duplicating
                          the current utterance which was already appended.
        """
        if self._redis is None:
            return []
        end = -2 if exclude_last else -1
        if limit == 0:
            raw: list[bytes] = await self._redis.lrange(
                eval_transcript(session_id), 0, end
            )
        else:
            start = -(limit + (1 if exclude_last else 0))
            raw = await self._redis.lrange(eval_transcript(session_id), start, end)
        history: list[dict[str, str]] = []
        for item in raw:
            try:
                history.append(json.loads(item))
            except json.JSONDecodeError:
                logger.warning(
                    f"Session {session_id}: corrupt eval_transcript entry skipped"
                )
        return history

    async def update_summary(self, session_id: str, summarise_fn: SummariseFn) -> None:
        """Generate and persist a rolling summary via the provided callable."""
        if self._redis is None:
            return
        ctx = await self.get_context(session_id)
        if not ctx.utterances:
            return

        transcript_text = "\n".join(
            f"{u['speaker']}: {u['text']}" for u in ctx.utterances
        )
        summary = await summarise_fn(transcript_text)

        key = session_summary(session_id)
        await self._redis.set(key, summary)
        await self._redis.expire(key, SESSION_TTL)
        logger.debug(f"Session {session_id}: summary updated ({len(summary)} chars)")
