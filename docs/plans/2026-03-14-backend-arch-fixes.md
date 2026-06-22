# Backend Architecture Fixes — Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-14
Status: COMPLETE
Spec: specs/FEAT-008-backend-arch-fixes.md
Source: docs/architecture-review-2026-03-14.md (findings C2, H1, H2, H3, H4 + agent-discovered bonus fixes)

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Fix critical and high-severity backend architecture findings: extract god function, add storage abstraction, create missing interfaces, separate evaluation logic, fix dependency violations, and address bonus issues (None guard, dead code, DI bypass, _call_llm duplication).

**Architecture:** Incremental refactoring — each task is a self-contained PR that keeps the system working. No behavior changes, only structural improvements. Tests must pass at every step.

**Tech Stack:** Python 3.11, FastAPI, redis.asyncio, Pydantic, pytest

## Scope

### In Scope
- C2: Extract `WebSocketHandler` from `main.py:websocket_endpoint` (281 lines)
- H1: Create `SessionStore` Protocol to abstract raw Redis usage
- H2: Create missing abstract interfaces (LLMClient Protocol, etc.)
- H3: Extract `EvaluationRunner` from `orchestrator.py:_run_evaluation` (170 lines)
- H4: Fix presentation→infrastructure import violations in main.py
- DTO extraction: Move domain types out of infrastructure modules
- Bonus: Redis None guard, dead code cleanup, DI fix, `_call_llm` dedup

### Out of Scope
- Medium/Low priority findings (M1-M7, L1-L4) — deferred to future sprint
- Frontend changes (separate plan)
- New features or behavior changes
- Auth/validation improvements found by agents — specifically: move eval token from query string to Authorization header (FEAT-00X, logged as deferred security task). Add `# TODO(security): move eval token to Authorization header` comment at `api/evaluation.py` query-param line during refactoring.
- Anti-corruption layers between bounded contexts (M5)
- Type generation from Pydantic to TypeScript (M3)

## Prerequisites
- All existing tests pass: `cd backend && python -m pytest`
- ruff and mypy pass: `cd backend && ruff check . && mypy .`
- Redis running locally (for integration tests if any)

## Context for Implementer

### Key patterns in the codebase
- Lazy imports are used extensively in main.py (inside route handlers)
- `app.state.redis` can be `None` if Redis connection fails at startup (lifespan handler sets it to None)
- `PipelineOrchestrator` constructor takes 7+ params, all typed as `Any`
- STTClient is the ONLY existing ABC — at `pipeline/stt.py:59`
- `_call_llm()` is duplicated in `briefing/portrait.py:42` and `summarize/call_summary.py:43`

### File locations
- `backend/main.py` — 696 LOC, fan-out=15, the main god module
- `backend/pipeline/orchestrator.py` — 394 LOC, fan-out=11
- `backend/pipeline/llm.py` — LLMClient class + HintContext/HintResponse DTOs
- `backend/pipeline/stt.py` — STTClient ABC + Transcript DTO + 6 provider classes
- `backend/pipeline/post_call.py` — PostCallProcessor + CallAnalytics/DiarizedUtterance DTOs
- `backend/session/manager.py` — SessionManager with raw Redis
- `backend/api/evaluation.py` — evaluation REST endpoints with raw Redis
- `backend/briefing/portrait.py` — `_call_llm` duplicate #1
- `backend/summarize/call_summary.py` — `_call_llm` duplicate #2

### Redis key patterns (11 patterns across 8 files — no central registry)
```
session:{id}:utterances    → session/manager.py:38     TTL 1800s
session:{id}:summary       → session/manager.py:42     TTL 1800s
session:{id}:kb_id         → main.py:278               TTL 1800s
kb:{id}:docs               → main.py:277               TTL 7200s
kb:{id}:scenario           → main.py:279               TTL 7200s
eval_transcript:{id}       → session/manager.py:54     TTL 86400s
eval_token:{id}            → orchestrator.py:117       TTL 86400s
eval:{id}                  → orchestrator.py:240       TTL 86400s
eval_analytics:{id}        → post_call.py:253          TTL 86400s
eval_config:default        → api/evaluation.py:13      No TTL
briefing:{kb}:{session}    → briefing/portrait.py:97   TTL 1800s
```

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Foundation: Types & Abstractions
- [x] 1.1 Extract shared DTO types to `backend/pipeline/types.py`
- [x] 1.2 Create `SessionStore` Protocol + Redis key registry
- [x] 1.3 Deduplicate `_call_llm` into shared LLM utility

### 2. Core Extractions
- [x] 2.1 Extract `EvaluationRunner` from orchestrator
- [x] 2.2 Extract `WebSocketHandler` from `main.py`

### 3. Interface & Cleanup
- [x] 3.1 Create missing Protocol interfaces + fix `Any` annotations
- [x] 3.2 Fix bonus issues (None guard, dead code, DI bypass)

**Total Tasks:** 7 | **Completed:** 7 | **Remaining:** 0

## Implementation Tasks

### 1. Foundation: Types & Abstractions

#### 1.1 Extract Shared DTO Types to `backend/pipeline/types.py`

**Objective:** Move domain data classes out of infrastructure modules into a dedicated types module. This breaks the coupling where importing a DTO forces importing its infrastructure module's dependencies (gRPC, Redis, httpx).

**Files:**
- Create: `backend/pipeline/types.py`
- Create: `backend/tests/test_types.py`
- Modify: `backend/pipeline/llm.py` (remove HintContext, HintResponse; re-export for backward compat)
- Modify: `backend/pipeline/stt.py` (remove Transcript; re-export for backward compat)
- Modify: `backend/pipeline/post_call.py` (remove CallAnalytics, DiarizedUtterance; re-export for backward compat)
- Modify: `backend/session/manager.py` (remove SessionContext if exists; re-export)
- Modify: all importers of these types (orchestrator.py, prompt_formatter.py, etc.)

**Implementation Steps:**
1. Write test that imports each DTO from `backend.pipeline.types` and verifies fields
2. Create `backend/pipeline/types.py` — move these dataclasses/Pydantic models:
   - `HintContext` (from llm.py:17)
   - `HintResponse` (from llm.py:27) — add `hint: str = Field(max_length=2000)` to enforce MAX_HINT_CHARS limit
   - `Transcript` (from stt.py:45)
   - `CallAnalytics` (from post_call.py:33) — **remove `to_redis_json`/`from_redis_json` methods** (Redis serialization moves to PostCallProcessor)
   - `DiarizedUtterance` (from post_call.py:23)
3. In each source file, replace the class definition with: `from backend.pipeline.types import ClassName` (backward compat re-export)
4. Update all direct importers to import from `backend.pipeline.types` instead
5. Move `to_redis_json`/`from_redis_json` logic into `PostCallProcessor._store_results()` as local helper functions
5b. Add a wire-contract regression test in `test_types.py` that asserts the serialized JSON field names of `CallAnalytics` match the TypeScript `CallAnalyticsWire` interface exactly:
   ```python
   def test_call_analytics_wire_contract():
       expected_keys = {
           'total_duration_s', 'rep_talk_ratio', 'rep_talk_time_s',
           'client_talk_time_s', 'rep_speech_rate_wpm', 'client_speech_rate_wpm',
           'interruptions_by_rep', 'interruptions_by_client',
           'avg_rep_pause_before_response_s', 'rep_word_count', 'client_word_count',
       }
       # Call the new serialization helper and assert field names
       assert set(serialized.keys()) == expected_keys
   ```
6. Run `python -m pytest` to verify no regressions
7. Run `ruff check . && mypy .` to verify no lint/type errors

**Definition of Done:**
- [ ] All DTOs importable from `backend.pipeline.types`
- [ ] Old import paths still work (re-exports in place)
- [ ] `CallAnalytics` no longer has Redis serialization methods
- [ ] Wire-contract test verifies `CallAnalytics` JSON field names match `CallAnalyticsWire` interface
- [ ] JSON serialization field names are byte-for-byte identical to existing `to_redis_json` output
- [ ] All tests pass
- [ ] No ruff/mypy errors

---

#### 1.2 Create `SessionStore` Protocol + Redis Key Registry

**Objective:** Abstract raw Redis behind a typed Protocol. Centralize all 11 Redis key patterns into a single registry module. This addresses H1 (no storage abstraction) and the scattered key problem.

**Files:**
- Create: `backend/storage/__init__.py`
- Create: `backend/storage/keys.py` (key registry)
- Create: `backend/storage/protocol.py` (SessionStore Protocol)
- Create: `backend/storage/redis_store.py` (Redis implementation)
- Create: `backend/tests/test_storage.py`
- Modify: `backend/session/manager.py` (use SessionStore instead of raw Redis)
- Modify: `backend/api/evaluation.py` (use SessionStore instead of raw Redis)
- Modify: `backend/summarize/call_summary.py` (use SessionStore + key registry instead of raw Redis)
- Modify: `backend/briefing/portrait.py` (use SessionStore + key registry instead of raw `redis.get(f"kb:{kb_id}:scenario")`)

**Implementation Steps:**
1. Write tests for the key registry — each function returns the expected key string
2. Create `backend/storage/keys.py`:
   ```python
   def session_utterances(session_id: str) -> str:
       return f"session:{session_id}:utterances"
   def eval_token(session_id: str) -> str:
       return f"eval_token:{session_id}"
   # ... all 11 patterns with TTL constants

   # TTL constants
   SESSION_TTL = 1800
   KB_TTL = 7200
   EVAL_TTL = 86400
   # eval_config:default — intentionally no TTL (admin-controlled persistent config)
   # See FEAT-00X for auth gap on put_config endpoint
   CONFIG_TTL: int | None = None  # Sentinel: no TTL by design
   ```
3. Create `backend/storage/protocol.py`:
   ```python
   class SessionStore(Protocol):
       async def get(self, key: str) -> str | None: ...
       async def set(self, key: str, value: str, ex: int | None = None) -> None: ...
       async def delete(self, key: str) -> None: ...
       async def lrange(self, key: str, start: int, stop: int) -> list[bytes]: ...
       async def rpush(self, key: str, *values: str) -> int: ...
       async def add_utterance(self, session_id: str, speaker: str, text: str) -> None: ...
       async def store_eval_transcript(self, session_id: str, items: list[str], ttl: int) -> None: ...
       # NOTE: session_id, NOT key — RedisStore constructs `eval_transcript:{session_id}` internally
   ```
3b. Create `RedisStore` implementation that internalizes pipeline operations (rpush+ltrim+expire for utterances, delete+rpush+expire for eval transcript) inside `add_utterance` and `store_eval_transcript` methods. This eliminates the need to expose `pipeline()` and keeps all pipeline semantics inside the concrete Redis implementation.
3c. **CRITICAL:** In `_store_results` (and `store_eval_transcript`), use `async with self._redis.pipeline(transaction=True) as pipe:` for the delete+rpush sequence. Without `transaction=True`, the pipeline sends commands individually — connection drop between delete and rpush loses transcript. MULTI/EXEC guarantees atomicity.
4. Create `backend/storage/redis_store.py` — thin wrapper around `redis.asyncio` that implements the Protocol
5. Refactor `session/manager.py` to accept `SessionStore` instead of raw Redis, use key registry functions
6. Refactor `api/evaluation.py` to use key registry functions
6b. Refactor `call_summary.py:generate_summary` to use `SessionStore` and key registry functions instead of raw `redis.lrange`/`redis.get` with inline key strings.
7. Run all tests

**Definition of Done:**
- [ ] All 11 Redis key patterns defined in `storage/keys.py`
- [ ] `SessionStore` Protocol exists with typed methods
- [ ] `session/manager.py` uses SessionStore and key registry
- [ ] `api/evaluation.py` uses key registry
- [ ] `call_summary.py` uses SessionStore and key registry (no raw Redis)
- [ ] `portrait.py` uses SessionStore and key registry (no raw `redis.get` with inline key strings)
- [ ] `store_eval_transcript` accepts `session_id: str` (not `key: str`) — RedisStore constructs key internally
- [ ] `_store_results` uses `pipeline(transaction=True)` for MULTI/EXEC atomicity
- [ ] All tests pass
- [ ] No ruff/mypy errors

---

#### 1.3 Deduplicate `_call_llm` Into Shared LLM Utility

**Objective:** Eliminate byte-for-byte duplicated `_call_llm` functions in `portrait.py` and `call_summary.py`. Create a shared utility that reuses the HTTP client.

**Files:**
- Create: `backend/pipeline/shared_llm.py`
- Create: `backend/tests/test_shared_llm.py`
- Modify: `backend/briefing/portrait.py` (remove `_call_llm`, import shared)
- Modify: `backend/summarize/call_summary.py` (remove `_call_llm`, import shared)

**Implementation Steps:**
1. Write test for the shared `call_llm_simple()` function — mock the OpenAI client, verify it passes prompt/system_prompt/model correctly
2. Create `backend/pipeline/shared_llm.py`:
   ```python
   from openai import AsyncOpenAI

   _OPENROUTER_BASE = "https://openrouter.ai/api/v1"

   async def call_llm_simple(
       prompt: str,
       system_prompt: str,
       api_key: str,
       model: str,
       timeout_s: float = 30.0,
   ) -> str:
       client = AsyncOpenAI(api_key=api_key, base_url=_OPENROUTER_BASE)
       try:
           response = await asyncio.wait_for(
               client.chat.completions.create(
                   model=model,
                   messages=[
                       {"role": "system", "content": system_prompt},
                       {"role": "user", "content": prompt},
                   ],
               ),
               timeout=timeout_s,
           )
           return response.choices[0].message.content or ""
       finally:
           await client.close()
   ```
   Note: The 30s default timeout is a behavior change — the existing `_call_llm` functions have no timeout. For large documents, briefing generation may take longer. Callers can override with `timeout_s=60.0` or higher. The `portrait.py` and `call_summary.py` callers should pass an explicit timeout appropriate for their use case.
3. Replace `_call_llm` in `portrait.py` with import from `shared_llm`
4. Replace `_call_llm` in `call_summary.py` with import from `shared_llm`
5. Run tests for portrait, call_summary, and shared_llm

**Definition of Done:**
- [ ] Single `call_llm_simple` function exists in `shared_llm.py`
- [ ] `portrait.py` and `call_summary.py` import from `shared_llm`
- [ ] No duplicate `_call_llm` functions remain
- [ ] Timeout added (30s default — improvement over no timeout)
- [ ] All tests pass

---

### 2. Core Extractions

#### 2.1 Extract `EvaluationRunner` From Orchestrator

**Objective:** Move the 170-line `_run_evaluation` method (orchestrator.py:124-293) into a dedicated `EvaluationRunner` class. This addresses H3 (feature envy) — evaluation logic is a separate concern from real-time hint generation.

**Files:**
- Create: `backend/pipeline/evaluation_runner.py`
- Create: `backend/tests/test_evaluation_runner.py`
- Modify: `backend/pipeline/orchestrator.py` (remove `_run_evaluation`, delegate to EvaluationRunner)

**Implementation Steps:**
1. Write tests for EvaluationRunner — test the run() method with mocked Redis, WebSocket, and LLM client
1b. Note: `AudioBuffer` (from `pipeline/audio_buffer.py`) is not abstracted in this plan. `EvaluationRunner` directly depends on it. This is an accepted coupling — `AudioBuffer` is a concrete data holder, not an infrastructure service. Document in the module docstring that `AudioBuffer` is a direct dependency.
1c. **DI strategy for `Settings`:** `EvaluationRunner.__init__` receives `settings: Settings` as a constructor parameter. The caller (`WebSocketHandler`) obtains `Settings` from `request.app.state.settings` (FastAPI convention). Do NOT call `get_settings()` inside `EvaluationRunner`. Same applies to `WebSocketHandler.__init__` — receives `settings: Settings` from `request.app.state.settings`.
2. Create `backend/pipeline/evaluation_runner.py`:
   ```python
   class EvaluationRunner:
       def __init__(
           self,
           session_id: str,
           eval_api_key: str,
           scenario_text: str,
           redis: SessionStore | None,  # Use the new Protocol from 1.2
       ) -> None:
           ...

       async def run(
           self,
           ws: WebSocket,
           eval_token: str,
           audio_buffer: AudioBuffer | None = None,
       ) -> None:
           analytics = await self._run_diarization(audio_buffer)
           transcript_raw = await self._load_transcript()
           config = await self._load_config()
           result = await self._evaluate(transcript_raw, config, analytics)
           await self._store_result(result)
           await self._notify(ws, eval_token, result, analytics)
   ```
2b. Add None guard at the top of `EvaluationRunner.run()`: if `self._redis is None`, log warning and send `evaluation_error` message to WebSocket, then return early.
3. Move all lazy imports from `_run_evaluation` to top-level imports in `evaluation_runner.py`
4. Move `get_settings()` call out — pass `enable_post_call_diarization: bool` and `yandex_api_key: str` as constructor params (fixes the DI bypass found by architect agent)
5. Update `PipelineOrchestrator.on_session_end` to construct and spawn `EvaluationRunner`:
   ```python
   async def on_session_end(self, session_id, ws, redis, *, audio_buffer=None) -> str:
       """Returns eval_token (str). Return type is part of the contract with WebSocketHandler."""
       async with self._eval_lock:  # asyncio.Lock — prevents double evaluation on rapid session_end
           if self._evaluation_started:
               return ""
           self._evaluation_started = True
       eval_token = secrets.token_urlsafe(16)
       if redis is not None:  # None guard (bonus fix)
           await redis.set(f"eval_token:{session_id}", eval_token, ex=86400)
       runner = EvaluationRunner(session_id, self._eval_api_key, self._scenario_text, redis, settings=self._settings)
       self._evaluation_task = asyncio.create_task(runner.run(ws, eval_token, audio_buffer))
       return eval_token
   ```
5b. **Return type contract:** `on_session_end() -> str` — always returns `eval_token` (or `""` if already started). The caller (`WebSocketHandler`) sends the token to the client via WebSocket. This is the explicit contract between the two classes.
5c. **asyncio.Lock for `_evaluation_started`:** Add `self._eval_lock = asyncio.Lock()` in `PipelineOrchestrator.__init__`. The lock prevents duplicate evaluations when two `session_end` messages arrive in rapid succession (e.g., WebSocket reconnect race).
5d. **`_evaluation_task` teardown in `WebSocketHandler.finally`:** The `WebSocketHandler._teardown()` method MUST await `self._evaluation_task` with a timeout to prevent silent cancellation on disconnect:
   ```python
   async def _teardown(self) -> None:
       if self._orchestrator and self._orchestrator._evaluation_task:
           try:
               await asyncio.wait_for(self._orchestrator._evaluation_task, timeout=150)
           except asyncio.TimeoutError:
               logger.warning("Evaluation timed out after 150s, cancelling")
               self._orchestrator._evaluation_task.cancel()
           except Exception:
               logger.exception("Evaluation task failed during teardown")
   ```
6. Run all tests

**Definition of Done:**
- [ ] `EvaluationRunner` class exists in `evaluation_runner.py`
- [ ] `_run_evaluation` removed from orchestrator
- [ ] Lazy imports moved to top-level in new module
- [ ] `get_settings()` call removed from orchestrator — params passed via constructor
- [ ] Redis None guard added to `on_session_end`
- [ ] `AudioBuffer` dependency documented in `evaluation_runner.py` module docstring
- [ ] `on_session_end() -> str` return type annotated and documented as contract
- [ ] `asyncio.Lock` guards `_evaluation_started` check-and-set (prevents double evaluation)
- [ ] `WebSocketHandler._teardown()` awaits `_evaluation_task` with 150s timeout
- [ ] `Settings` passed via constructor (DI), not via `get_settings()` runtime call
- [ ] All tests pass

---

#### 2.2 Extract `WebSocketHandler` From `main.py`

**Objective:** Extract the 281-line `websocket_endpoint` function into a `WebSocketHandler` class. This addresses C2 (god function) and H4 (presentation→infrastructure violations). After extraction, `main.py` becomes a thin composition root.

**Files:**
- Create: `backend/ws/__init__.py`
- Create: `backend/ws/handler.py`
- Create: `backend/tests/test_ws_handler.py`
- Modify: `backend/main.py` (replace websocket_endpoint body with 3-line delegation)

**Implementation Steps:**
1. Write test for `WebSocketHandler.run()` — mock WebSocket, verify it accepts connection and enters message loop
2. Create `backend/ws/handler.py`:
   ```python
   class WebSocketHandler:
       def __init__(self, cfg: Settings, redis: SessionStore | None) -> None:
           self._cfg = cfg
           self._redis = redis

       async def run(self, websocket: WebSocket) -> None:
           await websocket.accept()
           try:
               await self._message_loop(websocket)
           finally:
               await self._teardown()

       async def _message_loop(self, ws: WebSocket) -> None: ...
       async def _handle_session_start(self, ws, ctrl: dict) -> None: ...
       async def _handle_session_end(self, ws) -> None: ...
       async def _handle_audio_frame(self, payload: bytes) -> None: ...
       async def _handle_idle_timeout(self, ws) -> None: ...
       async def _teardown(self) -> None: ...
   ```
3. Move all code from `websocket_endpoint` (lines 407-685) into the class methods
4. Move all lazy imports from inside the function to top-level imports in `ws/handler.py`
5. Replace closures (`_on_transcript`, `_on_stt_error`) with handler methods
6. Update `main.py`:
   ```python
   @app.websocket("/ws")
   async def websocket_endpoint(websocket: WebSocket) -> None:
       handler = WebSocketHandler(settings=app.state.settings, redis=app.state.redis)
       await handler.run(websocket)
   ```
7. Also extract HTTP route handlers to separate router files:
   - `backend/api/health.py` — `/health`, `/preflight`
   - `backend/api/upload.py` — `/upload`
   - `backend/api/session.py` — `/session/{id}` DELETE
   - `backend/api/briefing.py` — `/briefing`
   - `backend/api/summarize.py` — `/summarize`
8. Keep `main.py` as a ~50 line composition root: app factory + router registration + lifespan
9. Run all tests

**Definition of Done:**
- [ ] `WebSocketHandler` class exists in `ws/handler.py`
- [ ] `main.py` websocket route is 3 lines
- [ ] HTTP routes extracted to `api/*.py` router modules
- [ ] `main.py` is ≤100 LOC (composition root only)
- [ ] No lazy imports inside functions (all moved to module level)
- [ ] All existing HTTP URL paths preserved — verified by `curl http://localhost:8000/health` and `curl http://localhost:8000/api/v1/evaluation-config`
- [ ] No double-prefix in route paths (verify router `prefix=` + individual `@router.get/post` paths don't duplicate segments)
- [ ] All tests pass
- [ ] No ruff/mypy errors

---

### 3. Interface & Cleanup

#### 3.1 Create Missing Protocol Interfaces + Fix `Any` Annotations

**Objective:** Create the 4 missing abstract interfaces identified in H2. Replace all 9 `Any` annotations in PipelineOrchestrator with proper types. This enables swapping implementations and testing with mocks.

**Files:**
- Create: `backend/pipeline/protocols.py` (all Protocol definitions)
- Create: `backend/tests/test_protocols.py`
- Modify: `backend/pipeline/orchestrator.py` (replace `Any` with Protocol types)
- Modify: `backend/pipeline/llm.py` (LLMClient implements Protocol)

**Implementation Steps:**
1. Write tests verifying each concrete class satisfies its Protocol (using `isinstance` with `runtime_checkable`)
2. Create `backend/pipeline/protocols.py`:
   ```python
   from typing import Protocol, runtime_checkable

   @runtime_checkable
   class LLMClientProtocol(Protocol):
       async def generate_hint_stream(self, context: HintContext) -> AsyncIterator[str]: ...

   @runtime_checkable
   class SessionManagerProtocol(Protocol):
       async def add_utterance(self, session_id: str, speaker: str, text: str, ...) -> None: ...
       async def get_summary(self, session_id: str) -> str: ...

   @runtime_checkable
   class AsyncRecognizerProtocol(Protocol):
       async def recognize(self, audio_data: bytes, ...) -> list[str]: ...

   @runtime_checkable
   class DocumentParserProtocol(Protocol):
       def parse(self, content: bytes, filename: str) -> list[ParsedChunk]: ...
   ```
3. Update `PipelineOrchestrator.__init__` signature:
   - `ws: Any` → `ws: WebSocket`
   - `llm_client: Any` → `llm_client: LLMClientProtocol`
   - `session_manager: Any` → `session_manager: SessionManagerProtocol`
4. Update `on_session_end` and method signatures similarly
5. Run mypy to verify type correctness
6. Run all tests

**Definition of Done:**
- [ ] `LLMClientProtocol`, `SessionManagerProtocol`, `AsyncRecognizerProtocol`, `DocumentParserProtocol` defined
- [ ] All Protocols are `runtime_checkable`
- [ ] `PipelineOrchestrator` has zero `Any` annotations
- [ ] Concrete classes satisfy their Protocols (verified by tests)
- [ ] All tests pass
- [ ] mypy passes with no errors

---

#### 3.2 Fix Bonus Issues (None Guard, Dead Code, DI Bypass)

**Objective:** Address agent-discovered issues that don't fit in other tasks: Redis None guard in orchestrator, unused `_background_tasks` set, `get_settings()` runtime call bypass.

**Files:**
- Modify: `backend/pipeline/orchestrator.py`
- Create: `backend/tests/test_orchestrator_edge_cases.py`

**Implementation Steps:**
1. Write test: `on_session_end` with `redis=None` should return empty string without raising
2. Write test: `_background_tasks` done callback removes completed tasks
3. Fix None guard at `orchestrator.py:117`:
   ```python
   if redis is None:
       logger.warning("Redis unavailable, skipping evaluation for session %s", session_id)
       return ""
   ```
   Note: Task 2.1 adds a None guard inside `EvaluationRunner.run()`. This task adds a guard at the `on_session_end` call site as a defense-in-depth layer — both guards must exist.
3b. Add None guard to `call_summary.py:generate_summary`: `if redis is None: raise HTTPException(status_code=503, detail='Storage unavailable')`
4. Fix `_background_tasks` — either:
   - Add done callback: `task.add_done_callback(self._background_tasks.discard)` if tasks are spawned
   - Remove `_background_tasks` entirely if no tasks are ever added (dead code)
5. Verify `get_settings()` DI bypass is already fixed by task 2.1 (EvaluationRunner extraction)
6. Run all tests

**Definition of Done:**
- [ ] `on_session_end` handles `redis=None` gracefully
- [ ] `_background_tasks` either properly cleaned up or removed
- [ ] No `get_settings()` call inside orchestrator (already fixed by 2.1)
- [ ] All tests pass
- [ ] No ruff/mypy errors

---

## Testing Strategy

- **Unit tests:** Each new module (types.py, storage/, shared_llm.py, evaluation_runner.py, ws/handler.py, protocols.py) gets its own test file
- **Integration tests:** Run existing test suite after each task — no regressions allowed
- **Manual verification:** After task 2.2, start the backend with `uvicorn backend.main:create_app --factory` and verify WebSocket connection works

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Import cycle after DTO extraction | Medium | Medium | Re-exports preserve backward compat; update imports incrementally |
| WebSocket handler extraction breaks connection flow | Medium | High | Write integration test that mocks full WS session lifecycle |
| SessionStore Protocol too narrow | Low | Medium | Start with methods actually used (get/set/delete/lrange/rpush/add_utterance/store_eval_transcript); extend later |
| Existing tests rely on internal module structure | Medium | Low | Re-exports mean old import paths still work; update tests gradually |

## Open Questions (Resolved)
- ~~Should `SessionStore` also wrap Redis pipeline operations?~~ **Yes** — pipeline operations are internalized inside `RedisStore` methods (`add_utterance`, `store_eval_transcript`). The Protocol does not expose `pipeline()`.
- ~~Should HTTP route extraction (task 2.2) be a separate PR from WebSocket handler extraction?~~ **Recommended yes** — two separate PRs within the same task for easier review. WebSocket handler first, HTTP routes second.

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
