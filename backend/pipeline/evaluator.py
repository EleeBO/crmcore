"""Call evaluator: prompt formatting, LLM call, score recomputation (FEAT-004)."""

from __future__ import annotations

import json
from typing import Any

from backend.logger import logger
from backend.pipeline.evaluation_schemas import (
    CallEvaluation,
    EvaluationConfig,
    FollowUpResult,
)
from backend.pipeline.evaluator_llm import EvaluatorLLMClient


class EvalParseFailedError(Exception):
    """JSON from LLM failed Pydantic validation after reparse."""


_MAX_TRANSCRIPT_CHARS = 48_000
_HEAD_CHARS = 16_000
_TAIL_CHARS = 32_000

_SYSTEM_PROMPT = (
    "Ты — опытный руководитель отдела продаж (РОП) с 10+ годами опыта"
    " в B2B-продажах.\n"
    "Твоя задача — оценить качество телефонного разговора менеджера"
    " по продажам.\n\n"
    "Правила оценки:\n"
    "- Анализируй ТОЛЬКО то, что есть в транскрипте. Не додумывай.\n"
    "- Для каждого критерия СНАЧАЛА проведи анализ (reasoning), ПОТОМ"
    " выставляй оценку.\n"
    "- Оценка 1-10: 1-3 = плохо, 4-5 = ниже среднего, 6-7 = хорошо,"
    " 8-9 = отлично, 10 = идеально.\n"
    "- Рекомендации должны быть конкретными и actionable, не общими"
    " фразами.\n"
    "- Если критерий неприменим к данному звонку, поставь 5 и укажи"
    " в reasoning что оценка нейтральная.\n"
    "- Учитывай брифинг: оценивай насколько менеджер следовал"
    " подготовленной стратегии.\n"
    "- Все ответы на русском языке.\n\n"
    "Бенчмарки (данные Gong, 519K+ звонков):\n"
    "- Оптимальное соотношение говорит/слушает: 43%/57%\n"
    "- Оптимальное количество выявленных проблем: 3-4\n"
    "- Успешные менеджеры делают паузу перед ответом на возражение\n"
    "- Конкретный next step повышает конверсию в 2.7 раза"
    "\n\n"
    "Если предоставлена секция АНАЛИТИКА ЗВОНКА:\n"
    "- Используй объективные данные (talk ratio, speech rate,"
    " паузы) вместо угадывания.\n"
    "- Talk ratio 43/57 (менеджер/клиент) — эталон."
    " Отклонение >15% — снижай оценку needs_discovery.\n"
    "- Темп речи 120-160 слов/мин — норма."
    " <100 = слишком медленно, >180 = слишком быстро.\n"
    "- Пауза менеджера перед ответом на возражение"
    " >1 сек — хорошо. <0.5 сек — плохо (не выслушал).\n"
    "- Перебивания менеджером >3 — снижай оценку"
    " communication.\n"
    "- Если аналитика отсутствует — оценивай как раньше,"
    " только по тексту.\n\n"
    "Поля follow_up_email и crm_note установи в null —"
    " они генерируются отдельным запросом."
)

_FOLLOW_UP_SYSTEM_PROMPT = (
    "Ты — деловой ассистент менеджера по продажам.\n"
    "На основе транскрипта звонка и брифинга сгенерируй:\n\n"
    "1. follow_up_email — черновик делового письма клиенту:\n"
    "   - subject: краткая тема (суть договорённостей)\n"
    "   - body: деловой стиль, обращение по имени из брифинга,"
    " благодарность за время, резюме договорённостей,"
    " следующие шаги с датами. Максимум 1500 символов.\n\n"
    "2. crm_note — заметка для CRM:\n"
    '   - title: "YYYY-MM-DD | Имя клиента | Исход"\n'
    "   - body: резюме, потребности, договорённости,"
    " следующие шаги с дедлайнами, возражения\n\n"
    "ВАЖНО: генерируй ВСЕГДА."
    " Если имя клиента неизвестно — используй 'Уважаемый клиент'."
    " Если договорённостей нет — предложи следующий шаг"
    " (демо, повторный звонок).\n"
    "Все ответы на русском языке."
)

_FOLLOW_UP_USER_TEMPLATE = (
    "ТРАНСКРИПТ ЗВОНКА:\n{transcript}\n\n"
    "БРИФИНГ (подготовка к звонку):\n{briefing}\n\n"
    "Сгенерируй follow_up_email и crm_note."
    " Ответ — ТОЛЬКО валидный JSON по схеме FollowUpResult."
)

_USER_TEMPLATE = (
    "ТРАНСКРИПТ ЗВОНКА:\n{transcript}\n\n"
    "БРИФИНГ (подготовка к звонку):\n{briefing}\n\n"
    "{analytics_section}\n"
    "КРИТЕРИИ ОЦЕНКИ:\n{criteria_list}\n\n"
    "Оцени звонок по каждому критерию. Ответ — ТОЛЬКО валидный JSON"
    " по схеме CallEvaluation."
)


def _format_criteria_list(config: EvaluationConfig) -> str:
    """Format criteria as numbered list for LLM prompt."""
    lines: list[str] = []
    for i, c in enumerate(config.criteria, 1):
        pct = int(c.weight * 100)
        lines.append(f"{i}. {c.name} (вес: {pct}%) — {c.description}")
    return "\n".join(lines)


def _truncate_transcript(raw_lines: list[str]) -> str:
    """Join transcript lines and truncate to ~12K tokens if needed."""
    from backend.pipeline.prompt_formatter import (
        format_diarized_transcript,
        format_plain_transcript,
    )

    parsed: list[dict] = []
    for line in raw_lines:
        try:
            item = (
                json.loads(line) if isinstance(line, str) else json.loads(line.decode())
            )
            parsed.append(item)
        except (
            json.JSONDecodeError,
            KeyError,
            UnicodeDecodeError,
        ):
            parsed.append({"speaker": "unknown", "text": str(line)})

    # Detect diarized format
    is_diarized = parsed and parsed[0].get("start_ms") is not None
    if is_diarized:
        full = format_diarized_transcript(parsed)
    else:
        full = format_plain_transcript(parsed)

    if len(full) <= _MAX_TRANSCRIPT_CHARS:
        return full

    head = full[:_HEAD_CHARS]
    tail = full[-_TAIL_CHARS:]
    return f"{head}\n\n[... часть транскрипта пропущена ...]\n\n{tail}"


def _compute_overall_score(
    results: list[Any],
    config: EvaluationConfig,
) -> float:
    """Recompute overall_score as weighted average. Do NOT trust LLM."""
    weight_map = {c.id: c.weight for c in config.criteria}
    total = 0.0
    for r in results:
        w = weight_map.get(r.criterion_id, 0.0)
        total += r.score * w
    return round(total, 2)


def _compute_verdict(score: float) -> str:
    """Compute verdict from overall_score."""
    if score >= 8.0:
        return "excellent"
    if score >= 6.0:
        return "good"
    if score >= 4.0:
        return "satisfactory"
    return "needs_improvement"


async def evaluate_call(
    *,
    llm_client: EvaluatorLLMClient,
    transcript_raw: list[str | bytes],
    config: EvaluationConfig,
    briefing: str = "",
    analytics: Any = None,  # CallAnalytics | None
) -> CallEvaluation:
    """Run full evaluation pipeline: format -> LLM -> validate -> recompute."""
    from backend.pipeline.prompt_formatter import format_analytics

    lines = [
        line.decode() if isinstance(line, bytes) else line for line in transcript_raw
    ]
    transcript_text = _truncate_transcript(lines)
    criteria_list = _format_criteria_list(config)
    analytics_section = format_analytics(analytics) if analytics else ""

    user_prompt = _USER_TEMPLATE.format(
        transcript=transcript_text,
        briefing=briefing or "(брифинг не предоставлен)",
        criteria_list=criteria_list,
        analytics_section=analytics_section,
    )

    schema = CallEvaluation.model_json_schema()

    raw = await llm_client.evaluate(_SYSTEM_PROMPT, user_prompt, schema)

    try:
        evaluation = CallEvaluation.model_validate(raw)
    except Exception as first_err:
        logger.warning(f"First parse failed: {first_err} — attempting reparse")
        reparse_prompt = (
            f"Предыдущий JSON не прошёл валидацию: {first_err!s}\n"
            "Исправь: 1) проверь типы, 2) проверь обязательные поля, "
            "3) верни ТОЛЬКО JSON.\n\n"
            f"Исходный запрос:\n{user_prompt}"
        )
        raw = await llm_client.evaluate(_SYSTEM_PROMPT, reparse_prompt, schema)
        try:
            evaluation = CallEvaluation.model_validate(raw)
        except Exception as second_err:
            raise EvalParseFailedError(
                f"Reparse also failed: {second_err}"
            ) from second_err

    evaluation.overall_score = _compute_overall_score(
        evaluation.criteria_results,
        config,
    )
    evaluation.verdict = _compute_verdict(evaluation.overall_score)

    return evaluation


async def generate_follow_up(
    *,
    llm_client: EvaluatorLLMClient,
    transcript_raw: list[str | bytes],
    briefing: str = "",
) -> FollowUpResult:
    """Generate follow-up email and CRM note (fast, parallel to evaluation)."""
    lines = [
        line.decode() if isinstance(line, bytes) else line for line in transcript_raw
    ]
    transcript_text = _truncate_transcript(lines)

    user_prompt = _FOLLOW_UP_USER_TEMPLATE.format(
        transcript=transcript_text,
        briefing=briefing or "(брифинг не предоставлен)",
    )

    schema = FollowUpResult.model_json_schema()
    raw = await llm_client.evaluate(
        _FOLLOW_UP_SYSTEM_PROMPT,
        user_prompt,
        schema,
    )

    try:
        return FollowUpResult.model_validate(raw)
    except Exception as first_err:
        logger.warning(f"Follow-up parse failed: {first_err} — attempting reparse")
        reparse_prompt = (
            f"Предыдущий JSON не прошёл валидацию: {first_err!s}\n"
            "Исправь и верни ТОЛЬКО валидный JSON.\n\n"
            f"Исходный запрос:\n{user_prompt}"
        )
        raw = await llm_client.evaluate(
            _FOLLOW_UP_SYSTEM_PROMPT,
            reparse_prompt,
            schema,
        )
        try:
            return FollowUpResult.model_validate(raw)
        except Exception as second_err:
            raise EvalParseFailedError(
                f"Follow-up reparse failed: {second_err}"
            ) from second_err
