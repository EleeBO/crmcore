"""Pre-call briefing endpoint (Task 6.1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.briefing.portrait import generate_briefing

router = APIRouter()


@router.post("/api/v1/briefing")
async def briefing(request: Request) -> JSONResponse:
    """Generate pre-call briefing: buyer portrait + strategy + objections."""
    cfg = request.app.state.settings

    body = await request.json()
    session_id: str = body.get("session_id", "")
    kb_id: str = body.get("kb_id", "")

    if not session_id or not kb_id:
        raise HTTPException(status_code=422, detail="session_id and kb_id required")

    redis_client = getattr(request.app.state, "redis", None)

    result = await generate_briefing(
        kb_id=kb_id,
        session_id=session_id,
        redis=redis_client,
        api_key=cfg.openrouter_api_key,
        model=cfg.llm_primary_model,
    )
    return JSONResponse(content=result.model_dump(by_alias=True))
