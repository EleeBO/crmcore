"""Tests for storage abstraction: key registry, Protocol, RedisStore."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Key registry tests ──────────────────────────────────────────────────


class TestKeyRegistry:
    def test_session_utterances(self) -> None:
        from backend.storage.keys import session_utterances

        assert session_utterances("abc") == "session:abc:utterances"

    def test_session_summary(self) -> None:
        from backend.storage.keys import session_summary

        assert session_summary("abc") == "session:abc:summary"

    def test_session_kb_id(self) -> None:
        from backend.storage.keys import session_kb_id

        assert session_kb_id("abc") == "session:abc:kb_id"

    def test_eval_transcript(self) -> None:
        from backend.storage.keys import eval_transcript

        assert eval_transcript("abc") == "eval_transcript:abc"

    def test_eval_token(self) -> None:
        from backend.storage.keys import eval_token

        assert eval_token("abc") == "eval_token:abc"

    def test_eval_analytics(self) -> None:
        from backend.storage.keys import eval_analytics

        assert eval_analytics("abc") == "eval_analytics:abc"

    def test_eval_result(self) -> None:
        from backend.storage.keys import eval_result

        assert eval_result("abc") == "eval:abc"

    def test_eval_config(self) -> None:
        from backend.storage.keys import eval_config

        assert eval_config() == "eval_config:default"

    def test_kb_docs(self) -> None:
        from backend.storage.keys import kb_docs

        assert kb_docs("k1") == "kb:k1:docs"

    def test_kb_scenario(self) -> None:
        from backend.storage.keys import kb_scenario

        assert kb_scenario("k1") == "kb:k1:scenario"

    def test_briefing_cache(self) -> None:
        from backend.storage.keys import briefing_cache

        assert briefing_cache("s1", "k1") == "briefing:s1:k1"

    def test_ttl_constants_exist(self) -> None:
        from backend.storage.keys import (
            CONFIG_TTL,
            EVAL_TTL,
            KB_TTL,
            SESSION_TTL,
        )

        assert SESSION_TTL == 1800
        assert KB_TTL == 7200
        assert EVAL_TTL == 86400
        assert CONFIG_TTL is None


# ── Protocol structural tests ────────────────────────────────────────────


class TestSessionStoreProtocol:
    def test_protocol_importable(self) -> None:
        from backend.storage.protocol import SessionStore

        assert SessionStore is not None

    def test_protocol_has_required_methods(self) -> None:
        from backend.storage.protocol import SessionStore

        for method in (
            "get",
            "set",
            "delete",
            "lrange",
            "rpush",
            "expire",
            "add_utterance",
            "store_eval_transcript",
        ):
            assert hasattr(SessionStore, method), (
                f"SessionStore missing method: {method}"
            )


# ── RedisStore tests ─────────────────────────────────────────────────────


class TestRedisStore:
    def _make_store(self) -> tuple:
        from backend.storage.redis_store import RedisStore

        mock_redis = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=AsyncMock())
        store = RedisStore(mock_redis)
        return store, mock_redis

    @pytest.mark.asyncio
    async def test_get_delegates(self) -> None:
        store, redis = self._make_store()
        redis.get.return_value = b"value"
        result = await store.get("key")
        redis.get.assert_called_once_with("key")
        assert result == b"value"

    @pytest.mark.asyncio
    async def test_set_delegates(self) -> None:
        store, redis = self._make_store()
        await store.set("key", "val", ex=100)
        redis.set.assert_called_once_with("key", "val", ex=100)

    @pytest.mark.asyncio
    async def test_delete_delegates(self) -> None:
        store, redis = self._make_store()
        await store.delete("key")
        redis.delete.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_lrange_delegates(self) -> None:
        store, redis = self._make_store()
        redis.lrange.return_value = [b"a", b"b"]
        result = await store.lrange("key", 0, -1)
        redis.lrange.assert_called_once_with("key", 0, -1)
        assert result == [b"a", b"b"]

    @pytest.mark.asyncio
    async def test_rpush_delegates(self) -> None:
        store, redis = self._make_store()
        redis.rpush.return_value = 3
        result = await store.rpush("key", "a", "b")
        redis.rpush.assert_called_once_with("key", "a", "b")
        assert result == 3

    @pytest.mark.asyncio
    async def test_expire_delegates(self) -> None:
        store, redis = self._make_store()
        await store.expire("key", 1800)
        redis.expire.assert_called_once_with("key", 1800)

    @pytest.mark.asyncio
    async def test_add_utterance_uses_pipeline(self) -> None:
        store, redis = self._make_store()
        pipe = redis.pipeline.return_value

        await store.add_utterance("sess1", "rep", "hello")

        redis.pipeline.assert_called_once()
        # Should rpush to both session utterances and eval transcript
        assert pipe.rpush.call_count == 2
        # Should ltrim session utterances
        pipe.ltrim.assert_called_once()
        # Should expire both keys
        assert pipe.expire.call_count >= 2
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_eval_transcript_uses_transaction(
        self,
    ) -> None:
        store, redis = self._make_store()
        pipe = redis.pipeline.return_value

        items = [
            json.dumps({"speaker": "rep", "text": "hi"}),
            json.dumps({"speaker": "client", "text": "hey"}),
        ]
        await store.store_eval_transcript("sess1", items, ttl=86400)

        redis.pipeline.assert_called_once_with(transaction=True)
        pipe.delete.assert_called_once()
        pipe.rpush.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_eval_transcript_session_id_not_key(
        self,
    ) -> None:
        """store_eval_transcript accepts session_id; RedisStore builds the key."""
        store, redis = self._make_store()
        pipe = redis.pipeline.return_value

        await store.store_eval_transcript(
            "my-session", ["data"], ttl=86400
        )

        # The delete call should use the constructed key
        pipe.delete.assert_called_once_with("eval_transcript:my-session")
