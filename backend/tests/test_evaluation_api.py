"""Tests for evaluation REST API (FEAT-004)."""
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.fixture
def app(mock_redis):
    a = FastAPI()
    a.state.redis = mock_redis
    from backend.api.evaluation import router as eval_router
    a.include_router(eval_router, prefix="/api/v1")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_config_returns_default(client, mock_redis):
    mock_redis.get.return_value = None
    resp = client.get("/api/v1/evaluation-config")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["criteria"]) == 7


def test_put_config_saves(client, mock_redis):
    payload = DEFAULT_CONFIG.model_dump()
    resp = client.put("/api/v1/evaluation-config", json=payload)
    assert resp.status_code == 200
    mock_redis.set.assert_called_once()


def test_put_config_invalid_weights(client, mock_redis):
    payload = DEFAULT_CONFIG.model_dump()
    payload["criteria"][0]["weight"] = 0.99  # sum > 1.0
    resp = client.put("/api/v1/evaluation-config", json=payload)
    assert resp.status_code == 422


def test_reset_config(client, mock_redis):
    resp = client.post("/api/v1/evaluation-config/reset")
    assert resp.status_code == 200
    mock_redis.delete.assert_called_once()


def test_get_evaluation_requires_token(client, mock_redis):
    resp = client.get("/api/v1/evaluation/test-session")
    assert resp.status_code == 403


def test_get_evaluation_invalid_token(client, mock_redis):
    mock_redis.get.side_effect = lambda k: (
        b"real-token" if "eval_token" in k else None
    )
    resp = client.get("/api/v1/evaluation/test-session?token=wrong")
    assert resp.status_code == 403


def test_get_evaluation_success(client, mock_redis):
    eval_data = {
        "call_summary": "test",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }

    async def _get(key):
        if "eval_token" in key:
            return b"valid-token"
        if "eval:" in key:
            return json.dumps(eval_data).encode()
        return None

    mock_redis.get = AsyncMock(side_effect=_get)
    resp = client.get("/api/v1/evaluation/test-session?token=valid-token")
    assert resp.status_code == 200
    assert resp.json()["call_summary"] == "test"


def test_get_evaluation_includes_analytics(client, mock_redis):
    """GET /evaluation includes analytics when stored in Redis."""
    eval_data = {
        "call_summary": "test",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    analytics_data = {
        "total_duration_s": 120.0,
        "rep_talk_ratio": 0.45,
        "rep_talk_time_s": 50.0,
        "client_talk_time_s": 60.0,
        "rep_speech_rate_wpm": 130,
        "client_speech_rate_wpm": 110,
        "interruptions_by_rep": 2,
        "interruptions_by_client": 1,
        "avg_rep_pause_before_response_s": 1.3,
        "rep_word_count": 200,
        "client_word_count": 180,
    }

    async def _get(key):
        if "eval_token" in key:
            return b"valid-token"
        if "eval_analytics" in key:
            return json.dumps(analytics_data).encode()
        if "eval:" in key:
            return json.dumps(eval_data).encode()
        return None

    mock_redis.get = AsyncMock(side_effect=_get)
    resp = client.get(
        "/api/v1/evaluation/test-session?token=valid-token",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "analytics" in data
    assert data["analytics"]["rep_talk_ratio"] == 0.45
    assert data["analytics"]["total_duration_s"] == 120.0


def test_get_evaluation_no_analytics(client, mock_redis):
    """GET /evaluation omits analytics when not in Redis."""
    eval_data = {
        "call_summary": "test",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }

    async def _get(key):
        if "eval_token" in key:
            return b"valid-token"
        if "eval:" in key:
            return json.dumps(eval_data).encode()
        return None

    mock_redis.get = AsyncMock(side_effect=_get)
    resp = client.get(
        "/api/v1/evaluation/test-session?token=valid-token",
    )
    assert resp.status_code == 200
    assert "analytics" not in resp.json()
