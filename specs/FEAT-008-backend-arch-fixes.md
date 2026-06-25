# FEAT-008: Backend Architecture Fixes

Status: DRAFT
Created: 2026-03-14
Last Modified: 2026-03-14

## Overview

Refactor the backend codebase to address critical and high-severity findings from the 2026-03-14 architecture review. The core problems are: a 281-line god function (`websocket_endpoint`), no storage abstraction (raw Redis in 8 files), only 1 of 5 needed abstract interfaces, 170 lines of evaluation logic misplaced in the orchestrator, and presentation-layer code importing infrastructure modules directly. Additionally, agent-discovered bonus issues include a missing Redis None guard, dead code, a DI bypass, and duplicated `_call_llm` functions.

## Current State

- `backend/main.py` — 696 LOC, fan-out=15. The `websocket_endpoint` function (lines 404-685) handles session lifecycle, protocol parsing, dependency construction, idle-timeout logic, and teardown in one 281-line function body.
- `backend/pipeline/orchestrator.py` — 394 LOC, fan-out=11. Contains `_run_evaluation` (170 lines, lines 124-293) which is evaluation logic unrelated to real-time hint generation. Constructor takes 9 `Any`-typed parameters.
- Raw `redis.asyncio` client passed as `Any` to 8 modules. 11 Redis key patterns scattered across 8 files with no central registry.
- Only 1 abstract interface exists: `STTClient(ABC)` at `pipeline/stt.py:59`. Missing: LLMClient, SessionManager, AsyncRecognizer, DocumentParser protocols.
- `_call_llm()` duplicated byte-for-byte in `briefing/portrait.py:42` and `summarize/call_summary.py:43`.
- `orchestrator.py:117` calls `redis.set()` without None guard — crashes when Redis is unavailable.
- `_background_tasks` set is declared but never populated (dead code in teardown).
- `_run_evaluation` calls `get_settings()` at runtime, bypassing constructor dependency injection.

### Components

| Component | File | LOC | Issue |
|-----------|------|-----|-------|
| websocket_endpoint | `backend/main.py:404-685` | 281 | God function (C2) |
| PipelineOrchestrator | `backend/pipeline/orchestrator.py` | 394 | Feature envy (H3), 9x `Any` types |
| _run_evaluation | `backend/pipeline/orchestrator.py:124-293` | 170 | Wrong module (H3) |
| Redis usage | 8 files, 11 key patterns | — | No abstraction (H1) |
| STTClient ABC | `backend/pipeline/stt.py:59` | — | Only existing interface (H2) |
| _call_llm (portrait) | `backend/briefing/portrait.py:42` | ~20 | Duplicate (bonus) |
| _call_llm (summary) | `backend/summarize/call_summary.py:43` | ~20 | Duplicate (bonus) |
| HintContext, HintResponse | `backend/pipeline/llm.py:17,27` | — | DTOs in infra module (H4) |
| Transcript | `backend/pipeline/stt.py:45` | — | DTO in infra module (H4) |
| CallAnalytics | `backend/pipeline/post_call.py:33` | — | DTO with Redis methods (H4) |

### Behavior

- WebSocket endpoint accepts connections, parses binary/text frames, constructs LLMClient + SessionManager + PipelineOrchestrator inline, routes audio to STT, manages idle timeouts, and handles teardown — all in one function.
- Orchestrator generates real-time hints AND runs post-call evaluation (two separate concerns).
- Redis keys are defined ad-hoc in each module with no compile-time consistency guarantee.
- DTOs (HintContext, HintResponse, Transcript, CallAnalytics) live inside infrastructure modules, forcing callers to import heavy dependencies.

### Acceptance Criteria

- Given the `websocket_endpoint` function When extracted to `WebSocketHandler` class Then `main.py` websocket route is ≤5 lines and the handler class has named methods for each concern
- Given HTTP routes in `main.py` When extracted to `api/*.py` routers Then `main.py` is ≤100 LOC (composition root only)
- Given raw Redis usage in 8 files When `SessionStore` Protocol is created Then at least `session/manager.py` and `api/evaluation.py` use the Protocol instead of raw Redis
- Given 11 scattered Redis key patterns When centralized in `storage/keys.py` Then all 11 patterns are defined in one module with TTL constants
- Given `_run_evaluation` in orchestrator When extracted to `EvaluationRunner` class Then orchestrator drops by ~170 LOC and `_run_evaluation` is gone
- Given 1 of 5 needed interfaces When `LLMClientProtocol`, `SessionManagerProtocol`, `AsyncRecognizerProtocol`, `DocumentParserProtocol` are created Then all 5 interfaces exist as `runtime_checkable` Protocols
- Given 9 `Any` annotations in PipelineOrchestrator When replaced with proper types Then zero `Any` annotations remain in the class
- Given duplicated `_call_llm` in portrait.py and call_summary.py When deduplicated to `shared_llm.py` Then both files import from the shared module and no duplicate exists
- Given `orchestrator.py:117` has no Redis None guard When fixed Then `on_session_end` with `redis=None` returns empty string without raising
- Given `_background_tasks` set is never populated When cleaned up Then dead code is removed or properly wired
- Given `get_settings()` called at runtime in `_run_evaluation` When extracted to EvaluationRunner Then config values are passed via constructor (DI)
- **Given any refactored module When old import paths are used Then they still work via re-exports (backward compatibility)**
- Given all changes applied When existing test suite runs Then all tests pass with no regressions
- Given all changes applied When `ruff check .` and `mypy .` run Then zero errors
- Given `call_summary.py` accesses Redis directly When refactored to use `SessionStore` Then no raw Redis calls remain in `call_summary.py`
- Given `CallAnalytics` serialization is moved to local helpers When tested Then JSON field names match `CallAnalyticsWire` interface exactly (wire-contract test)

### Edge Cases

- **Concurrency**: Two `session_end` messages arriving concurrently — `_evaluation_started` flag is not atomic in async context. On-transcript callback in flight could interleave.
- **State**: `session_start` with empty `kb_id` creates orchestrator without scenario context. Client receives no degradation signal.
- **Data**: `eval_transcript:{session_id}` is deleted then re-populated atomically in `PostCallProcessor._store_results`. Process crash between delete and rpush loses transcript permanently.
- **Integration**: Redis key TTL mismatch — `session:{id}:kb_id` expires at 1800s but `kb:{id}:scenario` lives until 7200s. Reconnect at t=1900 gets empty scenario.
- **State**: `orchestrator.py:117` calls `redis.set()` without None guard — Redis unavailability crashes evaluation start.
- **Data**: `HintResponse.from_json` places no length limit on hint field — misbehaving LLM can send 100KB+ hint.
- **Integration**: SaluteSpeech token expiry during active gRPC stream classified as permanent auth failure instead of transient (token refresh needed).
- **Concurrency**: `_on_transcript` closure captures mutable `stt_failed` and `last_transcript_time` via nonlocal. After `WebSocketHandler` extraction, these become instance attributes. If `_handle_audio_frame` and `_handle_idle_timeout` share these attributes across concurrent coroutines, read-modify-write races can occur across `await` boundaries.
- **Integration**: `RedisStore` wrapper must preserve `decode_responses=False` flag. If changed, `lrange` returns `list[str]` instead of `list[bytes]` and `raw_analytics.decode()` raises `AttributeError`.
- **Integration**: `call_llm_simple` adds a 30s timeout where none existed. For large documents, briefing generation may exceed this timeout, causing HTTP 504s. Timeout must be configurable per caller.
- **Data**: `CallAnalytics` JSON serialization field names must remain identical to `CallAnalyticsWire` TypeScript interface. Field rename during refactoring silently breaks extension analytics display.

## Change History

### v1 (2026-03-14) — Initial specification
- ADDED: Initial specification from architecture review findings C2, H1, H2, H3, H4
- ADDED: Bonus fixes (None guard, dead code, DI bypass, _call_llm dedup)
- ADDED: Backward compatibility requirement (re-exports for old import paths)
- Plan: [v1](../docs/plans/2026-03-14-backend-arch-fixes.md)

### v2 (2026-03-14) — Post-review edge cases and fixes
- ADDED: Edge cases from multi-agent review (closure captures, decode_responses, timeout behavior change, CallAnalytics wire contract)
- ADDED: Acceptance criteria for call_summary.py SessionStore migration and CallAnalytics wire-contract test
- MODIFIED: SessionStore Protocol — pipeline() replaced with typed domain methods (add_utterance, store_eval_transcript)
- MODIFIED: Out of Scope — eval token query-string logged as deferred security task (FEAT-00X)
- Plan: [v1](../docs/plans/2026-03-14-backend-arch-fixes.md) (updated in place)

### v3 (2026-03-14) — Round 2 review fixes
- ADDED: Edge cases — _evaluation_task cancelled on disconnect, re-entrant session_start idempotency, REST URL double-prefix risk
- ADDED: Acceptance criteria — on_session_end return type contract (-> str), asyncio.Lock on _evaluation_started, _evaluation_task teardown in finally block, DI strategy via request.app.state.settings, MULTI/EXEC atomicity, portrait.py SessionStore migration, MAX_HINT_CHARS validation
- MODIFIED: store_eval_transcript signature — session_id: str (not key: str)
- Plan: [v1](../docs/plans/2026-03-14-backend-arch-fixes.md) (updated in place)
