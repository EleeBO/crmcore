# Architect Review — FEAT-008

Plan: docs/plans/2026-03-14-backend-arch-fixes.md
Spec: specs/FEAT-008-backend-arch-fixes.md
Reviewer: Architect
Date: 2026-03-14
Verdict: CONDITIONAL PASS

---

## Checklist

| # | Item | Status | Severity | Notes |
|---|------|--------|----------|-------|
| 1 | System Boundaries | PASS | — | Module boundaries are clear and well-scoped. Each extraction (`WebSocketHandler`, `EvaluationRunner`, `SessionStore`, `shared_llm`, `protocols`) owns a single responsibility. The `ws/`, `storage/`, and `pipeline/` namespaces are logically correct. Re-exports for backward compatibility are explicitly planned. |
| 2 | Data Flow | FAIL | MAJOR | `call_summary.py:generate_summary` accesses Redis directly via raw `lrange`/`get` with inline key strings. The plan lists it as modified in task 1.2 (step 6b), but not in the "Files: Modify" section header, creating ambiguity for the implementer. More critically, the `SessionStore` Protocol in task 1.2 step 3 does not expose `pipeline()` — the plan correctly internalizes pipeline operations inside `RedisStore` methods — but the Protocol method `store_eval_transcript(key, items, ttl)` accepts a pre-built `key: str` instead of a `session_id: str`, bypassing the key registry. This means callers can construct arbitrary key strings and pass them to the store, defeating the centralization goal. |
| 3 | Technology Choices | PASS | — | Protocol-based structural subtyping over ABC is appropriate for the codebase scale. Using a thin `RedisStore` wrapper rather than an ORM-style abstraction is the right level. Placement of `call_llm_simple` in `pipeline/shared_llm.py` is consistent with the existing `pipeline/` boundary. The `runtime_checkable` Protocols are the correct choice for `isinstance` checks in tests without ABCMeta overhead. |
| 4 | Scalability | FAIL | MAJOR | `EvaluationRunner` is spawned via `asyncio.create_task` as fire-and-forget. The plan does not address task lifecycle management: if the process receives SIGTERM during a long-running evaluation (the `finally` block in `websocket_endpoint` already waits 150s for the task), the new `EvaluationRunner` extracted into its own class needs the same wait logic. The plan's task 2.2 step 6 says "Update `main.py` to 3-line delegation" but does not specify how the `_evaluation_task` reference is exposed from `WebSocketHandler` so the `finally` block can still `await` it. If this reference is lost, evaluations will be silently abandoned on disconnect. |
| 5 | Security | FAIL | MAJOR | The `put_config` endpoint (`api/evaluation.py:41`) writes arbitrary `EvaluationConfig` to Redis with no authentication. The plan's Out of Scope section defers this with a `# TODO(security)` comment on the eval token query param, but does not note the unauthenticated config write endpoint as a separate deferred risk. The `eval_config:default` key is stored with no TTL — centralized in the key registry as `CONFIG_TTL: int | None = None` which is correct — but the plan does not include a `TODO` or deferred task reference at the call site in `api/evaluation.py` to match the one added for the eval token. Security deferral should be documented symmetrically. Separately: task 1.3 creates `call_llm_simple` as a bare async function that accepts `api_key: str`. The plan does not specify how the API key reaches the shared utility — callers must pass it explicitly, which is correct, but this should be stated to avoid implementers pulling the key from a module-level global. |
| 6 | API Contracts | FAIL | MAJOR | The interface between `WebSocketHandler` and `PipelineOrchestrator.on_session_end` is broken by task 2.1. After extraction, `on_session_end` will construct and spawn `EvaluationRunner`, but it currently returns `eval_token: str` which `websocket_endpoint` immediately sends to the client as part of `evaluation_started`. The plan for task 2.2 (WebSocketHandler) does not specify that `WebSocketHandler._handle_session_end` must still await `on_session_end` and extract the returned `eval_token` before sending the message. If the implementer restructures `on_session_end` to be void (returning nothing), the `evaluation_started` message will be sent with an empty token, breaking the client's ability to poll for results. The return type contract of `on_session_end → str` must be preserved or explicitly redesigned. |
| 7 | Error Handling | FAIL | MAJOR | Task 2.1 adds a None guard at the top of `EvaluationRunner.run()` for `self._redis is None`. However, the `PostCallProcessor` constructor in `_run_evaluation` STEP A also accepts `redis` directly (`PostCallProcessor(recognizer=..., redis=redis, session_id=...)`). If `redis` is `None`, the guard in `EvaluationRunner.run()` fires before reaching this point — correct. But task 3.2 step 3b adds a separate None guard to `call_summary.py:generate_summary`. The current `call_summary.py` does NOT guard for `redis=None` — it calls `redis.lrange(...)` on line 93 unconditionally. If called when Redis is unavailable (which `main.py:summarize` endpoint allows — it passes `redis_client` which can be `None`), this raises `AttributeError`. Task 3.2 addresses it, but the plan does not flag this as a pre-existing production crash risk that should be fixed at the start, not at the end of the refactor. |
| 8 | Circular Dependencies | PASS | — | Proposed dependency direction is acyclic: `ws/handler.py` → `pipeline/orchestrator.py` → `pipeline/evaluation_runner.py` → `storage/protocol.py` → (leaf). `pipeline/types.py` is a pure-data leaf. `storage/keys.py` imports nothing from `pipeline/`. The re-export pattern is one-directional. One risk to monitor: `pipeline/evaluation_runner.py` will import from `storage/protocol.py` and `pipeline/post_call.py`. If `post_call.py` is later modified to import from `storage/`, a cycle `evaluation_runner → post_call → storage → evaluation_runner` could form. The plan does not add a cycle guard or note this as a risk. |

---

## Issues

### Issue 1: `store_eval_transcript` Protocol Method Bypasses Key Registry
- **Severity:** MAJOR
- **Section:** Task 1.2, Step 3 — `SessionStore` Protocol definition
- **Description:** The Protocol signature `async def store_eval_transcript(self, key: str, items: list[str], ttl: int) -> None` accepts `key: str` as a raw string. The purpose of the key registry is to ensure no caller constructs key strings by hand. If the Protocol accepts `key: str`, callers can pass `f"eval_transcript:{session_id}"` directly rather than using `storage.keys.eval_transcript(session_id)`, and the type checker cannot distinguish the two. The same issue applies to `add_utterance(self, session_id: str, ...)` which correctly uses `session_id` — that pattern should be applied consistently.
- **Fix:** Change `store_eval_transcript(self, key: str, ...)` to `store_eval_transcript(self, session_id: str, ...)` so the implementation constructs the key internally using the registry. Apply the same pattern to all compound-key Protocol methods.

### Issue 2: `_evaluation_task` Reference Lost After WebSocketHandler Extraction
- **Severity:** MAJOR
- **Section:** Task 2.2, Step 6 — "Update `main.py` to 3-line delegation"
- **Description:** The current `finally` block in `websocket_endpoint` accesses `orchestrator._evaluation_task` directly to await it with a 150s timeout (main.py lines 675–680). After extraction into `WebSocketHandler`, this private attribute is hidden inside the class. The plan does not specify how `WebSocketHandler` exposes the evaluation task for the `finally` block. If `main.py` becomes a 3-line delegation (`await WebSocketHandler(websocket, redis).run()`), the `finally` logic must move inside `WebSocketHandler.run()`'s own `finally` block. The plan does not address this migration, leaving an implementation ambiguity that could silently drop the 150s wait.
- **Fix:** Add an explicit requirement to task 2.2: `WebSocketHandler.run()` must contain its own `finally` block that mirrors the current `websocket_endpoint` finally logic, including the 150s await on `_evaluation_task`. The 3-line `main.py` delegation must not own teardown logic.

### Issue 3: `generate_summary` Crashes When Redis is None (Pre-existing, Unremarked)
- **Severity:** MAJOR
- **Section:** Task 3.2, Step 3b — `call_summary.py` None guard
- **Description:** `call_summary.py:generate_summary` calls `await redis.lrange(...)` on line 93 with no None guard. `main.py:summarize` endpoint passes `redis_client = getattr(request.app.state, "redis", None)` directly. If Redis is unavailable, calling `POST /api/v1/summarize` raises `AttributeError: 'NoneType' object has no attribute 'lrange'` — a 500 crash rather than a graceful error. This is a production crash path the plan defers to task 3.2 (the last task). Given this is a live crash risk, it should be fixed in task 1.2 when `call_summary.py` is already being modified, not left until task 3.2.
- **Fix:** Move the `call_summary.py` None guard addition to task 1.2 step 6b. Add: `if redis is None: return CallSummary()` at the top of `generate_summary`. The same guard pattern already exists in `portrait.py:generate_briefing` (line 90–92).

### Issue 4: `on_session_end` Return Type Contract Not Preserved in Task 2.1
- **Severity:** MAJOR
- **Section:** Task 2.1, Step 5 — "Update `PipelineOrchestrator.on_session_end`"
- **Description:** `on_session_end` currently returns `eval_token: str`, which `websocket_endpoint` sends in the `evaluation_started` message (main.py lines 644–651). Task 2.1 says to "construct and spawn `EvaluationRunner`" but does not state whether `on_session_end` continues to return the token. If an implementer moves token generation into `EvaluationRunner.__init__` or `run()`, `on_session_end` would no longer have a token to return, breaking the `evaluation_started` message. The plan is silent on this contract.
- **Fix:** Add an explicit requirement to task 2.1: `on_session_end` must continue to generate and return `eval_token: str`. Token generation (`secrets.token_urlsafe(16)`) and its Redis write must remain in `on_session_end`, not move to `EvaluationRunner`.

### Issue 5: `briefing/portrait.py` Also Accesses Redis Directly — Not Addressed by H1
- **Severity:** MINOR
- **Section:** Scope / Task 1.2
- **Description:** `portrait.py:generate_briefing` accesses Redis directly via `redis.get(cache_key)`, `redis.get(f"kb:{kb_id}:scenario")`, `redis.get(f"kb:{kb_id}:docs")`, `redis.set(...)`, `redis.expire(...)`. This file is not listed in task 1.2's "Files: Modify" section, yet the H1 objective states "Abstract raw Redis usage in 8 files." The plan's file count table (from the Context section) lists 8 files with Redis access but only migrates `session/manager.py`, `api/evaluation.py`, and `call_summary.py`. `portrait.py`, `post_call.py`, and `main.py` (3 of the 8) remain as raw Redis accessors after the refactor, leaving the abstraction partially applied.
- **Fix:** Either expand task 1.2 scope to include `portrait.py` and `post_call.py`, or explicitly acknowledge in the plan that H1 is partially addressed (SessionStore covers session/evaluation paths; briefing/post-call paths deferred to a follow-up). The acceptance criterion "at least `session/manager.py` and `api/evaluation.py` use the Protocol" is technically met, but does not align with the stated goal of abstracting raw Redis in 8 files.

---

## Edge Cases

1. **Concurrency — Double `session_end` via text fallback path:** The current `websocket_endpoint` has two code paths that call `on_session_end`: the binary control frame path (line 638) and the text frame fallback path (line 499). Both can fire if a client sends a text-frame `session_end` followed immediately by a binary `session_end` before the loop breaks. The `_evaluation_started` flag in `PipelineOrchestrator` prevents double evaluation, but both paths call `await orchestrator.on_session_end(...)` sequentially in the same coroutine — the second call returns `""` without error. After extraction into `WebSocketHandler`, if `_handle_session_end` is extracted as a method, both calling sites in `handle_text_frame` and `handle_control_frame` must both set a local `_session_ended` flag to avoid calling `on_session_end` twice. The plan does not mention this.

2. **State — `session_start` received after `session_end` on the same WebSocket:** The current loop `break`s after `session_end`, so this cannot happen. But after `WebSocketHandler` extraction, if the loop structure changes and `break` is replaced with a state machine, a second `session_start` on the same WebSocket would create a new `PipelineOrchestrator` while `_evaluation_task` from the first session is still running. The `audio_buffer` reference would be replaced, and `EvaluationRunner` holding the old reference would operate on a cleared buffer.

3. **Integration — `decode_responses=False` must be preserved in `RedisStore`:** The current Redis client is created with `decode_responses=False` (main.py line 31). `session/manager.py` returns `list[bytes]` from `lrange` and decodes manually. `api/evaluation.py:get_evaluation` also calls `.decode()` on results. If `RedisStore.__init__` wraps a client with `decode_responses=True` (e.g. for convenience), the `.decode()` calls in remaining raw-Redis code paths will raise `AttributeError: 'str' object has no attribute 'decode'`. The plan mentions this as an edge case in the spec but does not include a test assertion in `test_storage.py` verifying the `decode_responses` setting.

4. **Data — Non-atomic `delete + rpush` in `PostCallProcessor._store_results`:** The plan moves `CallAnalytics.to_redis_json`/`from_redis_json` out of the DTO into `PostCallProcessor._store_results`. The existing `_store_results` uses a Redis pipeline with `pipe.delete(eval_key)` followed by `pipe.rpush(eval_key, *diarized)`. This is atomic within the pipeline, but if the pipeline fails after `delete` and before `rpush`, the eval transcript is lost. The spec lists this as a known edge case. The plan does not require the implementer to add a compensating test or a pre-condition check, nor to use a transaction (`MULTI/EXEC`) instead of a pipeline.

5. **Concurrency — `_background_tasks` set is iterated during mutation in `teardown`:** `PipelineOrchestrator.teardown()` iterates `self._background_tasks` and cancels non-done tasks (orchestrator.py lines 88–93). If a task completes and removes itself from the set via a `done_callback` during iteration, a `RuntimeError: Set changed size during iteration` can occur. The plan's task 3.2 addresses dead code cleanup of `_background_tasks` but does not explicitly require fixing this iteration-during-mutation risk, even though it is a latent concurrency bug. The plan should require either `list(self._background_tasks)` for iteration (which the current `gather` call already does on line 93, but the `cancel` loop on line 89 does not), or a lock.

---

## Summary

The plan is structurally sound and the module decomposition is correct. The sequencing (Foundation → Core Extractions → Cleanup) is sensible. However, four MAJOR issues prevent unconditional approval:

1. The `eval_token` return contract of `on_session_end` is not preserved in task 2.1.
2. The `_evaluation_task` reference is not preserved after WebSocketHandler extraction in task 2.2.
3. The `call_summary.py` Redis None crash is deferred too late (task 3.2 instead of task 1.2).
4. The `SessionStore` Protocol partially undermines the key registry via raw `key: str` parameters.

All four are MAJOR scope clarifications, not design flaws. The plan can proceed as **CONDITIONAL PASS** if these four issues are addressed in the implementation tasks before coding begins. No BLOCKER-level issues were found.
