# Consolidated Review — FEAT-008: Backend Architecture Fixes (Round 2)

Plan: `docs/plans/2026-03-14-backend-arch-fixes.md`
Spec: `specs/FEAT-008-backend-arch-fixes.md`
Date: 2026-03-14
Verdict: **NEEDS REVISION**

## Summary

- **Architect:** CONDITIONAL PASS (0 BLOCKERS, 4 MAJOR, 1 MINOR → 5 issues)
- **Backend:** CONDITIONAL PASS (0 BLOCKERS, 3 HIGH, 1 MEDIUM, 1 LOW → 5 issues)
- **Frontend:** CONDITIONAL PASS (0 BLOCKERS, 1 BLOCKING advisory, 3 ADVISORY → 4 issues)
- **Total issues (deduplicated):** 9 (0 blockers, 6 major, 3 minor)

### Note on Previously Resolved Issues

The following items from Round 1 are **confirmed resolved** in the updated plan:

- ~~B1: SessionStore.pipeline() returns Any~~ ✅ Plan now internalizes all pipeline ops into typed RedisStore methods (`add_utterance`, `store_eval_transcript`, `store_results`)
- ~~M1: call_summary.py raw Redis~~ ✅ Added to task 1.2 scope with SessionStore migration
- ~~M2: EvaluationRunner None guard~~ ✅ Task 2.1 adds unconditional None guard in on_session_end + type annotation
- ~~M3: Eval token in query string~~ ✅ Deferred security note added to Out of Scope with FEAT-00X reference
- ~~M4: CallAnalytics serialization contract~~ ✅ Task 1.1 step 5b adds wire-contract regression test
- ~~M5: AudioBuffer not in DTO extraction~~ ✅ SessionEndPayload dataclass documented in task 2.1
- ~~m1: call_llm_simple no connection reuse~~ ✅ Task 1.3 accepts optional client param, configurable timeout_s: float = 30.0

**7 of 7 Round 1 issues resolved.** All items below are **genuinely new** from Round 2.

---

## All Issues (deduplicated — genuinely new from Round 2)

### BLOCKERS

None.

### MAJOR

**M1. `_evaluation_task` reference lost after WebSocketHandler extraction**
*Flagged by: Architect (MAJOR-1)*

When `on_session_end` spawns `asyncio.create_task(runner.run())`, the task reference is stored on `self._evaluation_task`. After extracting `WebSocketHandler` as a class, the `websocket_endpoint` function's `finally` block must await this task (with 150s timeout) to prevent silent cancellation on disconnect. If the task reference is lost during extraction, evaluation silently stops.

**Fix:** Add to task 2.1 implementation steps: "In `WebSocketHandler.finally`, await `self._evaluation_task` with `asyncio.wait_for(self._evaluation_task, timeout=150)` wrapped in `try/except asyncio.TimeoutError`."

---

**M2. `on_session_end` return type contract unspecified**
*Flagged by: Architect (MAJOR-2)*

`on_session_end` must return `eval_token: str` so the caller can send it to the client via WebSocket. The plan describes the token generation but does not specify the return type as a contract between `WebSocketHandler` and `on_session_end`.

**Fix:** Add to task 2.1: "`on_session_end() -> str` — returns `eval_token`. Document in DoD: return type is `str` (the evaluation token)."

---

**M3. `store_eval_transcript(key: str)` should be `(session_id: str)`**
*Flagged by: Architect (MAJOR-3)*

The `SessionStore` Protocol method `store_eval_transcript` accepts `key: str`, which leaks Redis key-format knowledge to callers. Should accept `session_id: str` and construct the key internally, consistent with `add_utterance(session_id, speaker, text)`.

**Fix:** Change Protocol signature: `async def store_eval_transcript(self, session_id: str) -> None`. RedisStore implementation constructs `session:{session_id}:transcript` internally.

---

**M4. `_store_results` needs `pipeline(transaction=True)` for MULTI/EXEC**
*Flagged by: Backend (HIGH-1)*

`_store_results` performs `delete` then `rpush` on the same key. Without `transaction=True`, the pipeline sends commands individually. If connection drops between delete and rpush, transcript is lost. Need MULTI/EXEC atomicity.

**Fix:** Add to task 1.2 implementation: "Use `async with self._redis.pipeline(transaction=True) as pipe:` for `_store_results` delete+rpush sequence."

---

**M5. `_evaluation_started` needs `asyncio.Lock`**
*Flagged by: Backend (HIGH-2)*

The `_evaluation_started` flag is checked and set non-atomically. If two `session_end` messages arrive in rapid succession (e.g., WebSocket reconnect), both can pass the check before either sets the flag, spawning duplicate evaluations.

**Fix:** Add to task 2.1: "Guard `_evaluation_started` check-and-set with `asyncio.Lock`. Pattern: `async with self._eval_lock: if self._evaluation_started: return; self._evaluation_started = True`."

---

**M6. DI strategy for `Settings` not specified**
*Flagged by: Backend (MEDIUM-1)*

Multiple modules need access to `Settings` (config). The plan does not specify how `Settings` flows into `WebSocketHandler`, `EvaluationRunner`, and `SessionStore`. Without explicit DI, modules will import `Settings` directly, defeating the abstraction goal.

**Fix:** Add to task 2.1: "Pass `Settings` via `request.app.state.settings` (FastAPI pattern). `WebSocketHandler.__init__` receives `settings: Settings`. `EvaluationRunner.__init__` receives `settings: Settings`."

---

### MINOR

**m1. `MAX_HINT_CHARS = 2000` not documented for `HintResponse`**
*Flagged by: Backend (LOW-1)*

`HintResponse` Pydantic model should validate `hint` field length. The backend truncates to 2000 chars but the model has no `max_length` constraint.

**Fix:** Add `hint: str = Field(max_length=2000)` to `HintResponse` in task 1.1.

---

**m2. `portrait.py` raw Redis access partially unaddressed**
*Flagged by: Architect (observation)*

`portrait.py` uses `redis.get(f"kb:{kb_id}:scenario")` directly. While `call_summary.py` was added to task 1.2 scope in Round 1, `portrait.py` was not explicitly mentioned. It should also use `SessionStore`.

**Fix:** Add `portrait.py` to task 1.2 modified files alongside `call_summary.py`.

---

**m3. REST URL path double-prefix risk**
*Flagged by: Frontend (ADVISORY-1)*

If `evaluation.py` router uses `prefix="/api/evaluation"` and individual routes also start with `/evaluation/`, the resulting path becomes `/api/evaluation/evaluation/...`. Need to verify prefix consistency during extraction.

**Fix:** Add to task 3.1 DoD: "Verify all route paths after extraction — no double prefixes."

---

## Edge Cases by Category

### Data

- **Transcript loss on `_store_results` partial failure:** Without MULTI/EXEC, delete+rpush is non-atomic. Connection drop between commands loses transcript. *(Backend EC-3 — addressed by M4 above)*
- **`decode_responses` flag mismatch:** `RedisStore` must preserve `decode_responses=False`. Otherwise `lrange` returns `list[str]` and `raw_analytics.decode()` raises `AttributeError`. *(Architect EC-4)*

### State

- **`_evaluation_task` cancelled on disconnect:** If WebSocket disconnects before eval completes and `finally` doesn't await the task, evaluation is silently cancelled. *(Architect — M1 above)*
- **Re-entrant `session_start`:** Second `session_start` on same WebSocket creates new `PipelineOrchestrator` without tearing down old STT session. Plan does not specify idempotency. *(Architect EC-2)*

### Concurrency

- **Double `session_end` race:** `_evaluation_started` check-and-set is non-atomic. *(Backend EC-1 — addressed by M5 above)*
- **`_on_transcript` closure captures mutable variables:** After extraction, `stt_failed` and `last_transcript_time` become instance attributes shared across concurrent coroutines. *(Backend EC-5)*

### Integration

- **TTL skew:** `session:{id}:kb_id` expires at 1800s, `kb:{id}:scenario` at 7200s. After 30 min, reconnecting client can't look up `kb_id`. *(Backend EC-4)*
- **`call_llm_simple` 30s timeout behavior change:** Adding timeout where none existed may cause 504s for legitimate slow LLM responses. *(Architect EC-5)*

### UX

- **`eval_config:default` no TTL:** Mis-formatted config persists indefinitely. Intentional but undocumented. *(Architect observation)*

---

## Recommended Actions

1. **[MAJOR] Add `_evaluation_task` teardown** — `finally` block with 150s `asyncio.wait_for`. Task 2.1.
2. **[MAJOR] Specify `on_session_end` return contract** — `-> str` returning eval_token. Task 2.1.
3. **[MAJOR] Fix `store_eval_transcript` signature** — `(session_id: str)` not `(key: str)`. Task 1.2.
4. **[MAJOR] Add MULTI/EXEC to `_store_results`** — `pipeline(transaction=True)`. Task 1.2.
5. **[MAJOR] Add `asyncio.Lock` for `_evaluation_started`** — Prevent double evaluation. Task 2.1.
6. **[MAJOR] Specify DI strategy for Settings** — `request.app.state.settings`. Task 2.1.
7. **[MINOR] Add `MAX_HINT_CHARS` validation** — `Field(max_length=2000)` on HintResponse. Task 1.1.
8. **[MINOR] Add `portrait.py` to task 1.2** — Migrate to SessionStore.
9. **[MINOR] Verify route path prefixes** — No double-prefix in task 3.1 DoD.

---

*Review complete. Resolve 6 MAJOR issues before proceeding to /implement.*
