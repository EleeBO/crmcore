# FEAT-012: SGR Contract — BriefData Schema

> Schema-Guided Reasoning: схема = контракт между LLM, бэкендом и фронтендом.
> Каждое поле документирует: что LLM генерирует, откуда берёт данные, как фронт отображает, что делать при отсутствии.

**Status:** DRAFT
**Date:** 2026-03-19

---

## Принцип

Pydantic-модель `BriefData` — единственный источник правды. Она:
1. Передаётся LLM через `response_format` (constrained decoding)
2. Валидируется Pydantic на бэкенде
3. Сериализуется в camelCase JSON для фронта
4. Десериализуется в TypeScript `BriefData` интерфейс

```
Документы → LLM (schema-constrained) → BriefData (Pydantic) → JSON (camelCase) → Preact components
```

---

## Schema

```python
from __future__ import annotations

from typing import Annotated, Literal

from annotated_types import MaxLen, MinLen
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
```

---

## Field-by-Field Contract

### `contact: BriefContact`

```python
class BriefContact(_CamelModel):
    role: str = Field(
        default="",
        description="Должность ЛПР. Извлеки из документов. Пример: 'Коммерческий директор'",
    )
    company: str = Field(
        default="",
        description="Название компании клиента. Извлеки из документов. Пример: 'ООО «СтройГрупп»'",
    )
    company_detail: str = Field(
        default="",
        description="Одна краткая деталь о компании: кол-во сотрудников, филиалов, оборот. "
                    "Если нет в документах — оставь пустым. Пример: '5 филиалов'",
    )
    budget_note: str = Field(
        default="",
        description="Кто согласовывает бюджет и как. Если нет в документах — оставь пустым. "
                    "Пример: 'Согласовывает ген. директор Петров С.А.'",
    )
```

| Field | LLM Source | Frontend Display | Fallback (empty) |
|-------|-----------|-----------------|-------------------|
| `role` | Извлечь из документов | `ContactCard`: 15px/500, первая строка | Скрыть ContactCard целиком |
| `company` | Извлечь из документов | `ContactCard`: 12px, вторая строка | Показать только role |
| `company_detail` | Извлечь если есть | После company через ` · ` | Не показывать |
| `budget_note` | Извлечь если есть | 11px tertiary, третья строка | Не показывать |

**`avatar_initials`** — НЕ в схеме LLM. Генерируется на фронте из `role`:
```typescript
function makeInitials(role: string): string {
  const words = role.split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return "";
}
```

---

### `profile_tags: list[BriefProfileTag]`

```python
class BriefProfileTag(_CamelModel):
    label: str = Field(
        description="Поведенческая черта покупателя, до 3 слов. "
                    "Примеры: 'ROI-ориентирован', 'Любит цифры', 'Нужна 1С интеграция'",
    )
    color: Literal["blue", "green", "amber"] = Field(
        description="Цвет тега. blue — аналитика/цифры, green — рост/развитие, amber — срочность/ограничения",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `label` | LLM определяет по стилю общения из документов | Pill badge, 11px | — |
| `color` | LLM выбирает из `Literal["blue","green","amber"]` | CSS class `.brief-tag--{color}` | Невалидный → default `blue` |

**Constraint:** `Annotated[list[BriefProfileTag], MaxLen(3)]` — максимум 3 тега.
**Fallback (empty list):** Скрыть блок тегов.

**Семантика цветов:**
- `blue` — аналитический, цифры, ROI, данные
- `green` — рост, развитие, новое, инновации
- `amber` — срочность, ограничения, дедлайны, риски

---

### `focus_points: list[BriefFocusPoint]`

```python
class BriefFocusPoint(_CamelModel):
    headline: str = Field(
        description="Краткий тезис до 5 слов — ЧТО предложить. "
                    "Пример: 'Экономия 2ч/день'",
    )
    detail: str = Field(
        default="",
        description="Одно предложение — ПОЧЕМУ это важно клиенту. "
                    "Пример: 'CRM сам заполняет карточки после звонков'",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `headline` | LLM генерирует из key_messages / документов | 13px/500 bold | — |
| `detail` | LLM поясняет headline | 13px/400 secondary после тире | Показать только headline |

**Constraint:** `Annotated[list[BriefFocusPoint], MinLen(1), MaxLen(3)]` — строго 1-3 пункта.
**Frontend:** Нумерация (①②③), фон `--bg-secondary`, label "ФОКУС РАЗГОВОРА".

---

### `pain_points: list[str]`

```python
    pain_points: Annotated[list[str], MaxLen(5)] = Field(
        default_factory=list,
        description="Боли/проблемы клиента, кратко (до 10 слов каждая). "
                    "Извлеки из документов. Примеры: '2 часа/день на ручное заполнение CRM'",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| each string | Извлечь из документов | Красный `!` + 12px text | Empty → скрыть блок |

**Frontend:** Компактный список без карточек. Красный маркер `!` (#E24B4A).

---

### `roi: BriefRoi | None`

```python
class BriefRoi(_CamelModel):
    value: str = Field(
        description="Главное число ROI с единицей измерения. Бери из документов verbatim. "
                    "Пример: '42 млн ₽'. Если нет числа — верни null для roi",
    )
    description: str = Field(
        description="Одно предложение — что это число означает. "
                    "Пример: 'потенциальная допвыручка/год при внедрении СберCRM'",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `value` | Числа из документов verbatim | 22px/500, зелёный (#3B6D11) | — |
| `description` | LLM поясняет | 12px, зелёный, max 2 строки | — |

**Constraint:** `roi: BriefRoi | None` — null если нет числовых данных.
**LLM instruction:** "Если в документах нет конкретных чисел для ROI — верни `null` для этого поля, не выдумывай."
**Frontend (null):** Блок полностью скрыт.

---

### `comparison: BriefComparison | None`

```python
class BriefComparisonSide(_CamelModel):
    name: str = Field(description="Название решения")
    price: str = Field(description="Цена verbatim из документов. Пример: '~35 000 ₽/мес'")
    pros: str = Field(default="", description="Плюсы (для нашего предложения)")
    cons: str = Field(default="", description="Минусы (для текущего решения)")

class BriefComparison(_CamelModel):
    current: BriefComparisonSide = Field(
        description="Текущее решение клиента. Извлеки из документов. "
                    "Если конкурент не упомянут — верни null для comparison",
    )
    proposed: BriefComparisonSide = Field(
        description="Наше предложение. Название, цена, плюсы",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `current.name` | Из документов | 11px/500, красный фон | — |
| `current.price` | Verbatim | 14px/500 | — |
| `current.cons` | LLM/документы | 12px/400 | Не показывать |
| `proposed.name` | Из документов | 11px/500, зелёный фон | — |
| `proposed.price` | Verbatim | 14px/500 | — |
| `proposed.pros` | LLM/документы | 12px/400 | Не показывать |

**Constraint:** `comparison: BriefComparison | None` — null если конкурент не упомянут.
**LLM instruction:** "Если в документах не упоминается текущее решение клиента — верни `null`, не придумывай конкурента."
**Frontend (null):** Блок полностью скрыт.

---

### `objections: list[BriefObjection]`

```python
class BriefObjection(_CamelModel):
    question: str = Field(
        description="Типичное возражение клиента. В кавычках, от первого лица. "
                    "Пример: '«У нас уже есть Bitrix24»'",
    )
    answer: str = Field(
        description="Готовый ответ менеджера. Конкретно, с цифрами. До 2 предложений. "
                    "Пример: 'СберCRM дешевле на 33%, нативная 1С, без тормозов. Пилот 30 дней бесплатно.'",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `question` | LLM генерирует типичные возражения | 12px/500 | — |
| `answer` | LLM генерирует с цифрами из документов | `→ ` prefix, 12px/400 secondary | — |

**Constraint:** `Annotated[list[BriefObjection], MinLen(1), MaxLen(3)]`
**Frontend:** Label "ГОТОВЫЕ ОТВЕТЫ НА ВОЗРАЖЕНИЯ", разделитель 0.5px между Q&A.

---

### `full_brief: str`

```python
    full_brief: str = Field(
        default="",
        description="Полный текстовый бриф в виде plain text (не markdown). "
                    "Включи всю ключевую информацию: контекст встречи, профиль клиента, "
                    "рекомендации, потенциальные сценарии. 300-500 слов.",
    )
```

| Field | LLM Source | Frontend Display | Fallback |
|-------|-----------|-----------------|----------|
| `full_brief` | LLM генерирует полный текст | `white-space: pre-wrap`, textContent | Empty → скрыть кнопку |

**Frontend:** Скрыт за кнопкой "Открыть полный бриф →". Рендерится как `textContent` (без HTML parsing, без XSS).

---

## Полная Pydantic-модель

```python
class BriefData(_CamelModel):
    """SGR-контракт для предзвонкового брифинга.

    Порядок полей важен для SGR: LLM сначала анализирует контакт и профиль,
    затем формулирует стратегию (focus_points), и только потом — тактику (objections).
    Это "прогревает" контекст модели для более точной генерации.
    """

    # ── Блок 1: КТО (анализ контекста) ──
    contact: BriefContact = Field(default_factory=BriefContact)
    profile_tags: Annotated[list[BriefProfileTag], MaxLen(3)] = Field(default_factory=list)

    # ── Блок 2: ЧТО БОЛИТ (извлечение фактов) ──
    pain_points: Annotated[list[str], MaxLen(5)] = Field(default_factory=list)

    # ── Блок 3: ЧТО ДЕЛАТЬ (стратегия — после анализа) ──
    focus_points: Annotated[list[BriefFocusPoint], MaxLen(3)] = Field(default_factory=list)

    # ── Блок 4: ГЛАВНЫЙ АРГУМЕНТ (вывод из анализа) ──
    roi: BriefRoi | None = Field(
        default=None,
        description="Если в документах нет конкретных чисел — верни null",
    )

    # ── Блок 5: СРАВНЕНИЕ (если есть конкурент) ──
    comparison: BriefComparison | None = Field(
        default=None,
        description="Если текущее решение клиента не упомянуто — верни null",
    )

    # ── Блок 6: ЗАЩИТА (тактика — после стратегии) ──
    objections: Annotated[list[BriefObjection], MaxLen(3)] = Field(default_factory=list)

    # ── Полный бриф (синтез всего выше) ──
    full_brief: str = Field(
        default="",
        description="Полный текстовый бриф, plain text, 300-500 слов",
    )
```

**SGR-порядок полей:** contact → profile → pains → focus → roi → comparison → objections → brief.
Модель сначала "понимает" клиента, затем формулирует стратегию, затем тактику. Каждое следующее поле строится на контексте предыдущих.

---

## Scenario → BriefData Mapping

Когда Scenario уже есть в Redis (нормальный production path), мы НЕ вызываем LLM. Трансформация:

| Scenario field | BriefData field | Transform |
|---------------|----------------|-----------|
| `portrait.role` | `contact.role` | Direct |
| `portrait.pain_points` | `pain_points` | Direct |
| `portrait.motivators` | `profile_tags[].label` | + rotating color |
| `portrait.budget` | `contact.budget_note` | Direct |
| `strategy.key_messages` | `focus_points[].headline` | `detail=""` |
| `objections[].trigger` | `objections[].question` | Key rename |
| `objections[].response` | `objections[].answer` | Key rename |
| — | `contact.company` | Пусто (нет в Scenario) |
| — | `roi` | `null` (нет в Scenario) |
| — | `comparison` | `null` (нет в Scenario) |
| — | `full_brief` | Пусто (нет в Scenario) |

**Ограничение Scenario path:** Нет `company`, `roi`, `comparison`, `full_brief`. Эти поля заполняются только через LLM path. Это осознанный tradeoff: скорость vs полнота.

---

## Frontend Display Map

```
┌─ ContactCard ──────────────────────────┐
│ [КД] contact.role                      │  ← скрыть если role пуст
│      contact.company · companyDetail   │  ← скрыть если company пуст
│      contact.budgetNote                │  ← скрыть если пуст
│ [tag] [tag] [tag]  ← profile_tags      │  ← скрыть если []
├─ Divider ──────────────────────────────┤
│ ФОКУС РАЗГОВОРА                        │
│ ① headline — detail                    │  ← focus_points (max 3)
│ ② headline — detail                    │
│ ③ headline — detail                    │
│                                        │
│ ! pain_point_1                         │  ← pain_points
│ ! pain_point_2                         │  ← скрыть блок если []
├─ Divider ──────────────────────────────┤
│ ┌────────────────────────────────────┐ │
│ │ roi.value                          │ │  ← зелёный фон, скрыть если null
│ │ roi.description                    │ │
│ └────────────────────────────────────┘ │
│ ┌──────────┐ ┌──────────────────────┐  │
│ │ current  │ │ proposed             │  │  ← скрыть если null
│ │ price    │ │ price                │  │
│ │ cons     │ │ pros                 │  │
│ └──────────┘ └──────────────────────┘  │
├─ Divider ──────────────────────────────┤
│ ГОТОВЫЕ ОТВЕТЫ НА ВОЗРАЖЕНИЯ           │
│ question → answer                      │  ← max 3
│ ────────────────────                   │
│ question → answer                      │
├────────────────────────────────────────┤
│ [Открыть полный бриф →]                │  ← скрыть если full_brief пуст
│ (expanded) full_brief text             │
└────────────────────────────────────────┘
```

---

## Validation Rules

| Rule | Pydantic | LLM Instruction | Frontend |
|------|---------|-----------------|----------|
| Max 3 tags | `MaxLen(3)` | "максимум 3" | `.slice(0, 3)` |
| Max 3 focus | `MaxLen(3)` | "строго 3 пункта" | `.slice(0, 3)` |
| Max 3 objections | `MaxLen(3)` | "2-3 штуки" | `.slice(0, 3)` |
| Tag color | `Literal["blue","green","amber"]` | Constrained decoding | CSS class mapping |
| ROI null | `BriefRoi \| None` | "если нет чисел — null" | Hide block |
| Comparison null | `BriefComparison \| None` | "если нет конкурента — null" | Hide block |
| Prices verbatim | `Field(description="verbatim")` | "не округляй" | Display as-is |

**Triple validation:**
1. **LLM level:** `response_format` + `Field(description=...)` constrain generation
2. **Backend level:** Pydantic validates, Reparser retries on failure
3. **Frontend level:** `.slice()` caps + null checks + graceful hide
