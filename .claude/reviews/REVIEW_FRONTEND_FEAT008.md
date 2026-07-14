# Frontend Review — FEAT-008: Backend Architecture Fixes

**Reviewer Role:** Frontend Engineer
**Plan:** Backend Architecture Fixes (god function extraction, storage abstraction, interface creation,
evaluation logic separation, dependency violation fixes)
**Date:** 2026-03-14
**Verdict:** CONDITIONAL PASS — 1 BLOCKING finding, 2 ADVISORY findings

---

## Scope and Approach

This is a pure backend structural refactoring. The reviewer examined all frontend files that
communicate with the backend to verify that no API contract, WebSocket protocol, TypeScript
interface, or error-response format is broken by the proposed changes.

Files inspected:

- `extension/src/lib/ws-client.ts` — binary WebSocket frame encoding
- `extension/src/shared/messages.ts` — WsMessage union, all downstream message shapes
- `extension/src/shared/types.ts` — HintPayload, AudioFrame, ControlFrame
- `extension/src/shared/evaluation-types.ts` — CallAnalyticsWire, WsEvaluationResult, etc.
- `extension/src/sidepanel/sidepanel.ts` — all HTTP calls and WS message handlers
- `extension/src/report/report.ts` — analytics rendering, REST polling
- `extension/src/settings/evaluation-settings.ts` — evaluation-config GET/PUT/reset
- `extension/src/shared/constants.ts` — hardcoded URL base and WS path
- `backend/main.py` — current route and WebSocket handler implementation
- `backend/pipeline/llm.py` — HintContext, HintResponse DTOs
- `backend/pipeline/post_call.py` — CallAnalytics serialization
- `backend/pipeline/orchestrator.py` — _run_evaluation, analytics payload construction
- `backend/api/evaluation.py` — /evaluation/{sid} REST endpoint
- `backend/pipeline/evaluation_schemas.py` — EvaluationConfig, CriterionResult, CallEvaluation
- `backend/session/manager.py` — Redis key patterns used by frontend indirectly

---

## Checklist

### 1. UI States — N/A

No frontend UI components are created or modified. No new loading, error, empty, or success states
are introduced by this plan. All UI state transitions remain under existing frontend code that is
not touched.

### 2. Component Hierarchy — N/A

No extension components, popup pages, or settings pages are added or restructured. Not applicable.

### 3. Server/Client Boundaries — WebSocket and REST contract review below

See findings 3a through 3f.

### 4. Form Validation (Request/Response Schemas) — PASS with ADVISORY

The evaluation settings page submits `{ criteria: CriterionData[], model: string }` to
`PUT /api/v1/evaluation-config`. The backend accepts `EvaluationConfig` (Pydantic). The plan
centralizes the `eval_config:default` Redis key in `storage/keys.py` but does not change the Pydantic
model or endpoint shape. Schema is preserved. See finding 3f for the key name stability advisory.

### 5. Optimistic Updates — N/A

The extension does not perform optimistic updates. The evaluation polling loop
(`evalPollTimer` in `sidepanel.ts:693-717`) retries `GET /api/v1/evaluation/{sid}?token=...` every
5s up to 8 attempts. The plan does not change polling behavior on the backend. No action required.

### 6. Accessibility — N/A

No HTML or UI changes. Not applicable.

### 7. Responsive Breakpoints — N/A

No CSS or layout changes. Not applicable.

### 8. Error Boundaries — PASS

Error message formats for WebSocket errors are defined in `messages.ts`:

```typescript
interface WsError { type: "error"; code: string; message: string; }
interface WsEvaluationError { type: "evaluation_error"; session_id: string; code: string; message: string; }
```

The backend emits these in `main.py` (websocket_endpoint) and `orchestrator.py`
(_run_evaluation). The plan extracts them into `WebSocketHandler` and `EvaluationRunner`
respectively. The field names are not renamed. The sidepanel error display
(`handleBackendError` in `sidepanel.ts:583-616`) maps error codes to Russian labels using
a hardcoded dict; those codes (`STT_BALANCE_EXHAUSTED`, `STT_AUTH_FAILED`, etc.) are defined
in the backend's `_on_stt_error` handler and are not changed by this plan.

The REST error responses (HTTP 403/404 from `/api/v1/evaluation/{sid}`) are not rendered directly
in UI — the sidepanel only checks `resp.ok` and falls back to the next poll attempt. No action
required.

---

## API Contract Analysis

### 3a. WebSocket Binary Frame Protocol — PASS

The extension `WsClient` (`ws-client.ts`) encodes frames as a 5-byte header (4-byte uint32 LE
sequence + 1-byte channel 0 or 1) followed by the payload. The backend decodes this in
`pipeline.audio.parse_frame()` and dispatches on `FrameType.AUDIO` / `FrameType.CONTROL`.

The plan's task 2.2 extracts the `websocket_endpoint` function body into a `WebSocketHandler`
class in `ws/handler.py`. The binary frame parsing uses `parse_frame` which is not being modified
— it is just called from a new call site inside `WebSocketHandler._handle_audio_frame()`.

The wire format is determined by `parse_frame`, not by `websocket_endpoint`. Moving the call site
does not change what bytes are accepted on the wire.

**Risk: NONE.**

### 3b. Upstream Control Message Shape — PASS

The extension sends two control JSON messages through the channel-1 binary frames:

- `session_start`: fields `type`, `session_id`, `kb_id`, `stt_provider` (optional)
- `session_end`: field `type`

Both are also sent as plain text frames by the offscreen document as a fallback (see
`main.py:491-515`). The plan moves parsing of these into `WebSocketHandler._handle_session_start()`
and `WebSocketHandler._handle_session_end()`. The plan explicitly states backward compat re-exports
are preserved. The field name parsing (`ctrl.get("session_id", "ws-anon")`, etc.) is a verbatim
move.

**Risk: NONE.** Provided the implementer copies the field-name parsing exactly.

### 3c. Downstream WebSocket Message Types — PASS

The extension `WsMessage` union covers 8 types. Their JSON shapes are locked in TypeScript and
the backend produces them by explicit `send_json({"type": ..., ...})` calls. The plan extracts
these call sites into new classes but does not rename any fields.

Current outbound messages verified against TypeScript interfaces:

| Backend call site | TS interface | Fields match |
|---|---|---|
| `hint_end` (orchestrator.py:381-392) | `WsHintEnd extends HintPayload` | YES: hint, source, sentiment, color, coaching, relevance |
| `transcript` (orchestrator.py:64-74) | `WsTranscript` | YES: type, speaker, text, is_final, utterance_id |
| `error` (main.py:605-615) | `WsError` | YES: type, code, message |
| `evaluation_started` (main.py:507-512) | `WsEvaluationStarted` | YES: type, session_id, eval_token |
| `evaluation_result` (orchestrator.py:260-267) | `WsEvaluationResult` | YES: type, session_id, eval_token, evaluation, analytics? |
| `evaluation_error` (orchestrator.py:284-291) | `WsEvaluationError` | YES: type, session_id, code, message |

**Note:** The `analytics` field in `WsEvaluationResult` is conditionally included when
`analytics is not None` (orchestrator.py:266). The extension types it as `analytics?: CallAnalyticsWire`,
meaning absence is valid. After `EvaluationRunner` extraction, the implementer must confirm this
conditional pattern is preserved — do not default it to `null` or `{}`.

**Risk: LOW.**

### 3d. CallAnalytics JSON Serialization — BLOCKING

**Severity: BLOCKING**

The extension's `CallAnalyticsWire` TypeScript interface (`evaluation-types.ts:28-40`) defines
exactly 11 fields mapped by name:

```typescript
interface CallAnalyticsWire {
  total_duration_s: number;
  rep_talk_ratio: number;
  rep_talk_time_s: number;
  client_talk_time_s: number;
  rep_speech_rate_wpm: number;
  client_speech_rate_wpm: number;
  interruptions_by_rep: number;
  interruptions_by_client: number;
  avg_rep_pause_before_response_s: number;
  rep_word_count: number;
  client_word_count: number;
}
```

This interface is used in three locations:

1. `sidepanel.ts:703` — REST polling destructures `{ analytics, ...evalData }` from the response
   and passes `analytics` to `renderEvaluationSummary` and stores in chrome.storage
2. `sidepanel.ts:735` — WS message stores `msg.analytics ?? null`
3. `report.ts:56,73,107-111,182-184` — renders every field by name

The backend constructs the analytics payload in `orchestrator.py:245-258` as an inline dict that
explicitly names all 11 fields. The plan's task 1.1 moves `CallAnalytics` (and implicitly its
serialization logic) to `pipeline/types.py` and removes `to_redis_json`/`from_redis_json` from the
dataclass, replacing them with "local helper functions" inside `PostCallProcessor._store_results()`.

**The concern:** The plan introduces a `CallAnalytics.to_dict()` method (or equivalent) for the
WebSocket payload serialized in `orchestrator.py`. If the implementer renames any field during
the refactoring (e.g., renaming `avg_rep_pause_before_response_s` to `avg_pause_s` to reduce
verbosity), every metric silently becomes `undefined` in the extension UI with no compile-time
error, because TypeScript does not validate incoming JSON at runtime.

The existing code `orchestrator.py:245-258` constructs the analytics dict manually with hardcoded
key names. If this is replaced by `analytics.to_dict()` or `dataclasses.asdict(analytics)`, the
field names come from the Python attribute names on the dataclass. Those are currently identical
to the TypeScript interface names — but there is no test enforcing this correspondence.

Additionally, the `report.ts:22-34` has a LOCAL copy of `CallAnalyticsWire` (not imported from
`evaluation-types.ts`) and `sidepanel.ts` imports it from `evaluation-types.ts`. If either copy
drifts from the other, the report page and sidepanel will render different data.

**Required action:** The plan must include an explicit requirement that the JSON keys produced by
the new serialization helper exactly match the existing 11 field names. A wire-contract test must
be added (already referenced in the plan as "Wire-contract test added" for DTO extraction) that
asserts:

```python
def test_call_analytics_wire_contract():
    """JSON keys must match TypeScript CallAnalyticsWire exactly."""
    from backend.pipeline.types import CallAnalytics  # new location
    a = CallAnalytics(
        total_duration_s=60.0, rep_talk_time_s=30.0, client_talk_time_s=30.0,
        rep_talk_ratio=0.5, rep_speech_rate_wpm=120.0, client_speech_rate_wpm=100.0,
        rep_word_count=60, client_word_count=50,
        interruptions_by_rep=2, interruptions_by_client=1,
        avg_rep_pause_before_response_s=1.5,
    )
    payload = a.to_wire_dict()  # whatever the new method is called
    expected_keys = {
        "total_duration_s", "rep_talk_ratio", "rep_talk_time_s",
        "client_talk_time_s", "rep_speech_rate_wpm", "client_speech_rate_wpm",
        "interruptions_by_rep", "interruptions_by_client",
        "avg_rep_pause_before_response_s", "rep_word_count", "client_word_count",
    }
    assert set(payload.keys()) == expected_keys
```

**Risk: HIGH.** This is the only place in the codebase where a Python dataclass field name is
the sole binding to a TypeScript interface field name with no compiler enforcement. Any rename
during refactoring causes silent UI breakage in production.

### 3e. REST Endpoint URL Paths — ADVISORY

**Severity: ADVISORY**

The extension uses hardcoded URL paths via `API_BASE = "http://localhost:8000/api/v1"` and
`BACKEND_WS_URL = "ws://localhost:8000/ws"` in `constants.ts`. The following paths are called:

| Endpoint | Extension call site |
|---|---|
| `POST /api/v1/upload` | `sidepanel.ts:1216` |
| `POST /api/v1/briefing` | `sidepanel.ts:1388` |
| `GET /api/v1/preflight?provider=` | `sidepanel.ts:1489` |
| `DELETE /api/v1/session/{sid}` | implicit via STOP_SESSION offscreen flow |
| `GET /api/v1/evaluation/{sid}?token=` | `sidepanel.ts:699`, `report.ts:98` |
| `GET /api/v1/evaluation-config` | `evaluation-settings.ts:29` |
| `PUT /api/v1/evaluation-config` | `evaluation-settings.ts:193` |
| `POST /api/v1/evaluation-config/reset` | `evaluation-settings.ts:175` |
| `ws://localhost:8000/ws` | `ws-client.ts` via `BACKEND_WS_URL` |

The plan's task 2.2 extracts handlers into `api/health.py`, `api/upload.py`, `api/session.py`,
`api/briefing.py`, `api/summarize.py`. The `api/evaluation.py` already exists. When these are
mounted with `app.include_router(router, prefix="/api/v1")` in the new `main.py` composition root,
the URL paths are preserved.

The concern is the existing `/api/v1` prefix registration. Currently `main.py` registers routes
directly with `@app.get("/api/v1/health")` etc. After extraction to routers without a prefix, the
router path would be `/health` and the mount prefix `/api/v1` gives the correct full path. If a
router already declares `/api/v1/...` paths and is also mounted with prefix `/api/v1`, the result
is a double prefix `/api/v1/api/v1/...`. This pattern is a known FastAPI pitfall.

The existing `api/evaluation.py` is already mounted at `prefix="/api/v1"` (main.py:689) and
correctly uses `/evaluation/{session_id}` (no `/api/v1` prefix in the decorator). The new routers
must follow the same pattern.

**Recommendation:** The Definition of Done for task 2.2 should include a smoke test that issues
one request to each extracted endpoint and verifies HTTP 200 (or expected status), not a 404.

**Risk: LOW** if the implementer follows the existing `api/evaluation.py` pattern exactly.

### 3f. Redis Key Stability for eval_config — ADVISORY

**Severity: ADVISORY (informational)**

The evaluation settings page (`evaluation-settings.ts`) reads from and writes to
`GET/PUT /api/v1/evaluation-config`. The backend uses Redis key `"eval_config:default"` (defined
in `api/evaluation.py:13`). The plan moves this to `storage/keys.py` as a centralized key
registry.

As long as the key function in `storage/keys.py` returns the string `"eval_config:default"`,
behavior is unchanged. If the key format changes (e.g., `"eval_config:{model}:default"`), any
existing Redis data stored under the old key becomes invisible to the new code, and the settings
page would silently show default values.

This is low risk because the plan mentions "no behavior changes" and the key name change would
be visible in code review. It is noted here because the key is the only persistent configuration
that the extension's evaluation settings page writes.

**Risk: LOW.**

### 3g. LLM Timeout Behavior Change — ADVISORY

**Severity: ADVISORY**

The plan notes that `call_llm_simple()` adds a 30s timeout (described as "behavior change —
configurable per caller"). This function is used in evaluation and scenario generation, not in
the real-time hint pipeline. From the extension's perspective:

- The evaluation result may take slightly longer or arrive faster depending on the timeout behavior
- The REST polling loop in `sidepanel.ts:693-717` retries for 40s total (8 attempts × 5s). If
  evaluation LLM calls now have a hard 30s timeout, a previously-succeeding evaluation that took
  35s would now fail with `EVAL_LLM_TIMEOUT`.
- The briefing POST request in `sidepanel.ts:1388` has no explicit timeout on the frontend side
  (the upload flow has a 30s abort controller, but the briefing fetch does not). If the scenario
  generation LLM call now takes longer due to timeout retry logic, the briefing request could
  appear to hang.

**Recommendation:** Confirm that the 30s timeout applies to per-attempt calls and that callers
in the evaluation pipeline handle `EvalLLMTimeoutError` before the polling window expires.
Confirm the briefing POST still completes within a reasonable time under the new timeout regime.

**Risk: LOW** as long as the 30s timeout is per attempt and not total pipeline time.

---

## Closure State Warning

The plan notes: "Closure captures mutable state after WebSocketHandler extraction." This is the
most subtle correctness risk in the plan. In the current `main.py`, the idle timeout tracking
uses nonlocal variables:

```python
last_transcript_time: float = 0.0
idle_warning_sent: bool = False
stt_failed: bool = False
```

These are mutated by closures (`_on_transcript`, `_on_stt_error`). If the extraction into
`WebSocketHandler` moves these to instance attributes but the closures still reference the local
variables (or vice versa), the idle timeout and balance error detection will silently stop working.

From the extension's perspective, the symptom would be:
- No `SESSION_IDLE_WARNING` or `SESSION_IDLE_TIMEOUT` error messages reaching the extension
- No `STT_BALANCE_EXHAUSTED` error sent to extension when balance is exhausted

The extension's `handleBackendError` in `sidepanel.ts:583-616` depends on receiving these error
codes to terminate the UI session and cache the balance error. Silent failures here would leave
the extension in a stuck "recording" state.

**Recommendation:** Add a test that verifies `SESSION_IDLE_TIMEOUT` is sent when no audio is
received for `session_idle_timeout_s` seconds, after the `WebSocketHandler` refactoring is complete.

---

## Summary

| Finding | Area | Severity | Status |
|---|---|---|---|
| 3d | CallAnalytics JSON serialization | BLOCKING | Must add wire-contract test |
| 3e | REST URL path double-prefix risk | ADVISORY | Follow existing router pattern |
| 3g | LLM timeout behavior change | ADVISORY | Verify polling window compatibility |
| Closure | Mutable state capture | ADVISORY | Add idle timeout regression test |
| 3a | WS binary frame protocol | PASS | Move is wire-neutral |
| 3b | Upstream control message shape | PASS | Field names unchanged |
| 3c | Downstream WS message types | PASS | Straight move, conditional analytics |
| 3f | eval_config Redis key | PASS | Key name stability informational only |
| 8 | Error response formats | PASS | Code strings unchanged |

---

## Required Actions

**BLOCKING — must resolve before implementation proceeds:**

1. **(3d)** Add an explicit contract test in `tests/test_types.py` (or equivalent) that asserts
   the JSON field names produced by the new `CallAnalytics` serialization method exactly match the
   11 field names in `CallAnalyticsWire`. The plan already references "Wire-contract test added"
   for DTO extraction — confirm this covers the analytics payload, not just `CallEvaluation`.

**ADVISORY — address in implementation or review:**

2. **(3e)** Verify all extracted routers use paths without `/api/v1` prefix in their decorators
   and are mounted with `prefix="/api/v1"`. Run a curl smoke test against each extracted endpoint
   after composition root is assembled.

3. **(3g)** Confirm the 30s `call_llm_simple()` timeout is per-attempt and does not cause
   evaluation to fail before the extension's 40s polling window expires.

4. **(Closure)** Add an integration test for `SESSION_IDLE_TIMEOUT` after `WebSocketHandler`
   extraction to verify the idle state mutation is not silently broken.

---

## Overall Verdict

**CONDITIONAL PASS.** The refactoring is well-scoped and does not introduce new frontend-facing
features or modify any frontend code. The structural changes are correct in intent. The single
blocking issue is the `CallAnalytics` serialization format: Python dataclass field names are the
only binding to TypeScript interface field names, and there is currently no test enforcing that
correspondence. Adding the wire-contract test fully resolves this risk. The advisory items are
low-probability but worth tracking during implementation review.
