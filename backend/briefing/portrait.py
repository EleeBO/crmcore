"""Pre-call briefing: buyer portrait + negotiation strategy generation (Task 6.1)."""

from __future__ import annotations

import json
import re
from typing import Any

from backend.briefing.models import (
    BriefContact,
    BriefData,
    BriefFocusPoint,
    BriefObjection,
    BriefProfileTag,
)
from backend.logger import logger
from backend.pipeline.scenario import Scenario
from backend.pipeline.shared_llm import call_llm_simple
from backend.storage.keys import briefing_cache, kb_docs, kb_scenario

_TAG_COLORS: tuple[str, ...] = ("blue", "green", "amber")


def scenario_to_brief(scenario: Scenario) -> BriefData:
    """Transform a Scenario into BriefData without an LLM call.

    This is the fast-path: when a Scenario already exists in Redis
    (generated during document upload), we map its fields directly
    to BriefData. Missing fields (company, roi, comparison, full_brief)
    stay as defaults -- speed vs completeness tradeoff.

    Args:
        scenario: The pre-generated Scenario from document upload.

    Returns:
        A BriefData instance with mapped fields.
    """
    p = scenario.portrait
    s = scenario.strategy

    contact = BriefContact(
        role=p.role,
        budget_note=p.budget,
    )

    tags = [
        BriefProfileTag(
            label=m,
            color=_TAG_COLORS[i % len(_TAG_COLORS)],
        )
        for i, m in enumerate(p.motivators[:3])
    ]

    focus = [BriefFocusPoint(headline=msg) for msg in s.key_messages[:3]]

    objs = [
        BriefObjection(question=o.trigger, answer=o.response)
        for o in scenario.objections[:3]
    ]

    return BriefData(
        contact=contact,
        profile_tags=tags,
        pain_points=p.pain_points[:5],
        focus_points=focus,
        objections=objs,
    )


_SGR_SYSTEM_PROMPT = (
    "Ты — ИИ-помощник для подготовки к переговорам. "
    "На основе предоставленных документов заполни JSON-схему брифинга.\n\n"
    "ВАЖНО:\n"
    "- Отвечай ТОЛЬКО валидным JSON по указанной схеме\n"
    "- Сохраняй числа и цены verbatim — не округляй\n"
    "- Если данных нет — используй null для необязательных полей\n"
    "- Не добавляй комментарии или markdown\n\n"
    "JSON Schema:\n{schema}"
)

_SGR_USER_PROMPT = (
    "Документы о клиенте:\n{context}\n\n"
    "Заполни брифинг по JSON-схеме из системного промпта."
)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_brief(raw: str) -> BriefData:
    """Parse LLM JSON into BriefData. Returns empty BriefData on failure."""
    text = _strip_code_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse briefing JSON: {exc}")
        return BriefData()
    # Detect v1 format (has "portrait" key, not "contact")
    if "portrait" in data and "contact" not in data:
        logger.info("Detected v1 briefing cache, returning empty for re-generation")
        return BriefData()
    try:
        return BriefData.model_validate(data)
    except Exception as exc:
        logger.warning(f"BriefData validation failed: {exc}")
        return BriefData()


async def generate_briefing(
    kb_id: str,
    session_id: str,
    redis: Any,
    api_key: str,
    model: str,
) -> BriefData:
    """Generate pre-call briefing using SGR schema.

    Three paths (all return BriefData):
    1. Redis cache hit (v2 format)
    2. Scenario fast-path -> transform + cache
    3. LLM fallback with SGR prompt + Reparser
    """
    if redis is None:
        logger.warning("Redis unavailable — returning empty briefing")
        return BriefData()

    cache_key = briefing_cache(session_id, kb_id)

    # Path 1: Check cache
    cached = await redis.get(cache_key)
    if cached:
        try:
            raw_str = cached.decode() if isinstance(cached, bytes) else cached
            data = json.loads(raw_str)
            # v1 detection: has "portrait" key -> stale, fall through
            if "portrait" not in data or "contact" in data:
                brief = BriefData.model_validate(data)
                return brief
            logger.info("Stale v1 briefing cache, regenerating")
        except Exception as exc:
            logger.warning(f"Failed to decode cached briefing: {exc}")

    # Path 2: Scenario fast-path
    scenario_raw = await redis.get(kb_scenario(kb_id))
    if scenario_raw:
        try:
            raw_str = (
                scenario_raw.decode()
                if isinstance(scenario_raw, bytes)
                else scenario_raw
            )
            scenario = Scenario.model_validate_json(raw_str)
            brief = scenario_to_brief(scenario)
            # Cache the transformed result
            try:
                await redis.set(
                    cache_key,
                    brief.model_dump_json(by_alias=True),
                )
                await redis.expire(cache_key, 1800)
            except Exception as exc:
                logger.warning(f"Failed to cache scenario briefing: {exc}")
            return brief
        except Exception as exc:
            logger.warning(f"Failed to parse scenario: {exc}")

    # Path 3: LLM with SGR
    docs_raw = await redis.get(kb_docs(kb_id))
    context = (
        docs_raw.decode()
        if isinstance(docs_raw, bytes) and docs_raw
        else docs_raw
        if docs_raw
        else "Документы не найдены."
    )

    schema_json = json.dumps(
        BriefData.model_json_schema(),
        indent=2,
        ensure_ascii=False,
    )
    system_prompt = _SGR_SYSTEM_PROMPT.format(schema=schema_json)
    user_prompt = _SGR_USER_PROMPT.format(context=context)

    raw = await call_llm_simple(
        prompt=user_prompt,
        system_prompt=system_prompt,
        api_key=api_key,
        model=model,
    )

    brief = _parse_brief(raw)

    # Reparser: one retry on empty result (validation failed)
    if not brief.contact.role and not brief.focus_points:
        logger.info("SGR parse failed, attempting reparse")
        raw2 = await call_llm_simple(
            prompt=(
                "Твой предыдущий ответ не прошёл валидацию. "
                "Исправь и верни ТОЛЬКО валидный JSON по схеме:\n"
                f"{raw}"
            ),
            system_prompt=system_prompt,
            api_key=api_key,
            model=model,
        )
        brief = _parse_brief(raw2)

    # Cache only after successful parse
    if brief.contact.role or brief.focus_points:
        try:
            await redis.set(
                cache_key,
                brief.model_dump_json(by_alias=True),
            )
            await redis.expire(cache_key, 1800)
        except Exception as exc:
            logger.warning(f"Failed to cache briefing: {exc}")

    return brief
