"""SGR BriefData models -- schema IS the LLM prompt (FEAT-012).

Every Field(description=...) serves dual purpose:
1. Pydantic documentation
2. LLM instruction when schema is passed via response_format

See specs/FEAT-012-sgr-contract.md for the full contract.
"""

from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    """Base model: camelCase JSON aliases, snake_case Python attrs."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class BriefContact(_CamelModel):
    role: str = Field(
        default="",
        description=(
            "Должность ЛПР. Извлеки из документов. Пример: 'Коммерческий директор'"
        ),
    )
    company: str = Field(
        default="",
        description=(
            "Название компании клиента. Извлеки из документов. "
            "Пример: 'ООО «СтройГрупп»'"
        ),
    )
    company_detail: str = Field(
        default="",
        description=(
            "Одна краткая деталь о компании: кол-во сотрудников, филиалов, оборот. "
            "Если нет в документах — оставь пустым. Пример: '5 филиалов'"
        ),
    )
    budget_note: str = Field(
        default="",
        description=(
            "Кто согласовывает бюджет и как. Если нет в документах — оставь пустым. "
            "Пример: 'Согласовывает ген. директор Петров С.А.'"
        ),
    )


class BriefProfileTag(_CamelModel):
    label: str = Field(
        description=(
            "Поведенческая черта покупателя, до 3 слов. "
            "Примеры: 'ROI-ориентирован', 'Любит цифры', 'Нужна 1С интеграция'"
        ),
    )
    color: Literal["blue", "green", "amber"] = Field(
        description=(
            "Цвет тега. blue — аналитика/цифры, green — рост/развитие, "
            "amber — срочность/ограничения"
        ),
    )


class BriefFocusPoint(_CamelModel):
    headline: str = Field(
        description=(
            "Краткий тезис до 5 слов — ЧТО предложить. Пример: 'Экономия 2ч/день'"
        ),
    )
    detail: str = Field(
        default="",
        description=(
            "Одно предложение — ПОЧЕМУ это важно клиенту. "
            "Пример: 'CRM сам заполняет карточки после звонков'"
        ),
    )


class BriefRoi(_CamelModel):
    value: str = Field(
        description=(
            "Главное число ROI с единицей измерения. Бери из документов verbatim. "
            "Пример: '42 млн ₽'. Если нет числа — верни null для roi"
        ),
    )
    description: str = Field(
        description=(
            "Одно предложение — что это число означает. "
            "Пример: 'потенциальная допвыручка/год при внедрении СберCRM'"
        ),
    )


class BriefComparisonSide(_CamelModel):
    name: str = Field(description="Название решения")
    price: str = Field(
        description="Цена verbatim из документов. Пример: '~35 000 ₽/мес'"
    )
    pros: str = Field(default="", description="Плюсы (для нашего предложения)")
    cons: str = Field(default="", description="Минусы (для текущего решения)")


class BriefComparison(_CamelModel):
    current: BriefComparisonSide = Field(
        description=(
            "Текущее решение клиента. Извлеки из документов. "
            "Если конкурент не упомянут — верни null для comparison"
        ),
    )
    proposed: BriefComparisonSide = Field(
        description="Наше предложение. Название, цена, плюсы",
    )


class BriefObjection(_CamelModel):
    question: str = Field(
        description=(
            "Типичное возражение клиента. В кавычках, "
            "от первого лица. "
            "Пример: '«У нас уже есть Bitrix24»'"
        ),
    )
    answer: str = Field(
        description=(
            "Готовый ответ менеджера. Конкретно, с цифрами. До 2 предложений."
        ),
    )


class BriefData(_CamelModel):
    """SGR root schema. Field order matters: context -> strategy -> tactics."""

    contact: BriefContact = Field(default_factory=BriefContact)
    profile_tags: Annotated[list[BriefProfileTag], MaxLen(3)] = Field(
        default_factory=list,
        description="Поведенческие теги покупателя, максимум 3.",
    )
    pain_points: Annotated[list[str], MaxLen(5)] = Field(
        default_factory=list,
        description=(
            "Боли/проблемы клиента, кратко (до 10 слов каждая). Извлеки из документов."
        ),
    )
    focus_points: Annotated[list[BriefFocusPoint], MaxLen(3)] = Field(
        default_factory=list,
        description="Строго 1-3 ключевых действия для менеджера.",
    )
    roi: BriefRoi | None = Field(
        default=None,
        description="Null если в документах нет конкретных чисел для ROI.",
    )
    comparison: BriefComparison | None = Field(
        default=None,
        description="Null если текущее решение клиента не упомянуто.",
    )
    objections: Annotated[list[BriefObjection], MaxLen(3)] = Field(
        default_factory=list,
        description="2-3 типичных возражения с готовыми ответами.",
    )
    full_brief: str = Field(
        default="",
        description="Полный текстовый бриф, plain text, 300-500 слов.",
    )
