# Backend Review — FEAT-008: Backend Architecture Fixes

**Reviewer Role:** Backend Engineer
**Date:** 2026-03-14
**Plan:** `docs/plans/2026-03-14-backend-arch-fixes.md`
**Spec:** `specs/FEAT-008-backend-arch-fixes.md`
**Source Files Inspected:**
- `backend/main.py` (696 LOC, verified)
- `backend/pipeline/orchestrator.py` (394 LOC, verified)
- `backend/session/manager.py`
- `backend/api/evaluation.py`
- `backend/pipeline/llm.py`
- `backend/briefing/portrait.py`
- `backend/summarize/call_summary.py`
- `backend/pipeline/post_call.py`

---

## Verdict: CONDITIONAL PASS — 4 blocking issues must be resolved before implementation begins

The plan is structurally sound and correctly identifies the architectural problems. All findings were verified against the actual source code. However, four gaps must be resolved in the plan itself before implementation starts, and one async correctness issue requires a new task.

---

## Checklist Evaluation

### 1. DB Schema / Storage Schema
**Result: FAIL**
**Severity: High**

The plan introduces `storage/keys.py` to centralize 11 Redis key patterns, but does not document the complete key inventory, their value types, TTL values, or the `decode_responses` invariant that must be enforced.

**Complete key inventory verified against source code:**

| Key Pattern | TTL | Value Type | Source |
|---|---|---|---|
| `session:{id}:utterances` | 1800s | Redis list of JSON strings | `session/manager.py:38` |
| `session:{id}:summary` | 1800s | plain string | `session/manager.py:42` |
| `session:{id}:kb_id` | 1800s | plain string | `main.py:278` |
| `kb:{id}:docs` | 7200s | bytes (raw text) | `main.py:277` |
| `kb:{id}:scenario` | 7200s | bytes (JSON) | `main.py:279` |
| `eval_transcript:{id}` | 86400s | Redis list of JSON strings | `session/manager.py:54` |
| `eval_analytics:{id}` | 86400s | bytes (JSON) | `post_call.py:253` |
| `eval:{id}` | 86400s | string (JSON) | `orchestrator.py:240` |
| `eval_token:{id}` | 86400s | plain string | `orchestrator.py:117` |
| `eval_config:default` | **no TTL** | string (JSON) | `api/evaluation.py:13` |
| `briefing:{session_id}:{kb_id}` | 1800s | string (JSON) | `briefing/portrait.py:97` |

**Blocking issue:** The plan does not specify that `storage/keys.py` must enforce or document the `decode_responses=False` invariant. The spec calls this out explicitly: "RedisStore must preserve `decode_responses=False`." If this invariant is not encoded as a constant or assertion in the `RedisStore.__init__`, implementers will repeat the mistake in any new `RedisStore` method. All `lrange` calls currently expect `list[bytes]`; a silent change to `decode_responses=True` would make them return `list[str]` and break `raw_analytics.decode()` with `AttributeError`.

**Required fix:** Add an assertion or explicit comment in `storage/keys.py` or `RedisStore.__init__` stating that all `lrange` return values are `list[bytes]`. TTL constants must be co-located with key patterns so the TTL skew between `session:{id}:kb_id` (1800s) and `kb:{id}:scenario` (7200s) is visible in one place.

Also note: `eval_config:default` has no TTL by design (admin-managed config). This must be explicitly documented in `storage/keys.py` as an intentional `None` TTL, so automated TTL enforcement logic does not accidentally add expiry to this key.

---

### 2. API Endpoints
**Result: FAIL**
**Severity: Medium**

Task 2.2 says HTTP routes move to `api/*.py` router files, and `main.py` becomes ~50 LOC. The plan does not enumerate which routes go to which file and does not address how `cfg`/`Settings` is threaded into extracted routers.

**Current routes that must be explicitly mapped:**

| Route | Method | Current Location | Required Target |
|---|---|---|---|
| `/api/v1/health` | GET | `main.py` closure | `api/health.py` or stays in `main.py` |
| `/api/v1/preflight` | GET | `main.py` closure | `api/preflight.py` |
| `/api/v1/upload` | POST | `main.py` closure | `api/upload.py` |
| `/api/v1/briefing` | POST | `main.py` closure | `api/briefing.py` |
| `/api/v1/summarize` | POST | `main.py` closure | `api/summarize.py` |
| `/api/v1/session/{id}` | DELETE | `main.py` closure | `api/session.py` |
| `/ws` | WebSocket | `main.py` closure | `WebSocketHandler` class |
| `/api/v1/evaluation-*` | GET/PUT/POST | `api/evaluation.py` | already extracted |

**Blocking issue:** All current routes inside `create_app` capture `cfg` from the outer closure. Moving them to separate routers requires DI of `Settings`. The existing `api/evaluation.py` works because it reads only `request.app.state.redis`. The `/api/v1/upload` route reads `cfg.openrouter_api_key`, `cfg.llm_primary_model`, `cfg.redis_url`, and `cfg.enable_post_call_diarization` — none of which are on `app.state` today. `app.state.settings = cfg` is already set at `main.py:51`, so the fix is straightforward: extracted routers must read `request.app.state.settings` instead of a closure variable.

The plan must add a task that explicitly states: "All extracted `api/*.py` routers access `Settings` via `request.app.state.settings`, not via closure or `get_settings()`."

**Required fix:** Add this DI pattern as a stated convention in the plan for task 2.2.

---

### 3. Auth Flow
**Result: PASS (with note)**

The only auth surface in this refactoring is the eval token flow: `eval_token:{session_id}` stored in Redis, verified with `hmac.compare_digest` in `api/evaluation.py`. This is correct and constant-time.

The `SessionStore` Protocol does not expose token storage methods, which is appropriate since token management is evaluation-specific and belongs in `EvaluationRunner`.

**Note:** Task 1.2 adds `store_eval_transcript` to the `SessionStore` Protocol. The plan must ensure `store_eval_token` is not exposed through the same Protocol — token operations must remain in `EvaluationRunner`, not the generic session store. This boundary is implicit in the plan but should be stated explicitly.

The eval token is passed as a query parameter (`?token=...`) which exposes it in server logs, browser history, and referrer headers. This is a pre-existing risk explicitly deferred to a follow-up task. The deferral is acceptable for an internal tool, but the plan should add a follow-up task reference in the Out of Scope section rather than leaving it undocumented.

---

### 4. Validation Rules
**Result: FAIL**
**Severity: Medium**

Two validation gaps exist in current code. The plan acknowledges them as edge cases but neither is tracked as a task.

**4a. No max length on `HintResponse.hint` field.**

From `pipeline/llm.py:54`:
```python
hint=data["hint"],
```

No length limit. The spec's own edge cases section states: "HintResponse.from_json places no length limit on hint field — misbehaving LLM can send 100KB+ hint." A 100KB hint forwarded over a WebSocket will degrade the extension UI and consume memory on every connected client. This is acknowledged in the spec but has no corresponding task in the plan.

After task 1.1 moves DTOs to `pipeline/types.py`, `HintResponse.from_json` is the correct place for this guard.

**4b. `generate_summary` in `call_summary.py:93` has no Redis None guard.**

From `call_summary.py:93`:
```python
raw_items: list[bytes] = await redis.lrange(utter_key, 0, -1)
```

If `redis=None`, this raises `AttributeError` at runtime. The `briefing/portrait.py` correctly guards `if redis is None: return BriefingResponse()` at lines 90-92. `call_summary.py` does not. Task 3.2 fixes the None guard in `orchestrator.py` but does not include the summarize path.

**Required fix for 4a:** Add `MAX_HINT_CHARS = 2000` constant to `pipeline/types.py` and enforce it in `HintResponse.from_json`:
```python
hint=data["hint"][:MAX_HINT_CHARS],
```

**Required fix for 4b:** Extend task 3.2 to include `call_summary.py`. Guard pattern:
```python
if redis is None:
    logger.warning("Redis unavailable — returning empty summary")
    return CallSummary()
```

---

### 5. Async Operations
**Result: FAIL**
**Severity: High**

This is the most significant gap in the plan. Three async correctness issues are identified.

**5a. `_evaluation_started` flag is not async-safe after extraction.**

From `orchestrator.py:110-112`:
```python
if self._evaluation_started:
    return ""
self._evaluation_started = True
```

In the current code, there is no `await` between the check and the set, so the guard is correct. However, Task 2.1 extracts this into `EvaluationRunner` and adds `await redis.set(...)`. If the `None` guard check or any log statement introduces an `await` before `self._evaluation_started = True`, a concurrent `session_end` message (possible from both the text-frame path at `main.py:496` and the binary control-frame path at `main.py:635`) can pass the guard simultaneously and trigger double evaluation.

The plan notes this as a known edge case but provides no fix. `asyncio.Lock` is the correct solution.

**Blocking issue:** Add a task to introduce `asyncio.Lock` in `EvaluationRunner` for the `_evaluation_started` guard:
```python
async with self._eval_lock:
    if self._evaluation_started:
        return ""
    self._evaluation_started = True
```

**5b. `_store_results` in `PostCallProcessor` uses a pipeline, not a transaction.**

From `post_call.py:268-274`:
```python
pipe = self._redis.pipeline()
pipe.delete(eval_key)
if diarized:
    pipe.rpush(eval_key, *diarized)
pipe.expire(eval_key, 86400)
pipe.set(analytics_key, analytics.to_redis_json(), ex=86400)
await pipe.execute()
```

A Redis pipeline batches commands but is **not atomic** — it does not prevent interleaved writes from other clients or prevent partial execution on connection drop. The `delete` command is the most dangerous: if the connection drops after `delete` is applied on the server but before `rpush` is applied, the transcript is permanently lost with no retry or compensation. The spec explicitly lists this as an edge case.

**Blocking issue:** Add a task to convert `_store_results` to use a Redis transaction:
```python
pipe = self._redis.pipeline(transaction=True)
```

This uses `MULTI`/`EXEC` semantics and makes the delete-then-push atomic.

**5c. `call_llm_simple` timeout must be a parameter, not a hardcoded constant.**

The plan mentions the 30s default as a behavior change in task 1.3. The spec explicitly states: "Timeout must be configurable per caller." The `/api/v1/briefing` endpoint generates from 120K-character documents; 30 seconds may be too short and will introduce HTTP 504 regressions for large-document briefings. The `/api/v1/summarize` endpoint does not have this concern since it works with the trimmed 10-utterance buffer.

**Blocking issue:** Task 1.3 must define `call_llm_simple` with a configurable timeout parameter:
```python
async def call_llm_simple(
    prompt: str,
    api_key: str,
    model: str,
    system_prompt: str,
    timeout_s: float = 30.0,
) -> str:
```

Each caller (`portrait.py`, `call_summary.py`) passes its own timeout. `portrait.py` should pass a longer timeout (e.g., 60s).

---

### 6. Migration Strategy
**Result: PASS (with notes)**

The incremental PR structure is correct. Ordering is sound: Foundation (1.1, 1.2, 1.3) before Core Extractions (2.1, 2.2) before Cleanup (3.1, 3.2). Each task can be merged independently without breaking the running service.

**Note 1: Re-export dependency directions are clean.** `HintContext`, `HintResponse` in `pipeline/llm.py` → move to `pipeline/types.py`, re-export from `pipeline/llm.py`. `Transcript` in `pipeline/stt.py` → same pattern. `CallAnalytics` in `pipeline/post_call.py` imports from `pipeline/yandex_async.py`; moving the DTO to `pipeline/types.py` inverts the dependency cleanly since `post_call.py` can then import the DTO from `types`. No circular import risk in any of these moves.

**Note 2: No rollback plan documented.** Since this is a pure refactoring with no Redis schema changes, rollback is a git revert and the service restarts with old code. Redis state is compatible in both directions since no key patterns are renamed. This should be stated explicitly in the plan for each task PR.

**Note 3: `eval_config:default` has no TTL.** If a malformed config is written to Redis and the reset endpoint fails (Redis down), the bad config persists indefinitely. This is a pre-existing risk, not introduced by this plan, but the TTL constant should be explicitly `None` in `storage/keys.py`.

---

### 7. Error Responses
**Result: PASS (with note)**

The existing error response format is consistent across WebSocket protocol and HTTP and is preserved by the plan.

WebSocket errors: `{"type": "error"|"evaluation_error", "code": "SCREAMING_SNAKE_CASE", "message": "..."}`.

HTTP errors: FastAPI `HTTPException` produces `{"detail": "..."}`.

The `WebSocketHandler` extraction in Task 2.2 moves error-sending code verbatim into class methods; format is unchanged. The Redis None guard in `on_session_end` correctly returns `""` (empty token) rather than crashing; the caller already handles empty token gracefully (`evaluation_started` message with empty `eval_token`).

**Note:** Task 2.1 specifies "None guard (defense-in-depth)" but does not state what happens to the WebSocket client when `redis=None` causes `on_session_end` to return `""`. The client receives `{"type": "evaluation_started", "eval_token": ""}` and will poll `GET /api/v1/evaluation/{id}?token=` with an empty token, getting a 403 immediately. This is technically correct behavior (no evaluation without Redis) but the client receives no signal that evaluation is impossible rather than just pending. This is pre-existing behavior; the plan should document it as intentional.

---

### 8. Performance Queries
**Result: FAIL**
**Severity: Low**

Three performance-sensitive operations are not identified in the plan.

**8a. `call_summary.py:93` calls `lrange(utterances, 0, -1)` with no upper bound.**

In practice, `ltrim` in `add_utterance` keeps the last 10 utterances, so this is safe. However, after `call_summary.py` migrates to `SessionStore` (task 1.2), the `SessionStore.get_context` method must enforce the same max fetch count. The current code in `session/manager.py:70` also uses `lrange(0, -1)` unbounded. A test or failure scenario that bypasses `ltrim` would result in loading all utterances into memory for the summary LLM call.

**8b. `generate_briefing` loads up to 120K characters from Redis in a single `redis.get`.**

`briefing/portrait.py:127`: `kb_docs = await redis.get(f"kb:{kb_id}:docs")`. This is a 120KB Redis fetch on the synchronous HTTP request path. No timeout is placed on this fetch. After `call_llm_simple` adds a 30s LLM timeout, the total request duration for `/api/v1/briefing` becomes: Redis fetch (unbounded) + 30s LLM timeout. This should be noted in the plan and the Redis fetch should have a timeout via `asyncio.wait_for` or httpx client-style timeout.

**8c. `PostCallProcessor._count_interruptions` is O(n²) over utterances.**

From `post_call.py:219`:
```python
for i, a in enumerate(utterances):
    for b in utterances[i + 1:]:
```

For a 2-hour call with dense utterances, this is O(n²) where n is total utterance count. For typical sales calls (30-60 minutes, ~100-300 utterances), this is not a performance problem. For long calls or high-density recognition outputs, it could be. Not a blocking issue for this refactoring, but should be noted.

---

## Edge Cases Not Addressed (5 items)

### EC-1 — Concurrency: `WebSocketHandler` instance state races after extraction

**Category: Concurrency**

After `websocket_endpoint` is extracted to `WebSocketHandler`, the local variables `last_transcript_time`, `idle_warning_sent`, and `stt_failed` become instance attributes. The coroutines `_handle_audio_frame`, `_handle_control_frame`, and `_handle_idle_timeout` will all read and write these attributes.

`_handle_idle_timeout` reads `last_transcript_time` and computes `idle_s`. Concurrently, `_handle_audio_frame` triggers `_on_transcript` which writes `last_transcript_time = now`. If `_handle_idle_timeout` is interrupted between reading `last_transcript_time` and checking `idle_s >= timeout`, across an `await` boundary, it may fire a timeout warning that the transcript update should have suppressed.

In the current closure-based code, these are captured via `nonlocal` and the asyncio event loop provides cooperative scheduling safety. After extraction, the implementer must verify that no `await` is inserted between read and write of `last_transcript_time` and `idle_warning_sent` within a single coroutine frame.

**Not covered by plan:** Task 2.2 only extracts the function; it does not audit shared state for async safety.

---

### EC-2 — State: WebSocket connection arrives before lifespan Redis setup completes

**Category: State**

The `lifespan` function connects to Redis asynchronously before the app is ready. If a WebSocket connection arrives during startup (possible in load tests or rapid restarts), `getattr(websocket.app.state, "redis", None)` may return `None` before the attribute is set. The session starts without Redis, no utterances are saved, and `on_session_end` hits the new None guard (returns `""` after task 2.1/3.2 fix). The client receives `evaluation_started` with empty token and gets 403 when polling. This is consistent behavior but the plan does not include a test for this startup-race scenario.

---

### EC-3 — Data: `eval_config:default` survives Redis flushes and has no expiry

**Category: Data**

From `api/evaluation.py:47`:
```python
await redis.set(_CONFIG_KEY, payload.model_dump_json())
```

No `ex=` argument. If a malformed evaluation config is written (e.g., during testing with wrong field types), the reset endpoint must be called to clear it. If Redis is unavailable when reset is attempted, the bad config persists indefinitely. After `storage/keys.py` centralizes key patterns in task 1.2, the `eval_config:default` entry must be explicitly documented as `TTL = None` (intentional, admin-managed), so any automated TTL enforcement logic in `RedisStore` does not accidentally expire it.

---

### EC-4 — Integration: `EvaluationRunner` holds a reference to a closed WebSocket

**Category: Integration**

`_run_evaluation` is dispatched as a background `asyncio.Task`. The WebSocket may close (client disconnect, network error) before the evaluation completes (evaluation can take up to 150s per `asyncio.wait_for` timeout in `main.py:679`). The current code wraps all `ws.send_json` calls in `contextlib.suppress(Exception)`, which silently swallows the disconnect.

After extraction to `EvaluationRunner`, the plan must specify whether `EvaluationRunner` holds a direct `WebSocket` reference or communicates results back via a callback or queue. If it holds a direct reference, the WebSocket object must remain alive for the full evaluation window. The current teardown in `main.py:672-685` waits for the evaluation task with `asyncio.wait_for(task, timeout=150.0)` before closing the WebSocket, so the reference is valid. This behavior must be explicitly preserved in the `WebSocketHandler` teardown method.

---

### EC-5 — Integration: `SessionStore.add_utterance` pipeline partial failure silently drops utterances

**Category: Integration**

`session/manager.py:57-63` uses a Redis pipeline with 5 commands. If Redis returns a partial error on pipeline execution (e.g., wrong type for a key — which can happen if a key is manually set to a string before the list operations), `pipe.execute()` raises an exception. The caller in `orchestrator.py:handle_transcript` catches this with:

```python
except Exception as exc:
    logger.warning(f"Не удалось сохранить реплику: {exc!r}")
```

The utterance is silently dropped from both `session:utterances` and `eval_transcript`. After `SessionStore` abstraction (task 1.2), the error handling contract must be documented: does `add_utterance` raise on failure, or silently no-op? The current behavior (silent no-op with warning log) should be preserved and explicitly tested. Changing to raise would require updates to all callers.

---

## Summary Table

| # | Item | Result | Severity | Key Finding |
|---|------|--------|----------|-------------|
| 1 | DB Schema / Storage Schema | FAIL | High | `decode_responses=False` invariant not encoded; `eval_config:default` TTL=None undocumented |
| 2 | API Endpoints | FAIL | Medium | No DI strategy for `cfg`/`Settings` in extracted routers documented |
| 3 | Auth Flow | PASS | — | Token flow correct; query-param exposure deferred (acceptable) |
| 4 | Validation Rules | FAIL | Medium | No hint length limit; missing Redis None guard in `call_summary.py` |
| 5 | Async Operations | FAIL | High | `_evaluation_started` needs `asyncio.Lock`; `_store_results` needs MULTI/EXEC; `call_llm_simple` timeout must be a parameter |
| 6 | Migration Strategy | PASS | — | Incremental PR order is correct; re-export directions are clean; no rollback complexity |
| 7 | Error Responses | PASS | — | Consistent format preserved; None guard behavior documented |
| 8 | Performance Queries | FAIL | Low | Unbounded `lrange` in `call_summary.py`; 120KB Redis fetch on briefing path; O(n²) interruption counting |

**Blocking issues (must be resolved in plan before implementation starts):**

1. **(5b)** Add a task to convert `PostCallProcessor._store_results` to use `MULTI`/`EXEC` transaction (`pipeline(transaction=True)`).
2. **(5a)** Add `asyncio.Lock` to `EvaluationRunner` for the `_evaluation_started` guard. Set the flag before any `await`.
3. **(5c)** `call_llm_simple` must accept `timeout_s: float = 30.0` as a parameter. `portrait.py` should pass a longer timeout. This is required by the spec.
4. **(2)** Document the DI strategy for `Settings` in extracted HTTP routers: all routers use `request.app.state.settings`, not closure variables or `get_settings()`.

**Non-blocking but recommended before merge:**

- Add `MAX_HINT_CHARS = 2000` enforcement in `HintResponse.from_json` (item 4a).
- Add Redis None guard to `generate_summary` in `call_summary.py` in task 3.2 scope (item 4b).
- Document `eval_config:default` TTL=None explicitly in `storage/keys.py` (EC-3).
- Add test for `EvaluationRunner.on_session_end` with `redis=None` returning `""` (item 7 note).
- Audit `WebSocketHandler` instance attributes for async safety after extraction (EC-1).
