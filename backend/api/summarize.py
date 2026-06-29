"""Post-call summary endpoint (Task 6.2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.summarize.call_summary import generate_summary

router = APIRouter()


@router.post("/api/v1/summarize")
async def summarize(request: Request) -> JSONResponse:
    """Generate post-call summary + email draft."""
    cfg = request.app.state.settings

    body = await request.json()
    session_id: str = body.get("session_id", "")

    if not session_id:
        raise HTTPException(status_code=422, detail="session_id required")

    redis_client = getattr(request.app.state, "redis", None)

    result = await generate_summary(
        session_id=session_id,
        redis=redis_client,
        api_key=cfg.openrouter_api_key,
        model=cfg.llm_primary_model,
    )
    return JSONResponse(
        content={
            "summary": result.summary,
            "key_points": result.key_points,
            "action_items": result.action_items,
            "email_draft": result.email_draft,
        }
    )
