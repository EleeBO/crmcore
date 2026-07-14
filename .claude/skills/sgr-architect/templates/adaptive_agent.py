"""
SGR Template: Adaptive Agent (NextStep)

Шаблон для адаптивного агента с планированием и Tool Calling.
Используй как основу для агентов, выполняющих многошаговые задачи.
"""

from pydantic import BaseModel, Field
from typing import Literal, Union, List, Annotated, Any
from annotated_types import MinLen, MaxLen


# === Определение инструментов ===

class SearchTool(BaseModel):
    """Инструмент: Поиск информации"""
    tool: Literal["search"]
    
    query: str = Field(
        description="Поисковый запрос"
    )
    max_results: int = Field(
        default=5, ge=1, le=20,
        description="Максимальное количество результатов"
    )
    source_filter: Literal["web", "docs", "knowledge_base", "all"] = Field(
        default="all",
        description="Фильтр по источникам"
    )


class ReadDocumentTool(BaseModel):
    """Инструмент: Чтение документа"""
    tool: Literal["read_document"]
    
    document_id: str = Field(
        description="ID документа для чтения"
    )
    sections: List[str] | Literal["all"] = Field(
        default="all",
        description="Разделы для чтения или 'all'"
    )


class WriteFileTool(BaseModel):
    """Инструмент: Запись в файл"""
    tool: Literal["write_file"]
    
    filename: str = Field(
        description="Имя файла"
    )
    content: str = Field(
        description="Содержимое для записи"
    )
    mode: Literal["overwrite", "append"] = Field(
        default="overwrite",
        description="Режим записи"
    )


class SendEmailTool(BaseModel):
    """Инструмент: Отправка email"""
    tool: Literal["send_email"]
    
    to: List[str] = Field(
        description="Адреса получателей"
    )
    subject: str = Field(
        description="Тема письма"
    )
    body: str = Field(
        description="Текст письма"
    )
    priority: Literal["low", "normal", "high"] = Field(
        default="normal"
    )


class ExecuteCodeTool(BaseModel):
    """Инструмент: Выполнение кода"""
    tool: Literal["execute_code"]
    
    language: Literal["python", "javascript", "bash"] = Field(
        description="Язык программирования"
    )
    code: str = Field(
        description="Код для выполнения"
    )
    timeout_seconds: int = Field(
        default=30, ge=1, le=300,
        description="Таймаут выполнения"
    )


class AskUserTool(BaseModel):
    """Инструмент: Запрос уточнения у пользователя"""
    tool: Literal["ask_user"]
    
    question: str = Field(
        description="Вопрос пользователю"
    )
    options: List[str] | None = Field(
        default=None,
        description="Варианты ответа (если применимо)"
    )


class ReportTaskCompletion(BaseModel):
    """Терминальное действие: Завершение задачи"""
    tool: Literal["complete"]
    
    summary: str = Field(
        description="Краткое описание выполненной работы"
    )
    result: Any = Field(
        description="Результат выполнения задачи"
    )
    success: bool = Field(
        description="Успешно ли завершена задача?"
    )
    follow_up_suggestions: List[str] = Field(
        default_factory=list,
        description="Предложения для дальнейших действий"
    )


# === Объединение инструментов ===

AvailableTools = Union[
    SearchTool,
    ReadDocumentTool,
    WriteFileTool,
    SendEmailTool,
    ExecuteCodeTool,
    AskUserTool,
    ReportTaskCompletion
]


# === Основная схема агента ===

class NextStep(BaseModel):
    """
    Схема адаптивного планирования агента
    
    Паттерн: Cascade (состояние → план → действие)
    
    Принцип: Планируй несколько шагов, выполняй только первый.
    Переоценивай стратегию после каждого действия.
    """
    
    # 1. Cascade: Оценка текущего состояния
    current_state: str = Field(
        description="Вербализация текущего прогресса. Что уже сделано? Что известно?"
    )
    
    blockers: List[str] = Field(
        default_factory=list,
        description="Препятствия для продолжения (если есть)"
    )
    
    # 2. Cascade: Формирование плана
    goal_assessment: str = Field(
        description="Насколько близко к достижению цели? Что ещё нужно?"
    )
    
    plan_remaining_steps: Annotated[List[str], MinLen(1), MaxLen(5)] = Field(
        description="План оставшихся шагов (1-5). Первый шаг будет выполнен немедленно."
    )
    
    # 3. Cascade: Выбор действия
    reasoning_for_next_action: str = Field(
        description="Почему именно это действие выбрано следующим?"
    )
    
    action: AvailableTools = Field(
        discriminator="tool",
        description="Инструмент для выполнения первого шага из плана"
    )
    
    # 4. Метаданные
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Уверенность в правильности выбранного действия"
    )
    
    estimated_steps_remaining: int = Field(
        ge=0, le=20,
        description="Оценка оставшегося количества шагов до завершения"
    )


# === Альтернативная схема для ReAct ===

class ReActStep(BaseModel):
    """
    Схема ReAct (Reasoning + Acting)
    
    Упрощённая версия для случаев, когда полное планирование избыточно.
    """
    
    thought: str = Field(
        description="Рассуждение о текущей ситуации и следующем шаге"
    )
    
    action: AvailableTools = Field(
        discriminator="tool",
        description="Выбранное действие"
    )


# === Пример использования ===

AGENT_SYSTEM_PROMPT = """
Ты — адаптивный агент для выполнения задач пользователя.

На каждом шаге:
1. Оцени текущее состояние (что сделано, что известно)
2. Составь план оставшихся шагов (1-5 шагов)
3. Выбери инструмент для первого шага
4. После получения результата — переоценивай ситуацию

Принципы:
- Планируй несколько шагов, выполняй только первый
- Если не уверен — используй ask_user
- Завершай задачу через complete когда цель достигнута

Доступные инструменты: search, read_document, write_file, send_email, execute_code, ask_user, complete
"""

EXAMPLE_USER_TASK = """
Найди последние новости о релизе GPT-5, составь краткое резюме и сохрани в файл news_summary.md
"""

if __name__ == "__main__":
    schema = NextStep.model_json_schema()
    print("JSON Schema для API:")
    import json
    print(json.dumps(schema, indent=2, ensure_ascii=False))
