"""AI Sales Copilot -- FastAPI backend entry point (composition root)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.websockets import WebSocket

from backend.config import Settings
from backend.logger import logger, setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = settings or Settings()
    setup_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        import redis.asyncio as aioredis

        logger.info("Starting AI Sales Copilot backend")

        # -- Redis ---------------------------------------------------------
        try:
            r = aioredis.from_url(cfg.redis_url, decode_responses=False)
            await r.ping()
            app.state.redis = r
            logger.info(f"Redis connected: {cfg.redis_url}")
        except Exception as exc:
            logger.warning(f"Redis unavailable (continuing without): {exc}")
            app.state.redis = None

        yield

        # -- Shutdown ------------------------------------------------------
        if getattr(app.state, "redis", None) is not None:
            await app.state.redis.aclose()
        logger.info("Shutting down AI Sales Copilot backend")

    app = FastAPI(
        title="AI Sales Copilot",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = cfg

    # -- Register routers --------------------------------------------------
    from backend.api.briefing import router as briefing_router
    from backend.api.evaluation import router as evaluation_router
    from backend.api.health import router as health_router
    from backend.api.session import router as session_router
    from backend.api.summarize import router as summarize_router
    from backend.api.upload import router as upload_router
    from backend.ws.handler import WebSocketHandler

    app.include_router(health_router)
    app.include_router(upload_router)
    app.include_router(session_router)
    app.include_router(briefing_router)
    app.include_router(summarize_router)
    app.include_router(evaluation_router, prefix="/api/v1")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        handler = WebSocketHandler(cfg=app.state.settings, redis=app.state.redis)
        await handler.run(websocket)

    return app


# For running directly: uvicorn backend.main:app
app = create_app()
