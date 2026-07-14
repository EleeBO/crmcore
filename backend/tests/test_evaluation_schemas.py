"""Tests for evaluation SGR schemas (FEAT-004)."""
import pytest
from pydantic import ValidationError


def test_criterion_weight_bounds():
    from backend.pipeline.evaluation_schemas import EvaluationCriterion
    with pytest.raises(ValidationError):
        EvaluationCriterion(id="x", name="X", description="d", weight=1.5)
    with pytest.raises(ValidationError):
        EvaluationCriterion(id="x", name="X", description="d", weight=-0.1)


def test_config_weight_sum_validation():
    from backend.pipeline.evaluation_schemas import (
        EvaluationConfig,
        EvaluationCriterion,
    )
    c = EvaluationCriterion(id="a", name="A", description="d", weight=0.3)
    with pytest.raises(ValidationError, match="1.0"):
        EvaluationConfig(criteria=[c])


def test_config_valid():
    from backend.pipeline.evaluation_schemas import (
        EvaluationConfig,
        EvaluationCriterion,
    )
    c = EvaluationCriterion(id="a", name="A", description="d", weight=1.0)
    cfg = EvaluationConfig(criteria=[c])
    assert len(cfg.criteria) == 1


def test_default_criteria_valid():
    from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG
    assert abs(sum(c.weight for c in DEFAULT_CONFIG.criteria) - 1.0) < 0.01
    assert len(DEFAULT_CONFIG.criteria) == 7


def test_criterion_result_score_bounds():
    from backend.pipeline.evaluation_schemas import CriterionResult
    with pytest.raises(ValidationError):
        CriterionResult(
            criterion_id="x", criterion_name="X",
            reasoning="r", score=11, comment="c",
            recommendations=["a"],
        )


def test_call_evaluation_verdict_literal():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "s",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "invalid_value",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    with pytest.raises(ValidationError):
        CallEvaluation(**data)


def test_call_evaluation_json_schema_export():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    schema = CallEvaluation.model_json_schema()
    assert "properties" in schema
    assert "call_summary" in schema["properties"]


# ── FEAT-011: FollowUpEmail and CrmNote schemas ──────────────────────────


def test_follow_up_email_valid():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    email = FollowUpEmail(
        subject="Итоги встречи",
        body="Добрый день, Александр! Благодарю за уделённое время.",
    )
    assert email.subject == "Итоги встречи"
    assert email.body.startswith("Добрый день")


def test_follow_up_email_empty_subject_rejected():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    with pytest.raises(ValidationError):
        FollowUpEmail(subject="", body="text")


def test_follow_up_email_empty_body_rejected():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    with pytest.raises(ValidationError):
        FollowUpEmail(subject="subj", body="")


def test_crm_note_valid():
    from backend.pipeline.evaluation_schemas import CrmNote
    note = CrmNote(
        title="2026-03-19 | Александр | Договорились о демо",
        body="Резюме: обсудили потребности, согласовали демо на пятницу.",
    )
    assert "Александр" in note.title
    assert "демо" in note.body


def test_crm_note_empty_title_rejected():
    from backend.pipeline.evaluation_schemas import CrmNote
    with pytest.raises(ValidationError):
        CrmNote(title="", body="text")


def test_crm_note_empty_body_rejected():
    from backend.pipeline.evaluation_schemas import CrmNote
    with pytest.raises(ValidationError):
        CrmNote(title="title", body="")


def test_call_evaluation_without_follow_up_fields():
    """Backwards compat: old evaluations without follow-up fields parse fine."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None
    assert ev.crm_note is None


def test_call_evaluation_with_follow_up_fields():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {
            "subject": "Итоги встречи",
            "body": "Добрый день!",
        },
        "crm_note": {
            "title": "2026-03-19 | Клиент | Демо",
            "body": "Резюме звонка.",
        },
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is not None
    assert ev.follow_up_email.subject == "Итоги встречи"
    assert ev.crm_note is not None
    assert ev.crm_note.title.startswith("2026-03-19")


# ── FEAT-011: Coercion validator ─────────────────────────────────────────


def test_coercion_partial_follow_up_email_becomes_none():
    """LLM returns partial object (missing body) → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "Hi"},
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_partial_crm_note_becomes_none():
    """LLM returns CRM note with missing title → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "crm_note": {"body": "some text"},
    }
    ev = CallEvaluation(**data)
    assert ev.crm_note is None


def test_coercion_empty_string_follow_up_email_becomes_none():
    """LLM returns empty subject → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "", "body": "text"},
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_non_dict_follow_up_becomes_none():
    """LLM returns a string instead of object → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": "not a dict",
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_valid_follow_up_preserved():
    """Valid follow-up objects are NOT coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "Re: Встреча", "body": "Добрый день!"},
        "crm_note": {"title": "2026-03-19 | Client", "body": "Summary."},
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is not None
    assert ev.crm_note is not None
