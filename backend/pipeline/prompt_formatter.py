"""Format scenario data into structured LLM prompt sections."""

from __future__ import annotations

from backend.pipeline.post_call import CallAnalytics
from backend.pipeline.scenario import Scenario


def _add_topic_perimeter(sections: list[str], scenario: Scenario) -> None:
    """Build the ТЕМА РАЗГОВОРА section — explicit topic boundary.

    This section is placed FIRST in the briefing so the LLM always
    sees the allowed topic perimeter before any other context.
    If the rep talks about something outside this perimeter, the LLM
    should flag it as off-topic (ОТКЛОНЕНИЕ).
    """
    s = scenario.strategy
    p = scenario.portrait

    # Only add if we have strategy or portrait data
    if not (s.approach or s.key_messages or p.pain_points):
        return

    lines = [
        "## ТЕМА РАЗГОВОРА (периметр — всё за пределами = ОТКЛОНЕНИЕ)",
    ]
    if s.approach:
        lines.append(f"Подход/продукт: {s.approach}")
    if s.key_messages:
        lines.append("Ключевые сообщения: " + "; ".join(s.key_messages))
    if p.pain_points:
        lines.append("Боли клиента: " + "; ".join(p.pain_points))
    lines.append(">>> Любая речь менеджера, НЕ связанная с этими темами = ОТКЛОНЕНИЕ.")
    sections.append("\n".join(lines))


def format_scenario_for_hints(scenario: Scenario) -> str:
    """Convert a Scenario into a structured, readable prompt section.

    Organizes data into labeled sections so the LLM can reference
    specific briefing material (portrait, strategy, objections).
    Starts with ТЕМА РАЗГОВОРА — an explicit topic perimeter for
    deviation detection.
    """
    sections: list[str] = []

    # Topic perimeter — explicit boundary for relevance checking
    _add_topic_perimeter(sections, scenario)

    # Portrait
    p = scenario.portrait
    if p.role or p.pain_points or p.motivators:
        lines = ["## ПОРТРЕТ КЛИЕНТА"]
        if p.role:
            lines.append(f"Роль: {p.role}")
        if p.pain_points:
            lines.append("Боли: " + "; ".join(p.pain_points))
        if p.motivators:
            lines.append("Мотиваторы: " + "; ".join(p.motivators))
        if p.budget:
            lines.append(f"Бюджет: {p.budget}")
        if p.communication_style:
            lines.append(f"Стиль общения: {p.communication_style}")
        sections.append("\n".join(lines))

    # Strategy
    s = scenario.strategy
    if s.approach or s.key_messages:
        lines = ["## СТРАТЕГИЯ"]
        if s.approach:
            lines.append(f"Подход: {s.approach}")
        if s.key_messages:
            for i, msg in enumerate(s.key_messages, 1):
                lines.append(f"  {i}. {msg}")
        if s.avoid:
            lines.append("Избегать: " + "; ".join(s.avoid))
        sections.append("\n".join(lines))

    # Objections
    if scenario.objections:
        lines = ["## ВОЗРАЖЕНИЯ"]
        for obj in scenario.objections:
            lines.append(f'- "{obj.trigger}" → {obj.response}')
        sections.append("\n".join(lines))

    # Key facts
    if scenario.key_facts:
        lines = ["## КЛЮЧЕВЫЕ ФАКТЫ"]
        for kf in scenario.key_facts:
            src = f" [{kf.source_file}"
            if kf.source_page:
                src += f", стр. {kf.source_page}"
            src += "]"
            lines.append(f"- {kf.fact}{src}")
        sections.append("\n".join(lines))

    # Talking points
    if scenario.talking_points:
        lines = ["## ТЕЗИСЫ"]
        for tp in scenario.talking_points:
            lines.append(f"- {tp}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "Сценарий не загружен."


# --- Post-call diarization formatting ---

_SPEAKER_LABELS = {"rep": "Менеджер", "client": "Клиент"}


def _ms_to_timestamp(ms: int) -> str:
    """Convert milliseconds to MM:SS timestamp (truncation, not rounding)."""
    total_s = ms // 1000
    minutes = total_s // 60
    seconds = total_s % 60
    return f"{minutes:02d}:{seconds:02d}"


def format_diarized_transcript(utterances: list[dict]) -> str:
    """Format transcript with timestamps: [MM:SS] Speaker: text"""
    if not utterances:
        return ""
    lines = []
    for u in utterances:
        ts = _ms_to_timestamp(u.get("start_ms", 0))
        speaker = _SPEAKER_LABELS.get(u.get("speaker", ""), u.get("speaker", ""))
        lines.append(f"[{ts}] {speaker}: {u['text']}")
    return "\n".join(lines)


def format_plain_transcript(utterances: list[dict]) -> str:
    """Format transcript without timestamps: Speaker: text"""
    if not utterances:
        return ""
    lines = []
    for u in utterances:
        speaker = _SPEAKER_LABELS.get(u.get("speaker", ""), u.get("speaker", ""))
        lines.append(f"{speaker}: {u['text']}")
    return "\n".join(lines)


def format_analytics(analytics: CallAnalytics | None) -> str:
    """Format АНАЛИТИКА ЗВОНКА section for evaluator prompt."""
    if analytics is None:
        return ""
    a = analytics
    client_ratio = 1.0 - a.rep_talk_ratio
    dur_min = a.total_duration_s / 60
    rep_pct = a.rep_talk_ratio * 100
    cli_pct = client_ratio * 100
    avg_pause = a.avg_rep_pause_before_response_s
    lines = [
        "АНАЛИТИКА ЗВОНКА (объективные данные, используй для оценки):",
        f"- Длительность: {a.total_duration_s:.0f} сек ({dur_min:.1f} мин)",
        f"- Менеджер говорил: {a.rep_talk_time_s:.0f} сек ({rep_pct:.0f}%)",
        f"- Клиент говорил: {a.client_talk_time_s:.0f} сек ({cli_pct:.0f}%)",
        f"- Темп речи менеджера: {a.rep_speech_rate_wpm:.0f} слов/мин",
        f"- Темп речи клиента: {a.client_speech_rate_wpm:.0f} слов/мин",
        f"- Перебивания менеджером: {a.interruptions_by_rep}",
        f"- Перебивания клиентом: {a.interruptions_by_client}",
        f"- Средняя пауза менеджера перед ответом: {avg_pause:.1f} сек",
        f"- Слов менеджера: {a.rep_word_count}, клиента: {a.client_word_count}",
    ]
    return "\n".join(lines)
