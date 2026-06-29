"""Health check and preflight endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.logger import logger

router = APIRouter()


@router.get("/api/v1/health")
async def health(request: Request) -> JSONResponse:
    """Check health of all dependencies."""
    redis_status = "ok"
    overall = "ok"

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            await redis_client.ping()
        except Exception as exc:
            logger.warning(f"Redis health check failed: {exc}")
            redis_status = "error"
    else:
        redis_status = "unavailable"

    if redis_status == "error":
        overall = "degraded"

    status_code = 503 if overall == "degraded" else 200
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "redis": redis_status,
        },
    )


async def _check_stt_yandex(cfg: Any) -> dict[str, str]:
    """Verify Yandex SpeechKit API key via gRPC channel."""
    if not cfg.yandex_speechkit_api_key:
        return {
            "status": "error",
            "provider": "yandex",
            "detail": "API key not configured",
        }
    try:
        import grpc
        import grpc.aio

        cred = grpc.ssl_channel_credentials()
        host = "stt.api.cloud.yandex.net:443"
        async with grpc.aio.secure_channel(host, cred) as ch:
            # Check channel connectivity
            await ch.channel_ready()
        return {"status": "ok", "provider": "yandex"}
    except Exception as exc:
        return {
            "status": "error",
            "provider": "yandex",
            "detail": str(exc)[:100],
        }


@router.get("/api/v1/preflight")
async def preflight(request: Request) -> JSONResponse:
    """Check connectivity to all external services (STT, LLM, Redis)."""
    cfg = request.app.state.settings
    results: dict[str, dict[str, str]] = {}

    # Task 1.7: support ?provider= query param override
    stt_provider = request.query_params.get("provider", cfg.stt_provider)

    async def check_stt() -> dict[str, str]:
        """Verify STT provider connectivity."""
        if stt_provider == "salutespeech":
            try:
                from backend.pipeline.stt import SaluteSpeechSTT

                client = SaluteSpeechSTT(
                    api_key=cfg.sber_speech_api_key,
                    scope=cfg.sber_speech_scope,
                )
                await client._get_token()
                return {
                    "status": "ok",
                    "provider": "salutespeech",
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "provider": "salutespeech",
                    "detail": str(exc)[:200],
                }
        if stt_provider == "yandex":
            return await _check_stt_yandex(cfg)
        return {"status": "ok", "provider": stt_provider}

    async def check_llm() -> dict[str, str]:
        """Verify OpenRouter API key by hitting /models."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {cfg.openrouter_api_key}"},
                )
                resp.raise_for_status()
            return {"status": "ok", "model": cfg.llm_primary_model}
        except Exception as exc:
            return {
                "status": "error",
                "model": cfg.llm_primary_model,
                "detail": str(exc)[:200],
            }

    async def check_redis() -> dict[str, str]:
        """Ping Redis."""
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is None:
            return {"status": "unavailable"}
        try:
            await redis_client.ping()
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)[:200]}

    stt_result, llm_result, redis_result = await asyncio.gather(
        check_stt(), check_llm(), check_redis()
    )
    results = {"stt": stt_result, "llm": llm_result, "redis": redis_result}

    statuses = [r["status"] for r in results.values()]
    if all(s == "ok" for s in statuses):
        status_code = 200
    elif any(s == "error" for s in statuses):
        status_code = 207
    else:
        status_code = 207

    return JSONResponse(status_code=status_code, content=results)
