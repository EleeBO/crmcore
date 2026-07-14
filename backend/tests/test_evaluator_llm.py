"""Tests for EvaluatorLLMClient (FEAT-004)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.evaluator_llm import (
    EvalLLMTimeoutError,
    EvalLLMUnavailableError,
    EvaluatorLLMClient,
)


@pytest.fixture
def client():
    return EvaluatorLLMClient(api_key="test-key")


def _mock_response(content: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_evaluate_returns_parsed_json(client):
    payload = {"call_summary": "test", "score": 8}
    with patch.object(
        client._client.chat.completions, "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ):
        result = await client.evaluate("sys", "usr", {"type": "object"})
    assert result == payload


@pytest.mark.asyncio
async def test_evaluate_falls_back_on_timeout(client):
    payload = {"fallback": True}
    call_count = 0

    async def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(100)
        return _mock_response(payload)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_side_effect,
    ):
        result = await client.evaluate("sys", "usr", {"type": "object"})
    assert result == payload
    assert call_count == 2


@pytest.mark.asyncio
async def test_evaluate_uses_response_format(client):
    schema = {"type": "object", "properties": {}}
    payload = {"ok": True}
    captured_kwargs = {}

    async def _capture(**kwargs):
        captured_kwargs.update(kwargs)
        return _mock_response(payload)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_capture,
    ):
        await client.evaluate("sys", "usr", schema)

    rf = captured_kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == schema
    assert captured_kwargs["stream"] is False


@pytest.mark.asyncio
async def test_evaluate_raises_timeout_when_both_fail(client):
    async def _always_timeout(**kwargs):
        await asyncio.sleep(100)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_always_timeout,
    ), pytest.raises(EvalLLMTimeoutError):
        await client.evaluate("sys", "usr", {"type": "object"})


@pytest.mark.asyncio
async def test_evaluate_raises_unavailable_on_non_timeout_error(client):
    with patch.object(
        client._client.chat.completions, "create",
        side_effect=RuntimeError("API 500"),
    ), pytest.raises(EvalLLMUnavailableError):
        await client.evaluate("sys", "usr", {"type": "object"})
