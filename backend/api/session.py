"""Session management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from backend.logger import logger
from backend.session.manager import SessionManager

router = APIRouter()


@router.delete("/api/v1/session/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    kb_id: str = Query("", description="Knowledge base ID for briefing cache cleanup"),
) -> dict[str, Any]:
    """Delete all session resources from Redis."""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            # Read kb_id from Redis if not provided via query param
            effective_kb_id = kb_id
            if not effective_kb_id:
                raw = await redis_client.get(f"session:{session_id}:kb_id")
                if raw:
                    effective_kb_id = raw.decode() if isinstance(raw, bytes) else raw

            mgr = SessionManager(redis=redis_client)
            await mgr.cleanup_session(session_id, kb_id=effective_kb_id)
        except Exception as exc:
            logger.warning(f"Redis cleanup failed for session {session_id}: {exc}")

    logger.info(f"Session {session_id} deleted")
    return {"status": "deleted", "session_id": session_id}
