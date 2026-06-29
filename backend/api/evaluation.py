"""REST API for evaluation config and results (FEAT-004)."""

from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, EvaluationConfig
from backend.storage.keys import (
    eval_analytics,
    eval_config,
    eval_result,
    eval_token,
)

router = APIRouter()


def _get_redis(request: Request) -> Any:
    """FastAPI dependency: get Redis from app.state."""
    return getattr(request.app.state, "redis", None)


async def _load_config(redis: Any) -> EvaluationConfig:
    if redis is None:
        return DEFAULT_CONFIG
    raw = await redis.get(eval_config())
    if raw is None:
        return DEFAULT_CONFIG
    data = json.loads(raw)
    return EvaluationConfig.model_validate(data)


@router.get("/evaluation-config")
async def get_config(request: Request) -> dict:
    redis = _get_redis(request)
    config = await _load_config(redis)
    return config.model_dump()


@router.put("/evaluation-config")
async def put_config(
    payload: EvaluationConfig,
    request: Request,
) -> dict:
    redis = _get_redis(request)
    if redis is not None:
        await redis.set(eval_config(), payload.model_dump_json())
    return payload.model_dump()


@router.post("/evaluation-config/reset")
async def reset_config(request: Request) -> dict:
    redis = _get_redis(request)
    if redis is not None:
        await redis.delete(eval_config())
    return DEFAULT_CONFIG.model_dump()


@router.get("/evaluation/{session_id}")
async def get_evaluation(
    session_id: str,
    request: Request,
    token: str = Query(default=""),
) -> dict:
    redis = _get_redis(request)
    if not token:
        raise HTTPException(status_code=403, detail="Token required")
    if redis is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    stored_token = await redis.get(eval_token(session_id))
    if stored_token is None:
        raise HTTPException(status_code=403, detail="Invalid token")

    stored_str = (
        stored_token.decode() if isinstance(stored_token, bytes) else stored_token
    )
    if not hmac.compare_digest(stored_str, token):
        raise HTTPException(status_code=403, detail="Invalid token")

    raw = await redis.get(eval_result(session_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    data = json.loads(raw)

    analytics_raw = await redis.get(eval_analytics(session_id))
    if analytics_raw:
        analytics_str = (
            analytics_raw.decode()
            if isinstance(analytics_raw, bytes)
            else analytics_raw
        )
        data["analytics"] = json.loads(analytics_str)

    return data
