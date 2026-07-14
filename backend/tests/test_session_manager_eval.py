"""Tests for SessionManager eval_transcript dual-write (FEAT-004)."""
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_add_utterance_writes_eval_transcript():
    """add_utterance must write to eval_transcript:{sid} without ltrim."""
    from backend.session.manager import SessionManager

    # Create regular mock for redis (not async)
    mock_redis = MagicMock()

    # Create regular mock for pipeline (NOT async)
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    pipe.rpush = MagicMock(return_value=None)
    pipe.ltrim = MagicMock(return_value=None)
    pipe.expire = MagicMock(return_value=None)
    mock_redis.pipeline.return_value = pipe

    mgr = SessionManager(redis=mock_redis)
    await mgr.add_utterance("sess-1", "rep", "Hello")

    mock_redis.pipeline.assert_called_once()
    # Check that both keys are written
    rpush_calls = [c for c in pipe.rpush.call_args_list]
    assert len(rpush_calls) == 2
    keys_written = {c.args[0] for c in rpush_calls}
    assert "session:sess-1:utterances" in keys_written
    assert "eval_transcript:sess-1" in keys_written

    # Check ltrim only on session key (not eval key)
    ltrim_calls = pipe.ltrim.call_args_list
    assert len(ltrim_calls) == 1
    assert ltrim_calls[0].args[0] == "session:sess-1:utterances"

    # Check eval key gets 24h TTL
    expire_calls = pipe.expire.call_args_list
    eval_expire = [c for c in expire_calls if c.args[0] == "eval_transcript:sess-1"]
    assert len(eval_expire) == 1
    assert eval_expire[0].args[1] == 86400
