"""Shared LLM utility for non-streaming OpenRouter calls."""

from __future__ import annotations

from openai import AsyncOpenAI

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


async def call_llm_simple(
    prompt: str,
    system_prompt: str,
    api_key: str,
    model: str,
) -> str:
    """Call the LLM and return raw text response."""
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=_OPENROUTER_BASE,
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    return response.choices[0].message.content or ""
