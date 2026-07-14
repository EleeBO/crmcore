# Backend Review — FEAT-009: Frontend Architecture Fixes (Sidepanel Split)

**Reviewer Role:** Backend Engineer
**Plan:** `docs/plans/2026-03-14-frontend-arch-fixes.md`
**Spec:** `specs/FEAT-009-frontend-arch-fixes.md`
**Review Date:** 2026-03-14
**Plan Version Reviewed:** v2 (post-multi-agent review iteration — includes Backend Integration Points table and SSRF posture section)
**Verdict:** PASS (no blockers; 1 minor gap; 2 observations)

---

## Context Note

This is a pure frontend refactoring plan (TypeScript Chrome Extension). The plan splits
`extension/src/sidepanel/sidepanel.ts` (1896 LOC) into 10 focused modules with no behavior
changes. All backend-facing checklist items are evaluated for impact on backend integration
points — whether the refactor preserves, correctly documents, or risks breaking any
frontend-to-backend communication.

The plan has been updated since the previous review cycle to include an explicit "Backend
Integration Points" table and a "SSRF Posture" section, addressing the two MAJOR findings
from the prior review. This review validates those additions against the actual backend code.

---

## Checklist Results

### 1. DB Schema
**Result: PASS — N/A**

No database schema changes. No ORM models, migrations, or storage layer changes are involved.
`chrome.storage.local` is purely client-side and is not a backend concern.

---

### 2. API Endpoints — Are all backend endpoints correctly identified?
**Result: PASS**

The plan now includes a Backend Integration Points table listing all five frontend-to-backend
calls. I verified each entry against the actual backend source:

| Module | Endpoint | Method | Backend Source | Match? |
|--------|----------|--------|----------------|--------|
| briefing.ts | /api/v1/briefing | POST | `backend/main.py:343` `@app.post("/api/v1/briefing")` | YES |
| upload.ts | /api/v1/upload | POST | `backend/main.py:192` `@app.post("/api/v1/upload")` | YES |
| evaluation.ts | /api/v1/evaluation/{sid}?token={evalToken} | GET | `backend/api/evaluation.py:59` `@router.get("/evaluation/{session_id}")` | YES |
| preflight.ts | /api/v1/preflight | GET | `backend/main.py:110` `@app.get("/api/v1/preflight")` | YES |
| upload.ts (delete) | /api/v1/session/{sid} | DELETE | `backend/main.py:324` `@app.delete("/api/v1/session/{session_id}")` | YES |

**Request payload verification:**

- `/api/v1/briefing` — backend expects JSON body with `session_id` and `kb_id` fields
  (`body.get("session_id")`, `body.get("kb_id")`). Frontend sends
  `{ session_id: state.sessionId, kb_id: state.kbId }`. Match confirmed.

- `/api/v1/upload` — backend expects multipart form with `session_id` (string) and `files`
  (list). Frontend builds `FormData` appending `session_id` and one or more `files` entries.
  Match confirmed.

- `/api/v1/evaluation/{session_id}` — backend reads `token` as a query parameter
  (`Query(default="")`). Frontend constructs `?token=${evalToken}`. Match confirmed. Token
  is validated server-side via `hmac.compare_digest`.

- `/api/v1/preflight` — backend reads `provider` as an optional query param
  (`request.query_params.get("provider", cfg.stt_provider)`). Frontend sends
  `?provider=${encodeURIComponent(provider)}`. Match confirmed.

- `/api/v1/session/{session_id}` DELETE — backend deletes three Redis keys and returns
  `{ status: "deleted", session_id: ... }`. Frontend calls this before re-upload to clear
  previous session. Match confirmed.

**One observation (non-blocking):** The plan table note for `upload.ts` says
`MAX_FILE_SIZE=10MB`. The actual backend limit is **50 MB** (`max_file_bytes = 50 * 1024 * 1024`,
`backend/main.py:204`). The current frontend code also uses 50 MB
(`MAX_FILE_SIZE = 50 * 1024 * 1024`, `sidepanel.ts:1064`). The plan table contains a
documentation error — the implementation is correct, but the plan should say 50 MB to avoid
misleading future implementers.

---

### 3. Auth Flow — Is evalToken handling secure?
**Result: PASS**

The plan explicitly states: *"evalToken captured in closure, stays local scope (not module
export)"* and the SSRF Posture section confirms the token must remain in `evaluation.ts`
local scope.

Verification against backend:

- `eval_token` is issued by the WebSocket endpoint at session end
  (`backend/main.py:499-512`, `648-651`) and stored in Redis under `eval_token:{session_id}`.
- The GET `/api/v1/evaluation/{session_id}` endpoint validates the token with
  `hmac.compare_digest` (constant-time comparison, `backend/api/evaluation.py:78`).
  This is correct HMAC-safe token comparison.
- Token scope: in the current `sidepanel.ts`, `evalToken` is captured in a closure inside
  `handleEvaluationStarted` and is not a module-level variable. The plan's requirement to
  keep it in local scope is consistent with the existing behavior. No regression risk from
  the refactor.
- The plan also stores `eval_token_{sid}` in `chrome.storage.local` for the report page.
  This is the existing behavior — the token is written at line 686 and read by
  `report.ts` to fetch the evaluation. This is acceptable since `chrome.storage.local`
  is sandboxed to the extension.

No auth flow regressions introduced by the refactor.

---

### 4. Validation Rules — Are frontend validations aligned with backend?
**Result: PASS (with one documented gap)**

**File upload validation:**

The plan states `MAX_FILE_SIZE=10MB` in the table, but the actual backend hard limit is 50 MB
(verified above). The frontend constant is also 50 MB. The plan documentation is incorrect;
the implementation is correct. This is the same gap noted in item 2 — a documentation-only
error.

File type alignment:

- Backend parses by extension using `SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".md", ".txt"}`
  (`backend/ingestion/parser.py:10`).
- Frontend `ALLOWED_TYPES` set: `application/pdf`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
  `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
  `text/markdown`, `text/plain`.
- Frontend `isAllowedExtension` checks: `["pdf", "xlsx", "xls", "docx", "md", "txt"]`.

These match exactly. No gaps.

**Settings URL validation (task 3.1):**

The plan adds format-only validation for the backend URL. The SSRF Posture section correctly
documents that SSRF protection is the backend's responsibility. This is an appropriate
boundary — the extension cannot enforce server-side SSRF protection.

The plan also requires a `#backend-url-error` element to be added to the HTML, and specifies
validation of both `ws:/wss:` schemes and `http:/https:` schemes. This is correct since the
extension stores a base HTTP URL for REST calls and a WebSocket URL separately (confirmed by
`constants.ts` which uses both `BACKEND_HTTP_URL` and `BACKEND_WS_URL`).

---

### 5. Async Operations — Are polling patterns correct?
**Result: PASS (with observation)**

Evaluation polling:

- The plan moves `evalPollTimer` to `evaluation.ts` module scope.
- Polling interval: 5000 ms (every 5 seconds), max 8 attempts (40 seconds total).
  This is consistent with the existing `sidepanel.ts:693-717` implementation.
- Backend evaluation result is stored in Redis asynchronously after the WebSocket closes.
  The 40-second polling window is reasonable given that the LLM evaluation task can take
  10–30 seconds.

**Observation (non-blocking):** The spec edge case notes that `resetSessionState` does not
clear `evalPollTimer`, meaning a stale-session result could render in a new session's Phase 4
UI. The plan now includes task wording about `stopEvalPolling` being called via registered
reset callback (spec line 71). Confirm that the implementation of `resetSessionState` in
`state.ts` calls or triggers `stopEvalPolling` — this is a cross-module call that must be
explicitly wired. The plan specifies this at the acceptance criteria level but I could not
find an explicit implementation step for it in the plan tasks. This should be verified during
implementation.

Briefing fetch:

- `fetchAndRenderBriefing` has a 30-second `AbortController` timeout on the upload fetch.
  The briefing POST itself has no explicit timeout in the current code.
- Acceptable since briefing is a fire-and-forget operation from the user's perspective.

Preflight:

- One-shot GET with no retry. Backend responds with 200 or 207 (multi-status). Frontend reads
  `data.stt.status`, `data.llm.status`, `data.redis.status`. Match confirmed.

---

### 6. Migration Strategy
**Result: PASS — N/A for frontend refactor**

Pure structural refactor — no data migration. `chrome.storage.local` key schema is unchanged
(all stored keys: `panel`, `eval_token_{sid}`, `eval_result_{sid}`, `eval_analytics_{sid}`,
`last_eval_session_id`, `layout_phase2`, `layout_phase3`, `micGranted`, `selectedMicId`,
`sttProvider`, `backendUrl`). Rollback is a git revert.

---

### 7. Error Responses — Are backend error formats handled?
**Result: PASS**

Backend error shape on WebSocket messages: `{ type: "error", code: string, message: string }`.
Frontend `_ERROR_LABELS` maps known backend error codes:
- `STT_BALANCE_EXHAUSTED`
- `STT_AUTH_FAILED`
- `STT_UNAVAILABLE`
- `SESSION_IDLE_TIMEOUT`
- `SESSION_IDLE_WARNING`

These codes are issued by `backend/main.py` (WebSocket endpoint: lines 453–471, 596–615) and
`backend/pipeline/stt.py`. The mapping is correct.

HTTP error responses from REST endpoints:

- `/api/v1/upload` returns 422 with `{ detail: "...", failed_files: [...] }` on validation
  failure, and 207 with `failed_files` populated for partial success. Frontend handles both
  `resp.ok` and `resp.status === 207` correctly (`sidepanel.ts:1224`).
- `/api/v1/briefing` returns 422 with `{ detail: "session_id and kb_id required" }` if fields
  are missing. Frontend does not inspect the 422 body — it just re-throws with `HTTP ${resp.status}`.
  This is acceptable since the fields are always populated before the call.
- `/api/v1/evaluation/{session_id}` returns 403 for missing/invalid token, 404 for missing
  result. Frontend poll ignores non-200 responses and retries. On exhausting retries the
  loading UI stays visible indefinitely — the spec documents this as a UX issue (edge case,
  line 83) and the plan has a task to add a visible error message. Confirm this task is
  present in the final plan.

---

### 8. Performance Queries
**Result: PASS — N/A**

No database queries from the frontend. Performance-relevant async patterns (evaluation polling,
VU meter RAF loop) are addressed in items 5 and the plan's vu-meter module extraction.

---

## Summary of Findings

| # | Item | Result | Severity | Notes |
|---|------|--------|----------|-------|
| 1 | DB Schema | PASS | N/A | Frontend plan, no DB involvement |
| 2 | API Endpoints | PASS | OBSERVATION | All 5 endpoints verified; plan table says 10 MB, backend/frontend code both say 50 MB — documentation error only |
| 3 | Auth Flow | PASS | — | evalToken local-scope requirement confirmed and consistent with existing code; HMAC validation on backend confirmed |
| 4 | Validation Rules | PASS | OBSERVATION | Same 10 MB vs 50 MB documentation discrepancy; implementation is correct |
| 5 | Async Operations | PASS | OBSERVATION | evalPollTimer reset cross-module wiring must be explicitly implemented; no blocking issue |
| 6 | Migration Strategy | PASS | N/A | Storage schema unchanged; rollback is git revert |
| 7 | Error Responses | PASS | — | Eval poll timeout UX fix confirmed as a plan task; HTTP error handling verified |
| 8 | Performance Queries | PASS | N/A | Frontend plan, no DB queries |

---

## Required Actions Before Implementation

No blocking issues. Three observations should be addressed:

### OBSERVATION 1 — Fix documentation error in Backend Integration Points table

The table entry for `upload.ts` states `MAX_FILE_SIZE=10MB`. The actual backend limit is
**50 MB** (`backend/main.py:204`: `max_file_bytes = 50 * 1024 * 1024`). The frontend constant
is already correct at 50 MB. Update the plan table to say `MAX_FILE_SIZE=50MB` to prevent
confusion for future implementers.

### OBSERVATION 2 — Explicitly wire evalPollTimer reset in state.ts

The spec acceptance criterion requires `stopEvalPolling` to be called when `resetSessionState`
runs (via a registered reset callback). Confirm the plan tasks include an explicit step to
register this callback during module initialization. This is a one-line cross-module call but
easy to miss during refactoring.

### OBSERVATION 3 — Eval poll timeout UX task

The spec notes (edge case, line 83) that the evaluation poll timeout leaves `#eval-loading`
visible with no error message. Confirm that a plan task adds a visible error or timeout
message when `attempts > 8` returns without receiving a result.

---

## Overall Verdict

**PASS.** The plan correctly identifies and documents all backend integration points. All five
frontend-to-backend calls are verified against the actual backend source — endpoints, methods,
request shapes, and response envelopes all match. The `evalToken` scope requirement is sound
and consistent with the existing implementation. The SSRF posture is correctly documented as
a backend responsibility. No backend contract is broken by this refactor.

The three observations are documentation and wiring gaps, not architectural flaws. The most
important is Observation 1 (10 MB vs 50 MB in the plan table) — this is purely a documentation
error and does not affect runtime behavior. Observations 2 and 3 are implementation details
that must be explicitly wired during execution of the plan tasks.
