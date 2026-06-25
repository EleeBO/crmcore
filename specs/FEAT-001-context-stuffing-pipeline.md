# FEAT-001: Context Stuffing Pipeline

Status: ACTIVE
Created: 2026-03-01
Last Modified: 2026-03-01

## Overview

При загрузке файлов (тарифы, прайсы, типовые возражения, заметки о клиенте) AI извлекает текст и сразу генерирует структурированный сценарий разговора: портрет покупателя, стратегию переговоров, ключевые факты с источниками, возражения с ответами. Во время SIP-звонка AI слушает клиента и стримит подсказки на основе сценария и контекста разговора.

Заменяет текущий RAG-стек (embeddings, ChromaDB, BM25) на Context Stuffing — полный текст документов передаётся в LLM для генерации сценария, а сценарий используется как контекст для реал-тайм подсказок.

## Целевой сценарий демо

Это единственный сценарий, который должен работать безупречно. Все инженерные решения подчинены этому пути.

### Шаг 1: Загрузка и подготовка
1. Продавец открывает Chrome Extension
2. Загружает файлы: тарифы (PDF), прайсы (Excel), типовые возражения (TXT/MD), заметки о клиенте (MD/TXT)
3. AI извлекает текст → генерирует полный сценарий разговора
4. На экране появляется готовый playbook: портрет покупателя, стратегия, возражения с ответами, ключевые факты

### Шаг 2: Звонок
1. Продавец открывает Mizugate (Web-SIP) и звонит руководителю
2. Extension захватывает два аудиоканала (микрофон + tab audio)
3. Widget появляется как overlay

### Шаг 3: Реал-тайм поддержка
1. Клиент говорит → STT декодирует → транскрипция отображается в виджете в реальном времени
2. На основе транскрипции AI стримит подсказку
3. Подсказки включают: что ответить, как ответить, ободрения
4. При ошибке продавца — предупреждение
5. При агрессии клиента — рекомендация по тону
6. Продавец видит живую транскрипцию разговора (и свою речь, и клиента)

### Результат демо
Руководство SberCRM видит: загрузил файлы → AI сразу подготовил playbook → во время звонка AI подсказывает в реальном времени. Один непрерывный поток без лишних кнопок.

## Current State

Полностью реализовано. RAG-стек удалён. Context Stuffing пайплайн работает.

### Components

| Компонент | Файл | Описание |
|-----------|------|----------|
| Scenario model | `backend/pipeline/scenario.py` | Pydantic-схема: BuyerPortrait, Strategy, Objection, KeyFact, Scenario |
| Scenario generator | `backend/pipeline/scenario.py` | `generate_scenario(docs_text, api_key, model)` — LLM-генерация из полного текста |
| Upload endpoint | `backend/main.py` | POST /api/v1/upload — parse → join → generate_scenario → Redis |
| Orchestrator | `backend/pipeline/orchestrator.py` | scenario-based hints, transcript forwarding, debounce 500ms |
| LLM prompts | `backend/pipeline/llm.py` | Русские промпты: СЦЕНАРИЙ РАЗГОВОРА + coaching |
| Transcript forwarding | `backend/pipeline/orchestrator.py` | `{type: "transcript", speaker, text, is_final}` → WebSocket |
| WebSocket handler | `backend/main.py` | Загружает scenario из Redis при session_start |
| Briefing endpoint | `backend/briefing/portrait.py` | Читает scenario из Redis, fallback на docs_text |
| Config | `backend/config.py` | `extra="ignore"` для обратной совместимости .env |

### Behavior

#### Upload Flow (новый)
```
POST /api/v1/upload [files + session_id]
  → parse_file() для каждого файла
  → join chunks → docs_text (до 120K chars ≈ 30K tokens)
  → вызвать LLM: generate_scenario(docs_text) → Scenario JSON
  → redis.set(kb:{kb_id}:scenario, scenario_json, ex=7200)
  → return {kb_id, scenario_preview, status}
```

#### Scenario Structure (JSON)
```json
{
  "portrait": {
    "role": "CTO",
    "pain_points": ["..."],
    "motivators": ["..."],
    "budget": "500 000 руб.",
    "communication_style": "консервативный"
  },
  "strategy": {
    "approach": "Акцент на ROI и надёжность",
    "key_messages": ["..."],
    "avoid": ["Не предлагать скидку первым"]
  },
  "objections": [
    {
      "trigger": "дорого",
      "response": "Bitrix24 на 30% дороже при учёте стоимости внедрения",
      "source_file": "competitors.xlsx",
      "source_detail": "строки 15-17"
    }
  ],
  "key_facts": [
    {
      "fact": "Тариф Gold — 500 руб/мес на пользователя",
      "source_file": "tariffs.pdf",
      "source_page": 3
    },
    {
      "fact": "SLA Gold — RTO 15 минут",
      "source_file": "tariffs.pdf",
      "source_page": 5
    }
  ],
  "talking_points": [
    "Упомянуть кейс Газпрома с SAP-интеграцией",
    "Подчеркнуть наличие двух ЦОДов в Казахстане"
  ]
}
```

#### Real-time Pipeline Flow (новый)
```
WebSocket session_start {session_id, kb_id}
  → scenario = redis.get(kb:{kb_id}:scenario)
  → PipelineOrchestrator(ws, session_id, scenario, llm_client, session_manager)

Audio → VAD → STT → transcript
  → WebSocket: {type: "transcript", speaker, text, is_final}  ← НОВОЕ (бэкенд → extension)
  → if final client utterance:
      → build_prompt(scenario, utterance, conversation_history)
      → LLM.generate_hint_stream()
      → WebSocket: hint_start → hint_chunk* → hint_end
```

#### Transcript Forwarding (новое)
Extension уже готов принимать транскрипции:
- `WsTranscript` интерфейс: `{type: "transcript", speaker: string, text: string, is_final: boolean}` — `extension/src/shared/messages.ts:20-25`
- `widget.handleTranscript(text)` показывает текст в `#transcript-bar` — `extension/src/content/widget.ts:416-422`
- Service worker форвардит `TRANSCRIPT` в content scripts — `extension/src/background/service-worker.ts:126`

**Бэкенд НЕ отправляет транскрипции** — нужно добавить `send_json({type: "transcript", ...})` в `orchestrator.handle_transcript()`.
```

#### Hint Prompt Structure (новый)
```
[SYSTEM]
Ты — реал-тайм ассистент продаж для Сбер КИБ.
Генерируй КОРОТКУЮ (1-2 предложения) подсказку для менеджера.
Правила:
  1) Используй ТОЛЬКО факты из СЦЕНАРИЯ. Если факта нет — "Нет верифицированных данных".
  2) Указывай источник факта.
  3) Оценивай настроение клиента: POSITIVE / NEUTRAL / NEGATIVE.
  4) Если менеджер допустил ошибку — WARNING.
  5) Подбадривай менеджера когда он хорошо ответил.
  6) Рекомендуй тон и темп речи.

[СЦЕНАРИЙ] {scenario_json}
[ИСТОРИЯ РАЗГОВОРА] {last_10_utterances}
[КЛИЕНТ ТОЛЬКО ЧТО СКАЗАЛ] {latest_utterance}
```

## Acceptance Criteria

- Given 3 файла (~50 страниц: tariff PDF + competitor Excel + client notes MD) When upload When LLM генерирует сценарий Then сценарий готов за <20 секунд
- Given загружены CRM-заметки о клиенте When AI генерирует сценарий Then портрет покупателя создаётся из заметок (роль, болевые точки, стиль коммуникации)
- Given сценарий сгенерирован и SIP-звонок начат When клиент произносит реплику Then подсказка появляется в виджете менее чем через 2 секунды
- Given 15-минутный демо-звонок When AI генерирует подсказки Then 5+ релевантных подсказок без галлюцинаций
- Given клиент задаёт вопрос, ответа на который нет в документах When AI генерирует подсказку Then AI отвечает "Нет верифицированных данных" (не галлюцинирует)
- Given менеджер назвал неверную цифру (SLA, цена) When AI сравнивает с фактами из сценария Then виджет показывает WARNING красным цветом
- Given SIP-звонок активен When клиент или менеджер говорит Then транскрипция отображается в виджете в реальном времени (interim + final)

## Что удаляется (RAG-стек)

### Файлы на удаление
- `backend/pipeline/rag.py` — HybridSearchEngine, RRF fusion
- `backend/ingestion/embedder.py` — embed_chunks, index_chunks, build_and_save_bm25, load_bm25_index

### Код на удаление из существующих файлов
- `backend/main.py`: ChromaDB init (lifespan), embedding warm-up (lifespan), HybridSearchEngine + load_bm25_index (websocket handler)
- `backend/pipeline/orchestrator.py`: speculative RAG (_start_speculative_rag, _get_rag_results, _cosine), rag_engine из конструктора
- `backend/pipeline/llm.py`: rag_context из HintContext, "RAG context" из промпта
- `backend/briefing/portrait.py`: rag_engine параметр, rag_engine.search()

### Зависимости на удаление из pyproject.toml
- `chromadb`
- `sentence-transformers`
- `rank-bm25`
- `onnxruntime`

### Docker-сервисы на удаление
- `chromadb` сервис из `docker-compose.yml`
- `chroma_data` volume

### Настройки на удаление из config.py
- `chroma_persist_dir`
- `embedding_model`

## Edge Cases

- **LLM timeout при генерации сценария:** Если LLM не ответил за 30 сек — вернуть ошибку с предложением повторить. Сохранить docs_text как fallback.
- **Файл обрезан лимитом:** При MAX_CONTEXT_CHARS=120K последний файл может не влезть. Обрезать по целым файлам, не по символам. Логировать предупреждение.
- **Клиент задаёт вопрос вне базы:** LLM должен честно сказать "нет данных", не галлюцинировать из общих знаний. Системный промпт должен это явно требовать.
- **Быстрая речь клиента:** Несколько финальных транскриптов за 2 сек → debounce на уровне оркестратора (не запускать hint если предыдущий <500мс назад).
- **Добавление файлов после генерации:** Перегенерировать сценарий с новыми файлами (~10 сек). UI показывает "Обновляю сценарий..."
- **Redis недоступен при session_start:** Оркестратор стартует без сценария → отправить предупреждение пользователю {type: "warning", message: "scenario_not_ready"}.
- **Невалидный JSON от LLM:** Pydantic validation при парсинге. При ошибке — retry 1 раз, затем fallback: передавать raw docs_text вместо сценария.

## Change History

### v1 (2026-03-01) — Initial specification
- ADDED: Целевой сценарий демо (загрузка → сценарий → SIP-звонок → подсказки)
- ADDED: Scenario JSON structure с портретом, стратегией, возражениями, ключевыми фактами
- ADDED: Upload и real-time pipeline flows
- ADDED: Acceptance criteria (upload <20s, портрет из заметок, hints <2s)
- ADDED: Полный список файлов/зависимостей/сервисов на удаление (RAG-стек)
- ADDED: Edge cases
- Plan: (pending — use /plan to create)

### v2 (2026-03-01) — Добавлена транскрипция разговора
- ADDED: Транскрипция в реальном времени (interim + final) отображается в виджете
- ADDED: Transcript forwarding из orchestrator → WebSocket → extension
- ADDED: Acceptance criteria для транскрипции
- ADDED: Документация текущего состояния: extension готов (WsTranscript, handleTranscript, #transcript-bar), бэкенд не отправляет
- Plan: [v1](../docs/plans/FEAT-001-context-stuffing-pipeline.md)

### v3 (2026-03-01) — Implementation complete
- ADDED: `backend/pipeline/scenario.py` — Scenario Pydantic model + LLM generator
- MODIFIED: `backend/main.py` — upload generates scenario, WebSocket loads scenario, briefing reads scenario, removed ChromaDB
- MODIFIED: `backend/pipeline/orchestrator.py` — scenario-based hints, transcript forwarding, removed RAG
- MODIFIED: `backend/pipeline/llm.py` — Russian scenario-based prompts, removed rag_context
- MODIFIED: `backend/briefing/portrait.py` — reads scenario from Redis, removed rag_engine
- MODIFIED: `backend/config.py` — removed chroma_persist_dir/embedding_model, added extra="ignore"
- MODIFIED: `docker-compose.yml` — removed chromadb service and volume
- REMOVED: `backend/pipeline/rag.py`, `backend/ingestion/embedder.py`
- REMOVED: `backend/tests/test_rag.py`, `backend/tests/test_embedder.py`
- Plan: [v1](../docs/plans/FEAT-001-context-stuffing-pipeline.md)
