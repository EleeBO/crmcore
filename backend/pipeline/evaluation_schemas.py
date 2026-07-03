"""SGR schemas for call evaluation (FEAT-004)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class EvaluationCriterion(BaseModel):
    """One evaluation criterion."""

    id: str = Field(description="Unique ID: greeting, needs_discovery, etc.")
    name: str = Field(description="Criterion name in Russian")
    description: str = Field(description="Detailed description of what is evaluated")
    weight: float = Field(
        ge=0.0,
        le=1.0,
        description="Criterion weight (0.0–1.0, all must sum to 1.0)",
    )


class EvaluationConfig(BaseModel):
    """Evaluation config — stored in Redis, editable via UI."""

    criteria: Annotated[list[EvaluationCriterion], Field(min_length=1, max_length=10)]
    model: str = Field(default="google/gemini-2.5-flash")

    @model_validator(mode="after")
    def validate_weights_sum(self) -> EvaluationConfig:
        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > 0.01:
            msg = f"Сумма весов критериев должна быть 1.0, получено: {total:.2f}"
            raise ValueError(msg)
        return self


class CriterionResult(BaseModel):
    """Single criterion evaluation result. Cascade: reasoning → score → comment."""

    criterion_id: str
    criterion_name: str
    reasoning: str = Field(
        description="Transcript analysis for this criterion — BEFORE scoring",
    )
    score: int = Field(ge=1, le=10, description="Score 1-10, assigned AFTER analysis")
    comment: str = Field(description="Brief conclusion for UI (1-2 sentences)")
    recommendations: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Specific improvement recommendations (1-3 items)",
    )


class FollowUpEmail(BaseModel):
    """Draft follow-up email generated from call context (FEAT-011)."""

    subject: str = Field(
        min_length=1,
        max_length=200,
        description="Email subject line, concise and professional",
    )
    body: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Email body in plain text, formal business style. "
            "Keep under 1500 characters to avoid Gmail URL truncation."
        ),
    )


class CrmNote(BaseModel):
    """Structured CRM note for post-call documentation (FEAT-011)."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="Note title: date + client name + call outcome",
    )
    body: str = Field(
        min_length=1,
        max_length=3000,
        description="Structured: summary, commitments, next steps, deadlines",
    )


class FollowUpResult(BaseModel):
    """Standalone follow-up result for fast parallel generation."""

    follow_up_email: FollowUpEmail = Field(
        description="Draft follow-up email for the client",
    )
    crm_note: CrmNote = Field(
        description="Structured CRM note for copy-paste",
    )


class CallEvaluation(BaseModel):
    """Full call evaluation. Cascade: summary → criteria → overall → verdict."""

    @model_validator(mode="before")
    @classmethod
    def coerce_invalid_follow_ups(cls, data: dict) -> dict:
        """Coerce malformed follow-up objects to None."""
        if not isinstance(data, dict):
            return data
        for key, required_keys in (
            ("follow_up_email", {"subject", "body"}),
            ("crm_note", {"title", "body"}),
        ):
            val = data.get(key)
            if val is None:
                continue
            if (
                not isinstance(val, dict)
                or not required_keys.issubset(val.keys())
                or any(not val.get(k) for k in required_keys)
            ):
                data[key] = None
        return data

    call_summary: str = Field(description="Brief call summary (3-5 sentences)")
    criteria_results: list[CriterionResult] = Field(
        description="Evaluation per criterion",
    )
    overall_score: float = Field(
        ge=1.0,
        le=10.0,
        description="Computed on backend, NOT trusted from LLM",
    )
    verdict: Literal["excellent", "good", "satisfactory", "needs_improvement"] = Field(
        description="Computed on backend by overall_score",
    )
    strengths: list[str] = Field(
        min_length=2,
        max_length=4,
        description="Manager strengths in this call",
    )
    growth_areas: list[str] = Field(
        min_length=2,
        max_length=4,
        description="Growth areas — what manager can improve",
    )
    action_plan: list[str] = Field(
        min_length=3,
        max_length=5,
        description="Concrete steps for skill development",
    )
    follow_up_email: FollowUpEmail | None = Field(
        default=None,
        description="Draft follow-up email for the client",
    )
    crm_note: CrmNote | None = Field(
        default=None,
        description="Structured CRM note for copy-paste",
    )


_DEFAULT_CRITERIA = [
    EvaluationCriterion(
        id="greeting",
        name="Приветствие и установление контакта",
        description=(
            "Менеджер представился (имя, компания), озвучил цель звонка, "
            "согласовал повестку, обращается к клиенту по имени, "
            "создал позитивный настрой"
        ),
        weight=0.10,
    ),
    EvaluationCriterion(
        id="needs_discovery",
        name="Выявление потребностей",
        description=(
            "Задавал открытые вопросы, выявил 3-4 проблемы/потребности, "
            "соотношение говорит/слушает близко к 43/57, активное слушание"
        ),
        weight=0.25,
    ),
    EvaluationCriterion(
        id="value_presentation",
        name="Презентация ценности",
        description=(
            "Привязал решение к выявленным потребностям, говорил о выгодах "
            "а не характеристиках, использовал цифры и кейсы"
        ),
        weight=0.15,
    ),
    EvaluationCriterion(
        id="objection_handling",
        name="Работа с возражениями",
        description=(
            "Выслушал возражение полностью, сделал паузу, "
            "признал точку зрения клиента, привёл аргумент с доказательствами, "
            "проверил снято ли возражение"
        ),
        weight=0.20,
    ),
    EvaluationCriterion(
        id="closing",
        name="Закрытие и следующие шаги",
        description=(
            "Предложил конкретный следующий шаг с привязкой ко времени, "
            "зафиксировал взаимные обязательства, подвёл итог разговора"
        ),
        weight=0.15,
    ),
    EvaluationCriterion(
        id="communication",
        name="Коммуникативные навыки",
        description=(
            "Ясная речь, подходящий темп, эмпатия, уверенность "
            "без высокомерия, адаптация к стилю собеседника"
        ),
        weight=0.10,
    ),
    EvaluationCriterion(
        id="strategy_adherence",
        name="Следование стратегии",
        description=(
            "Использовал тезисы из брифинга, работал по портрету клиента, "
            "применял подготовленные ответы на возражения"
        ),
        weight=0.05,
    ),
]

DEFAULT_CONFIG = EvaluationConfig(criteria=_DEFAULT_CRITERIA)
