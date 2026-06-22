# Frontend Architecture Fixes — Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-14
Status: PENDING
Spec: specs/FEAT-009-frontend-arch-fixes.md
Source: docs/architecture-review-2026-03-14.md (finding C1 + agent-discovered bonus fixes)

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Split the 1896-line `sidepanel.ts` god module into 10 focused modules with unit tests. Fix bonus issues: error boundaries, settings validation, and accessibility gaps for aria-live regions.

**Architecture:** Pure mechanical refactor — move functions to modules without changing behavior. Each extraction is a self-contained PR. Tests written alongside each module extraction. No new features, no behavior changes.

**Tech Stack:** TypeScript (strict), Chrome Extension APIs, Vite, Vitest (for unit tests)

## Scope

### In Scope
- C1: Split `sidepanel.ts` (1896 LOC, 56 functions, 22 event handlers) into 10 focused modules
- Unit tests for each extracted module
- Bonus: Error boundaries (unhandled promise rejections)
- Bonus: Settings form URL validation
- Bonus: aria-live regions for hints and transcript

### Out of Scope
- Settings password hardcoding (requires product decision on auth approach)
- CSS media queries / responsive design (minor priority, separate effort)
- Settings overlay focus trap (a11y improvement, separate effort)
- Evaluation gauge SVG accessibility (separate effort)
- Type duplication with backend (M3 — separate effort)
- `report.ts` type duplication (L3 — separate effort)

## Prerequisites
- Extension builds successfully: `cd extension && npm run build`
- TypeScript compiles: `cd extension && npx tsc --noEmit`
- Test infrastructure set up (task 0.1 handles this — Vitest + jsdom + chrome mock)

## Context for Implementer

### Current structure of sidepanel.ts

The file has 56 functions organized into these logical groups (identified by the frontend agent):

| Concern | Functions | Lines (approx) |
|---------|-----------|-----------------|
| DOM helpers | `$`, `show`, `hide`, `escapeHtml` | 17-33 |
| Splitter layout | `Splitter` class, `initPhase2/3Splitter` | 35-179 |
| Phase engine | `setPhase`, `updateHeader` | 182-240 |
| State management | `loadState`, `saveState`, `resetSessionState` | 242-300 |
| Port/SW connection | `connectPort`, `handlePortMessage`, `restoreFromHandshake`, etc. | 302-436 |
| VU meters | `scheduleVuUpdate` | 438-461 |
| Call timer | `startCallTimer`, `stopCallTimer`, `updateTimerDisplay`, `getCallDuration` | 463-494 |
| Capture flow | `showCapturePrompt`, `handleCaptureStarted`, `handleBackendError`, etc. | 496-616 |
| Evaluation display | `animateEvalProgress`, `handleEvaluationStarted`, `renderEvaluationSummary`, etc. | 618-823 |
| WS dispatch | `handleWsMessage` | 825-855 |
| Hint display | `handleHintEnd`, `renderHint`, `flushPendingHint` | 857-950 |
| Transcript display | `handleTranscript`, `initTranscriptScroll`, `downloadTranscript` | 952-1060 |
| Upload flow | `validateFiles`, `setStep`, `initUpload`, `doUpload` | 1062-1271 |
| Briefing render | `renderPortrait`, `renderStrategy`, `fetchAndRenderBriefing`, etc. | 1273-1449 |
| Preflight | `runPreflight`, `initPreflight` | 1451-1523 |
| REC button | `initRecButton`, `updateRecButtonState` | 1525-1645 |
| Mic permission/selection | `checkMicPermission`, `populateMicList`, `initMicSelect` | 1647-1728 |
| Settings overlay | `initSettingsOverlay` | 1730-1813 |
| Download/New call | `downloadTranscript`, `initDownloadButton`, `initNewCallButton` | 1815-1857 |
| Init | `init()`, DOMContentLoaded | 1859-1896 |

### Global state variables (20+)
```
currentPhase, swPort, reconnectAttempts, handshakeReceived,
pendingMic, pendingTab, vuRafPending, callTimerInterval, callStartTime,
capturePromptTimeout, sttBalanceError, sttBalanceErrorTime,
evalPollTimer, evalReceived, evalStepTimer,
lastHintRenderedAt, pendingHintEnd, pendingHintTimer,
isAutoScrolling, phase2Splitter, phase3Splitter
```

### Dependency graph (no circular dependencies)
```
helpers.ts        ← imported by all modules (leaf, no sidepanel deps)
state.ts          ← imported by: port, upload, briefing, rec-button, evaluation, init
                     (registers reset callbacks from other modules)
phase-engine.ts   ← called by: port, capture, upload, rec-button, init
                     (uses callback from rec-button, never imports directly)
capture.ts        → helpers, phase-engine, hint (resetHintState), transcript (resetAutoScroll)
settings.ts       → helpers, mic, preflight, capture (resetBalanceError)
briefing.ts       → helpers, state, preflight (void runPreflight)
```

### Backend Integration Points

| Module | Function | Endpoint | Method | Notes |
|--------|----------|----------|--------|-------|
| `briefing.ts` | `fetchAndRenderBriefing` | `/api/v1/briefing` | POST | Sends `kb_id` + `session_id`, receives briefing JSON |
| `upload.ts` | `doUpload` | `/api/v1/upload` | POST | Multipart form, `MAX_FILE_SIZE=50MB`, `ALLOWED_TYPES` must match backend validation |
| `evaluation.ts` | eval poll timer | `/api/v1/evaluation/{sid}?token={evalToken}` | GET | Polls every 5s, max 8 attempts. `evalToken` must stay in local scope. |
| `preflight.ts` | `runPreflight` | `/api/v1/preflight` | GET | Checks STT provider availability, returns status per provider |
| `upload.ts` | `doUpload` (delete) | `/api/v1/session/{sid}` | DELETE | Called on re-upload to clear previous session |

**SSRF posture:** Backend URL is stored in `chrome.storage.local` and is user-controlled. URL validation in `settings.ts` (task 3.1) checks format only. SSRF protection is the backend's responsibility. `evalToken` must remain in `evaluation.ts` local scope — never promoted to module-level export.

### tsconfig.json key settings
- `"module": "ESNext"`, `"moduleResolution": "bundler"` — ES module imports work
- `"strict": true` — all strict checks enabled
- `"outDir": "dist"` — compiled output

## Feature Inventory — Files Being Replaced

| Old File | Functions/Classes | Mapped to Task |
|----------|-------------------|----------------|
| `sidepanel.ts` (lines 17-33) | `$`, `show`, `hide`, `escapeHtml` | 1.1 |
| `sidepanel.ts` (lines 35-179) | `Splitter` class, `initPhase2Splitter`, `initPhase3Splitter` | 1.1 |
| `sidepanel.ts` (lines 182-300) | `setPhase`, `updateHeader`, `loadState`, `saveState`, `resetSessionState` | 1.2 |
| `sidepanel.ts` (lines 302-494) | `connectPort`, `handlePortMessage`, `restoreFromHandshake`, VU, timer | 2.1 |
| `sidepanel.ts` (lines 496-616) | Capture flow + backend error | 2.1 |
| `sidepanel.ts` (lines 618-855) | Evaluation + WS dispatch | 2.2 |
| `sidepanel.ts` (lines 857-1060) | Hint + Transcript display | 2.2 |
| `sidepanel.ts` (lines 1062-1449) | Upload + Briefing | 2.3 |
| `sidepanel.ts` (lines 1451-1728) | Preflight + REC + Mic | 2.4 |
| `sidepanel.ts` (lines 1730-1813) | Settings overlay | 2.4 |
| `sidepanel.ts` (lines 1815-1843) | `downloadTranscript`, `initDownloadButton` | 2.2 (transcript.ts) |
| `sidepanel.ts` (lines 1845-1857) | `initNewCallButton` | 1.2 (phase-engine.ts) |
| `sidepanel.ts` (lines 1859-1896) | `init()`, DOMContentLoaded | 2.5 |

### Feature Mapping Verification

- [x] All old file sections listed above
- [x] All 56 functions identified and assigned to tasks
- [x] Every feature has a task number
- [x] No features accidentally omitted

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 0. Prerequisites
- [ ] 0.1 Set up test infrastructure (Vitest + chrome mock)

### 1. Foundation: Shared Modules
- [ ] 1.1 Extract helpers.ts, splitter.ts (pure utilities, no state)
- [ ] 1.2 Extract state.ts, phase-engine.ts (core state machine)

### 2. Feature Module Extraction
- [ ] 2.1 Extract port.ts, capture.ts, vu-meter.ts, call-timer.ts (connection & call lifecycle)
- [ ] 2.2 Extract evaluation.ts, hint.ts, transcript.ts, ws-dispatch.ts (live data display)
- [ ] 2.3 Extract upload.ts, briefing.ts (pre-call flow)
- [ ] 2.4 Extract settings.ts, mic.ts, preflight.ts, rec-button.ts (controls & config)
- [ ] 2.5 Rewrite sidepanel.ts as init-only entry point

### 3. Bonus Fixes
- [ ] 3.1 Add error boundaries + settings validation + aria-live regions

**Total Tasks:** 9 | **Completed:** 0 | **Remaining:** 9

## Implementation Tasks

### 0. Prerequisites

#### 0.1 Set Up Test Infrastructure (Vitest + Chrome Mock)

**Objective:** Establish the test runner, DOM environment, and Chrome API mock pattern before any module extraction begins. This unblocks all test writing in subsequent tasks.

**Files:**
- Create: `extension/vitest.config.ts`
- Create: `extension/src/sidepanel/__tests__/setup.ts` (global test setup with chrome mock)
- Modify: `extension/package.json` (add vitest, jsdom, @vitest/coverage-v8 as devDependencies)
- Modify: `extension/tsconfig.json` (add `__tests__` to include if needed)

**Implementation Steps:**
1. Install dependencies: `cd extension && npm install -D vitest jsdom @vitest/coverage-v8`
2. Create `extension/vitest.config.ts`:
   ```typescript
   import { defineConfig } from 'vitest/config';
   export default defineConfig({
     test: {
       environment: 'jsdom',
       setupFiles: ['./src/sidepanel/__tests__/setup.ts'],
       include: ['src/**/__tests__/**/*.test.ts'],
     },
   });
   ```
3. Create `extension/src/sidepanel/__tests__/setup.ts` — establish the chrome mock pattern:
   ```typescript
   import { vi } from 'vitest';

   // Chrome Extension API mock — single source of truth for all tests
   globalThis.chrome = {
     storage: {
       local: {
         get: vi.fn().mockResolvedValue({}),
         set: vi.fn().mockResolvedValue(undefined),
       },
       onChanged: {
         addListener: vi.fn(),
         removeListener: vi.fn(),
       },
     },
     runtime: {
       connect: vi.fn().mockReturnValue({
         onMessage: { addListener: vi.fn() },
         onDisconnect: { addListener: vi.fn() },
         postMessage: vi.fn(),
       }),
       id: 'test-extension-id',
     },
   } as unknown as typeof chrome;
   ```
4. Add `"test"` script to `package.json`: `"test": "vitest run"`
5. Add `"test:watch"` script: `"test:watch": "vitest"`
6. Write a smoke test `extension/src/sidepanel/__tests__/smoke.test.ts`:
   ```typescript
   import { describe, it, expect } from 'vitest';
   describe('test infrastructure', () => {
     it('chrome.storage.local.get is mocked', async () => {
       const result = await chrome.storage.local.get('test');
       expect(result).toEqual({});
     });
   });
   ```
7. Run `cd extension && npm test` — verify smoke test passes.

**Definition of Done:**
- [ ] `vitest` installed and configured
- [ ] `jsdom` environment set up
- [ ] Chrome API mock pattern established in `setup.ts`
- [ ] `npm test` runs and passes smoke test
- [ ] `npm run build` still succeeds (no interference)

---

### 1. Foundation: Shared Modules

#### 1.1 Extract `helpers.ts` and `splitter.ts`

**Objective:** Extract pure utility functions and the Splitter class — these have zero dependencies on other sidepanel code and are the natural foundation for the module split.

**Files:**
- Create: `extension/src/sidepanel/helpers.ts`
- Create: `extension/src/sidepanel/splitter.ts`
- Create: `extension/src/sidepanel/__tests__/helpers.test.ts`
- Create: `extension/src/sidepanel/__tests__/splitter.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts` (remove extracted code, add imports)

**Implementation Steps:**
1. Create `helpers.ts` — move functions:
   - `$<T extends Element>(sel: string, root?)` (line 19)
   - `show(el: HTMLElement)` (line 22)
   - `hide(el: HTMLElement)` (line 25)
   - `escapeHtml(str: string)` (line 29)
   Export all as named exports.

2. Create `splitter.ts` — move:
   - `LayoutData` interface
   - `Splitter` class (lines 41-165)
   - `initPhase2Splitter()` (line 170)
   - `initPhase3Splitter()` (line 176)
   Import `$` from `./helpers`.

3. Write tests:
   - `helpers.test.ts`: test `escapeHtml` with XSS payloads, test `show`/`hide` toggle display style
   - `splitter.test.ts`: test `Splitter.savePercentages` / `restore` with mocked localStorage

4. In `sidepanel.ts`, replace removed code with:
   ```typescript
   import { $, show, hide, escapeHtml } from './helpers';
   import { Splitter, initPhase2Splitter, initPhase3Splitter } from './splitter';
   ```

5. Build extension: `cd extension && npm run build`
6. Verify no TypeScript errors: `npx tsc --noEmit`

**Definition of Done:**
- [ ] `helpers.ts` exports `$`, `show`, `hide`, `escapeHtml`
- [ ] `splitter.ts` exports `Splitter`, `initPhase2Splitter`, `initPhase3Splitter`
- [ ] Tests pass for both modules
- [ ] Extension builds without errors
- [ ] Sidepanel loads and Splitter works (manual check)

---

#### 1.2 Extract `state.ts` and `phase-engine.ts`

**Objective:** Extract the state management (PanelState, loadState, saveState) and phase engine (setPhase, updateHeader) — these are the core state machine that all other modules depend on.

**Files:**
- Create: `extension/src/sidepanel/state.ts`
- Create: `extension/src/sidepanel/phase-engine.ts`
- Create: `extension/src/sidepanel/__tests__/state.test.ts`
- Create: `extension/src/sidepanel/__tests__/phase-engine.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts` (remove extracted code, add imports)

**Implementation Steps:**
1. Create `state.ts` — move:
   - `PanelState` interface and `DEFAULT_STATE` constant
   - `BriefingData`, `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection` interfaces — these MUST live in `state.ts` alongside `PanelState` (because `PanelState` references `BriefingData`). If left in `briefing.ts`, it creates a circular dependency: `state.ts → briefing.ts` and `briefing.ts → state.ts`.
   - `Phase` type (0 | 1 | 2 | 3 | 4)
   - `loadState()` (line 288)
   - `saveState(patch)` (line 297)
   - `resetSessionState()` (line 428) — note: this function resets global variables. It will need to accept callbacks or emit events for the parts that touch other modules' state.
   Export a `registerResetCallback(fn: () => void): void` function that allows other modules to register cleanup functions called during `resetSessionState()`. This enables `evaluation.ts` to register `stopEvalPolling` without `state.ts` importing from `evaluation.ts`.
   Export all.

2. Create `phase-engine.ts` — move:
   - `currentPhase` variable (exported as getter/setter or module-level let)
   - `setPhase(phase)` (line 187)
   - `updateHeader()` (line 207)
   Import from `./helpers` (`$`, `show`, `hide`) and `./splitter` (`initPhase2Splitter`, `initPhase3Splitter`).
   Export `setUpdateRecButtonCallback(fn: () => Promise<void>): void` setter function. `updateHeader()` calls this callback instead of importing directly from `rec-button.ts`. `rec-button.ts` calls `setUpdateRecButtonCallback(updateRecButtonState)` during initialization. This avoids the `phase-engine ↔ rec-button` circular dependency.

3. Write tests:
   - `state.test.ts`: mock `chrome.storage.local`, test loadState returns defaults, saveState merges correctly
   - `phase-engine.test.ts`: mock DOM, test setPhase shows/hides correct phase containers, test updateHeader toggles rec button visibility

4. Update `sidepanel.ts` imports.

5. Build and verify.

**Definition of Done:**
- [ ] `state.ts` exports `PanelState`, `Phase`, `BriefingData`, `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection`, `loadState`, `saveState`, `resetSessionState`
- [ ] `phase-engine.ts` exports `setPhase`, `updateHeader`, `currentPhase` getter
- [ ] Tests pass for both modules
- [ ] Extension builds without errors
- [ ] Phase transitions work correctly (manual check: upload → briefing → recording)

---

### 2. Feature Module Extraction

#### 2.1 Extract `port.ts`, `capture.ts`, `vu-meter.ts`, `call-timer.ts`

**Objective:** Extract the Service Worker connection, capture flow, VU meter, and call timer — the connection and call lifecycle modules.

**Files:**
- Create: `extension/src/sidepanel/port.ts`
- Create: `extension/src/sidepanel/capture.ts`
- Create: `extension/src/sidepanel/vu-meter.ts`
- Create: `extension/src/sidepanel/call-timer.ts`
- Create: `extension/src/sidepanel/__tests__/port.test.ts`
- Create: `extension/src/sidepanel/__tests__/capture.test.ts`
- Create: `extension/src/sidepanel/__tests__/call-timer.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**
1. Create `vu-meter.ts` — move `scheduleVuUpdate`, `pendingMic`, `pendingTab`, `vuRafPending`. No dependencies on other sidepanel modules.

2. Create `call-timer.ts` — move `startCallTimer`, `stopCallTimer`, `updateTimerDisplay`, `getCallDuration`, `callTimerInterval`, `callStartTime`. Import `$` from helpers.

3. Create `capture.ts` — move `showCapturePrompt`, `hideCapturePrompt`, `handleCaptureStarted`, `handleCaptureFailed`, `handleBackendError`, error label constants, `sttBalanceError`, `sttBalanceErrorTime`, `capturePromptTimeout`. Import from helpers, phase-engine. Export `resetBalanceError(): void` function that sets `sttBalanceError = false` and `sttBalanceErrorTime = 0`. This is called by `settings.ts` when STT provider changes.

3b. In `handleCaptureStarted`, replace direct mutations of hint/transcript state with calls to exported reset functions:
   - Call `resetHintState()` from `hint.ts` (resets `lastHintRenderedAt`, `pendingHintEnd`, clears `pendingHintTimer`)
   - Call `resetAutoScroll()` from `transcript.ts` (sets `isAutoScrolling = true`)
   This creates `capture → hint` and `capture → transcript` dependency edges.

4. Create `port.ts` — move `connectPort`, `updateStatusPill`, `handlePortMessage`, `restoreFromHandshake`, `updateWsStatus`, `handleSessionAborted`, `showReconnectedBadge`, `swPort`, `reconnectAttempts`, `handshakeReceived`. Import from helpers, state, phase-engine, capture, vu-meter, call-timer.

4c. In `port.ts`, define reconnect-in-progress state: during attempts 1–9, update `#status-pill` with text like `'Переподключение...'` instead of leaving it unchanged.

5. Write tests:
   - `call-timer.test.ts`: test `getCallDuration` formatting, `startCallTimer` sets interval
   - `capture.test.ts`: test `handleBackendError` maps error codes to correct banners
   - `port.test.ts`: test `handlePortMessage` dispatches correctly for each message type

6. Update `sidepanel.ts` imports.
7. Build and verify.

**Definition of Done:**
- [ ] `port.ts`, `capture.ts`, `vu-meter.ts`, `call-timer.ts` created and exported
- [ ] Tests pass for call-timer, capture, port
- [ ] Extension builds without errors
- [ ] SW connection works, VU meters animate, call timer counts (manual check)

---

#### 2.2 Extract `evaluation.ts`, `hint.ts`, `transcript.ts`, `ws-dispatch.ts`

**Objective:** Extract the live call data display modules — evaluation results, hints, transcript, and the WebSocket message dispatcher.

**Files:**
- Create: `extension/src/sidepanel/evaluation.ts`
- Create: `extension/src/sidepanel/hint.ts`
- Create: `extension/src/sidepanel/transcript.ts`
- Create: `extension/src/sidepanel/ws-dispatch.ts`
- Create: `extension/src/sidepanel/__tests__/hint.test.ts`
- Create: `extension/src/sidepanel/__tests__/transcript.test.ts`
- Create: `extension/src/sidepanel/__tests__/evaluation.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**
1. Create `hint.ts` — move `handleHintStart`, `handleHintChunk`, `handleHintEnd`, `flushPendingHint`, `renderHint`, `DISPLAY_COOLDOWN_MS`, `lastHintRenderedAt`, `pendingHintEnd`, `pendingHintTimer`. Import from helpers. Export `resetHintState(): void` function that resets `lastHintRenderedAt = 0`, `pendingHintEnd = null`, and clears `pendingHintTimer` via `clearTimeout`. Called by `capture.ts:handleCaptureStarted`.

2. Create `transcript.ts` — move `handleTranscript`, `initTranscriptScroll`, `downloadTranscript`, `initDownloadButton`, `isAutoScrolling`. Import from helpers. Export `resetAutoScroll(): void` function that sets `isAutoScrolling = true`. Called by `capture.ts:handleCaptureStarted`. In `downloadTranscript`, check if `#transcript-full-list` is empty. If so, show a toast or disable the download button — don't produce an empty file.

3. Create `evaluation.ts` — move `stopEvalPolling`, `animateEvalProgress`, `handleEvaluationStarted`, `handleEvaluationResult`, `handleEvaluationError`, `renderEvaluationSummary`, `evalPollTimer`, `evalReceived`, `evalStepTimer`. Import from helpers, state.

3b. In `evaluation.ts`, register `stopEvalPolling` with `state.ts` via `registerResetCallback(stopEvalPolling)` during module initialization. This ensures `resetSessionState()` clears the eval poll timer, preventing stale evaluation results from rendering in a new session.

4. Create `ws-dispatch.ts` — move `handleWsMessage`. Import from hint, transcript, evaluation, capture. This is the router that dispatches WS messages to the correct handler.

4b. In `evaluation.ts`, when eval poll exceeds max attempts (8), show error message in `#eval-error`: `'Оценка недоступна'` and hide `#eval-loading`. Currently the poll stops silently with no user feedback.

5. Write tests:
   - `hint.test.ts`: test cooldown logic — hint within 8s is queued, hint after 8s renders immediately
   - `transcript.test.ts`: test dedup — same utterance_id doesn't create duplicate DOM entries
   - `evaluation.test.ts`: test `animateEvalProgress` step transitions

6. Update `sidepanel.ts` imports.
7. Build and verify.

**Definition of Done:**
- [ ] `evaluation.ts`, `hint.ts`, `transcript.ts`, `ws-dispatch.ts` created
- [ ] Tests pass for hint, transcript, evaluation
- [ ] `stopEvalPolling` registered as a reset callback in `state.ts` — stale polls cleared on session reset
- [ ] Eval poll timeout shows visible error message (not perpetual loading)
- [ ] Extension builds without errors
- [ ] Hints display during call, transcript scrolls, evaluation renders (manual check)

---

#### 2.3 Extract `upload.ts` and `briefing.ts`

**Objective:** Extract the pre-call flow — file upload and briefing rendering.

**Files:**
- Create: `extension/src/sidepanel/upload.ts`
- Create: `extension/src/sidepanel/briefing.ts`
- Create: `extension/src/sidepanel/__tests__/upload.test.ts`
- Create: `extension/src/sidepanel/__tests__/briefing.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**
1. Create `upload.ts` — move `isAllowedExtension`, `validateFiles`, `setStep`, `initUpload` (which contains `doUpload` as an inner function). Move `MAX_FILE_SIZE`, `ALLOWED_TYPES` constants. Import from helpers, state, phase-engine.

2. Create `briefing.ts` — move `renderPortrait`, `renderStrategy`, `renderObjections`, `renderBriefingToContainers`, `fetchAndRenderBriefing`, `updateFileStrip`, `initBriefing`. Import from helpers, state.

3. Write tests:
   - `upload.test.ts`: test `validateFiles` — rejects oversized files, rejects wrong extensions, accepts valid files
   - `briefing.test.ts`: test `renderPortrait` produces correct HTML structure with escaped content

4. Update `sidepanel.ts` imports.
5. Build and verify.

**Definition of Done:**
- [ ] `upload.ts` and `briefing.ts` created
- [ ] Tests pass for upload validation and briefing rendering
- [ ] Extension builds without errors
- [ ] File upload + briefing flow works end-to-end (manual check)

---

#### 2.4 Extract `settings.ts`, `mic.ts`, `preflight.ts`, `rec-button.ts`

**Objective:** Extract the controls and configuration modules — settings overlay, microphone selection, preflight checks, and the REC button.

**Files:**
- Create: `extension/src/sidepanel/settings.ts`
- Create: `extension/src/sidepanel/mic.ts`
- Create: `extension/src/sidepanel/preflight.ts`
- Create: `extension/src/sidepanel/rec-button.ts`
- Create: `extension/src/sidepanel/__tests__/mic.test.ts`
- Create: `extension/src/sidepanel/__tests__/preflight.test.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**
1. Create `mic.ts` — move `checkMicPermission`, `updateMicStatus`, `populateMicList`, `initMicSelect`. Import from helpers.

2. Create `preflight.ts` — move `getSavedProvider`, `runPreflight`, `initPreflight`, `_PROVIDER_LABELS`. Import from helpers, state.

3. Create `rec-button.ts` — move `initRecButton`, `updateRecButtonState`. Import from helpers, state, mic, capture, phase-engine. During initialization, call `setUpdateRecButtonCallback(updateRecButtonState)` to register the callback with `phase-engine.ts`. Read `currentPhase` via `getPhase()` getter instead of direct variable access.

4. Create `settings.ts` — move `initSettingsOverlay`. Import from helpers, mic, preflight. Also import `resetBalanceError` from `capture.ts`. Call `resetBalanceError()` when STT provider changes instead of directly assigning `sttBalanceError = false`.

5. Write tests:
   - `mic.test.ts`: test `populateMicList` with mocked `navigator.mediaDevices.enumerateDevices`
   - `preflight.test.ts`: test `runPreflight` renders correct status chips for OK/FAIL responses

6. Update `sidepanel.ts` imports.
7. Build and verify.

**Definition of Done:**
- [ ] `settings.ts`, `mic.ts`, `preflight.ts`, `rec-button.ts` created
- [ ] Tests pass for mic and preflight
- [ ] Extension builds without errors
- [ ] Settings overlay opens/closes, mic dropdown works, preflight runs (manual check)

---

#### 2.5 Rewrite `sidepanel.ts` as Init-Only Entry Point

**Objective:** The final extraction — `sidepanel.ts` becomes a ~35-line file that imports all modules and wires them together in `init()`.

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts` (rewrite to ~35 lines)

**Implementation Steps:**
1. Verify all functions have been extracted — no function definitions should remain in `sidepanel.ts`
2. Rewrite `sidepanel.ts`:
   ```typescript
   import { connectPort } from './port';
   import { loadState, saveState } from './state';
   import { setPhase } from './phase-engine';
   import { initSettingsOverlay } from './settings';
   import { initUpload } from './upload';
   import { initRecButton, updateRecButtonState } from './rec-button';
   import { initBriefing, renderBriefingToContainers, updateFileStrip } from './briefing';
   import { initPreflight, runPreflight } from './preflight';
   import { initTranscriptScroll, initDownloadButton } from './transcript';
   import { initNewCallButton } from './phase-engine';
   // ... etc

   let initialized = false;

   async function init(): Promise<void> {
     if (initialized) return;  // Guard against double-init (HMR, fast panel reopen)
     initialized = true;
     connectPort();
     initSettingsOverlay();
     initUpload();
     initRecButton();
     initBriefing();
     initPreflight();
     initTranscriptScroll();
     initDownloadButton();
     initNewCallButton();

     const state = await loadState();
     if (state.kbId) {
       renderBriefingToContainers(state.briefing);
       updateFileStrip(state.fileNames);
       setPhase(2);
       void runPreflight();
     }
   }

   document.addEventListener('DOMContentLoaded', () => {
     init().catch(console.error);
   });
   ```
3. Remove all remaining global variable declarations (they now live in their respective modules)
4. Build and verify the entire extension works
5. Count LOC — should be ≤50 lines

**Definition of Done:**
- [ ] `sidepanel.ts` is ≤50 LOC
- [ ] No function definitions in `sidepanel.ts` (only imports + init wiring)
- [ ] No global state variables in `sidepanel.ts` (except `initialized` guard)
- [ ] Double-init guard: `if (initialized) return;` at top of `init()`
- [ ] Extension builds without errors
- [ ] Full end-to-end flow works: upload → briefing → preflight → record → hints → transcript → evaluation (manual check)

---

### 3. Bonus Fixes

#### 3.1 Add Error Boundaries + Settings Validation + aria-live Regions

**Objective:** Address the three bonus issues discovered by the frontend agent: unhandled promise rejections, missing settings validation, and inaccessible hint/transcript updates.

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts` (error boundary on init)
- Modify: `extension/src/sidepanel/port.ts` (try/catch in handlePortMessage)
- Modify: `extension/src/sidepanel/ws-dispatch.ts` (try/catch in handleWsMessage)
- Modify: `extension/src/sidepanel/settings.ts` (URL validation on save)
- Modify: `extension/src/sidepanel/sidepanel.html` (aria-live on hint/transcript containers)
- Create: `extension/src/sidepanel/__tests__/error-handling.test.ts`
- Create: `extension/src/sidepanel/__tests__/settings.test.ts`

**Implementation Steps:**
1. **Error boundaries:**
   - In `sidepanel.ts`: change `void init()` to `init().catch(showFatalError)`
   - Create `showFatalError(err: unknown)` helper that renders error to `#session-error-banner`
   - In `port.ts`: wrap `handlePortMessage` body in try/catch
   - In `ws-dispatch.ts`: wrap `handleWsMessage` body in try/catch
   - Add `window.addEventListener('unhandledrejection', e => showFatalError(e.reason))`
   - Specify `showFatalError` location: create in `helpers.ts` (since it uses `$` to find `#session-error-banner`)
   - In `port.ts`: wrap `void resetSessionState()` call in `handleSessionAborted` with `.catch(console.error)` instead of discarding rejection
   - In `settings.ts`: wrap `void updateRecButtonState()` in `chrome.storage.onChanged` callback with `.catch(console.error)`
   - In `evaluation.ts`: add `console.error(err)` inside the eval poll timer's empty `catch { }` block

2. **Settings validation:**
   - In `settings.ts`: validate backend URL with `new URL(value)` in try/catch before saving
   - Validate URL scheme is `ws:` or `wss:` (or `http:`/`https:` if used for REST calls) — reject other schemes
   - Add `<div id="backend-url-error" class="field-error" hidden aria-live="polite"></div>` to `sidepanel.html` below the backend URL input
   - Show error in `#backend-url-error` on invalid format or wrong scheme
   - Clear error on valid input
   - Add basic URL pattern validation for `#url-pattern-input` (CRM URL pattern) — reject obviously malformed globs

3. **aria-live regions:**
   - In `sidepanel.html`: add `aria-live="polite" aria-atomic="true"` to `#hint-text` container
   - Add `aria-live="polite" aria-relevant="additions"` to `#transcript-list`
   - Add `aria-live="polite"` to `#eval-loading` container (so screen readers know when evaluation starts)
   - In `evaluation.ts`: add `aria-live="polite"` to evaluation summary container
   - In `hint.ts`: verify that `textContent` mutation in `renderHint()` happens AFTER the 300ms fade completes (the `setTimeout` callback), so the aria-live announcement coincides with visible text. If the current timing is correct, add a code comment confirming this.
   - Replace `recBtn.title` with `recBtn.setAttribute('aria-describedby', 'rec-btn-desc')` pointing to a visually hidden `<span id="rec-btn-desc">` element that describes the current button state

4. Write tests:
   - `error-handling.test.ts`: test that malformed port message doesn't crash handler
   - `settings.test.ts`: test URL validation rejects invalid URLs, accepts valid ones

5. Build and verify.

**Definition of Done:**
- [ ] `init()` failure shows error banner instead of blank screen
- [ ] Malformed WS/port messages are caught and logged, not thrown
- [ ] Settings form validates URL format before saving
- [ ] `#hint-text` has `aria-live="polite"`
- [ ] `#transcript-list` has `aria-live="polite"`
- [ ] All tests pass
- [ ] Extension builds without errors

---

## Testing Strategy

- **Unit tests:** Each extracted module gets a test file in `__tests__/` directory
- **Key test targets:** File validation (upload), HTML escaping (helpers), cooldown logic (hint), dedup (transcript), phase transitions (phase-engine), timer formatting (call-timer)
- **Integration:** Extension build must succeed after each task
- **Manual verification:** After task 2.5, full end-to-end flow test: upload → briefing → preflight → record → hints → transcript → evaluation → download

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Circular import between modules | Low | High | Dependency graph verified by agent — no cycles exist. Use callback pattern for cross-module calls if needed. |
| Global variable scope changes break runtime behavior | Medium | High | Module-level `let` exports behave differently from file-level `let`. Use explicit getter/setter functions for shared mutable state. |
| Event listener registration order matters | Medium | Medium | Preserve exact `init()` call order from original file. Document any order dependencies. |
| Test infrastructure doesn't exist yet | ~~Medium~~ Resolved | ~~Medium~~ Resolved | Task 0.1 sets up Vitest + jsdom + chrome mock before any extraction begins. |
| Vite bundling changes with new module structure | Low | Medium | Vite handles ES module imports natively. Verify bundle size doesn't regress. |

## Open Questions (Resolved)
- ~~Is Jest or Vitest preferred?~~ **Vitest** — uses the same Vite config, zero additional setup for ES modules, native ESM support.
- ~~Should `chrome.storage.local` mocks use `jest-chrome` or manual mocks?~~ **Manual mocks** via `globalThis.chrome` in test setup file. Simpler, no external dependency, full control.
- ~~Should `initNewCallButton` go to phase-engine.ts or a separate module?~~ **`phase-engine.ts`** — it only calls `setPhase(2)`, which is the phase engine's core concern. Feature Inventory updated: lines 1845-1857 → task 1.2 (phase-engine.ts), lines 1815-1843 → task 2.2 (transcript.ts).
- ~~How to resolve `phase-engine ↔ rec-button` circular dep?~~ **Callback pattern** — `phase-engine.ts` exports `setUpdateRecButtonCallback()`, `rec-button.ts` registers during init.

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
