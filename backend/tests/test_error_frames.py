"""Tests for WS error frames sent to extension on backend failures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_llm_failure_handled_gracefully() -> None:
    """When LLM stream raises, orchestrator handles it without crashing.

    With silent generation, LLM errors are logged internally — no error
    frame is sent to the frontend, and no hint_end is produced.
    """
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    # LLM that raises on streaming
    async def failing_stream(ctx):
        raise RuntimeError("LLM provider timeout")
        # Make it a generator
        yield  # type: ignore[misc]  # noqa: E501

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = failing_stream

    session_mgr = AsyncMock()
    session_mgr.get_context = AsyncMock(
        return_value=MagicMock(utterances=[], summary="")
    )

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-err",
        llm_client=llm,
        session_manager=session_mgr,
        scenario_text="test",
    )

    t = Transcript(speaker="client", text="Test question", is_final=True)
    await orch.handle_transcript(t)

    # Silent generation swallows the error — no hint_end, no error frame
    hint_ends = [m for m in ws_messages if m.get("type") == "hint_end"]
    assert len(hint_ends) == 0, "Failed LLM should not produce hint_end"


@pytest.mark.asyncio
async def test_session_start_failure_sends_error_frame() -> None:
    """When session_start fails in WS handler, error frame is sent."""
    import json
    import struct

    from starlette.testclient import TestClient

    from backend.main import create_app

    app = create_app()
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    # Make scenario lookup raise
    mock_redis.get = AsyncMock(side_effect=RuntimeError("Redis connection lost"))
    app.state.redis = mock_redis

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws_conn:
        # Send session_start control frame
        ctrl_payload = json.dumps({
            "type": "session_start",
            "session_id": "test-fail",
            "kb_id": "test-kb",
        }).encode()
        header = struct.pack("<IB", 1, 1)  # seq=1, channel=1 (control)
        ws_conn.send_bytes(header + ctrl_payload)

        # The handler should send an error frame back
        resp = ws_conn.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "SESSION_START_FAILED"
