"""File upload and scenario generation endpoint."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.errors import IngestionError
from backend.ingestion.chunker import chunk_table, chunk_text
from backend.ingestion.parser import ParsedChunk, parse_file
from backend.logger import logger

router = APIRouter()


@router.post("/api/v1/upload")
async def upload(request: Request) -> JSONResponse:
    """Upload knowledge base files: parse -> store full text in Redis context."""
    cfg = request.app.state.settings

    # ~120K chars ~ 30K tokens -- fits well inside Gemini Flash 1M context
    max_context_chars = 120_000
    max_file_bytes = 50 * 1024 * 1024  # 50 MB

    form = await request.form()
    session_id: str = form.get("session_id", "")  # type: ignore[assignment]
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")

    raw_files = form.getlist("files")
    if not raw_files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    start = time.monotonic()
    kb_id = str(uuid.uuid4())
    redis_client = getattr(request.app.state, "redis", None)

    all_chunks: list[ParsedChunk] = []
    failed_files: list[dict[str, str]] = []
    files_indexed = 0

    for f in raw_files:
        filename: str = getattr(f, "filename", None) or "unknown"
        try:
            data: bytes = await f.read()  # type: ignore[union-attr]
            if len(data) > max_file_bytes:
                failed_files.append(
                    {"name": filename, "error": "File too large (>50MB)"}
                )
                continue
            parsed = parse_file(data, filename)
            if any(c.chunk_type == "table" for c in parsed):
                chunks = chunk_table(parsed)
            else:
                chunks = chunk_text(parsed)
            all_chunks.extend(chunks)
            files_indexed += 1
        except IngestionError as exc:
            failed_files.append({"name": filename, "error": exc.message})
        except Exception as exc:
            failed_files.append({"name": filename, "error": str(exc)})

    if not all_chunks:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "No content could be extracted from the uploaded files.",
                "failed_files": failed_files,
            },
        )

    from backend.pipeline.scenario import generate_scenario

    # File-level truncation: don't cut a file in the middle
    docs_text = ""
    for chunk in all_chunks:
        candidate = chunk.text
        separator = "\n\n---\n\n" if docs_text else ""
        if len(docs_text) + len(separator) + len(candidate) > max_context_chars:
            logger.warning(
                f"Truncated docs at file level: {len(docs_text)} chars, "
                "skipping remaining"
            )
            break
        docs_text += separator + candidate

    # Generate scenario via LLM
    scenario = await generate_scenario(
        docs_text=docs_text,
        api_key=cfg.openrouter_api_key,
        model=cfg.llm_primary_model,
    )
    scenario_json = scenario.model_dump_json()

    if redis_client is not None:
        await redis_client.set(f"kb:{kb_id}:docs", docs_text.encode(), ex=7200)
        await redis_client.set(f"session:{session_id}:kb_id", kb_id, ex=1800)
        await redis_client.set(f"kb:{kb_id}:scenario", scenario_json.encode(), ex=7200)
    else:
        logger.warning(f"Redis unavailable -- scenario not persisted for kb={kb_id}")

    scenario_preview: dict[str, Any] | None = None
    if scenario.key_facts or scenario.objections:
        scenario_preview = {
            "portrait": scenario.portrait.model_dump(),
            "strategy": scenario.strategy.model_dump(),
            "objections_count": len(scenario.objections),
            "key_facts_count": len(scenario.key_facts),
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)
    status = 207 if failed_files else 200

    logger.info(
        f"Upload: session={session_id} kb={kb_id} "
        f"chunks={len(all_chunks)} ok={files_indexed} "
        f"fail={len(failed_files)} ms={elapsed_ms}"
    )

    return JSONResponse(
        status_code=status,
        content={
            "knowledge_base_id": kb_id,
            "files_indexed": files_indexed,
            "chunks_count": len(all_chunks),
            "time_ms": elapsed_ms,
            "failed_files": failed_files,
            "scenario": scenario_preview,
            "scenario_generated": scenario_preview is not None,
        },
    )
