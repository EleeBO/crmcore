# SGR Patterns Reference

## 1. Cascade Pattern (Каскад)

Последовательное уточнение от анализа к решению. Порядок полей программирует порядок рассуждения.

### Когда использовать
- Многошаговый анализ перед решением
- Требуется аудируемость процесса
- Нужен "бюджет на размышление"

### Реализация

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class PreliminaryAnalysis(BaseModel):
    """Первый уровень каскада — сбор фактов"""
    key_facts: List[str] = Field(
        description="Выдели 3-5 ключевых фактов из контекста"
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Какой информации не хватает для решения?"
    )

class RiskAssessment(BaseModel):
    """Второй уровень — оценка рисков"""
    identified_risks: List[str] = Field(
        min_length=2,
        description="Минимум 2 потенциальных риска"
    )
    mitigation_options: List[str]

class FinalDecision(BaseModel):
    """Финальный каскад — решение на основе предыдущих уровней"""
    preliminary: PreliminaryAnalysis
    risks: RiskAssessment
    decision: Literal["approve", "reject", "escalate"]
    justification: str = Field(
        description="Обоснование со ссылками на preliminary и risks"
    )
    confidence: float = Field(ge=0.0, le=1.0)
```

### Антипаттерн

```python
# ПЛОХО: decision перед reasoning
class BadDecision(BaseModel):
    decision: str  # Модель сначала решает, потом придумывает обоснование
    reasoning: str
```

---

## 2. Routing Pattern (Маршрутизация)

Принудительный выбор одного из взаимоисключающих путей через Discriminated Unions.

### Когда использовать
- Классификация с разными структурами данных
- Маршрутизация в мультиагентных системах
- Выбор инструмента/стратегии

### Реализация

```python
from pydantic import BaseModel, Field
from typing import Literal, Union

# Определяем варианты с дискриминатором
class HardwareIssue(BaseModel):
    kind: Literal["hardware"]  # Дискриминатор
    component: Literal["battery", "display", "keyboard", "other"]
    symptoms: str
    warranty_check_needed: bool

class SoftwareIssue(BaseModel):
    kind: Literal["software"]
    application: str
    error_code: str | None = None
    reinstall_attempted: bool

class AccountIssue(BaseModel):
    kind: Literal["account"]
    issue_type: Literal["password", "billing", "permissions"]
    account_id: str | None = None

class UnknownIssue(BaseModel):
    kind: Literal["unknown"]
    summary: str
    suggested_department: str

# Объединяем в Union
class SupportTriage(BaseModel):
    customer_sentiment: Literal["frustrated", "neutral", "satisfied"]
    issue: Union[HardwareIssue, SoftwareIssue, AccountIssue, UnknownIssue] = Field(
        discriminator="kind",
        description="Классифицируй проблему и заполни соответствующую структуру"
    )
    priority: Literal["low", "medium", "high", "critical"]
    suggested_response_template: str
```

### Динамическая маршрутизация

Для динамических категорий используй фабрику:

```python
from typing import get_args

def create_category_schema(categories: list[str]):
    CategoryLiteral = Literal[tuple(categories)]
    
    class DynamicClassification(BaseModel):
        reasoning: str
        category: CategoryLiteral
        confidence: float = Field(ge=0.0, le=1.0)
    
    return DynamicClassification

# Использование
ProductSchema = create_category_schema(["electronics", "clothing", "food"])
```

---

## 3. Cycle Pattern (Цикл)

Принудительная итерация через `Annotated[List[T], MinLen(N), MaxLen(M)]`.

### Когда использовать
- Предотвращение "ленивой" генерации
- Гарантия минимального покрытия
- Обязательный анализ альтернатив

### Реализация

```python
from pydantic import BaseModel, Field
from typing import List, Annotated
from annotated_types import MinLen, MaxLen

class RiskFactor(BaseModel):
    name: str
    severity: Literal["low", "medium", "high", "critical"]
    likelihood: float = Field(ge=0.0, le=1.0)
    mitigation: str

class ComprehensiveRiskAnalysis(BaseModel):
    """Модель ОБЯЗАНА найти минимум 3, максимум 7 рисков"""
    context_summary: str
    risks: Annotated[List[RiskFactor], MinLen(3), MaxLen(7)] = Field(
        description="Идентифицируй 3-7 различных рисков. Если очевидных рисков меньше 3, ищи неочевидные."
    )
    overall_risk_level: Literal["acceptable", "elevated", "critical"]
    recommended_actions: Annotated[List[str], MinLen(2), MaxLen(5)]
```

### Цикл с уникальностью

```python
from pydantic import field_validator

class BrainstormIdeas(BaseModel):
    topic: str
    ideas: Annotated[List[str], MinLen(5), MaxLen(10)]
    
    @field_validator("ideas")
    @classmethod
    def ideas_must_be_unique(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Ideas must be unique")
        return v
```

---

## 4. Комбинированные паттерны

### Cascade + Routing

```python
class AnalysisResult(BaseModel):
    # Cascade: сначала анализ
    observations: List[str]
    hypothesis: str
    
    # Routing: затем выбор действия
    recommended_action: Union[
        EscalateToManager,
        AutoResolve,
        RequestMoreInfo
    ]
```

### Routing + Cycle

```python
class MultiPathAnalysis(BaseModel):
    # Routing: определи тип задачи
    task_type: Union[TechnicalTask, BusinessTask, CreativeTask]
    
    # Cycle: для каждого типа — минимум N подзадач
    subtasks: Annotated[List[Subtask], MinLen(2), MaxLen(5)]
```

---

## 5. Best Practices

### Именование полей

```python
# ХОРОШО: глагольные description
class Good(BaseModel):
    analysis: str = Field(description="Проанализируй входные данные")
    decision: str = Field(description="Прими решение на основе анализа")

# ПЛОХО: существительные без действия
class Bad(BaseModel):
    analysis: str = Field(description="Анализ")
    decision: str = Field(description="Решение")
```

### Обработка отсутствующих данных

```python
class SafeExtraction(BaseModel):
    # Вариант 1: Optional с None
    email: str | None = Field(
        default=None,
        description="Email или None если не найден"
    )
    
    # Вариант 2: Literal для явного "нет данных"
    status: Literal["found", "not_found", "ambiguous"]
    
    # Вариант 3: Специальное значение
    phone: str = Field(
        description="Телефон или строка 'N/A' если не найден"
    )
```

### Ограничение длины для контроля токенов

```python
from pydantic import constr

class ConciseResponse(BaseModel):
    summary: constr(max_length=500) = Field(
        description="Краткое резюме до 500 символов"
    )
    key_points: Annotated[List[constr(max_length=100)], MaxLen(5)]
```
