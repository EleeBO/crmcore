"""Non-streaming LLM client for call evaluation (FEAT-004)."""

from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI

from backend.logger import logger

PRIMARY_MODEL = "google/gemini-2.5-flash"
PRIMARY_TIMEOUT_S = 25.0
FALLBACK_MODEL = "openai/gpt-4.1-mini"
FALLBACK_TIMEOUT_S = 30.0


class EvalLLMTimeoutError(Exception):
    """Both primary and fallback LLM timed out."""


class EvalLLMUnavailableError(Exception):
    """LLM returned a non-timeout error (429, 500, etc.)."""


class EvaluatorLLMClient:
    """Non-streaming LLM client with response_format=json_schema."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def evaluate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        """Single blocking call with json_schema response_format.

        Primary model: 15s timeout. On timeout -> fallback model: 30s.
        Raises EvalLLMTimeoutError if both models time out.
        Raises EvalLLMUnavailableError on non-timeout LLM errors.
        """
        try:
            return await self._call_llm(
                PRIMARY_MODEL,
                system_prompt,
                user_prompt,
                json_schema,
                PRIMARY_TIMEOUT_S,
            )
        except TimeoutError:
            logger.warning("Primary eval model timeout, switching to fallback")
            try:
                return await self._call_llm(
                    FALLBACK_MODEL,
                    system_prompt,
                    user_prompt,
                    json_schema,
                    FALLBACK_TIMEOUT_S,
                )
            except TimeoutError as exc:
                raise EvalLLMTimeoutError("Both models timed out") from exc
            except Exception as exc:
                raise EvalLLMUnavailableError(str(exc)) from exc
        except Exception as exc:
            # Non-timeout error from primary -> try fallback
            logger.warning(f"Primary eval model error: {exc!r}, trying fallback")
            try:
                return await self._call_llm(
                    FALLBACK_MODEL,
                    system_prompt,
                    user_prompt,
                    json_schema,
                    FALLBACK_TIMEOUT_S,
                )
            except TimeoutError as fb_exc:
                raise EvalLLMTimeoutError("Fallback timed out") from fb_exc
            except Exception as fb_exc:
                raise EvalLLMUnavailableError(str(fb_exc)) from fb_exc

    async def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        timeout_s: float,
    ) -> dict:
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "CallEvaluation",
                        "schema": json_schema,
                    },
                },
                stream=False,
            ),
            timeout=timeout_s,
        )
        return json.loads(response.choices[0].message.content)
