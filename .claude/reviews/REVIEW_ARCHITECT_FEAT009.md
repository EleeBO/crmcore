# Architecture Review — FEAT-009: Frontend Architecture Fixes (Sidepanel Split)

**Reviewer:** Architect Agent
**Date:** 2026-03-14
**Plan:** `docs/plans/2026-03-14-frontend-arch-fixes.md`
**Spec:** `specs/FEAT-009-frontend-arch-fixes.md`
**Source Verified:** `extension/src/sidepanel/sidepanel.ts` (1896 lines, read in full)
**Config Verified:** `extension/package.json`, `extension/tsconfig.json`

---

## Summary

The plan proposes splitting a 1896-line god module into 10 focused ES modules with unit tests, plus three bonus fixes (error boundaries, settings URL validation, aria-live regions). The decomposition is architecturally sound, the module boundaries are clearly motivated by the source, and the dependency graph is largely accurate. However, two issues are blockers that must be resolved before implementation begins, and several lower-severity findings need to be addressed before task 2.5.

---

## Checklist Evaluation

### 1. System Boundaries — PASS with caveat

The plan identifies 20 logical concerns and maps them to 10 output modules. The decomposition is defensible and matches what actually exists in the source:

- `helpers.ts` / `splitter.ts` — pure utilities with no circular risk
- `state.ts` / `phase-engine.ts` — the core state machine forming the foundation layer
- `port.ts`, `capture.ts`, `vu-meter.ts`, `call-timer.ts` — connection and call lifecycle layer
- `evaluation.ts`, `hint.ts`, `transcript.ts`, `ws-dispatch.ts` — live data rendering layer
- `upload.ts`, `briefing.ts` — pre-call data preparation layer
- `settings.ts`, `mic.ts`, `preflight.ts`, `rec-button.ts` — controls and configuration layer

The layered structure is correct. Each layer only depends on the one below it, with the notable resolved exception of `phase-engine ↔ rec-button`.

**Caveat:** The plan's Feature Inventory maps `initNewCallButton` and `downloadTranscript`/`initDownloadButton` to task 2.4, but the task 2.5 entry-point sketch shows `import { initDownloadButton } from './transcript'`. The function logically belongs in `transcript.ts` by concern (it reads `#transcript-full-list`), but the Feature Inventory must match the import sketch. This inconsistency will confuse the implementer during task 2.4. Resolve before task 2.4 begins.

---

### 2. Data Flow — FAIL (BLOCKER)

**Problem: Cross-module shared mutable state is specified in principle but not in practice.**

The plan states that "module-level `let` exports use getter/setter/reset functions" but does not enumerate which variables require this treatment. Source analysis reveals three concrete gaps:

**Gap A — `sttBalanceError` / `sttBalanceErrorTime` (source lines 579–581):**
These are written by `handleBackendError` (line 600, future `capture.ts`), read by the REC button handler (line 1562, future `rec-button.ts`), and reset by the provider-change listener (line 1766, future `settings.ts`). Three different modules touching two variables that will be privately owned by `capture.ts`. The plan does not define a `resetBalanceError()` export or a `getBalanceError()` getter. Without these, the implementer in tasks 2.1 and 2.4 will independently invent inconsistent patterns — or will silently omit the cross-module reset.

**Gap B — `lastHintRenderedAt`, `pendingHintEnd`, `pendingHintTimer` (source lines 860–862):**
`handleCaptureStarted` (line 550–552) resets all three. After the split, these live in `hint.ts` but `handleCaptureStarted` lives in `capture.ts`. The plan's dependency graph does not show a `capture → hint` edge. Without an exported `resetHintState()` function in `hint.ts`, this cross-module reset is either silently dropped (causing hints from previous sessions to be suppressed for 8 seconds into a new call) or forces `capture.ts` to import from `hint.ts` without the edge being documented.

**Gap C — `isAutoScrolling` (source line 954):**
Reset in `handleCaptureStarted` (line 553) and written in `initTranscriptScroll` (line 1049). After the split, `capture.ts` would need to call `resetAutoScroll()` on `transcript.ts`. This edge is also absent from the plan's dependency graph. The omission is confirmed in the spec's own Edge Cases section: "handleCaptureStarted cross-module state resets" is listed as a known edge case, but no task addresses it with concrete implementation steps.

**Resolution required:** Before task 2.1, add explicit getter/setter/reset function names to the plan for each of the above variables, and update the dependency graph to include `capture → hint` and `capture → transcript` edges.

---

### 3. Technology Choices — FAIL (BLOCKER)

**Problem: Test infrastructure does not exist, and task 0.1 is underspecified.**

`extension/package.json` has four devDependencies: `@types/chrome`, `typescript`, `vite`, and `vite-plugin-web-extension`. There is no test runner, no jsdom, no chrome mock library, and no `test` script. `extension/tsconfig.json` has `"include": ["src/**/*.ts"]` — it explicitly excludes anything outside `src/`, which would exclude `src/sidepanel/__tests__/` unless that path is inside `src/`. The `__tests__` directories are inside `src/sidepanel/`, so they are included. However, `"rootDir": "src"` means TypeScript will attempt to emit test files alongside source — a `vitest.config.ts` with `include` pointing at `__tests__` patterns is required to prevent this.

The plan adds task 0.1 titled "Test infrastructure (Vitest + chrome mock)" which is the right decision. However, the task description is incomplete:

1. The plan does not specify how the `chrome.*` API will be mocked. The three options have different tradeoffs: (a) manual `globalThis.chrome = { ... }` in a setup file — most transparent, requires maintaining the mock; (b) `jest-chrome` — pre-built but targets Jest; (c) `vitest-chrome` or direct `@types/chrome` stubs — least maintenance. The choice must be made before task 1.1, since each test file will use this mock.

2. `moduleResolution: "bundler"` in `tsconfig.json` is a Vite-specific mode. Vitest can use the same tsconfig, but the test runner needs explicit `environment: "jsdom"` in `vitest.config.ts`. The plan does not show a `vitest.config.ts` template or specify which environment is used.

3. The plan does not address whether test files should be compiled separately (separate `tsconfig.test.json`) or included in the main compile. Given `"noUnusedLocals": true` in tsconfig, test helpers imported only in tests would trigger errors unless the test tsconfig excludes source files from the `unused` check.

**The plan correctly identifies Vitest as the choice.** This is the right call: Vite-based project, ESM modules, same transform pipeline. The blocker is not the choice but the underspecification. Task 0.1 must include: a `vitest.config.ts` with `environment: "jsdom"` and `globals: true`, a setup file at `extension/src/sidepanel/__tests__/setup.ts` that constructs the `globalThis.chrome` mock with the minimum API surface needed (storage.local, runtime.connect, tabs.query, runtime.getManifest, runtime.getURL), and a `"test": "vitest"` script in `package.json`.

---

### 4. Scalability — PASS

The 10-module decomposition with one concern per file is appropriate for the scale of a Chrome Extension sidepanel. The module graph is a DAG with `helpers` at the root, which is the correct shape for incremental extension. Adding a new display feature (strategy deviation panel, real-time coaching overlay) would slot into the `ws-dispatch → [new-module]` layer with no structural changes required. The entry point will be approximately 35 lines after the split, making future init function additions trivial to review.

No scalability concerns are identified for the projected scope.

---

### 5. Security — PASS with noted gap

The plan correctly identifies settings URL validation as a gap and addresses it with `new URL(value)` validation in task 3.1. `escapeHtml` (source lines 29–33) is used consistently in all three briefing render functions (`renderPortrait`, `renderStrategy`, `renderObjections`) and will be preserved in `helpers.ts`. The `innerHTML` assignments in briefing rendering (lines 1305, 1329, 1343) are all sanitized through `escapeHtml`. XSS risk from briefing data is covered.

**Noted gap — URL scheme validation is incomplete (MINOR):**
The plan specifies `new URL(value)` to validate the backend URL format. This accepts `http://`, `ftp://`, and even `javascript://` as valid URLs. The backend URL is used for REST API calls (fetch) and the storage value is also read by `constants.ts` as `API_BASE`. The validation should additionally check that the scheme is `http:` or `https:`. The plan does not specify this constraint.

**Noted gap — hardcoded password (MINOR):**
The settings overlay has `if (pwd === "123")` (line 1793). The spec correctly marks this out of scope. However, when `settings.ts` is extracted as a standalone module, this becomes immediately visible and will attract future contributors who "fix" it to something equally insecure. A `// TODO(FEAT-010): replace hardcoded password with proper auth token` comment should be added at extraction time.

**Noted gap — `sttBalanceError` cross-module reset creates a state exposure vector:**
As described in item 2 above, the provider-change handler in `settings.ts` will need to call `resetBalanceError()` exported from `capture.ts`. The security implication is minor but real: any module that can import from `capture.ts` can reset the balance error cache, potentially allowing retry attempts that the backend has already rejected. This is acceptable given the extension's trust model but should be documented.

---

### 6. API Contracts — PASS with caveat

The plan specifies named exports for each module with sufficient detail to derive the contracts from the task descriptions and the entry-point sketch in task 2.5. The entry-point sketch serves as an implicit integration test for the API surface.

**Caveat — interfaces not yet assigned to modules:**
The plan does not specify where the TypeScript interfaces currently defined in `sidepanel.ts` will live after the split:
- `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection`, `BriefingData` (lines 244–268): should move to `briefing.ts` or to `state.ts` (since `PanelState` references `BriefingData`)
- `PanelState`, `DEFAULT_STATE` (lines 270–286): clearly belong in `state.ts`
- `PreflightResult` (lines 1452–1456): belongs in `preflight.ts`
- `LayoutData` (lines 37–39): belongs in `splitter.ts`

The shared `extension/src/shared/` directory already contains `messages.ts` and `evaluation-types.ts`. Sidepanel-specific types should stay local to their modules rather than being added to `shared/`, since they are not consumed by any other extension entry point. This decision should be documented in the plan to prevent the implementer from incorrectly migrating types to `shared/`.

**Caveat — `resetSessionState` return type:**
`resetSessionState` (line 428) returns `Promise<void>` but is called as `void resetSessionState()` in `handleSessionAborted` (line 420). After extraction to `state.ts`, this unawaited call remains a pre-existing issue. The contract between `port.ts` and `state.ts` should note that `resetSessionState` is intentionally fire-and-forget in this call path, to prevent future contributors from adding `await` and inadvertently blocking the session aborted handler.

---

### 7. Error Handling — PASS with gap

The three targeted error handling fixes in task 3.1 are correct:
- `void init()` swallows rejections → fixed with `.catch(showFatalError)`
- `handlePortMessage` has no try/catch → fixed
- `handleWsMessage` has no try/catch → fixed
- `window.addEventListener('unhandledrejection', ...)` adds a global safety net

**Gap — `evalPollTimer` timeout leaves UI in perpetual loading state (MAJOR, not a blocker but must fix before task 2.2):**
The eval poll runs for 8 attempts at 5-second intervals (40 seconds total). When `attempts > 8`, `stopEvalPolling()` is called with no user-visible feedback. `#eval-loading` remains shown, `#eval-summary` and `#eval-error` remain hidden. The user sees a loading spinner with no way to recover. The spec explicitly lists this as an acceptance criterion: "Eval poll timeout shows visible error message." Task 3.1 mentions "eval-loading aria-live" but does not show the timeout error path being wired. The `handleEvaluationStarted` polling closure must be extended to call `handleEvaluationError` (or equivalent) when `attempts > 8`.

**Gap — `evalPollTimer` not cleared in `resetSessionState`:**
`resetSessionState` (line 428) clears `capturing`, `briefing`, `kbId`, `sessionId`, and `fileNames` in storage, but does not call `stopEvalPolling()`. After the split, `evaluation.ts` owns `evalPollTimer` and `state.ts` owns `resetSessionState`. The stale timer will fire against the closed session's `sid` and `evalToken` captured in the closure and call `renderEvaluationSummary`, writing evaluation results into the current session's Phase 4 DOM. This is a concrete data corruption scenario. The spec's Edge Cases section identifies this explicitly. The plan must add `stopEvalPolling()` to either `resetSessionState` (via `registerResetCallback`) or require every caller of `resetSessionState` to also call `stopEvalPolling`.

**Gap — `fetchAndRenderBriefing` re-throw chain:**
`fetchAndRenderBriefing` (line 1417) re-throws caught errors to the caller. The `initBriefing` caller wraps this correctly (line 1436). The `doUpload` outer try/catch (line 1260) also catches it. The chain is functionally safe. However, after the split, `upload.ts` will call across module boundaries into `briefing.ts` through an async chain that ends with `setStep("error", ...)`. This should be verified explicitly in task 2.3 and documented as the intended error propagation path, not left for the implementer to rediscover.

---

### 8. Circular Dependencies — PASS with required resolution

The plan's dependency graph is accurate for the non-circular portion. No true circular dependencies are found in the source. However, two edges require explicit resolution before implementation:

**Edge 1 — `phase-engine ↔ rec-button` (must resolve in task 1.2):**
`updateHeader` (line 226) calls `void updateRecButtonState()` for phase 2. After extraction, `phase-engine.ts` would import from `rec-button.ts`, and `rec-button.ts` would import from `phase-engine.ts` for `setPhase` and `currentPhase`. This is a genuine circular dependency.

The plan acknowledges this and proposes either a lazy import or a callback. Lazy dynamic imports (`await import('./rec-button')`) inside a synchronous function like `updateHeader` would require converting `updateHeader` to async and then `setPhase` to async — this cascades through every caller of `setPhase`, which is called from 8 different locations. That is an invasive change for a "pure mechanical refactor."

The callback pattern is correct and lower-impact: `phase-engine.ts` exports `setUpdateRecButtonCallback(fn: () => Promise<void>): void`, and `initRecButton` in `rec-button.ts` calls this registration function. `updateHeader` then calls the registered callback if set. This is exactly the pattern the plan names but does not specify concretely. The plan must commit to the callback pattern and include the function signature before task 1.2 begins.

**Edge 2 — `briefing → preflight` (document, not blocking):**
`fetchAndRenderBriefing` (line 1414) calls `void runPreflight()`. After the split, `briefing.ts` imports from `preflight.ts`. This is not circular but it is an undocumented dependency edge that does not appear in the plan's dependency graph. Add it before task 2.3 to prevent the implementer from treating it as an unexpected coupling.

**Verified complete dependency graph (corrected from plan):**
```
helpers.ts        (no sidepanel deps)
splitter.ts       -> helpers
state.ts          -> (no sidepanel deps, uses chrome.storage)
phase-engine.ts   -> helpers, splitter
                     uses registered callback for rec-button
capture.ts        -> helpers, phase-engine
                     exports: resetBalanceError(), getBalanceError()
                     calls: resetHintState() from hint.ts (undocumented in plan)
                     calls: resetAutoScroll() from transcript.ts (undocumented in plan)
vu-meter.ts       -> helpers
call-timer.ts     -> helpers
port.ts           -> helpers, state, phase-engine, capture, vu-meter, call-timer
hint.ts           -> helpers
                     exports: resetHintState()
transcript.ts     -> helpers
                     exports: resetAutoScroll()
evaluation.ts     -> helpers, state
ws-dispatch.ts    -> hint, transcript, evaluation, capture
upload.ts         -> helpers, state, phase-engine
briefing.ts       -> helpers, state, preflight (via void runPreflight())
preflight.ts      -> helpers, state
rec-button.ts     -> helpers, state, capture, phase-engine, call-timer, vu-meter, mic
                     registers callback with phase-engine
mic.ts            -> helpers
settings.ts       -> helpers, mic, preflight, capture (via resetBalanceError())
```

---

## Additional Edge Cases

### EC-1: Double init race on panel reopen (HIGH risk, not in plan)

The spec notes: "User uploads files, quickly closes and reopens side panel. Two `init()` calls race against same `chrome.storage.local` with no mutex." The source confirms this is possible because Chrome's sidepanel can be closed and reopened without the extension being reloaded, and each `DOMContentLoaded` fires a new `init()` call. After the modular split, the port module owns `swPort` and `reconnectAttempts` as module-level singletons. In the Chrome Extension model, each sidepanel document is a fresh HTML document with fresh module scope — there is no true singleton across reopens. However, within a single document, a rapid DOMContentLoaded + reopened sidepanel scenario could result in `connectPort()` being called twice. The plan does not include a guard (e.g., `let initialized = false` in `init.ts`). This should be added to task 2.5.

### EC-2: `noUnusedLocals` compilation failures during incremental extraction (MEDIUM risk)

`tsconfig.json` enables `noUnusedLocals: true` and `noUnusedParameters: true`. During task 1.1 extraction, after `helpers.ts` is created and imported, the original definitions in `sidepanel.ts` must be removed atomically in the same task. If the plan's "build extension after each task" instruction is followed faithfully, the implementer will get TypeScript errors if they add the import before removing the original definition (duplicate identifier) or remove the original before updating all callers (missing function). This is the intended fast-fail behavior of strict TypeScript, and it is useful here, but the plan should note that each task is an atomic unit: create module + add exports + update all callers + remove originals from sidepanel.ts — all in one commit.

### EC-3: Port reconnection during active evaluation poll (MEDIUM risk)

If the Service Worker disconnects and reconnects during Phase 4 evaluation polling, `restoreFromHandshake` may call `setPhase(2)` if `state.capturing` is false (call just ended). This hides the Phase 4 evaluation UI while `evalPollTimer` is still running. When the poll fires, it calls `renderEvaluationSummary`, which writes to DOM elements in `#phase-4` that are now hidden behind `#phase-2`. The evaluation result is silently lost. This is not addressed in any task. A check in `restoreFromHandshake` — "if phase 4 is currently active and eval polling is in progress, do not call setPhase(2)" — should be added to task 2.1 or 2.2.

### EC-4: Splitter restore() race with section height (LOW risk)

`setPhase(2)` calls `requestAnimationFrame(() => { initPhase2Splitter(); phase2Splitter?.restore(); })`. `restore()` reads `chrome.storage.local` asynchronously and then sets `flex` values on section elements. If the user scrolls or the panel layout renders before the storage read completes, the initial layout will be browser-default heights. The `restore()` call will then snap the layout, causing a visible layout jump. The plan does not address this. An accepted approach is to set `visibility: hidden` on the splitter container until `restore()` completes, which prevents the visual jump without affecting scroll position.

---

## Verdict

**CONDITIONAL PASS** — Two blockers must be resolved before implementation begins. Three major issues must be fixed before task 2.5.

### Blockers (must fix before /implement)

**BLOCKER-1 (Data Flow / Circular Deps):** The plan does not specify the concrete exported functions for cross-module shared mutable state (`resetBalanceError` in `capture.ts`, `resetHintState` in `hint.ts`, `resetAutoScroll` in `transcript.ts`), does not document the `capture → hint` and `capture → transcript` dependency edges introduced by `handleCaptureStarted`'s state resets, and does not commit to the callback pattern for `phase-engine ↔ rec-button`. All three must be specified in the plan before task 1.2 begins.

**BLOCKER-2 (Technology):** No test runner, no chrome mock, no jsdom, no `test` script exists in `extension/package.json`. Task 0.1 must specify: (a) `vitest.config.ts` with `environment: "jsdom"` and `globals: true`, (b) a setup file that constructs the minimum `globalThis.chrome` mock surface (storage.local.get/set, runtime.connect, runtime.sendMessage, tabs.query, tabs.create, runtime.getManifest, runtime.getURL, storage.onChanged.addListener), (c) `"test": "vitest run"` and `"test:watch": "vitest"` scripts in `package.json`. Without this, every test task is unbounded.

### Major Issues (fix before task 2.5)

**MAJOR-1:** `evalPollTimer` is not cleared in `resetSessionState`. Add `stopEvalPolling()` registration via `registerResetCallback` or require all callers to explicitly clear. Stale eval results can render in a new session's Phase 4 UI.

**MAJOR-2:** Eval poll timeout (40 seconds, 8 attempts) leaves `#eval-loading` shown indefinitely with no user feedback. Task 2.2 must wire the `attempts > 8` path to call `handleEvaluationError` (or show a visible timeout message in `#eval-error`).

**MAJOR-3:** `BriefingData` type location not specified. Since `PanelState` references `BriefingData`, both must be defined in the same file or one must import from the other. Specify that `BriefingData` and related interfaces move to `state.ts` alongside `PanelState` before task 1.2.

### Minor Issues (fix during implementation)

**MINOR-1:** Add undocumented `briefing.ts → preflight.ts` edge to the dependency graph.

**MINOR-2:** Resolve `initNewCallButton`/`initDownloadButton` mapping inconsistency between Feature Inventory (task 2.4) and the task 2.5 entry-point sketch (imports from `transcript`). The plan's task 2.5 import sketch shows `import { initDownloadButton } from './transcript'`, which is correct by concern but contradicts the inventory.

**MINOR-3:** Extend URL scheme validation in task 3.1 to check that the backend URL scheme is `http:` or `https:`. `new URL(value)` alone does not prevent `ftp://` or `ws://` values from being saved.

**MINOR-4:** Add `// TODO(FEAT-010): replace hardcoded password with auth token` comment in `settings.ts` at extraction time to prevent inadvertent "improvements" to the hardcoded `"123"` comparison.

**MINOR-5:** Add a double-init guard to `init()` in task 2.5 (`let initialized = false; if (initialized) return; initialized = true;`) to handle the panel reopen race condition identified in EC-1.

---

*Review complete. Resolve BLOCKER-1 and BLOCKER-2 before proceeding to /implement.*
