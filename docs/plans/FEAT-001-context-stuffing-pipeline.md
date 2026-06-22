# Context Stuffing Pipeline — Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-01
Status: VERIFIED
Spec: specs/FEAT-001-context-stuffing-pipeline.md

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Заменить RAG-пайплайн (embeddings → ChromaDB → BM25 → hybrid search) на Context Stuffing: при upload LLM генерирует структурированный сценарий из полного текста документов, сценарий используется как контекст для реал-тайм подсказок. Добавить форвард транскрипций в extension.

**Architecture:** Upload синхронно вызывает LLM для генерации Scenario JSON (портрет, стратегия, возражения, ключевые факты с источниками). Scenario хранится в Redis. WebSocket handler загружает scenario при session_start. Orchestrator передаёт scenario + utterance + history в LLM для генерации подсказок. Transcript forwarding отправляет транскрипции обратно в extension через WebSocket.

**Tech Stack:** FastAPI, redis.asyncio, OpenRouter (Gemini 2.5 Flash), Pydantic v2, Deepgram Nova-3

## Scope

### In Scope
- Создание Pydantic-модели Scenario + генератор
- Обновление upload endpoint: parse → join text → LLM → Scenario → Redis
- Переписывание orchestrator: убрать RAG, добавить scenario, добавить transcript forwarding
- Обновление LLM промптов под scenario-based контекст
- Обновление WebSocket handler: загружать scenario из Redis
- Обновление briefing endpoint: читать из scenario в Redis
- Удаление: rag.py, embedder.py, ChromaDB, BM25, зависимости, Docker-сервис
- Обновление всех тестов

### Out of Scope
- Async upload (background task + polling) — для демо используем синхронный вызов
- Feature flag SCENARIO_MODE — удаляем RAG полностью
- Редактирование сценария в UI
- Изменение extension кода (уже готов к transcript forwarding)
- UX-индикатор загрузки в extension во время генерации сценария (~10-15с) — extension UI вне скоупа
- Отображение playbook/scenario в extension после upload — extension UI вне скоупа
- Эмоциональный коучинг (tone_advice) в ответе LLM — добавим в следующей итерации

## Prerequisites
- Redis запущен и доступен
- OpenRouter API key настроен (OPENROUTER_API_KEY)
- Deepgram API key настроен (DEEPGRAM_API_KEY)

## Context for Implementer

- **Upload endpoint** (`backend/main.py:123-218`) уже частично мигрирован — сохраняет docs_text в Redis, НЕ вызывает embed/index. Но scenario ещё не генерируется.
- **WebSocket handler** (`backend/main.py:311-427`) всё ещё использует `load_bm25_index()` и `HybridSearchEngine` — это сломано прямо сейчас (BM25 не строится, ChromaDB пуста).
- **Extension** полностью готов к транскрипциям: `WsTranscript` тип, `handleTranscript()` в widget, service worker форвардит `TRANSCRIPT` — backend просто не отправляет.
- **Промпты** в `llm.py` используют `rag_context` — нужно заменить на `scenario`.
- Все тесты, использующие `embed_chunks`, `index_chunks`, `load_bm25_index`, `mock_chroma` — сломаются при удалении файлов.

## Feature Inventory — Files Being Replaced/Removed

### Files to DELETE

| File | Functions/Classes | Mapped to Task |
|------|-------------------|----------------|
| `backend/pipeline/rag.py` | `SearchResult`, `HybridSearchEngine` (embed_query, search, _chroma_search, _bm25_search), `_rrf_fuse()` | 4.1 |
| `backend/ingestion/embedder.py` | `_get_model()`, `embed_query()`, `embed_chunks()`, `index_chunks()`, `build_and_save_bm25()`, `load_bm25_index()` | 4.1 |
| `backend/tests/test_rag.py` | 5 tests: exact_match, no_match, search_result_objects, rrf_merges, top_k_limits | 4.2 |
| `backend/tests/test_embedder.py` | 7 tests: embed_query, embed_chunks, index_chunks, collection_isolation, bm25_persist, bm25_load, bm25_corrupt | 4.2 |
| `backend/tests/test_edge_cases.py` | 8 tests using `rag_engine=` and `rag.search`/`rag.embed_query` — need `scenario_text=` instead | 4.2 |

### Files to MODIFY

| File | What Changes | Mapped to Task |
|------|-------------|----------------|
| `backend/main.py` | Lifespan: remove ChromaDB + embedding warm-up. Upload: add scenario generation. WebSocket: remove RAG, load scenario. Briefing: read from Redis. Health: remove ChromaDB check. | 2.1, 3.1, 3.2, 4.1 |
| `backend/pipeline/orchestrator.py` | Remove rag_engine, speculative RAG. Add scenario param. Add transcript forwarding. | 2.2 |
| `backend/pipeline/llm.py` | Replace rag_context with scenario in HintContext. Update prompts. | 2.3 |
| `backend/briefing/portrait.py` | Remove rag_engine param, read docs from Redis. | 3.2 |
| `backend/config.py` | Remove chroma_persist_dir, embedding_model. | 4.1 |
| `pyproject.toml` | Verify: chromadb/sentence-transformers/rank-bm25/onnxruntime NOT in deps (confirmed absent). No changes needed. | 4.1 |
| `docker-compose.yml` | Remove chromadb service, chroma_data volume, backend depends_on chromadb. | 4.1 |
| `backend/tests/conftest.py` | Remove mock_chroma fixture, update app_with_mocks, remove chroma_persist_dir from test_settings. | 4.2 |
| `backend/tests/test_upload.py` | Remove embedder patches from all 5 tests. | 4.2 |
| `backend/tests/test_websocket.py` | Remove load_bm25_index patches from all 4 tests. | 4.2 |
| `backend/tests/test_pipeline.py` | Remove mock_rag_engine, delete speculative RAG tests, update orchestrator instantiation. | 4.2 |
| `backend/tests/test_briefing.py` | Remove rag_engine from generate_briefing calls in all 6 tests. | 4.2 |
| `backend/tests/test_health.py` | Update ChromaDB health expectations in 3 tests. | 4.2 |

### Feature Mapping Verification

- [x] All old files listed above
- [x] All functions/classes identified
- [x] Every feature has a task number
- [x] No features accidentally omitted

## Progress Tracking

### 1. Foundation
- [x] 1.1 Create Scenario Pydantic model + LLM generator

### 2. Core Pipeline Rewrite
- [x] 2.1 Update upload endpoint — add scenario generation
- [x] 2.2 Rewrite orchestrator — remove RAG, add scenario, add transcript forwarding
- [x] 2.3 Update LLM prompts — scenario-based HintContext

### 3. Endpoint Integration
- [x] 3.1 Update WebSocket handler — load scenario, remove RAG
- [x] 3.2 Update briefing endpoint — read scenario from Redis

### 4. Cleanup & Tests
- [x] 4.1 Remove RAG files, dependencies, Docker services, config
- [x] 4.2 Fix all tests

**Total Tasks:** 7 | **Completed:** 7 | **Remaining:** 0

## Implementation Tasks

### 1. Foundation

#### 1.1 Create Scenario Pydantic model + LLM generator

**Objective:** Создать типизированную модель Scenario и функцию генерации сценария из полного текста документов через LLM.

**Files:**
- Create: `backend/pipeline/scenario.py`
- Test: `backend/tests/test_scenario.py`

**Implementation Steps:**

1. **Write failing test** — `test_scenario.py`:
   - `test_scenario_model_validates_correct_json()` — проверяет парсинг валидного JSON
   - `test_scenario_model_rejects_invalid_json()` — проверяет ошибку при невалидном
   - `test_generate_scenario_calls_llm()` — мокает LLM, проверяет что генератор вызывает API и парсит ответ
   - `test_generate_scenario_retries_on_invalid_json()` — retry 1 раз при невалидном ответе
   - `test_generate_scenario_timeout_returns_empty()` — при asyncio.TimeoutError возвращает пустой Scenario()

2. **Implement `backend/pipeline/scenario.py`:**

   ```python
   from pydantic import BaseModel

   class KeyFact(BaseModel):
       fact: str
       source_file: str
       source_page: int | None = None
       source_detail: str = ""

   class Objection(BaseModel):
       trigger: str
       response: str
       source_file: str = ""
       source_detail: str = ""

   class BuyerPortrait(BaseModel):
       role: str = ""
       pain_points: list[str] = []
       motivators: list[str] = []
       budget: str = ""
       communication_style: str = ""

   class Strategy(BaseModel):
       approach: str = ""
       key_messages: list[str] = []
       avoid: list[str] = []

   class Scenario(BaseModel):
       portrait: BuyerPortrait = BuyerPortrait()
       strategy: Strategy = Strategy()
       objections: list[Objection] = []
       key_facts: list[KeyFact] = []
       talking_points: list[str] = []
   ```

3. **Implement `generate_scenario()` function:**
   - Принимает `docs_text: str`, `api_key: str`, `model: str`
   - Использует `asyncio.wait_for(coro, timeout=30.0)` для таймаута (не raw timeout)
   - Вызывает OpenRouter с системным промптом на русском:
     - "Ты — ИИ-помощник подготовки к переговорам. На основе документов создай структурированный сценарий разговора."
     - "ВАЖНО: Сохраняй все числа, цены, сроки, SLA verbatim — не округляй. Для каждого факта укажи source_file и source_page."
     - "Отвечай ТОЛЬКО валидным JSON по указанной схеме."
   - **JSON Schema в промпте** — включить Pydantic JSON Schema в системный промпт:
     ```python
     schema_json = Scenario.model_json_schema()
     # Добавить в системный промпт: f"Ответь JSON по схеме:\n{json.dumps(schema_json, indent=2, ensure_ascii=False)}"
     ```
   - Парсит ответ через `Scenario.model_validate_json()`
   - При невалидном JSON — retry 1 раз
   - При повторной ошибке — возвращает пустой `Scenario()` с логированием warning
   - При `asyncio.TimeoutError` — логирует error, возвращает пустой `Scenario()`

4. **Verify** — `pytest backend/tests/test_scenario.py`

**Definition of Done:**
- [ ] Scenario model валидирует JSON из спеки
- [ ] generate_scenario вызывает LLM и парсит ответ
- [ ] Retry при невалидном JSON
- [ ] Graceful fallback при полном отказе
- [ ] Тесты проходят

---

### 2. Core Pipeline Rewrite

#### 2.1 Update upload endpoint — add scenario generation

**Objective:** После парсинга файлов вызвать `generate_scenario()` и сохранить результат в Redis вместе с docs_text.

**Files:**
- Modify: `backend/main.py` (upload endpoint, lines 123-218)
- Test: `backend/tests/test_upload.py` (update existing tests)

**Implementation Steps:**

1. **Write failing test:**
   - `test_upload_generates_scenario()` — мокает `generate_scenario`, проверяет что он вызывается с docs_text и результат сохраняется в Redis как `kb:{kb_id}:scenario`
   - `test_upload_returns_scenario_preview()` — проверяет что response содержит `scenario` поле (portrait, strategy)
   - `test_upload_llm_failure_still_saves_docs_text()` — при пустом Scenario() response содержит `scenario_generated: false`, но docs_text сохранён в Redis
   - `test_upload_file_level_truncation()` — при превышении MAX_CONTEXT_CHARS последний файл не обрезается посередине

2. **Modify upload endpoint** (`backend/main.py`):
   - Добавить import: `from backend.pipeline.scenario import generate_scenario, Scenario`
   - **Заменить character-based обрезку на file-level** (line 186):
     ```python
     # File-level truncation (spec requirement: не обрезать файл посередине)
     docs_text = ""
     for chunk in all_chunks:
         if len(docs_text) + len(chunk.text) + 5 > MAX_CONTEXT_CHARS:
             logger.warning("Truncated docs at file level: %d chars, skipping remaining", len(docs_text))
             break
         if docs_text:
             docs_text += "\n\n---\n\n"
         docs_text += chunk.text
     ```
   - **Generate scenario** — после формирования docs_text:
     ```python
     # Generate scenario via LLM
     scenario = await generate_scenario(
         docs_text=docs_text,
         api_key=cfg.openrouter_api_key,
         model=cfg.llm_primary_model,
     )
     scenario_json = scenario.model_dump_json()
     ```
   - **Redis storage** — сохранять docs_text и scenario, логировать warning при Redis=None:
     ```python
     if redis_client is not None:
         await redis_client.set(f"kb:{kb_id}:docs", docs_text.encode(), ex=7200)
         await redis_client.set(f"session:{session_id}:kb_id", kb_id, ex=1800)
         await redis_client.set(f"kb:{kb_id}:scenario", scenario_json.encode(), ex=7200)
     else:
         logger.warning("Redis unavailable — scenario not persisted for kb=%s", kb_id)
     ```
   - **Scenario preview в response** — проверять что scenario не пустой:
     ```python
     scenario_preview = None
     if scenario.key_facts or scenario.objections:
         scenario_preview = {
             "portrait": scenario.portrait.model_dump(),
             "strategy": scenario.strategy.model_dump(),
             "objections_count": len(scenario.objections),
             "key_facts_count": len(scenario.key_facts),
         }
     ```
   - В response JSON:
     ```python
     "scenario": scenario_preview,
     "scenario_generated": scenario_preview is not None,
     ```

3. **Verify** — `pytest backend/tests/test_upload.py`

**Definition of Done:**
- [ ] Upload вызывает generate_scenario с полным текстом
- [ ] Scenario сохраняется в Redis (kb:{kb_id}:scenario, TTL 2h)
- [ ] Response содержит scenario preview (или scenario_generated: false при пустом)
- [ ] docs_text по-прежнему сохраняется в Redis (fallback)
- [ ] File-level truncation: файлы не обрезаются посередине
- [ ] Redis=None: логирует warning, не крашится
- [ ] Тесты проходят

---

#### 2.2 Rewrite orchestrator — remove RAG, add scenario, add transcript forwarding

**Objective:** Убрать speculative RAG и rag_engine из оркестратора. Добавить scenario как параметр. Добавить отправку транскрипций в WebSocket.

**Files:**
- Modify: `backend/pipeline/orchestrator.py`
- Test: `backend/tests/test_pipeline.py` (update existing tests)

**Implementation Steps:**

1. **Write failing test:**
   - `test_orchestrator_accepts_scenario()` — создаёт orchestrator с scenario вместо rag_engine
   - `test_transcript_forwarded_to_websocket()` — проверяет что при handle_transcript отправляется `{type: "transcript", speaker, text, is_final}` в WebSocket
   - `test_pipeline_uses_scenario_in_hint()` — проверяет что HintContext получает scenario_text
   - `test_pipeline_debounce_skips_rapid_hints()` — два handle_transcript подряд (<500мс) — второй hint не генерируется

2. **Rewrite `backend/pipeline/orchestrator.py`:**

   **Конструктор** — заменить `rag_engine` на `scenario_text`, добавить debounce state:
   ```python
   import time

   _HINT_DEBOUNCE_MS = 500  # Не запускать hint если предыдущий <500мс назад

   def __init__(
       self,
       ws: Any,
       session_id: str,
       llm_client: Any,
       session_manager: Any,
       scenario_text: str = "",
       kb_id: str = "",
   ) -> None:
       self._ws = ws
       self._session_id = session_id
       self._llm = llm_client
       self._session = session_manager
       self._scenario_text = scenario_text
       self._kb_id = kb_id or session_id
       self._background_tasks: set[asyncio.Task[None]] = set()
       self._last_hint_time: float = 0.0  # debounce
   ```

   **handle_transcript** — добавить transcript forwarding:
   ```python
   async def handle_transcript(self, transcript: Transcript) -> None:
       # Forward transcript to extension widget
       with contextlib.suppress(Exception):
           await self._ws.send_json({
               "type": "transcript",
               "speaker": transcript.speaker,
               "text": transcript.text,
               "is_final": transcript.is_final,
           })

       if transcript.is_final:
           with contextlib.suppress(Exception):
               await self._session.add_utterance(
                   self._session_id, transcript.speaker, transcript.text
               )
           if transcript.speaker == "client":
               await self._run_pipeline(transcript.text)
   ```

   **_run_pipeline** — убрать RAG, использовать scenario, добавить debounce:
   ```python
   async def _run_pipeline(self, query: str) -> None:
       # Debounce: не запускать hint если предыдущий <500мс назад (быстрая речь)
       now = time.monotonic()
       if now - self._last_hint_time < _HINT_DEBOUNCE_MS / 1000:
           logger.debug("Debounce: skipping hint, last was %dms ago",
                        int((now - self._last_hint_time) * 1000))
           return
       self._last_hint_time = now

       try:
           ctx_data = await self._session.get_context(self._session_id)
           summary = ctx_data.summary
       except Exception:
           summary = ""

       hint_ctx = HintContext(
           utterance=query,
           speaker="client",
           rag_context=[self._scenario_text] if self._scenario_text else [],
           session_summary=summary,
       )

       with contextlib.suppress(Exception):
           await self._stream_hint(hint_ctx)
   ```

   **Удалить полностью:**
   - `_start_speculative_rag()` (lines 83-104)
   - `_get_rag_results()` (lines 106-121)
   - `_cosine()` helper (lines 18-25)
   - `_SPEC_SIMILARITY_THRESHOLD` constant (line 15)
   - Speculative state vars из `__init__` (lines 49-52)

   **teardown** — упростить (убрать spec_task):
   ```python
   async def teardown(self) -> None:
       for task in self._background_tasks:
           if not task.done():
               task.cancel()
       if self._background_tasks:
           await asyncio.gather(*list(self._background_tasks), return_exceptions=True)
   ```

3. **Verify** — `pytest backend/tests/test_pipeline.py`

**Definition of Done:**
- [ ] Orchestrator принимает scenario_text вместо rag_engine
- [ ] Transcript forwarding: каждый transcript → send_json → extension
- [ ] _run_pipeline использует scenario_text в HintContext
- [ ] Debounce: hints не генерируются чаще 500мс
- [ ] Speculative RAG полностью удалён
- [ ] Тесты проходят

---

#### 2.3 Update LLM prompts — scenario-based HintContext

**Objective:** Обновить системный промпт и user template для работы со сценарием вместо RAG-чанков.

**Files:**
- Modify: `backend/pipeline/llm.py` (lines 54-66)
- Test: `backend/tests/test_llm.py` (verify existing tests still pass)

**Implementation Steps:**

1. **Write failing test:**
   - `test_prompt_contains_scenario_section()` — проверяет что собранный промпт содержит "СЦЕНАРИЙ РАЗГОВОРА" вместо "RAG context"

2. **Update prompts in `backend/pipeline/llm.py`:**

   ```python
   _SYSTEM_PROMPT = (
       "Ты — реал-тайм ассистент продаж для Сбер КИБ.\n"
       "Генерируй КОРОТКУЮ (1-2 предложения) подсказку для менеджера.\n"
       "Правила:\n"
       "  1) Используй ТОЛЬКО факты из СЦЕНАРИЯ. Если факта нет — 'Нет верифицированных данных'.\n"
       "  2) Указывай источник факта из сценария.\n"
       "  3) Оценивай настроение клиента: POSITIVE / NEUTRAL / NEGATIVE.\n"
       "  4) Если менеджер допустил ошибку — WARNING.\n"
       "  5) Подбадривай менеджера когда он хорошо ответил.\n"
       "  6) Рекомендуй тон и темп речи.\n"
       "Отвечай ТОЛЬКО валидным JSON."
   )

   _USER_TEMPLATE = (
       "Говорит: {speaker}\n"
       "Реплика: {utterance}\n\n"
       "СЦЕНАРИЙ РАЗГОВОРА:\n{rag_context}\n\n"
       "Контекст сессии: {session_summary}\n\n"
       'Ответь JSON: {{"hint": "...", "source": "файл.pdf, стр. N", '
       '"sentiment": "positive|neutral|negative", "color": "green|blue|red", '
       '"coaching": "опциональный совет по тону/темпу речи"}}'
   )
   ```

   Note: Поле `rag_context` в `HintContext` переименовывать НЕ будем — это потребует обновления слишком многих тестов. Семантика поля меняется (теперь это scenario text), но тип `list[str]` остаётся.

   **HintResponse** — добавить `coaching` поле в `HintResponse.from_json()` (опциональное, default "").

3. **Verify** — `pytest backend/tests/test_llm.py`

**Definition of Done:**
- [ ] Промпт на русском, содержит раздел "СЦЕНАРИЙ РАЗГОВОРА"
- [ ] Правила явно запрещают галлюцинации
- [ ] Существующие тесты LLM по-прежнему проходят
- [ ] Формат ответа JSON сохраняется

---

### 3. Endpoint Integration

#### 3.1 Update WebSocket handler — load scenario, remove RAG

**Objective:** При session_start загружать scenario из Redis и передавать в orchestrator вместо RAG engine.

**Files:**
- Modify: `backend/main.py` (WebSocket handler, lines 311-427)
- Test: `backend/tests/test_websocket.py` (update all 4 tests)

**Implementation Steps:**

1. **Write failing test:**
   - `test_websocket_loads_scenario_from_redis()` — при session_start читает `kb:{kb_id}:scenario` из Redis mock

2. **Modify WebSocket handler** (`backend/main.py:311-427`):

   **Remove imports** (lines 318-322):
   ```python
   # DELETE these lines:
   from backend.ingestion.embedder import load_bm25_index
   from backend.pipeline.rag import HybridSearchEngine
   ```

   **Remove variables** (line 330):
   ```python
   # DELETE:
   chroma_client = getattr(websocket.app.state, "chroma", None)
   ```

   **Replace session_start block** (lines 377-405):
   ```python
   if ctrl_type == "session_start":
       session_id = ctrl.get("session_id", "ws-anon")
       kb_id: str = ctrl.get("kb_id", "")

       # Load scenario from Redis (validate kb_id)
       scenario_text = ""
       if not kb_id:
           logger.warning("session_start without kb_id, no scenario")
       elif redis_client is not None:
           raw = await redis_client.get(f"kb:{kb_id}:scenario")
           if raw:
               scenario_text = raw.decode() if isinstance(raw, bytes) else raw
           else:
               logger.warning("No scenario found for kb=%s", kb_id)

       llm = LLMClient(
           primary_model=cfg.llm_primary_model,
           fallback_model=cfg.llm_fallback_model,
           api_key=cfg.openrouter_api_key,
           primary_timeout_ms=cfg.llm_primary_timeout_ms,
           fallback_timeout_ms=cfg.llm_fallback_timeout_ms,
       )
       session_mgr = SessionManager(redis=redis_client)
       orchestrator = PipelineOrchestrator(
           ws=websocket,
           session_id=session_id,
           llm_client=llm,
           session_manager=session_mgr,
           scenario_text=scenario_text,
           kb_id=kb_id,
       )
       stt.on_transcript = orchestrator.handle_transcript
       await stt.start_session(session_id)
       logger.info("Session started: id=%s kb=%s scenario_len=%d", session_id, kb_id, len(scenario_text))
   ```

3. **Verify** — `pytest backend/tests/test_websocket.py`

**Definition of Done:**
- [ ] WebSocket handler не импортирует rag.py и embedder.py
- [ ] Scenario загружается из Redis при session_start
- [ ] PipelineOrchestrator получает scenario_text
- [ ] Логирует warning при отсутствии сценария
- [ ] Тесты проходят

---

#### 3.2 Update briefing endpoint — read scenario from Redis

**Objective:** Briefing endpoint читает scenario из Redis и возвращает portrait + strategy + objections. Если scenario нет — генерирует по-старому из docs_text.

**Files:**
- Modify: `backend/main.py` (briefing endpoint, lines 241-277)
- Modify: `backend/briefing/portrait.py`
- Test: `backend/tests/test_briefing.py` (update all 6 tests)

**Implementation Steps:**

1. **Write failing test:**
   - `test_briefing_reads_scenario_from_redis()` — Redis содержит scenario JSON, briefing возвращает portrait/strategy/objections из него

2. **Modify `backend/briefing/portrait.py`:**
   - Убрать `rag_engine` из сигнатуры `generate_briefing()`
   - Заменить RAG-поиск на чтение из Redis:
     ```python
     async def generate_briefing(
         kb_id: str,
         session_id: str,
         redis: Any,
         api_key: str,
         model: str,
     ) -> BriefingResponse:
         cache_key = f"briefing:{session_id}:{kb_id}"

         # Check briefing cache
         cached = await redis.get(cache_key)
         if cached:
             try:
                 return _parse_briefing(cached.decode() if isinstance(cached, bytes) else cached)
             except Exception as exc:
                 logger.warning("Failed to decode cached briefing: %s", exc)

         # Try to read scenario from Redis
         scenario_raw = await redis.get(f"kb:{kb_id}:scenario")
         if scenario_raw:
             try:
                 from backend.pipeline.scenario import Scenario
                 scenario = Scenario.model_validate_json(
                     scenario_raw.decode() if isinstance(scenario_raw, bytes) else scenario_raw
                 )
                 return BriefingResponse(
                     portrait=scenario.portrait.model_dump(),
                     strategy=scenario.strategy.model_dump(),
                     objections=[obj.model_dump() for obj in scenario.objections],
                 )
             except Exception as exc:
                 logger.warning("Failed to parse scenario for briefing: %s", exc)

         # Fallback: generate from docs_text
         kb_docs = await redis.get(f"kb:{kb_id}:docs")
         context = kb_docs.decode() if kb_docs else "Документы не найдены."
         prompt = _BRIEFING_TEMPLATE.format(context=context)
         raw = await _call_llm(prompt, api_key=api_key, model=model)

         try:
             await redis.set(cache_key, raw)
             await redis.expire(cache_key, 1800)
         except Exception as exc:
             logger.warning("Failed to cache briefing: %s", exc)

         return _parse_briefing(raw)
     ```

3. **Update briefing endpoint** (`backend/main.py:241-277`):
   - Убрать import `HybridSearchEngine`
   - Убрать создание `rag_engine`
   - Убрать `rag_engine` из вызова `generate_briefing()`
   - Убрать `chroma_client` из scope

4. **Verify** — `pytest backend/tests/test_briefing.py`

**Definition of Done:**
- [ ] Briefing endpoint не использует RAG
- [ ] Если scenario есть в Redis — возвращает данные из него (без LLM вызова)
- [ ] Fallback: генерирует из docs_text если scenario нет
- [ ] portrait.py не принимает rag_engine
- [ ] Тесты проходят

---

### 4. Cleanup & Tests

#### 4.1 Remove RAG files, dependencies, Docker services, config

**Objective:** Удалить все файлы, зависимости, Docker-сервисы и настройки, связанные с RAG/embeddings/ChromaDB.

**Files:**
- Delete: `backend/pipeline/rag.py`
- Delete: `backend/ingestion/embedder.py`
- Modify: `backend/main.py` (lifespan: remove ChromaDB + embedding warm-up; health: remove ChromaDB check)
- Modify: `backend/config.py` (remove chroma_persist_dir, embedding_model)
- Modify: `pyproject.toml` (remove dependencies)
- Modify: `docker-compose.yml` (remove chromadb service)

**Implementation Steps:**

1. **Delete files:**
   - `rm backend/pipeline/rag.py`
   - `rm backend/ingestion/embedder.py`

2. **Modify `backend/main.py` lifespan** (lines 20-68):
   - Remove `import chromadb` (line 24)
   - Remove `import os` (line 22) — if only used for chroma_persist_dir
   - Delete ChromaDB init block (lines 39-48)
   - Delete embedding warm-up block (lines 50-62, including `from backend.ingestion.embedder import _get_model`)
   - Remove `app.state.chroma` references

3. **Modify health endpoint** (`backend/main.py:79-119`):
   - Remove ChromaDB health check entirely
   - Remove `chromadb` from response JSON (or set to "removed")
   - Simplify: only check Redis

4. **Modify `backend/config.py`:**
   - Delete: `chroma_persist_dir: str = "./chroma_data"`
   - Delete: `embedding_model: str = "intfloat/multilingual-e5-base"`

5. **Verify `pyproject.toml`:**
   - CONFIRMED: `chromadb`, `sentence-transformers`, `rank-bm25`, `onnxruntime` are NOT in pyproject.toml dependencies (they were never added there)
   - No changes needed to pyproject.toml for dependency removal

6. **Modify `docker-compose.yml`:**
   - Delete chromadb service block
   - Delete `chroma_data:` from volumes
   - Remove `chromadb` from backend's `depends_on`

7. **Verify:** `grep -r "chromadb\|embedder\|rag\.\|bm25" backend/ --include="*.py"` — не должно быть ссылок на удалённые модули (кроме тестов, которые исправляются в 4.2)

**Definition of Done:**
- [ ] rag.py и embedder.py удалены
- [ ] Нет импортов удалённых модулей в production-коде
- [ ] ChromaDB убрана из lifespan, health, docker-compose
- [ ] pyproject.toml проверен: RAG-зависимости отсутствуют (подтверждено)
- [ ] config.py не содержит chroma/embedding настроек
- [ ] `uv sync` проходит без ошибок

---

#### 4.2 Fix all tests

**Objective:** Обновить/удалить все тесты, ссылающиеся на удалённые модули. Добавить новые тесты для scenario pipeline.

**Files:**
- Delete: `backend/tests/test_rag.py`
- Delete: `backend/tests/test_embedder.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_upload.py`
- Modify: `backend/tests/test_websocket.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_briefing.py`
- Modify: `backend/tests/test_health.py`
- Modify: `backend/tests/test_edge_cases.py`

**Implementation Steps:**

1. **Delete test files:**
   - `rm backend/tests/test_rag.py` (5 tests)
   - `rm backend/tests/test_embedder.py` (7 tests)

2. **Fix `conftest.py`:**
   - Удалить `mock_chroma` fixture (lines 52-71)
   - В `app_with_mocks`: убрать `mock_chroma` из параметров и `app.state.chroma = mock_chroma` (line 84)
   - В `test_settings`: убрать `chroma_persist_dir="/tmp/test_chroma"` (line 24) — поле будет удалено из Settings

3. **Fix `test_upload.py`** (5 tests):
   - Убрать все `patch("backend.ingestion.embedder.*")` — 3 патча в каждом тесте
   - Добавить `patch("backend.pipeline.scenario.generate_scenario")` mock вместо них
   - Добавить assertion: `mock_redis.set` вызывается с `kb:{kb_id}:scenario`

4. **Fix `test_websocket.py`** (4 tests):
   - Убрать `patch("backend.ingestion.embedder.load_bm25_index")` из всех тестов
   - Добавить Redis mock для `redis.get(f"kb:{kb_id}:scenario")` → возвращает scenario JSON
   - Обновить PipelineOrchestrator instantiation (без rag_engine)

5. **Fix `test_pipeline.py`:**
   - Удалить `mock_rag_engine` fixture
   - Удалить тесты: `test_speculative_rag_reuse`, `test_speculative_rag_discard`
   - Обновить оставшиеся тесты: PipelineOrchestrator(scenario_text=...) вместо rag_engine=...
   - Добавить: `test_transcript_sent_to_websocket()` — mock ws, вызвать handle_transcript, assert send_json called with type="transcript"

6. **Fix `test_briefing.py`** (6 tests):
   - Убрать `rag_engine` из вызовов `generate_briefing()`
   - Добавить Redis mock для `redis.get(f"kb:{kb_id}:scenario")`

7. **Fix `test_edge_cases.py`** (8 tests using `rag_engine=` / `rag.search` / `rag.embed_query`):
   - В каждом тесте TestEdgeCases и TestLatency: заменить `rag_engine=rag` на `scenario_text="test scenario"`
   - Удалить все `rag = AsyncMock()` / `rag.search` / `rag.embed_query` моки
   - Убрать assertion `rag.search.call_count` — заменить на проверку что `ws.send_json` вызван (для hint) или что pipeline не крашится
   - Конкретно обновить `PipelineOrchestrator(ws=ws, session_id=..., scenario_text=..., llm_client=llm, session_manager=session)` вместо `rag_engine=rag`

8. **Fix `test_health.py`** (3 tests):
   - `test_health_includes_chromadb_status` — удалить или обновить: ожидать отсутствие chromadb в ответе
   - `test_lifespan_connects_redis_and_chroma` — убрать chromadb assertion
   - `test_lifespan_redis_unavailable` — убрать chromadb mock

8. **Run full suite:** `pytest backend/tests/ -v`

**Definition of Done:**
- [ ] Все тесты проходят: `pytest backend/tests/ -v` → 0 failures
- [ ] Нет imports из удалённых модулей в тестах
- [ ] Новые тесты: scenario model, scenario generation, transcript forwarding
- [ ] test_rag.py и test_embedder.py удалены

---

## Testing Strategy

- **Unit tests:** Scenario model validation, generate_scenario (mocked LLM), transcript forwarding
- **Integration tests:** Upload → scenario in Redis, WebSocket session_start → scenario loaded, briefing → reads scenario
- **Manual verification:**
  1. `uv run uvicorn backend.main:app --port 8001`
  2. Upload файл через curl: `curl -F "files=@test.pdf" -F "session_id=test" localhost:8001/api/v1/upload`
  3. Проверить: ответ содержит scenario, Redis содержит `kb:{id}:scenario`
  4. WebSocket: подключиться, отправить session_start, проверить что transcript приходит
  5. `pytest backend/tests/ -v` — все тесты зелёные

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM timeout при генерации scenario (>30s) | Medium | High — upload зависнет | asyncio.wait_for(30s), при timeout — пустой Scenario(), docs_text сохранён в Redis |
| LLM не возвращает валидный JSON для scenario | Medium | Medium — пустой сценарий | JSON schema в промпте, retry 1 раз, fallback: пустой Scenario() |
| Тесты сломаются каскадно при удалении файлов | High | Medium — CI red | Порядок: сначала новый код (1.1-3.2), потом удаление (4.1), потом фикс тестов (4.2) |
| Transcript forwarding увеличивает трафик WebSocket | Low | Low | Interim transcripts короткие, JSON маленький |
| Scenario не помещается в prompt hint-LLM | Low | Medium — обрезка | MAX_CONTEXT_CHARS=120K ≈ 30K tokens, Gemini Flash 1M context |
| Быстрая речь клиента (>2 final transcripts/2с) | Medium | Low — лишние LLM вызовы | Debounce 500мс в orchestrator |
| Redis=None при upload | Low | High — scenario потерян | Логируем warning, docs_text и scenario генерируются, но не сохраняются |

## Review Fixes Applied
Исправления по результатам ревью (Architect, Backend, Product):
- **[BLOCKER → FIXED]** test_edge_cases.py добавлен в Feature Inventory и Task 4.2
- **[BLOCKER → FIXED]** Upload при LLM failure: сохраняет docs_text, возвращает scenario_generated: false
- **[BLOCKER → FIXED]** pyproject.toml: подтверждено — RAG-зависимости отсутствуют, инструкция обновлена
- **[BLOCKER → OUT OF SCOPE]** UX-индикатор загрузки и playbook в extension — extension UI вне скоупа
- **[MAJOR → FIXED]** asyncio.wait_for(30s) вместо raw timeout в generate_scenario
- **[MAJOR → FIXED]** JSON Schema включена в промпт generate_scenario
- **[MAJOR → FIXED]** File-level truncation вместо character-based обрезки docs_text
- **[MAJOR → FIXED]** kb_id validation в WebSocket session_start
- **[MAJOR → FIXED]** Redis=None warning при upload
- **[MAJOR → OUT OF SCOPE]** Emotional coaching (coaching field) — добавлен в HintResponse как опциональное поле
- **[MINOR → FIXED]** Debounce 500мс в orchestrator
- **[MINOR → FIXED]** conftest.py: chroma_persist_dir удалён из test_settings
- **[MINOR → FIXED]** Embedding warm-up line numbers исправлены

## Open Questions
- Нет открытых вопросов — все решения зафиксированы в спеке и подтверждены пользователем

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
