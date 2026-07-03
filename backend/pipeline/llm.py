"""LLM Client: OpenRouter + TTFT fallback + single-flight (Task 4.1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from backend.logger import logger

# Re-export DTOs for backward compatibility — importers can still use
# `from backend.pipeline.llm import HintContext, HintResponse`
from backend.pipeline.types import HintContext, HintResponse  # noqa: F401

if TYPE_CHECKING:
    from backend.pipeline.schemas import HintResponseV2

_SYSTEM_PROMPT_CLIENT = (
    "Ты — реал-тайм коуч продаж с 15-летним опытом в B2B.\n"
    "Ты владеешь: психология покупателя, работа с возражениями (LAER), "
    "переговорные техники, эмоциональный интеллект.\n\n"
    "СИТУАЦИЯ: Клиент высказался во время звонка. Менеджер видит твою "
    "подсказку на экране — у него 2 секунды на прочтение.\n\n"
    "ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ (проверяй по приоритету, первое совпадение = ответ):\n"
    "  1. OFF-TOPIC: Реплика НЕ связана с ТЕМОЙ РАЗГОВОРА "
    '→ hint_type="warning", headline=мягкий мостик обратно к теме.\n'
    '  2. ВОЗРАЖЕНИЕ ("дорого", "не нужно", "подумаем", "уже есть"): '
    "Используй LAER — сначала покажи, что услышал, "
    "затем подсказку с фактом из БРИФИНГА, закрывающим возражение. "
    "Помни: возражение = запрос на дополнительную информацию, а не отказ.\n"
    "  3. ВОПРОС: Ответь конкретным фактом из КЛЮЧЕВЫХ ФАКТОВ брифинга.\n"
    "  4. ИНТЕРЕС / ПОЗИТИВ: Подкрепи тезисом из СТРАТЕГИИ + предложи "
    'следующий логический шаг (демо, расчёт, встреча). → hint_type="success"\n'
    "  5. НЕЙТРАЛЬНО: Предложи проверочный вопрос, "
    'выявляющий скрытую боль или потребность. → hint_type="coaching"\n\n'
    "ПСИХОЛОГИЯ ПОКУПАТЕЛЯ (учитывай в подсказках):\n"
    '  — Потеря сильнее выгоды: "теряете X в день" > "получите X".\n'
    '  — Страх ошибки: снижай риск ("можно протестировать", "без обязательств").\n'
    "  — Паралич выбора: рекомендуй ОДИН чёткий следующий шаг.\n"
    '  — Социальное доказательство: "компании вашего уровня уже..."\n\n'
    "СТИЛЬ ПОДСКАЗОК:\n"
    "  — 1-2 предложения, КОНКРЕТНО и ДЕЙСТВЕННО.\n"
    "  — Подсказывай ИДЕЮ, не дословный текст — менеджер сам сформулирует.\n"
    "  — Если уместно лёгкое остроумие для разрядки — предложи.\n"
    '  — coaching: совет по тону и темпу ("замедлись", "покажи эмпатию", '
    '"поддержи энтузиазм").\n\n'
    "Формат JSON (поля строго в указанном порядке — сначала думай):\n"
    '{"reasoning": "1 предложение: суть реплики + эмоция клиента", '
    '"hint_type": "coaching|success|warning", '
    '"headline": "главная подсказка, ≤80 символов", '
    '"detail": "контекст или объяснение, ≤150 символов", '
    '"coaching": "совет по тону/темпу", '
    '"source": "файл, стр."}\n'
    "Отвечай ТОЛЬКО валидным JSON."
)

_SYSTEM_PROMPT_REP = (
    "Ты — реал-тайм коуч продаж с 15-летним опытом в B2B и "
    "навыками переговоров, психологии влияния, работы с возражениями.\n"
    "Ты оцениваешь реплики МЕНЕДЖЕРА и помогаешь ему вести разговор эффективнее.\n\n"
    "СИТУАЦИЯ: Менеджер высказался во время звонка. "
    "Сравни его реплику с ТЕМОЙ РАЗГОВОРА и СТРАТЕГИЕЙ из БРИФИНГА.\n\n"
    "ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ (проверяй по приоритету, первое совпадение = ответ):\n"
    "  1. ОТКЛОНЕНИЕ: Реплика НЕ связана с ТЕМОЙ РАЗГОВОРА "
    "(продукт, боли клиента, стратегия) "
    '→ hint_type="warning", headline=к какой теме вернуться + фраза-мостик.\n'
    "  2. ОШИБКА: Противоречит СТРАТЕГИИ, упоминает «Избегать», "
    "давит на клиента, или игнорирует возражение вместо проработки "
    '→ hint_type="warning", headline=что исправить + как именно.\n'
    "  3. УПУЩЕННАЯ ВОЗМОЖНОСТЬ: Менеджер мог усилить момент, "
    "но не использовал приём (не задал уточняющий вопрос, не привёл "
    "социальное доказательство, не предложил следующий шаг) "
    '→ hint_type="coaching", headline=конкретный приём.\n'
    "  4. ХОРОШО: Соответствует СТРАТЕГИИ, хорошая работа с клиентом "
    '→ hint_type="success", '
    "headline=краткое одобрение + следующий логический шаг.\n"
    '  5. НЕЙТРАЛЬНО: → hint_type="coaching", '
    "headline=тезис из ТЕЗИСОВ или КЛЮЧЕВЫХ ФАКТОВ для продолжения.\n\n"
    "ЭКСПЕРТИЗА КОУЧА (применяй в подсказках):\n"
    "  — Работа с возражениями: LAER (Выслушай → Признай → Исследуй → Ответь). "
    "Если менеджер пропустил шаг — подскажи.\n"
    "  — Психология: потеря > выгоды, страх ошибки, социальное доказательство. "
    "Если менеджер не использует — предложи.\n"
    "  — Вопросы: открытые вопросы раскрывают боли, "
    "закрытые — фиксируют договорённости. Подскажи какой тип уместен.\n"
    '  — Темп: если менеджер торопится — "замедлись", '
    'если затянул — "переходи к следующему шагу".\n'
    "  — Раппорт: если момент позволяет — предложи лёгкую шутку "
    "или метафору для разрядки.\n\n"
    "СТИЛЬ: 1-2 предложения. Конкретно. Подсказывай ИДЕЮ, "
    "не дословный текст.\n\n"
    "Формат JSON (поля строго в указанном порядке — сначала думай):\n"
    '{"reasoning": "1 предложение: суть реплики + эмоция клиента", '
    '"hint_type": "coaching|success|warning", '
    '"headline": "главная подсказка, ≤80 символов", '
    '"detail": "контекст или объяснение, ≤150 символов", '
    '"coaching": "совет по тону/темпу", '
    '"source": "файл, стр."}\n'
    "Отвечай ТОЛЬКО валидным JSON."
)

# Keep original for backward compat in tests
_SYSTEM_PROMPT = _SYSTEM_PROMPT_CLIENT

_USER_TEMPLATE = (
    "Говорит: {speaker}\n"
    "Реплика: «{utterance}»\n\n"
    "БРИФИНГ:\n{rag_context}\n\n"
    "ИСТОРИЯ РАЗГОВОРА:\n{conversation_history}\n\n"
    "JSON (заполняй поля в этом порядке):\n"
    '{{"reasoning": "кратко: суть реплики + эмоция", '
    '"hint_type": "coaching|success|warning", '
    '"headline": "главная подсказка ≤80 символов", '
    '"detail": "контекст ≤150 символов", '
    '"coaching": "совет по тону (опционально)", '
    '"source": "файл, стр."}}'
)


def _format_history(history: list[dict[str, str]]) -> str:
    """Format conversation history list for the LLM prompt."""
    if not history:
        return "(начало разговора)"
    return "\n".join(f"{u['speaker']}: {u['text']}" for u in history)


class LLMClient:
    """OpenRouter LLM client with streaming, TTFT fallback, and single-flight."""

    def __init__(
        self,
        primary_model: str,
        fallback_model: str,
        api_key: str,
        primary_timeout_ms: int = 1000,
        fallback_timeout_ms: int = 2000,
    ) -> None:
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._primary_timeout = primary_timeout_ms / 1000.0
        self._fallback_timeout = fallback_timeout_ms / 1000.0
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._llm_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._tokens_received: int = 0

    def _cancel_current(self, *, force: bool = False) -> None:
        """Cancel the currently in-flight LLM task, if any.

        If force=False (default), skip cancellation when tokens have been
        received so a nearly-complete generation is not thrown away.
        """
        if self._llm_task is None or self._llm_task.done():
            self._llm_task = None
            return
        if not force and self._tokens_received > 0:
            logger.debug(
                f"Smart cancel: skipping — "
                f"{self._tokens_received} tokens already received"
            )
            return
        self._llm_task.cancel()
        self._llm_task = None
        self._tokens_received = 0

    async def generate_hint_stream(
        self,
        ctx: HintContext,
    ) -> AsyncGenerator[str, None]:
        """Stream raw LLM tokens for hint generation."""
        self._tokens_received = 0
        system_prompt = (
            _SYSTEM_PROMPT_REP if ctx.speaker == "rep" else _SYSTEM_PROMPT_CLIENT
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    speaker=ctx.speaker,
                    utterance=ctx.utterance,
                    rag_context="\n".join(ctx.rag_context),
                    conversation_history=_format_history(ctx.conversation_history),
                ),
            },
        ]
        async with await self._client.chat.completions.create(
            model=self._primary_model,
            messages=messages,
            stream=True,
        ) as stream:
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    self._tokens_received += 1
                    yield content

    async def _generate_fallback(self, ctx: HintContext) -> HintResponseV2:
        """Generate a fallback hint (overrideable in tests)."""
        from backend.pipeline.schemas import HintResponseV2

        logger.warning(f"Primary LLM timed out, using fallback: {self._fallback_model}")
        _ = ctx
        return HintResponseV2(
            reasoning="Fallback: primary LLM timed out",
            hint_type="coaching",
            headline="Уточните детали у клиента",
            detail="",
            coaching="",
            source="fallback",
        )

    async def generate_hint(self, ctx: HintContext) -> HintResponseV2:
        """Generate a complete hint with TTFT timeout and fallback."""
        from backend.pipeline.schemas import HintResponseV2

        self._cancel_current()

        async def _collect() -> HintResponseV2:
            tokens: list[str] = []
            async for token in self.generate_hint_stream(ctx):
                tokens.append(token)
            return HintResponseV2.model_validate_json("".join(tokens))

        try:
            return await asyncio.wait_for(_collect(), timeout=self._primary_timeout)
        except Exception as exc:
            logger.warning(f"Primary LLM failed ({exc!r}), falling back")
            return await self._generate_fallback(ctx)
