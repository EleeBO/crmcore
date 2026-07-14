"""Tests for Redis=None resilience: SessionManager and briefing endpoint."""

import pytest

from backend.session.manager import SessionContext, SessionManager


@pytest.mark.asyncio
async def test_session_manager_add_utterance_with_none_redis():
    """add_utterance should no-op silently when redis is None."""
    mgr = SessionManager(redis=None)
    # Should not raise
    await mgr.add_utterance("sess-1", "client", "hello")


@pytest.mark.asyncio
async def test_session_manager_get_context_with_none_redis():
    """get_context should return empty SessionContext when redis is None."""
    mgr = SessionManager(redis=None)
    ctx = await mgr.get_context("sess-1")
    assert isinstance(ctx, SessionContext)
    assert ctx.utterances == []
    assert ctx.summary == ""


@pytest.mark.asyncio
async def test_session_manager_update_summary_with_none_redis():
    """update_summary should no-op silently when redis is None."""
    mgr = SessionManager(redis=None)

    async def dummy_summarise(text: str) -> str:
        return "summary"

    # Should not raise
    await mgr.update_summary("sess-1", dummy_summarise)


@pytest.mark.asyncio
async def test_briefing_endpoint_with_none_redis():
    """Briefing endpoint should return 200 with fallback data when redis is None."""

    from httpx import ASGITransport, AsyncClient

    from backend.main import create_app

    app = create_app()
    app.state.redis = None  # Simulate Redis unavailable

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/v1/briefing",
            json={"session_id": "test-session", "kb_id": "test-kb"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "contact" in data
        assert "focusPoints" in data
        assert "objections" in data
