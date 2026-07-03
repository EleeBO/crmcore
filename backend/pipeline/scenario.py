"""Scenario model and LLM generator for Context Stuffing (FEAT-001)."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from backend.logger import logger

_SCENARIO_TIMEOUT_S = 30.0


class KeyFact(BaseModel):
    """A verified fact from the uploaded documents."""

    fact: str
    source_file: str
    source_page: int | None = None
    source_detail: str = ""


class Objection(BaseModel):
    """A client objection with a prepared response."""

    trigger: str
    response: str
    source_file: str = ""
    source_detail: str = ""


class BuyerPortrait(BaseModel):
    """Profile of the buyer / decision-maker."""

    role: str = ""
    pain_points: list[str] = []
    motivators: list[str] = []
    budget: str = ""
    communication_style: str = ""


class Strategy(BaseModel):
    """Negotiation strategy."""

    approach: str = ""
    key_messages: list[str] = []
    avoid: list[str] = []


class Scenario(BaseModel):
    """Full conversation scenario generated from uploaded documents."""

    portrait: BuyerPortrait = BuyerPortrait()
    strategy: Strategy = Strategy()
    objections: list[Objection] = []
    key_facts: list[KeyFact] = []
    talking_points: list[str] = []


_SCENARIO_SYSTEM_PROMPT = (
    "Ты — ИИ-помощник подготовки к переговорам.\n"
    "На основе документов создай структурированный сценарий разговора.\n\n"
    "ВАЖНО:\n"
    "  - Сохраняй все числа, цены, сроки, SLA verbatim — не округляй.\n"
    "  - Для каждого факта укажи source_file и source_page.\n"
    "  - Отвечай ТОЛЬКО валидным JSON по указанной схеме.\n"
    "  - Не добавляй комментарии, пояснения или markdown.\n\n"
    "JSON Schema:\n{schema}"
)


async def _call_openrouter(
    docs_text: str,
    api_key: str,
    model: str,
) -> str:
    """Call OpenRouter API and return raw response text."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    schema_json = json.dumps(Scenario.model_json_schema(), indent=2, ensure_ascii=False)
    system_prompt = _SCENARIO_SYSTEM_PROMPT.format(schema=schema_json)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": docs_text},
        ],
    )
    content: str = response.choices[0].message.content or ""
    # Strip markdown code fences if present
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last lines (```json and ```)
        if len(lines) >= 2:
            content = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )
    return content.strip()


async def generate_scenario(
    docs_text: str,
    api_key: str,
    model: str,
) -> Scenario:
    """Generate a Scenario from document text via LLM.

    - Calls LLM with full docs_text and JSON schema in prompt
    - Retries once on invalid JSON
    - Returns empty Scenario() on complete failure or timeout
    """
    for attempt in range(2):
        try:
            raw = await asyncio.wait_for(
                _call_openrouter(docs_text, api_key, model),
                timeout=_SCENARIO_TIMEOUT_S,
            )
            scenario = Scenario.model_validate_json(raw)
            logger.info(
                f"Scenario generated: {len(scenario.key_facts)} facts, "
                f"{len(scenario.objections)} objections, "
                f"{len(scenario.talking_points)} talking points"
            )
            return scenario
        except TimeoutError:
            logger.error(f"Scenario generation timed out (attempt {attempt + 1})")
            return Scenario()
        except Exception as exc:
            if attempt == 0:
                logger.warning(f"Scenario parse failed (attempt 1, retrying): {exc!r}")
            else:
                logger.warning(
                    f"Scenario parse failed (attempt 2, returning empty): {exc!r}"
                )

    return Scenario()
