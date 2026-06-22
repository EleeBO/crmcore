# FEAT-004: Автоматическая оценка менеджеров по транскрипту звонка (SGR)

**Status:** DRAFT
**Date:** 2026-03-12
**Author:** Claude Code + Human

---

## 1. Проблема

После завершения звонка менеджер получает транскрипт, но не получает обратной связи по качеству разговора. Руководителю продаж (РОПу) приходится вручную прослушивать звонки и оценивать менеджеров, что занимает много времени и не масштабируется.

## 2. Решение

Автоматическая оценка качества звонка сразу после его завершения. LLM выступает в роли РОПа: анализирует транскрипт + брифинг и выставляет структурированную оценку по настраиваемым критериям.

**Архитектура:** Single-Pass SGR (Schema-Guided Reasoning) — один вызов LLM с Pydantic-схемой, использующей Cascade-паттерн (reasoning → score → comment для каждого критерия).

## 3. Scope (для демо)

### В scope

- Backend: модуль `evaluator.py` с SGR-схемами
- Backend: API эндпоинт для CRUD критериев оценки
- Backend: интеграция в orchestrator (триггер на session_end)
- Extension: страница настроек критериев (premium dark UI)
- Extension: краткая сводка оценки в Phase 4 (Side Panel)
- Extension: полная страница отчёта (новая вкладка)
- 7 дефолтных критериев B2B-продаж
- Хранение в Redis

### Вне scope

- Исторические отчёты / аналитика по менеджерам
- Сравнение менеджеров между собой
- Экспорт в PDF
- Настройка промпта через UI (только критерии)
- Multi-pass или fan-out оценка

## 4. Архитектура

### 4.1 Поток данных

```
Extension отправляет session_end control frame по WebSocket
  │
  ▼
backend/main.py: ws_handler() — получает session_end JSON
  │
  ├── Отправляет evaluation_started в WebSocket
  ├── Вызывает await orchestrator.on_session_end(session_id, ws)
  │   └── on_session_end() ЗАПУСКАЕТ evaluation как отдельный asyncio.Task
  │       (self._evaluation_task, НЕ добавляется в _background_tasks)
  ├── Затем вызывает orchestrator.teardown()
  │   └── teardown() НЕ отменяет self._evaluation_task
  │       (только _background_tasks для hint pipeline)
  ├── await self._evaluation_task (ожидает завершения оценки после teardown)
  │
  ▼
orchestrator.py: on_session_end(session_id, ws)
  │
  ├── Guard: if self._evaluation_started → return (idempotency)
  ├── self._evaluation_started = True
  ├── Собирает: transcript[] из Redis — из ОТДЕЛЬНОГО ключа eval_transcript:{session_id}
  │   └── (полный список utterances, НЕ обрезанный до 10 как session:{session_id})
  ├── Guard: if len(transcript) == 0 → send evaluation_error, return
  ├── Собирает: briefing/scenario (rag_context из prompt_formatter)
  ├── Загружает: EvaluationConfig из Redis (eval_config:default)
  │   └── Если ключ не найден → загружает DEFAULT_CRITERIA (hardcoded)
  │
  ▼
evaluator.py: evaluate_call()
  │
  ├── Redis lrange ограничен 4000 utterances (upper bound guard)
  ├── Обрезает транскрипт до ~12K токенов (оставляет начало + конец)
  ├── Формирует system prompt (роль РОПа)
  ├── Формирует user prompt (транскрипт + брифинг + критерии)
  ├── Вызов EvaluatorLLMClient (НЕ-стриминговый, отдельный от hint-клиента)
  │   └── response_format={"type": "json_schema", "json_schema": CallEvaluation.model_json_schema()}
  ├── Pydantic-валидация CallEvaluation
  ├── При невалидном JSON → reparse с конкретной ошибкой в промпте (1 повтор)
  ├── overall_score ПЕРЕСЧИТЫВАЕТСЯ на бэкенде (не доверяем LLM):
  │   └── sum(result.score * criterion.weight) для каждого критерия
  ├── verdict вычисляется по пересчитанному overall_score
  │
  ▼
Результат: CallEvaluation
  │
  ├── Сохраняет в Redis: eval:{session_id} (TTL 24h)
  ├── Генерирует eval_token = secrets.token_urlsafe(16) → Redis eval_token:{session_id} TTL 24h
  ├── Отправляет по WebSocket: type="evaluation_result" (с eval_token)
  │
  ▼
Extension (Side Panel):
  ├── Сохраняет evaluation + eval_token в chrome.storage.local
  ├── Phase 4: краткая сводка (gauge + мини-бары)
  └── Кнопка "Подробный отчёт" → report.html (новая вкладка)

Extension (report.html):
  ├── Читает session_id из URL query param
  ├── Читает backendUrl из chrome.storage.local → формирует API_BASE
  ├── Читает eval_token из chrome.storage.local
  └── GET /api/v1/evaluation/{session_id}?token={eval_token}
```

### 4.2 Новые файлы

| Файл | Назначение |
|------|------------|
| `backend/pipeline/evaluator.py` | SGR-оценщик: промпт, вызов LLM, валидация |
| `backend/pipeline/evaluator_llm.py` | EvaluatorLLMClient — НЕ-стриминговый LLM-клиент с response_format и 30s timeout |
| `backend/pipeline/evaluation_schemas.py` | Pydantic-схемы (EvaluationConfig, CallEvaluation, defaults) |
| `backend/api/evaluation.py` | REST API для CRUD критериев (FastAPI Router) |
| `extension/src/settings/evaluation-settings.html` | Страница настроек критериев |
| `extension/src/settings/evaluation-settings.css` | Стили (premium dark) |
| `extension/src/settings/evaluation-settings.ts` | Логика настроек |
| `extension/src/report/report.html` | Полная страница отчёта |
| `extension/src/report/report.css` | Стили отчёта (premium dark) |
| `extension/src/report/report.ts` | Логика отчёта |

### 4.3 Изменяемые файлы

| Файл | Изменение |
|------|-----------|
| `backend/main.py` | Заменить `session_end` → `break` на полноценную обработку (см. сниппет ниже), регистрация evaluation router |
| `backend/pipeline/orchestrator.py` | Новые атрибуты `_evaluation_task`, `_evaluation_started`; метод `on_session_end()`; `teardown()` НЕ отменяет `_evaluation_task` |
| `extension/src/shared/messages.ts` | Добавить типы `WsEvaluationStarted`, `WsEvaluationResult` в union `WsMessage`; добавить TypeScript interface `CallEvaluation` |
| `extension/src/sidepanel/sidepanel.ts` | Обработка `evaluation_started` и `evaluation_result` в `handleWsMessage()`, рендер сводки в Phase 4, сохранение в `chrome.storage.local` |
| `extension/src/sidepanel/sidepanel.css` | Стили блока сводки оценки |
| `extension/src/sidepanel/sidepanel.html` | Контейнер для блока оценки |
| `extension/src/background/service-worker.ts` | Прокидывание `evaluation_result`, `evaluation_started`, `evaluation_error` из WS в Side Panel port; буферизация `lastEvaluationResult` для replay при reconnect (аналогично `lastHintEnd`) |
| `backend/session/manager.py` | `add_utterance()` пишет в два Redis-ключа (см. сниппет ниже) |
| `extension/manifest.json` | Добавить `report.html` и `evaluation-settings.html` в `web_accessible_resources` (если требуется) |

### 4.4 Критичные сниппеты реализации

**main.py — замена `session_end` → `break`:**

```python
# Было:
elif msg_type == "session_end":
    break

# Стало:
elif msg_type == "session_end":
    await ws.send_json({"type": "evaluation_started", "session_id": session_id})
    await orchestrator.on_session_end(session_id, ws)
    break

# В finally-блоке — ПОСЛЕ teardown():
finally:
    await orchestrator.teardown()  # отменяет hint tasks, НЕ evaluation
    if orchestrator._evaluation_task is not None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(orchestrator._evaluation_task, timeout=35.0)
    # ... остальной cleanup
```

**orchestrator.py — on_session_end():**

```python
class PipelineOrchestrator:
    def __init__(self, ...):
        ...
        self._evaluation_task: asyncio.Task | None = None
        self._evaluation_started: bool = False

    async def on_session_end(self, session_id: str, ws: WebSocket) -> None:
        if self._evaluation_started:
            return
        self._evaluation_started = True
        # Запускаем как отдельный Task (НЕ в self._background_tasks)
        self._evaluation_task = asyncio.create_task(
            self._run_evaluation(session_id, ws)
        )

    async def _run_evaluation(self, session_id: str, ws: WebSocket) -> None:
        try:
            transcript = await self._redis.lrange(
                f"eval_transcript:{session_id}", 0, 3999  # upper bound guard
            )
            if not transcript:
                await ws.send_json({"type": "evaluation_error", ...})
                return
            config = await self._load_eval_config()
            result = await self._evaluator.evaluate_call(transcript, config, ...)
            await self._save_and_send(session_id, result, ws)
        except Exception as e:
            logger.exception("Evaluation failed")
            with contextlib.suppress(Exception):
                await ws.send_json({"type": "evaluation_error", ...})

    def teardown(self) -> None:
        # Отменяем ТОЛЬКО hint-related tasks
        for task in self._background_tasks:
            task.cancel()
        # НЕ трогаем self._evaluation_task
```

**session/manager.py — dual-write:**

```python
async def add_utterance(self, session_id: str, utterance: str) -> None:
    utter_key = self._utter_key(session_id)           # session:{sid}:utterances
    eval_key = f"eval_transcript:{session_id}"         # полный лог для оценки

    pipe = self._redis.pipeline()
    pipe.rpush(utter_key, utterance)
    pipe.ltrim(utter_key, -_MAX_UTTERANCES, -1)        # лимит 10 для hint summary
    pipe.rpush(eval_key, utterance)                     # БЕЗ ltrim
    pipe.expire(eval_key, 86400)                        # TTL 24h
    await pipe.execute()
```

## 5. SGR-схемы (Pydantic)

### 5.1 Конфигурация критериев

```python
from pydantic import BaseModel, Field
from typing import Annotated, Literal

class EvaluationCriterion(BaseModel):
    """Один критерий оценки звонка."""
    id: str = Field(description="Уникальный идентификатор: greeting, needs_discovery и т.д.")
    name: str = Field(description="Название критерия на русском")
    description: str = Field(description="Подробное описание что именно оценивается")
    weight: float = Field(ge=0.0, le=1.0, description="Вес критерия (0.0–1.0, сумма всех = 1.0)")
    # scale_max убран — фиксирован на 10 для демо (упрощает валидацию и промпт)

class EvaluationConfig(BaseModel):
    """Конфигурация оценки — хранится в Redis, редактируется через UI."""
    criteria: Annotated[list[EvaluationCriterion], Field(min_length=1, max_length=10)]
    model: str = Field(default="google/gemini-2.5-flash")

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "EvaluationConfig":
        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Сумма весов критериев должна быть 1.0, получено: {total:.2f}")
        return self
```

### 5.2 Результат оценки (SGR Cascade)

Порядок полей критичен — определяет порядок мышления LLM:

```python
class CriterionResult(BaseModel):
    """Оценка одного критерия. Cascade: reasoning → score → comment → recommendations."""
    criterion_id: str
    criterion_name: str
    reasoning: str = Field(description="Анализ транскрипта по данному критерию — ДО выставления оценки")
    score: int = Field(ge=1, le=10, description="Оценка 1-10, выставляется ПОСЛЕ анализа")
    comment: str = Field(description="Краткий вывод для отображения в UI (1-2 предложения)")
    recommendations: list[str] = Field(
        min_length=1, max_length=3,
        description="Конкретные рекомендации по улучшению (1-3 пункта)"
    )

class CallEvaluation(BaseModel):
    """Полная оценка звонка. Cascade: summary → criteria → overall → verdict → growth."""
    call_summary: str = Field(description="Краткое резюме разговора (3-5 предложений)")
    criteria_results: list[CriterionResult] = Field(description="Оценка по каждому критерию")
    overall_score: float = Field(ge=1.0, le=10.0, description="Вычисляется на бэкенде, НЕ доверяется LLM")
    verdict: Literal["excellent", "good", "satisfactory", "needs_improvement"] = Field(
        description="Вычисляется на бэкенде по overall_score: 8+=excellent, 6-7.9=good, 4-5.9=satisfactory, <4=needs_improvement"
    )
    strengths: list[str] = Field(
        min_length=2, max_length=4,
        description="Сильные стороны менеджера в этом звонке"
    )
    growth_areas: list[str] = Field(
        min_length=2, max_length=4,
        description="Зоны роста — что менеджер может улучшить"
    )
    action_plan: list[str] = Field(
        min_length=3, max_length=5,
        description="Конкретные шаги для развития навыков"
    )
```

### 5.3 Паттерн SGR Cascade

Ключевой принцип: структура Pydantic-модели **программирует** порядок мышления LLM.

1. `call_summary` — модель сначала резюмирует разговор (разогрев контекста)
2. `criteria_results[]` — для каждого критерия:
   - `reasoning` — анализ ПЕРЕД оценкой (Chain of Thought внутри JSON)
   - `score` — оценка ПОСЛЕ анализа (constrained decoding гарантирует 1-10)
   - `recommendations` — конкретные советы
3. `overall_score` — **вычисляется на бэкенде** как `sum(score * weight)`, не доверяется LLM
4. `verdict` — вычисляется на бэкенде по `overall_score`
5. `strengths` / `growth_areas` / `action_plan` — синтез после полного анализа (генерирует LLM)

Constrained decoding (response_format=json_schema) отсекает токены, не соответствующие схеме, на этапе сэмплинга.

### 5.4 EvaluatorLLMClient (отдельный от hint-клиента)

Существующий `LLMClient` (llm.py) — streaming-only с 1-5s timeout, заточен под подсказки. Для оценки нужен отдельный клиент:

```python
class EvaluatorLLMClient:
    """НЕ-стриминговый LLM-клиент для оценки звонков."""

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    PRIMARY_MODEL = "google/gemini-2.5-flash"
    PRIMARY_TIMEOUT_S = 15.0
    FALLBACK_MODEL = "openai/gpt-4.1-mini"
    FALLBACK_TIMEOUT_S = 30.0

    async def evaluate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        """Один блокирующий вызов с response_format=json_schema.
        Primary model: 15s timeout. При timeout → fallback model: 30s timeout.
        """
        try:
            return await self._call_llm(
                self.PRIMARY_MODEL, system_prompt, user_prompt,
                json_schema, self.PRIMARY_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("Primary model timeout, switching to fallback")
            return await self._call_llm(
                self.FALLBACK_MODEL, system_prompt, user_prompt,
                json_schema, self.FALLBACK_TIMEOUT_S,
            )

    async def _call_llm(self, model, system_prompt, user_prompt, json_schema, timeout_s):
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "CallEvaluation", "schema": json_schema}
                },
                stream=False,
            ),
            timeout=timeout_s,
        )
        return json.loads(response.choices[0].message.content)
```

**Отличия от LLMClient (hint):**
- `stream=False` (не стриминг)
- `response_format=json_schema` (constrained decoding)
- Primary timeout 15s → fallback timeout 30s (вместо 1-5s у hint-клиента)
- Нет `_cancel_current()` — один вызов, один ответ
- Fallback: если primary model не поддерживает structured output → `openai/gpt-4.1-mini`

## 6. LLM-промпт

### 6.1 System prompt

```
Ты — опытный руководитель отдела продаж (РОП) с 10+ годами опыта в B2B-продажах.
Твоя задача — оценить качество телефонного разговора менеджера по продажам.

Правила оценки:
- Анализируй ТОЛЬКО то, что есть в транскрипте. Не додумывай.
- Для каждого критерия СНАЧАЛА проведи анализ (reasoning), ПОТОМ выставляй оценку.
- Оценка 1-10: 1-3 = плохо, 4-5 = ниже среднего, 6-7 = хорошо, 8-9 = отлично, 10 = идеально.
- Рекомендации должны быть конкретными и actionable, не общими фразами.
- Если критерий неприменим к данному звонку (например, не было возражений),
  поставь 5 и укажи в reasoning что оценка нейтральная.
- Учитывай брифинг: оценивай насколько менеджер следовал подготовленной стратегии.
- Все ответы на русском языке.

Бенчмарки (данные Gong, 519K+ звонков):
- Оптимальное соотношение говорит/слушает: 43%/57%
- Оптимальное количество выявленных проблем: 3-4
- Успешные менеджеры делают паузу перед ответом на возражение
- Конкретный next step повышает конверсию в 2.7 раза
```

### 6.2 User prompt template

```
ТРАНСКРИПТ ЗВОНКА:
{transcript}

БРИФИНГ (подготовка к звонку):
{briefing}

КРИТЕРИИ ОЦЕНКИ:
{criteria_list}

Оцени звонок по каждому критерию. Ответ — ТОЛЬКО валидный JSON по схеме CallEvaluation.
```

Где `{criteria_list}` формируется динамически из EvaluationConfig:
```
1. Приветствие и установление контакта (вес: 10%) — Представление, настрой, agenda-setting...
2. Выявление потребностей (вес: 25%) — Открытые вопросы, глубина...
...
```

## 7. Дефолтные критерии

Загружаются при первом запуске, пользователь может изменить через настройки.

| id | name | description | weight |
|----|------|-------------|--------|
| `greeting` | Приветствие и установление контакта | Менеджер представился (имя, компания), озвучил цель звонка, согласовал повестку, обращается к клиенту по имени, создал позитивный настрой | 0.10 |
| `needs_discovery` | Выявление потребностей | Задавал открытые вопросы, выявил 3-4 проблемы/потребности, соотношение говорит/слушает близко к 43/57, активное слушание (перефразирование, уточнения) | 0.25 |
| `value_presentation` | Презентация ценности | Привязал решение к выявленным потребностям (не шаблонная презентация), говорил о выгодах а не характеристиках, использовал цифры и кейсы | 0.15 |
| `objection_handling` | Работа с возражениями | Выслушал возражение полностью, сделал паузу, признал точку зрения клиента, привёл аргумент с доказательствами, проверил снято ли возражение | 0.20 |
| `closing` | Закрытие и следующие шаги | Предложил конкретный следующий шаг с привязкой ко времени, зафиксировал взаимные обязательства, подвёл итог разговора | 0.15 |
| `communication` | Коммуникативные навыки | Ясная речь, подходящий темп, эмпатия (отражение эмоций клиента), уверенность без высокомерия, адаптация к стилю собеседника | 0.10 |
| `strategy_adherence` | Следование стратегии | Использовал тезисы из брифинга, работал по портрету клиента, применял подготовленные ответы на возражения, упоминал ключевые факты | 0.05 |

## 8. API эндпоинты

Регистрация: `app.include_router(evaluation_router, prefix="/api/v1")` в `backend/main.py`.

```
GET  /api/v1/evaluation-config            → EvaluationConfig
PUT  /api/v1/evaluation-config            ← EvaluationConfig (сохранить)
POST /api/v1/evaluation-config/reset      → EvaluationConfig (сбросить на дефолт)
GET  /api/v1/evaluation/{session_id}      → CallEvaluation (требует ?token=...)
```

### Аутентификация evaluation endpoint

`GET /api/v1/evaluation/{session_id}` требует query-параметр `token`:
- Токен генерируется через `secrets.token_urlsafe(16)` (128-bit entropy): `eval_token:{session_id}` в Redis (TTL 24h, совпадает с TTL результата)
- Токен отправляется клиенту в `evaluation_result` WebSocket-сообщении
- Клиент сохраняет токен в `chrome.storage.local` и передаёт при открытии report.html
- При невалидном/отсутствующем токене → HTTP 403

## 9. WebSocket-сообщения

### Новый тип: `evaluation_result`

```json
{
  "type": "evaluation_result",
  "session_id": "abc-123",
  "eval_token": "a1b2c3d4e5",
  "evaluation": {
    "call_summary": "...",
    "criteria_results": [...],
    "overall_score": 7.2,
    "verdict": "good",
    "strengths": [...],
    "growth_areas": [...],
    "action_plan": [...]
  }
}
```

### Новый тип: `evaluation_started`

```json
{
  "type": "evaluation_started",
  "session_id": "abc-123"
}
```

Отправляется сразу при запуске оценки — extension показывает индикатор загрузки.

### Новый тип: `evaluation_error`

```json
{
  "type": "evaluation_error",
  "session_id": "abc-123",
  "code": "EVAL_LLM_TIMEOUT",
  "message": "Не удалось оценить звонок"
}
```

### TypeScript-типы (extension/src/shared/messages.ts)

```typescript
interface CriterionResultWire {
  criterion_id: string;
  criterion_name: string;
  reasoning: string;    // Chain of Thought — отображается только в полном отчёте
  score: number;
  comment: string;
  recommendations: string[];
}

interface CallEvaluationResult {
  call_summary: string;
  criteria_results: CriterionResultWire[];
  overall_score: number;
  verdict: "excellent" | "good" | "satisfactory" | "needs_improvement";
  strengths: string[];
  growth_areas: string[];
  action_plan: string[];
}

interface WsEvaluationStarted {
  type: "evaluation_started";
  session_id: string;
}

interface WsEvaluationResult {
  type: "evaluation_result";
  session_id: string;
  eval_token: string;
  evaluation: CallEvaluationResult;
}

interface WsEvaluationError {
  type: "evaluation_error";
  session_id: string;
  code: string;
  message: string;
}

// Добавить в union WsMessage:
// | WsEvaluationStarted | WsEvaluationResult | WsEvaluationError
```

## 10. UI: Страница настроек критериев

**Путь:** `extension/src/settings/evaluation-settings.html`
**Открытие:** из Side Panel → иконка шестерёнки или пункт меню

### Компоненты

1. **Заголовок:** "Критерии оценки звонков" + кнопка "Сбросить на стандартные"
2. **Список критериев:** drag-and-drop карточки
   - Drag handle (⠿) слева
   - Название (редактируемое поле)
   - Описание (textarea, collapsed по дефолту, expand по клику)
   - Вес: slider (0–50%) + number input
   - Кнопка удаления (🗑) с confirm
3. **Кнопка "Добавить критерий":** раскрывает пустую карточку
4. **Валидация:**
   - Сумма весов ≠ 100% → подсветка красным + сообщение
   - Пустое название → подсветка
   - Минимум 1 критерий
5. **Футер:** общая сумма весов (визуально) + кнопка "Сохранить"

### Визуальный стиль (Premium Dark)

- Фон: `#0a0a0f` (body), `#12121a` (карточки)
- Акцент: градиент `#6366f1 → #8b5cf6` (indigo → violet)
- Карточки: `border-radius: 16px`, `backdrop-filter: blur(12px)`, `border: 1px solid rgba(255,255,255,0.06)`
- Тени: `0 4px 24px rgba(0,0,0,0.4)`
- Slider: кастомный с градиентным заполнением
- Анимации: `transition: all 0.3s ease`, fade-in при добавлении, slide-out при удалении
- Типографика: `Inter` / `-apple-system`, заголовки 18-24px, body 14px
- Кнопка "Сохранить": градиентный фон, hover glow-эффект

## 11. UI: Краткая сводка в Phase 4 (Side Panel)

### Компоненты

Появляется под транскриптом в Phase 4 после получения `evaluation_result`:

1. **Общий балл:** круговой gauge (SVG arc), цвет по вердикту:
   - Зелёный (#22c55e): excellent (8+)
   - Синий (#3b82f6): good (6-7.9)
   - Оранжевый (#f59e0b): satisfactory (4-5.9)
   - Красный (#ef4444): needs_improvement (<4)
2. **Вердикт:** текст ("Отлично", "Хорошо", "Удовлетворительно", "Требует внимания")
3. **Мини-бары:** горизонтальные прогресс-бары по каждому критерию (название + score/10)
4. **Кнопка "Подробный отчёт":** открывает report.html в новой вкладке

### Состояние загрузки

При получении `evaluation_started`:
- Пульсирующий skeleton-блок
- Текст: "Оцениваем звонок..."

## 12. UI: Полная страница отчёта

**Путь:** `extension/src/report/report.html`
**Открытие:** `chrome.tabs.create({ url: "report.html?session_id=..." })`

### Инициализация report.ts

```typescript
// 1. Читаем session_id из URL
const sessionId = new URLSearchParams(location.search).get("session_id");

// 2. Читаем backendUrl и eval_token из chrome.storage.local
const { backendUrl, [`eval_token_${sessionId}`]: token } =
  await chrome.storage.local.get(["backendUrl", `eval_token_${sessionId}`]);
const API_BASE = backendUrl || "http://localhost:8000";

// 3. Fetch evaluation
const resp = await fetch(`${API_BASE}/api/v1/evaluation/${sessionId}?token=${token}`);
const evaluation: CallEvaluation = await resp.json();
```

### Структура (top → bottom)

1. **Шапка**
   - Логотип + "Отчёт об оценке звонка"
   - Дата и время звонка
   - Длительность
   - Общий балл (крупно, 72px+) + вердикт-бейдж

2. **Резюме разговора**
   - Текст call_summary в карточке

3. **Скоркард по критериям**
   - Карточка на каждый критерий:
     - Название + балл (прогресс-бар + число)
     - Комментарий РОПа
     - Блок "Рекомендации" (список с иконками 💡)

4. **Сильные стороны**
   - Карточка с зелёной боковой полосой
   - Список пунктов с галочками (✓)

5. **Зоны роста**
   - Карточка с оранжевой боковой полосой
   - Список пунктов с стрелками (↑)

6. **План действий**
   - Карточка с фиолетовой боковой полосой
   - Нумерованный список конкретных шагов

7. **Футер**
   - Кнопка "Скопировать как текст"
   - Мелким шрифтом: "Оценка сгенерирована автоматически"

### Визуальный стиль

Идентичен странице настроек (единый design system): Premium Dark, glass-morphism карточки, градиентные акценты.

## 13. Хранение

### 13.1 Redis (backend)

| Ключ | Тип | TTL | Описание |
|------|-----|-----|----------|
| `eval_config:default` | JSON (EvaluationConfig) | — | Конфигурация критериев |
| `eval_transcript:{session_id}` | Redis List (строки) | 24h | **Полный** список utterances для оценки (без лимита в 10, в отличие от `session:{session_id}`) |
| `eval:{session_id}` | JSON (CallEvaluation) | 24h | Результат оценки |
| `eval_token:{session_id}` | string | 24h | Токен доступа к результату оценки (`secrets.token_urlsafe(16)`) |

**ВАЖНО:** `SessionManager.add_utterance()` пишет в два ключа параллельно:
1. `session:{session_id}` — обрезается до 10 последних (для hint pipeline summary)
2. `eval_transcript:{session_id}` — **не обрезается** (для оценки полного звонка)

### 13.2 chrome.storage.local (extension)

| Ключ | Тип | Описание |
|------|-----|----------|
| `eval_token_{sessionId}` | string | Токен для доступа к API оценки (получен из WS evaluation_result) |
| `eval_result_{sessionId}` | JSON (CallEvaluationResult) | Кеш результата оценки (для recovery при reconnect) |
| `backendUrl` | string | URL бэкенда (уже существует) |

## 14. Обработка ошибок

| Ситуация | Поведение |
|----------|-----------|
| LLM вернул невалидный JSON | Reparse: повторный вызов с ошибкой в промпте (1 попытка) |
| LLM primary timeout (>15 секунд) | Fallback на `openai/gpt-4.1-mini` с timeout 30s |
| Оба LLM недоступны | WebSocket: `type="evaluation_error"`, UI показывает "Не удалось оценить" |
| Пустой транскрипт | Не запускать оценку, отправить `evaluation_error` |
| Сумма весов ≠ 1.0 | Нормализация на бэкенде перед подстановкой в промпт |
| `eval_config:default` не найден в Redis | Загрузить `DEFAULT_CRITERIA` (hardcoded в `evaluation_schemas.py`) |
| Двойной session_end (reconnect race) | Idempotency guard: `self._evaluation_started` flag в orchestrator |
| Транскрипт > 12K токенов | Обрезка: первые 4K + последние 8K токенов (начало + конец). Оценка токенов по формуле len(text)//4 (приблизительная) |
| WebSocket disconnected до прихода evaluation_result | **Механизм recovery:** (1) SW буферизует `lastEvaluationResult` аналогично `lastHintEnd`; (2) при reconnect панели SW отправляет буферизованный результат в `GET_SESSION_STATE` ответе; (3) дополнительно sidepanel проверяет `chrome.storage.local` ключ `eval_result_{sessionId}` |
| Evaluation приходит когда user ушёл из Phase 4 | Side Panel **всегда** сохраняет evaluation в `chrome.storage.local` при получении; при возврате в Phase 4 — рендерит из storage |
| Reparse validation error | Промпт: "Предыдущий JSON не прошёл валидацию: {error}. Исправь: 1) проверь типы, 2) проверь обязательные поля, 3) верни ТОЛЬКО JSON." |

### Коды ошибок (evaluation_error.code)

| Код | Когда |
|-----|-------|
| `EVAL_EMPTY_TRANSCRIPT` | Транскрипт пуст (0 utterances) |
| `EVAL_LLM_TIMEOUT` | Оба LLM (primary + fallback) не ответили |
| `EVAL_LLM_UNAVAILABLE` | Оба LLM вернули ошибку (не timeout) |
| `EVAL_PARSE_FAILED` | JSON невалиден после reparse (2 попытки исчерпаны) |
| `EVAL_INTERNAL_ERROR` | Непредвиденная ошибка в evaluator |

### HTTP-ответы API

| Код | Ситуация |
|-----|----------|
| 200 | Успешный ответ |
| 403 | Невалидный/отсутствующий eval_token |
| 404 | Результат оценки не найден (session_id не существует или TTL истёк) |
| 422 | Невалидный EvaluationConfig (сумма весов ≠ 1.0, пустые поля) |

## 15. Ограничения (для демо)

- Оценка привязана к сессии, нет агрегации по менеджерам
- Критерии общие для всех менеджеров (нет per-user конфигурации)
- Нет экспорта в PDF (только копирование текста)
- Нет сравнения звонков
- Результат оценки хранится 24 часа в Redis
