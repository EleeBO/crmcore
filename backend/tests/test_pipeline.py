"""Tests for Pipeline Orchestrator + Session Manager (FEAT-001)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Session Manager ────────────────────────────────────────────────────────


def test_session_manager_creation() -> None:
    """SessionManager can be created with a Redis client."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    manager = SessionManager(redis)
    assert manager is not None


@pytest.mark.asyncio
async def test_session_utterance_buffer() -> None:
    """add_utterance pushes to Redis list and trims to 10 entries."""
    from backend.session.manager import SessionManager

    # Create pipe mock (not async) since pipeline() is not async
    pipe = MagicMock()
    pipe.execute = AsyncMock(return_value=[])
    pipe.rpush = MagicMock(return_value=None)
    pipe.ltrim = MagicMock(return_value=None)
    pipe.expire = MagicMock(return_value=None)

    redis = MagicMock()
    redis.pipeline.return_value = pipe

    manager = SessionManager(redis)
    await manager.add_utterance("sess-001", "client", "Какой RTO?")

    redis.pipeline.assert_called_once()
    pipe.rpush.assert_called()
    pipe.ltrim.assert_called_once()
    pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_conversation_history_happy_path() -> None:
    """get_conversation_history returns parsed dicts from eval_transcript."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        b'{"speaker": "rep", "text": "Hello"}',
        b'{"speaker": "client", "text": "Hi"}',
        b'{"speaker": "rep", "text": "How can I help?"}',
    ])

    manager = SessionManager(redis)
    history = await manager.get_conversation_history("sess-001")

    assert len(history) == 3
    assert history[0] == {"speaker": "rep", "text": "Hello"}
    assert history[2] == {"speaker": "rep", "text": "How can I help?"}


@pytest.mark.asyncio
async def test_conversation_history_empty() -> None:
    """get_conversation_history returns empty list when no entries."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])

    manager = SessionManager(redis)
    history = await manager.get_conversation_history("sess-001")

    assert history == []


@pytest.mark.asyncio
async def test_conversation_history_corrupt_json_skipped() -> None:
    """Corrupt JSON entries are skipped with warning."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        b'{"speaker": "rep", "text": "Good"}',
        b'not-json-at-all',
        b'{"speaker": "client", "text": "Also good"}',
    ])

    manager = SessionManager(redis)
    history = await manager.get_conversation_history("sess-001")

    assert len(history) == 2


@pytest.mark.asyncio
async def test_conversation_history_redis_none() -> None:
    """get_conversation_history returns [] when Redis is None."""
    from backend.session.manager import SessionManager

    manager = SessionManager(redis=None)
    history = await manager.get_conversation_history("sess-001")

    assert history == []


@pytest.mark.asyncio
async def test_conversation_history_with_limit() -> None:
    """get_conversation_history with limit=2 uses correct LRANGE args."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[
        b'{"speaker": "rep", "text": "A"}',
        b'{"speaker": "client", "text": "B"}',
    ])

    manager = SessionManager(redis)
    await manager.get_conversation_history("sess-001", limit=2)

    redis.lrange.assert_called_once()
    args = redis.lrange.call_args[0]
    assert args[1] == -2  # start = -limit
    assert args[2] == -1  # end


@pytest.mark.asyncio
async def test_conversation_history_exclude_last() -> None:
    """exclude_last=True uses LRANGE end=-2 to skip current utterance."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])

    manager = SessionManager(redis)
    await manager.get_conversation_history("sess-001", exclude_last=True)

    args = redis.lrange.call_args[0]
    assert args[2] == -2  # end = -2 (exclude last)


@pytest.mark.asyncio
async def test_conversation_history_limit_with_exclude_last() -> None:
    """limit=2 + exclude_last=True offsets start correctly."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])

    manager = SessionManager(redis)
    await manager.get_conversation_history("sess-001", limit=2, exclude_last=True)

    args = redis.lrange.call_args[0]
    assert args[1] == -3  # start = -(limit + 1)
    assert args[2] == -2  # end = -2


@pytest.mark.asyncio
async def test_session_get_context_returns_utterances() -> None:
    """get_context returns SessionContext with parsed utterances."""
    from backend.session.manager import SessionContext, SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(
        return_value=[b'{"speaker": "client", "text": "Hello"}']
    )
    redis.get = AsyncMock(return_value=None)

    manager = SessionManager(redis)
    ctx = await manager.get_context("sess-001")

    assert isinstance(ctx, SessionContext)
    assert len(ctx.utterances) == 1
    assert ctx.utterances[0]["speaker"] == "client"


@pytest.mark.asyncio
async def test_session_rolling_summary() -> None:
    """update_summary persists a generated summary to Redis."""
    from backend.session.manager import SessionManager

    redis = AsyncMock()
    redis.lrange = AsyncMock(
        return_value=[b'{"speaker": "client", "text": "Test"}']
    )
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)

    async def fake_summarise(text: str) -> str:
        return "Обсуждали тарифы"

    manager = SessionManager(redis)
    await manager.update_summary("sess-001", fake_summarise)

    redis.set.assert_called_once()


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient with streaming support."""
    client = MagicMock()
    client._cancel_current = MagicMock()

    async def _stream(ctx):
        for token in [
            '{"reasoning": "клиент спросил про RTO", ',
            '"hint_type": "success", ',
            '"headline": "Упомяните RTO 15 минут", "source": "tariffs.pdf"}',
        ]:
            yield token

    client.generate_hint_stream = _stream
    client.generate_hint = AsyncMock(
        return_value=MagicMock(
            hint_type="success",
            headline="Упомяните RTO 15 минут",
            source="tariffs.pdf",
        )
    )
    return client


@pytest.fixture
def mock_session_manager() -> AsyncMock:
    """Mock SessionManager."""
    manager = AsyncMock()
    manager.add_utterance = AsyncMock()
    manager.get_context = AsyncMock(
        return_value=MagicMock(utterances=[], summary="", portrait="", strategy="")
    )
    manager.get_conversation_history = AsyncMock(return_value=[])
    manager.update_summary = AsyncMock()
    return manager


# ── Orchestrator ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_accepts_scenario(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """Orchestrator accepts scenario_text instead of rag_engine."""
    from backend.pipeline.orchestrator import PipelineOrchestrator

    ws = AsyncMock()
    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text='{"portrait": {}, "key_facts": []}',
    )
    assert orch._scenario_text == '{"portrait": {}, "key_facts": []}'


@pytest.mark.asyncio
async def test_transcript_forwarded_to_websocket(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """handle_transcript sends transcript JSON to WebSocket."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text="test scenario",
    )

    t = Transcript(speaker="client", text="Привет", is_final=False)
    await orch.handle_transcript(t)

    transcript_msgs = [m for m in ws_messages if m.get("type") == "transcript"]
    assert len(transcript_msgs) == 1
    assert transcript_msgs[0]["speaker"] == "client"
    assert transcript_msgs[0]["text"] == "Привет"
    assert transcript_msgs[0]["is_final"] is False


@pytest.mark.asyncio
async def test_transcript_includes_utterance_id(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """WS transcript message includes utterance_id field."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text="",
    )

    t = Transcript(
        speaker="client",
        text="Hi",
        is_final=True,
        utterance_id="client-1",
    )
    await orch.handle_transcript(t)

    transcript_msg = [
        m for m in ws_messages if m["type"] == "transcript"
    ][0]
    assert transcript_msg["utterance_id"] == "client-1"


@pytest.mark.asyncio
async def test_pipeline_full_flow(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """Final client transcript triggers hint delivery via WebSocket."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text="SLA Gold: RTO 15 минут",
    )

    t = Transcript(speaker="client", text="Какой RTO у SLA Gold?", is_final=True)
    await orch.handle_transcript(t)

    assert len(ws_messages) > 0
    msg_types = {m.get("type") for m in ws_messages}
    assert "transcript" in msg_types
    assert "hint_end" in msg_types
    assert "hint_start" not in msg_types


@pytest.mark.asyncio
async def test_pipeline_uses_scenario_in_hint(
    mock_session_manager: AsyncMock,
) -> None:
    """HintContext receives scenario_text in rag_context field."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    captured_ctx = []

    async def capture_stream(ctx):
        captured_ctx.append(ctx)
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = capture_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="My scenario text",
    )

    t = Transcript(speaker="client", text="Вопрос", is_final=True)
    await orch.handle_transcript(t)

    assert len(captured_ctx) == 1
    assert captured_ctx[0].rag_context == ["My scenario text"]


@pytest.mark.asyncio
async def test_pipeline_no_scenario_empty_context(
    mock_session_manager: AsyncMock,
) -> None:
    """Without scenario, rag_context is empty list."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    captured_ctx = []

    async def capture_stream(ctx):
        captured_ctx.append(ctx)
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = capture_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="",
    )

    t = Transcript(speaker="client", text="Вопрос", is_final=True)
    await orch.handle_transcript(t)

    assert len(captured_ctx) == 1
    assert captured_ctx[0].rag_context == []


@pytest.mark.asyncio
async def test_rep_speech_triggers_pipeline(
    mock_session_manager: AsyncMock,
) -> None:
    """Rep (manager) speech triggers pipeline with speaker='rep'."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    captured_ctx: list = []

    async def capture_stream(ctx):  # type: ignore[no-untyped-def]
        captured_ctx.append(ctx)
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = capture_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t = Transcript(speaker="rep", text="Наш продукт", is_final=True)
    await orch.handle_transcript(t)

    assert len(captured_ctx) == 1
    assert captured_ctx[0].speaker == "rep"


@pytest.mark.asyncio
async def test_orchestrator_teardown() -> None:
    """teardown() cancels all in-flight background tasks."""
    from backend.pipeline.orchestrator import PipelineOrchestrator

    ws = AsyncMock()
    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=MagicMock(),
        session_manager=AsyncMock(),
    )

    task = asyncio.create_task(asyncio.sleep(10))
    orch._background_tasks.add(task)

    await orch.teardown()

    assert all(t.done() for t in orch._background_tasks)


@pytest.mark.asyncio
async def test_silent_hint_generation(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """Hint is delivered as a single hint_end — no hint_start or hint_chunk."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text="test scenario",
    )

    t = Transcript(speaker="client", text="Какой RTO?", is_final=True)
    await orch.handle_transcript(t)

    msg_types = {m.get("type") for m in ws_messages}
    assert "hint_end" in msg_types
    assert "hint_start" not in msg_types, "Silent generation should not send hint_start"
    assert "hint_chunk" not in msg_types, "Silent generation should not send hint_chunk"


@pytest.mark.asyncio
async def test_pipeline_cooldown_skips_rapid_hints(
    mock_session_manager: AsyncMock,
) -> None:
    """Two rapid handle_transcript calls — second hint is blocked by cooldown."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    hint_count = 0

    async def counting_stream(ctx):
        nonlocal hint_count
        hint_count += 1
        yield (
            '{"reasoning": "test", "hint_type": "coaching", '
            '"headline": "ok", "source": "", "detail": "", "coaching": ""}'
        )

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = counting_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t1 = Transcript(speaker="client", text="First", is_final=True)
    t2 = Transcript(speaker="client", text="Second", is_final=True)

    await orch.handle_transcript(t1)
    # Immediately send second — should be blocked by cooldown
    await orch.handle_transcript(t2)

    assert hint_count == 1, f"Expected 1 hint (cooldown), got {hint_count}"


@pytest.mark.asyncio
async def test_pipeline_cooldown_allows_after_timeout(
    mock_session_manager: AsyncMock,
) -> None:
    """After cooldown expires, next utterance triggers a hint."""
    import time

    from backend.pipeline import orchestrator as orch_mod
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    hint_count = 0

    async def counting_stream(ctx):
        nonlocal hint_count
        hint_count += 1
        yield (
            '{"reasoning": "test", "hint_type": "coaching", '
            '"headline": "ok", "source": "", "detail": "", "coaching": ""}'
        )

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = counting_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t1 = Transcript(speaker="client", text="First", is_final=True)
    await orch.handle_transcript(t1)
    assert hint_count == 1

    # Simulate cooldown elapsed
    orch._last_hint_time = time.monotonic() - orch_mod._HINT_COOLDOWN_S - 1.0

    t2 = Transcript(speaker="client", text="Second", is_final=True)
    await orch.handle_transcript(t2)
    assert hint_count == 2, "Should fire after cooldown"


@pytest.mark.asyncio
async def test_hint_generation_timeout(
    mock_session_manager: AsyncMock,
) -> None:
    """Slow LLM that exceeds timeout produces no hint_end."""
    from backend.pipeline.orchestrator import (
        _HINT_GENERATION_TIMEOUT_S,
        PipelineOrchestrator,
    )
    from backend.pipeline.stt import Transcript

    async def slow_stream(ctx):
        await asyncio.sleep(_HINT_GENERATION_TIMEOUT_S + 2)
        yield '{"hint": "late", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = slow_stream

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t = Transcript(speaker="client", text="Question", is_final=True)
    timeout = _HINT_GENERATION_TIMEOUT_S + 3
    await asyncio.wait_for(orch.handle_transcript(t), timeout=timeout)

    hint_ends = [m for m in ws_messages if m.get("type") == "hint_end"]
    assert len(hint_ends) == 0, "Timed-out generation should not send hint_end"


@pytest.mark.asyncio
async def test_hint_end_v2_includes_hint_type(
    mock_session_manager: AsyncMock,
) -> None:
    """hint_end v2 WebSocket message must include hint_type from LLM response."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    async def warning_stream(ctx):
        yield (
            '{"reasoning": "менеджер говорит про погоду, не про CRM", '
            '"hint_type": "warning", '
            '"headline": "Вернитесь к теме CRM", '
            '"detail": "Клиент ждёт обсуждения продукта", '
            '"coaching": "мягко верните разговор", '
            '"source": ""}'
        )

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = warning_stream

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s-offtopic",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text='{"strategy": {"approach": "CRM продажа"}}',
    )

    t = Transcript(speaker="rep", text="А вот сегодня погода хорошая", is_final=True)
    await orch.handle_transcript(t)

    hint_msgs = [m for m in ws_messages if m.get("type") == "hint_end"]
    assert len(hint_msgs) == 1
    assert hint_msgs[0]["v"] == 2
    assert hint_msgs[0]["hint_type"] == "warning"
    assert hint_msgs[0]["headline"] == "Вернитесь к теме CRM"


# ── Conversation History (FEAT-010) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_passes_conversation_history(
    mock_session_manager: AsyncMock,
) -> None:
    """_run_pipeline passes conversation_history from SessionManager to HintContext."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    captured_ctx = []

    async def capture_stream(ctx):
        captured_ctx.append(ctx)
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    history = [
        {"speaker": "rep", "text": "Здравствуйте"},
        {"speaker": "client", "text": "Добрый день"},
    ]
    mock_session_manager.get_conversation_history = AsyncMock(return_value=history)

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = capture_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t = Transcript(speaker="client", text="Какая цена?", is_final=True)
    await orch.handle_transcript(t)

    assert len(captured_ctx) == 1
    assert captured_ctx[0].conversation_history == history
    mock_session_manager.get_conversation_history.assert_called_once_with(
        "s1", limit=50, exclude_last=True,
    )


@pytest.mark.asyncio
async def test_pipeline_history_fallback_on_error(
    mock_session_manager: AsyncMock,
) -> None:
    """If get_conversation_history raises, pipeline uses empty history."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    captured_ctx = []

    async def capture_stream(ctx):
        captured_ctx.append(ctx)
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    mock_session_manager.get_conversation_history = AsyncMock(
        side_effect=RuntimeError("Redis down")
    )

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = capture_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t = Transcript(speaker="client", text="Вопрос", is_final=True)
    await orch.handle_transcript(t)

    assert len(captured_ctx) == 1
    assert captured_ctx[0].conversation_history == []


@pytest.mark.asyncio
async def test_pipeline_custom_hint_context_utterances(
    mock_session_manager: AsyncMock,
) -> None:
    """hint_context_utterances setting is passed to get_conversation_history."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    async def noop_stream(ctx):
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    mock_session_manager.get_conversation_history = AsyncMock(return_value=[])

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = noop_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
        hint_context_utterances=20,
    )

    t = Transcript(speaker="client", text="Вопрос", is_final=True)
    await orch.handle_transcript(t)

    mock_session_manager.get_conversation_history.assert_called_once_with(
        "s1", limit=20, exclude_last=True,
    )
