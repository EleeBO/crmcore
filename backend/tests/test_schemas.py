"""Tests for HintResponseV2 Pydantic schema."""

import pytest
from pydantic import ValidationError


def test_valid_coaching_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Client raised price objection, emotional tension high",
        hint_type="coaching",
        headline="Покажите ROI за 3 месяца",
        detail="Клиент считает цену высокой — переведите в стоимость простоя",
        coaching="Замедлитесь, покажите эмпатию",
        source="Brief, p.3",
    )
    assert hint.hint_type == "coaching"
    assert len(hint.headline) <= 80


def test_valid_success_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Rep handled LAER correctly",
        hint_type="success",
        headline="Отлично отработали возражение",
        detail="",
        coaching="",
        source="",
    )
    assert hint.hint_type == "success"


def test_valid_warning_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Client losing interest, short answers",
        hint_type="warning",
        headline="Клиент теряет интерес",
        detail="Задайте открытый вопрос о боли",
    )
    assert hint.hint_type == "warning"


def test_invalid_hint_type_rejected() -> None:
    from backend.pipeline.schemas import HintResponseV2

    with pytest.raises(ValidationError):
        HintResponseV2(
            reasoning="test",
            hint_type="positive",  # invalid — not in Literal
            headline="test",
        )


def test_headline_accepts_long_text() -> None:
    """max_length relaxed to avoid parse failures from verbose LLM responses."""
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="test",
        hint_type="coaching",
        headline="x" * 200,  # no hard limit — LLMs often exceed 80 chars
    )
    assert len(hint.headline) == 200


def test_from_json_round_trip() -> None:
    from backend.pipeline.schemas import HintResponseV2

    raw = (
        '{"reasoning": "test reason", "hint_type": "coaching", '
        '"headline": "Do this", "detail": "because", '
        '"coaching": "slow down", "source": "brief"}'
    )
    hint = HintResponseV2.model_validate_json(raw)
    assert hint.hint_type == "coaching"
    assert hint.headline == "Do this"
    assert hint.coaching == "slow down"


def test_v2_hint_from_llm_json_format() -> None:
    """Simulate LLM output in new prompt format."""
    from backend.pipeline.schemas import HintResponseV2

    llm_output = (
        '{"reasoning": "Клиент упомянул бюджет — скрытое возражение по цене", '
        '"hint_type": "coaching", '
        '"headline": "Переведите в стоимость простоя", '
        '"detail": "Спросите: сколько теряете в день без решения?", '
        '"coaching": "замедлитесь", '
        '"source": "Brief, p.2"}'
    )
    hint = HintResponseV2.model_validate_json(llm_output)
    assert hint.hint_type == "coaching"
    assert hint.headline == "Переведите в стоимость простоя"


def test_v2_fallback_hint() -> None:
    """Fallback hint must be valid HintResponseV2."""
    from backend.pipeline.schemas import HintResponseV2

    fallback = HintResponseV2(
        reasoning="Fallback: primary LLM timed out",
        hint_type="coaching",
        headline="Уточните детали у клиента",
        detail="",
        coaching="",
        source="fallback",
    )
    assert fallback.hint_type == "coaching"


def test_null_fields_coerced_to_empty_string() -> None:
    """LLMs sometimes return null for optional string fields."""
    from backend.pipeline.schemas import HintResponseV2

    raw = (
        '{"reasoning": "test", "hint_type": "warning", '
        '"headline": "test headline", "detail": null, '
        '"coaching": null, "source": null}'
    )
    hint = HintResponseV2.model_validate_json(raw)
    assert hint.detail == ""
    assert hint.coaching == ""
    assert hint.source == ""
