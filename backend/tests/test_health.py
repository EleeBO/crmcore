"""Tests for health check endpoint (Task 1.1)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """Health endpoint returns HTTP 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_ok_status(client: AsyncClient) -> None:
    """Health endpoint returns status:ok when all services are up."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_includes_redis_status(client: AsyncClient) -> None:
    """Health endpoint reports Redis status."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert "redis" in data
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_fail_reports_error(mock_redis) -> None:
    """Health endpoint reports error when Redis is down."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import create_app

    mock_redis.ping.side_effect = Exception("Connection refused")
    app = create_app()
    app.state.redis = mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/v1/health")

    data = response.json()
    assert response.status_code == 503
    assert data["redis"] == "error"
    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_delete_session_returns_200(
    client: AsyncClient, mock_redis
) -> None:
    """DELETE /api/v1/session/{id} returns 200."""
    mock_redis.delete.return_value = 2
    response = await client.delete("/api/v1/session/test-session-123")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deleted"
    assert data["session_id"] == "test-session-123"


def test_lifespan_connects_redis() -> None:
    """Lifespan calls redis.asyncio.from_url."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from starlette.testclient import TestClient

    from backend.main import create_app

    mock_r = MagicMock()
    mock_r.ping = AsyncMock(return_value=True)
    mock_r.aclose = AsyncMock()

    with patch(
        "redis.asyncio.from_url", return_value=mock_r
    ) as mock_redis_from_url:
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")

    assert resp.status_code == 200
    mock_redis_from_url.assert_called_once()


def test_lifespan_redis_unavailable_does_not_crash() -> None:
    """If Redis is down at startup, app starts gracefully."""
    from unittest.mock import patch

    from starlette.testclient import TestClient

    from backend.main import create_app

    with patch(
        "redis.asyncio.from_url",
        side_effect=Exception("ECONNREFUSED"),
    ):
        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")

    assert resp.status_code in (200, 503)
