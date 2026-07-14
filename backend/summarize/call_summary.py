"""Post-call summary + email draft generation (Task 6.2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from backend.logger import logger
from backend.pipeline.shared_llm import call_llm_simple
from backend.storage.keys import session_summary, session_utterances


@dataclass
class CallSummary:
    """Structured post-call summary with email draft."""

    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    email_draft: str = ""


_SYSTEM_PROMPT = (
    "Ты — ИИ-ассистент для CRM. Создай резюме звонка и черновик follow-up письма. "
    "Отвечай ТОЛЬКО валидным JSON без комментариев."
)

_SUMMARY_TEMPLATE = (
    "Транскрипт звонка:\n{transcript}\n\n"
    "Краткое резюме разговора:\n{rolling_summary}\n\n"
    "Создай резюме в формате JSON:\n"
    "{{\n"
    '  "summary": "Краткое описание звонка",\n'
    '  "key_points": ["Ключевой момент 1", "Ключевой момент 2"],\n'
    '  "action_items": ["Действие 1", "Действие 2"],\n'
    '  "email_draft": "Текст follow-up письма"\n'
    "}}"
)


def _parse_summary(raw: str) -> CallSummary:
    """Parse LLM JSON response into CallSummary, stripping code fences."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse summary JSON: {exc}")
        return CallSummary(summary=raw[:200] if raw else "")
    return CallSummary(
        summary=data.get("summary", ""),
        key_points=data.get("key_points", []),
        action_items=data.get("action_items", []),
        email_draft=data.get("email_draft", ""),
    )


async def generate_summary(
    session_id: str,
    redis: Any,
    api_key: str,
    model: str,
) -> CallSummary:
    """Generate post-call summary + email draft from Redis conversation history.

    Retrieves all utterances and rolling summary from Redis, then calls LLM.

    Raises:
        ValueError: If redis is None (unavailable).
    """
    if redis is None:
        raise ValueError("Redis unavailable for summary generation")

    utter_key = session_utterances(session_id)
    summary_key = session_summary(session_id)

    # Load utterances
    raw_items: list[bytes] = await redis.lrange(utter_key, 0, -1)
    utterances: list[dict[str, str]] = []
    for item in raw_items:
        try:
            decoded = item.decode() if isinstance(item, bytes) else item
            utterances.append(json.loads(decoded))
        except Exception:
            continue

    # Build transcript text
    transcript_lines = [
        f"{u.get('speaker', 'unknown')}: {u.get('text', '')}" for u in utterances
    ]
    transcript = "\n".join(transcript_lines) if transcript_lines else "(нет данных)"

    # Load rolling summary
    raw_summary = await redis.get(summary_key)
    rolling_summary = ""
    if raw_summary:
        rolling_summary = (
            raw_summary.decode() if isinstance(raw_summary, bytes) else str(raw_summary)
        )

    prompt = _SUMMARY_TEMPLATE.format(
        transcript=transcript,
        rolling_summary=rolling_summary or "(нет резюме)",
    )

    raw = await call_llm_simple(
        prompt=prompt,
        system_prompt=_SYSTEM_PROMPT,
        api_key=api_key,
        model=model,
    )
    return _parse_summary(raw)
