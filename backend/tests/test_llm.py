"""Tests for LLM client: OpenRouter + fallback + single-flight queue (Task 4.1)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_openai_client():
    """Mock openai.AsyncOpenAI streaming client."""
    client = MagicMock()

    async def _stream_iter(tokens):
        for token in tokens:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = token
            yield chunk

    stream_mock = MagicMock()
    stream_mock.__aenter__ = AsyncMock(return_value=stream_mock)
    stream_mock.__aexit__ = AsyncMock(return_value=False)
    stream_mock.__aiter__ = lambda self: _stream_iter(
        ['{"hint": "Упомяните RTO 15 минут", ', '"source": "tariffs.pdf", ', '"sentiment": "positive", "color": "green"}']
    )

    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=stream_mock)
    return client


# ── HintContext & HintResponse ─────────────────────────────────────────────


def test_hint_context_creation() -> None:
    """HintContext can be created with required fields."""
    from backend.pipeline.llm import HintContext

    ctx = HintContext(
        utterance="Какой RTO?",
        speaker="client",
        rag_context=["SLA Gold: RTO 15 минут"],
        session_summary="Разговор о тарифах",
    )
    assert ctx.utterance == "Какой RTO?"
    assert len(ctx.rag_context) == 1


def test_hint_response_parsing() -> None:
    """HintResponse.from_json parses valid JSON including relevance and reasoning."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"reasoning": "клиент спросил про RTO", "relevance": "on_topic", '
        '"hint": "Упомяните RTO", "source": "tariffs.pdf", '
        '"sentiment": "positive", "color": "green"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.hint == "Упомяните RTO"
    assert resp.color == "green"
    assert resp.relevance == "on_topic"
    assert resp.reasoning == "клиент спросил про RTO"


def test_hint_response_strips_code_fences() -> None:
    """HintResponse.from_json strips markdown code fences."""
    from backend.pipeline.llm import HintResponse

    raw = '```json\n{"hint": "Test", "source": "", "sentiment": "neutral", "color": "blue"}\n```'
    resp = HintResponse.from_json(raw)
    assert resp.hint == "Test"


def test_hint_response_invalid_json_raises() -> None:
    """HintResponse.from_json raises ValueError on invalid JSON."""
    from backend.pipeline.llm import HintResponse

    with pytest.raises(ValueError):
        HintResponse.from_json("not json at all")


# ── Streaming generation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_streams_tokens(mock_openai_client) -> None:
    """generate_hint_stream yields token strings."""
    with patch("backend.pipeline.llm.AsyncOpenAI", return_value=mock_openai_client):
        from backend.pipeline.llm import HintContext, LLMClient

        client = LLMClient(
            primary_model="google/gemini-2.5-flash",
            fallback_model="openai/gpt-4.1-mini",
            api_key="test",
            primary_timeout_ms=1000,
            fallback_timeout_ms=2000,
        )
        ctx = HintContext(utterance="Тест", speaker="client", rag_context=["doc"])
        tokens = []
        async for token in client.generate_hint_stream(ctx):
            tokens.append(token)

    assert len(tokens) > 0
    assert all(isinstance(t, str) for t in tokens)


# ── Single-flight cancellation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_flight_cancels_previous() -> None:
    """Starting a new LLM request cancels the in-flight one."""
    with patch("backend.pipeline.llm.AsyncOpenAI"):
        from backend.pipeline.llm import HintContext, LLMClient

        client = LLMClient(
            primary_model="google/gemini-2.5-flash",
            fallback_model="openai/gpt-4.1-mini",
            api_key="test",
            primary_timeout_ms=5000,
            fallback_timeout_ms=5000,
        )

        slow_done = asyncio.Event()

        async def slow_stream(ctx):
            try:
                await asyncio.sleep(10)
                yield "never"
            except asyncio.CancelledError:
                slow_done.set()
                raise

        ctx = HintContext(utterance="Тест", speaker="client", rag_context=[])

        # Start first request (slow)
        client._llm_task = asyncio.create_task(asyncio.sleep(10))
        first_task = client._llm_task
        assert not first_task.done()

        # Cancel it
        client._cancel_current()
        await asyncio.sleep(0)
        assert first_task.cancelled() or first_task.done()


# ── Fallback on timeout ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_triggers_on_primary_ttft_timeout() -> None:
    """generate_hint falls back to secondary model when primary TTFT times out."""
    with patch("backend.pipeline.llm.AsyncOpenAI") as mock_cls:
        fallback_called = False

        async def _fallback_complete(ctx):
            nonlocal fallback_called
            fallback_called = True
            from backend.pipeline.schemas import HintResponseV2

            return HintResponseV2(
                reasoning="Fallback: primary LLM timed out",
                hint_type="coaching",
                headline="Fallback hint",
                detail="",
                coaching="",
                source="cache",
            )

        from backend.pipeline.llm import HintContext, LLMClient

        client = LLMClient(
            primary_model="google/gemini-2.5-flash",
            fallback_model="openai/gpt-4.1-mini",
            api_key="test",
            primary_timeout_ms=1,  # 1ms = instant timeout
            fallback_timeout_ms=5000,
        )
        client._generate_fallback = _fallback_complete

        ctx = HintContext(utterance="Тест", speaker="client", rag_context=[])
        result = await client.generate_hint(ctx)

        assert fallback_called
        assert result.headline == "Fallback hint"


# ── Prompt content ────────────────────────────────────────────────────


def test_prompt_contains_briefing_section() -> None:
    """User template contains БРИФИНГ and ИСТОРИЯ РАЗГОВОРА sections."""
    from backend.pipeline.llm import _USER_TEMPLATE

    assert "БРИФИНГ" in _USER_TEMPLATE
    assert "ИСТОРИЯ РАЗГОВОРА" in _USER_TEMPLATE
    assert "coaching" in _USER_TEMPLATE


def test_format_history_empty() -> None:
    """_format_history returns placeholder for empty list."""
    from backend.pipeline.llm import _format_history

    assert _format_history([]) == "(начало разговора)"


def test_format_history_with_entries() -> None:
    """_format_history formats speaker: text lines."""
    from backend.pipeline.llm import _format_history

    history = [
        {"speaker": "rep", "text": "Здравствуйте"},
        {"speaker": "client", "text": "Добрый день"},
    ]
    result = _format_history(history)
    assert result == "rep: Здравствуйте\nclient: Добрый день"


def test_prompt_template_uses_conversation_history() -> None:
    """User template uses conversation_history instead of session_summary."""
    from backend.pipeline.llm import _USER_TEMPLATE

    assert "{conversation_history}" in _USER_TEMPLATE
    assert "{session_summary}" not in _USER_TEMPLATE


def test_hint_response_includes_coaching() -> None:
    """HintResponse parses coaching field from JSON."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"hint": "tip", "source": "f.pdf", '
        '"sentiment": "neutral", "color": "blue", '
        '"coaching": "говорите медленнее"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.coaching == "говорите медленнее"


def test_hint_response_coaching_optional() -> None:
    """HintResponse defaults coaching and new fields to defaults."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"hint": "tip", "source": "f.pdf", '
        '"sentiment": "neutral", "color": "blue"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.coaching == ""
    assert resp.relevance == "on_topic"
    assert resp.reasoning == ""


def test_hint_response_off_topic() -> None:
    """HintResponse parses off_topic relevance for strategy deviation."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"reasoning": "менеджер говорит про медицинский инструмент, а не CRM", '
        '"relevance": "off_topic", '
        '"hint": "Вернитесь к теме CRM и болям клиента", '
        '"source": "", "sentiment": "negative", "color": "red"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.relevance == "off_topic"
    assert resp.color == "red"
    assert "менеджер" in resp.reasoning


def test_hint_response_off_topic_forces_red_color() -> None:
    """Off-topic relevance must enforce color=red regardless of LLM output."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"reasoning": "off topic", "relevance": "off_topic", '
        '"hint": "tip", "source": "", '
        '"sentiment": "neutral", "color": "green"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.color == "red", "off_topic must force color=red"


def test_hint_response_invalid_relevance_defaults_to_on_topic() -> None:
    """Invalid relevance values fall back to on_topic."""
    from backend.pipeline.llm import HintResponse

    for bad_value in ["off-topic", "ОТКЛОНЕНИЕ", "", "partially_relevant"]:
        raw = (
            '{"hint": "tip", "source": "", '
            f'"sentiment": "neutral", "color": "blue", "relevance": "{bad_value}"}}'
        )
        resp = HintResponse.from_json(raw)
        assert resp.relevance == "on_topic", f"'{bad_value}' should fall back to on_topic"


def test_speaker_specific_prompts_exist() -> None:
    """Client and rep system prompts exist and differ."""
    from backend.pipeline.llm import (
        _SYSTEM_PROMPT_CLIENT,
        _SYSTEM_PROMPT_REP,
    )

    assert "клиент" in _SYSTEM_PROMPT_CLIENT.lower()
    assert "менеджер" in _SYSTEM_PROMPT_REP.lower()
    assert _SYSTEM_PROMPT_CLIENT != _SYSTEM_PROMPT_REP


def test_rep_prompt_has_deviation_detection() -> None:
    """Rep system prompt must include strategy deviation detection rules."""
    from backend.pipeline.llm import _SYSTEM_PROMPT_REP

    assert "ОТКЛОНЕНИЕ" in _SYSTEM_PROMPT_REP
    assert "hint_type" in _SYSTEM_PROMPT_REP
    assert "ТЕМОЙ РАЗГОВОРА" in _SYSTEM_PROMPT_REP
    assert "reasoning" in _SYSTEM_PROMPT_REP


def test_user_template_has_sgr_cascade() -> None:
    """User template must include SGR cascade fields: reasoning before hint_type."""
    from backend.pipeline.llm import _USER_TEMPLATE

    assert "reasoning" in _USER_TEMPLATE
    assert "hint_type" in _USER_TEMPLATE
    # SGR cascade: reasoning must appear before hint_type in template
    assert _USER_TEMPLATE.index("reasoning") < _USER_TEMPLATE.index("hint_type")


# ── Smart cancellation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smart_cancel_skips_when_tokens_received() -> None:
    """_cancel_current(force=False) does NOT cancel when tokens_received > 0."""
    with patch("backend.pipeline.llm.AsyncOpenAI"):
        from backend.pipeline.llm import LLMClient

        client = LLMClient(
            primary_model="m", fallback_model="f", api_key="k",
            primary_timeout_ms=5000, fallback_timeout_ms=5000,
        )
        client._llm_task = asyncio.create_task(asyncio.sleep(10))
        client._tokens_received = 3
        original_task = client._llm_task

        client._cancel_current()  # force=False by default

        await asyncio.sleep(0)
        assert not original_task.cancelled(), "Should NOT cancel when tokens > 0"
        original_task.cancel()  # cleanup


@pytest.mark.asyncio
async def test_smart_cancel_force_overrides() -> None:
    """_cancel_current(force=True) cancels even when tokens_received > 0."""
    with patch("backend.pipeline.llm.AsyncOpenAI"):
        from backend.pipeline.llm import LLMClient

        client = LLMClient(
            primary_model="m", fallback_model="f", api_key="k",
            primary_timeout_ms=5000, fallback_timeout_ms=5000,
        )
        client._llm_task = asyncio.create_task(asyncio.sleep(10))
        client._tokens_received = 3

        client._cancel_current(force=True)

        await asyncio.sleep(0)
        assert client._llm_task is None
