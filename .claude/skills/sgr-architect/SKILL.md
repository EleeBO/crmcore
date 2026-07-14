---
name: sgr-architect
description: Schema-Guided Reasoning (SGR) для создания надёжных LLM-систем с типизированными выводами. Применяй когда нужно спроектировать Pydantic-схемы для структурированного вывода LLM, реализовать паттерны Cascade/Routing/Cycle для агентов, построить Enterprise RAG пайплайн, провести рефакторинг промптов в схемы, настроить оценку качества через RAGAS, создать адаптивное планирование с Tool Calling.
---

# SGR Architect — Schema-Guided Reasoning

SGR превращает ненадёжную генерацию LLM в детерминированный пайплайн через типизированные схемы.

## Философия

**Схема = Алгоритм рассуждения.** Структура ответа программирует когнитивный процесс модели. Pydantic-аннотации заменяют текстовые инструкции жёсткими синтаксическими фильтрами.

**Constrained Decoding.** На этапе сэмплинга токенов отсекаются варианты, не соответствующие JSON-схеме. Модель физически не может нарушить структуру.

## Быстрый старт

### Минимальная SGR-схема

```python
from pydantic import BaseModel, Field
from typing import Literal

class Decision(BaseModel):
    reasoning: str = Field(description="Пошаговый анализ перед решением")
    conclusion: Literal["approve", "reject", "escalate"]
    confidence: float = Field(ge=0.0, le=1.0)
```

Поле `reasoning` перед `conclusion` — критически важно. Это "разогревает" контекст модели перед финальным выбором (+12% к точности по данным Vanguard).

### Вызов с response_format

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    response_format={"type": "json_schema", "json_schema": Decision.model_json_schema()},
    messages=[{"role": "user", "content": "..."}]
)
result = Decision.model_validate_json(response.choices[0].message.content)
```

## Три фундаментальных паттерна

| Паттерн | Когда использовать | Механика |
|---------|-------------------|----------|
| **Cascade** | Многошаговое рассуждение | Вложенные BaseModel с логическим порядком полей |
| **Routing** | Выбор из взаимоисключающих путей | `Union` типов + `Literal` дискриминатор |
| **Cycle** | Обязательная итерация | `Annotated[List[T], MinLen(N), MaxLen(M)]` |

→ Детальные примеры: `references/patterns.md`

## Адаптивное планирование (NextStep)

Для агентов с Tool Calling используй модель NextStep:

```python
from typing import Union, Annotated, List
from annotated_types import MinLen, MaxLen

class NextStep(BaseModel):
    current_state: str = Field(description="Вербализация текущего прогресса")
    plan_remaining_steps: Annotated[List[str], MinLen(1), MaxLen(5)]
    action: Union[SearchTool, EmailTool, ReportCompletion] = Field(
        description="Выполнить первый шаг из плана"
    )
```

**Принцип:** Планируй несколько шагов, исполняй только первый. Переоценивай стратегию на каждой итерации.

## Workflow: Рефакторинг промптов в схемы

1. **Инвентаризация** — каталогизируй все узлы и их JSON-выводы
2. **Baseline** — измерь текущую точность/надёжность/стоимость
3. **Проектирование схем** — замени неявную логику на Pydantic-модели
4. **Замена узлов** — передавай схему в `response_format`
5. **Верификация** — сравни метрики с baseline

→ Детальный чеклист: `references/refactoring-checklist.md`

## Обработка ошибок: Reparser Pattern

Для моделей без native Structured Outputs:

```python
def safe_parse(response: str, schema: type[BaseModel], llm, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            return schema.model_validate_json(response)
        except ValidationError as e:
            if attempt == max_retries:
                raise
            response = llm.complete(f"""
Твой ответ не прошёл валидацию схемы.
ОШИБКА: {e}
Исправь JSON, сохранив логику. Верни ТОЛЬКО валидный JSON.
""")
    return None
```

## Enterprise RAG интеграция

SGR встраивается в RAG на этапе генерации ответа:

1. **Retrieval** → гибридный поиск (Dense + BM25)
2. **Reranking** → LLM оценивает релевантность чанков
3. **Generation** → SGR-схема с полями `evidence` и `page_numbers`

→ Архитектура: `references/enterprise-rag.md`

## Оценка качества (RAGAS)

| Метрика | Что измеряет | Формула |
|---------|-------------|---------|
| Faithfulness | Верность фактам из контекста | `|V| / |S|` (подтверждённые / все утверждения) |
| Answer Relevance | Соответствие интенту пользователя | LLM-оценка 0-1 |
| Context Relevance | Сигнал vs шум в извлечённых данных | Доля релевантных предложений |

→ Реализация: `references/evaluation.md`

## Типичные ошибки и решения

| Проблема | Причина | Решение |
|----------|---------|---------|
| Silent Hallucinations | Модель придумывает данные для обязательных полей | Добавь `Literal["N/A"]` + инструкция в description |
| Cognitive Overload | Слишком сложная схема | Разбей на Union узкоспециализированных схем |
| Stale Data | Устаревшие документы в RAG | Lifecycle management: cold storage для старых чанков |

## Скрипты

```bash
# Валидация схемы на SGR best practices
python .claude/skills/sgr-architect/scripts/validate_schema.py path/to/schema.py
```

## Шаблоны

- `templates/adaptive_agent.py` — адаптивный агент с NextStep

## Интеграция с Anthropic API

```python
import anthropic

client = anthropic.Anthropic()

# Используй tools для structured output
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=[{
        "name": "decision",
        "description": "Принять решение",
        "input_schema": Decision.model_json_schema()
    }],
    tool_choice={"type": "tool", "name": "decision"},
    messages=[{"role": "user", "content": "..."}]
)

# Парсинг результата
result = Decision.model_validate(response.content[0].input)
```
