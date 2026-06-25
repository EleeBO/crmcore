# FEAT-009: Frontend Architecture Fixes — Sidepanel Split

Status: DRAFT
Created: 2026-03-14
Last Modified: 2026-03-14

## Overview

Split the 1896-line `sidepanel.ts` god module into 10 focused modules with unit tests. The file currently contains 56 functions, 20+ global variables, and 22 event handlers covering 12+ distinct concerns (phase engine, port communication, VU meters, call timer, upload, briefing, hints, transcript, evaluation, settings, mic selection, preflight). This monolith is untestable, unmaintainable, and grows with every new feature. Additionally, fix bonus issues: unhandled promise rejections, missing settings validation, and inaccessible hint/transcript updates (no aria-live regions).

## Current State

- `extension/src/sidepanel/sidepanel.ts` — 1896 LOC, 56 functions, 22 event handlers, 20+ global state variables in a single file.
- No module structure exists in the sidepanel directory — everything is in one file.
- No unit tests exist for sidepanel logic.
- Settings form accepts any string for backend URL (no validation), password "123" hardcoded.
- Hints and transcript update via textContent with no `aria-live` regions — screen readers never hear updates.
- `void init()` discards Promise — uncaught rejection shows blank panel with no error.
- `handlePortMessage` and `handleWsMessage` have no try/catch — malformed message crashes silently.

### Components

| Concern | Functions | Lines | Global Vars |
|---------|-----------|-------|-------------|
| DOM helpers | `$`, `show`, `hide`, `escapeHtml` | 17-33 | 0 |
| Splitter layout | `Splitter` class + init functions | 35-179 | `phase2Splitter`, `phase3Splitter` |
| Phase engine | `setPhase`, `updateHeader` | 182-240 | `currentPhase` |
| State management | `loadState`, `saveState`, `resetSessionState` | 242-300 | 0 |
| Port/SW connection | `connectPort`, `handlePortMessage`, etc. | 302-436 | `swPort`, `reconnectAttempts`, `handshakeReceived` |
| VU meters | `scheduleVuUpdate` | 438-461 | `pendingMic`, `pendingTab`, `vuRafPending` |
| Call timer | `startCallTimer`, `stopCallTimer`, etc. | 463-494 | `callTimerInterval`, `callStartTime` |
| Capture flow | `showCapturePrompt`, `handleCaptureStarted`, etc. | 496-616 | `capturePromptTimeout`, `sttBalanceError` |
| Evaluation display | `animateEvalProgress`, `renderEvaluationSummary`, etc. | 618-823 | `evalPollTimer`, `evalReceived`, `evalStepTimer` |
| WS dispatch | `handleWsMessage` | 825-855 | 0 |
| Hint display | `handleHintEnd`, `renderHint`, `flushPendingHint` | 857-950 | `lastHintRenderedAt`, `pendingHintEnd`, `pendingHintTimer` |
| Transcript display | `handleTranscript`, `initTranscriptScroll` | 952-1060 | `isAutoScrolling` |
| Upload flow | `validateFiles`, `setStep`, `initUpload` | 1062-1271 | 0 |
| Briefing render | `renderPortrait`, `fetchAndRenderBriefing`, etc. | 1273-1449 | 0 |
| Preflight | `runPreflight`, `initPreflight` | 1451-1523 | 0 |
| REC button | `initRecButton`, `updateRecButtonState` | 1525-1645 | 0 |
| Mic selection | `checkMicPermission`, `populateMicList`, etc. | 1647-1728 | 0 |
| Settings overlay | `initSettingsOverlay` | 1730-1813 | 0 |
| Download/New call | `downloadTranscript`, `initNewCallButton` | 1815-1857 | 0 |
| Init | `init()`, DOMContentLoaded | 1859-1896 | 0 |

### Behavior

- All 56 functions live in one file with no module boundaries.
- 20+ module-level `let` variables serve as mutable shared state across all concerns.
- Event handlers are registered inline in various `init*()` functions.
- Dependencies between functions form a DAG with no circular dependencies (verified by agent analysis).
- Phase engine is the core state machine — called by port, capture, upload, rec-button, and init.
- State module (loadState/saveState) is read by port, upload, briefing, rec-button, and init.

### Acceptance Criteria

- Given `sidepanel.ts` at 1896 LOC When split into modules Then `sidepanel.ts` entry point is ≤50 LOC
- Given 56 functions in one file When split Then each module file contains only functions for its concern
- Given no unit tests When modules are extracted Then each module has a corresponding `__tests__/*.test.ts` file
- Given no circular dependencies in the function graph When split into modules Then no circular import exists between any modules
- Given `void init()` swallows rejections When error boundary added Then `init()` failure displays error banner to user
- Given `handlePortMessage` has no try/catch When error boundary added Then malformed port messages are caught and logged without crashing
- Given `handleWsMessage` has no try/catch When error boundary added Then malformed WS messages are caught and logged without crashing
- Given settings backend URL input accepts any string When validation added Then invalid URLs show inline error and are not saved
- Given `#hint-text` has no aria-live When attribute added Then screen readers announce hint updates
- Given `#transcript-list` has no aria-live When attribute added Then screen readers announce new transcript entries
- **Given any extracted module When imported by other modules Then no circular dependency exists (enforced by build)**
- Given all changes applied When `npm run build` runs Then extension builds successfully with zero errors
- Given all changes applied When `npx tsc --noEmit` runs Then zero TypeScript errors
- Given `handleCaptureStarted` resets hint/transcript state When modules are split Then reset functions (`resetHintState`, `resetAutoScroll`, `resetBalanceError`) are exported and called across module boundaries
- Given `evalPollTimer` runs during a session When `resetSessionState` is called Then `stopEvalPolling` is also called (via registered reset callback)
- Given evaluation poll exceeds max attempts When timeout occurs Then user sees visible error message instead of perpetual loading

### Edge Cases

- **State**: Port reconnects while evaluation polling is active. `restoreFromHandshake` may call `setPhase(2)` overwriting Phase 4 and hiding evaluation loading UI. `evalPollTimer` is not cleared on reconnect.
- **Concurrency**: User uploads files, quickly closes and reopens side panel. Two `init()` calls race against same `chrome.storage.local` with no mutex.
- **Data**: Transcript from Phase 3 cloned to Phase 4 via `cloneNode(true)` — if `final_refinement` updates the original, the Phase 4 clone shows stale pre-refinement text.
- **UX**: Hint cooldown queue is a single slot (`pendingHintEnd`). If 3+ hints arrive within 8-second cooldown, earlier hints are silently dropped with no user feedback.
- **Integration**: Evaluation REST poll captures `sid` and `evalToken` in closure. `resetSessionState` does not clear `evalPollTimer` — stale session's result could render in current session's Phase 4 UI.
- **State**: Module-level `let` exports behave differently from file-level `let`. Extracted modules must use explicit getter/setter functions for shared mutable state to avoid stale references.
- **State**: `handleCaptureStarted` resets `lastHintRenderedAt`, `pendingHintEnd`, `pendingHintTimer`, and `isAutoScrolling` — variables that live in `hint.ts` and `transcript.ts` after the split. Without exported reset functions, the implementer either violates module boundaries or silently omits the resets, causing hints from previous sessions to be suppressed.
- **UX**: Evaluation poll timeout (40s) leaves `#eval-loading` visible with no error message. User sees perpetual loading spinner with no way to recover.
- **UX**: `downloadTranscript()` produces empty file if user enters Phase 4 directly via reconnect (without Phase 3 `cloneNode` populating `#transcript-full-list`).
- **Integration**: `MAX_FILE_SIZE` and `ALLOWED_TYPES` in frontend must match backend validation rules. Mismatch causes confusing post-upload errors.
- **Concurrency**: Splitter `restore()` runs via `requestAnimationFrame`. User scrolling before rAF fires sees incorrect `scrollHeight` because section heights haven't been restored yet.

## Change History

### v1 (2026-03-14) — Initial specification
- ADDED: Initial specification from architecture review finding C1 (God Module: sidepanel.ts)
- ADDED: Bonus fixes (error boundaries, settings validation, aria-live regions)
- ADDED: Backward compatibility requirement (extension builds without errors)
- Plan: [v1](../docs/plans/2026-03-14-frontend-arch-fixes.md)

### v2 (2026-03-14) — Post-review edge cases and fixes
- ADDED: Edge cases from multi-agent review (cross-module state resets, eval poll timeout, empty transcript download, file size sync, splitter race)
- ADDED: Acceptance criteria for cross-module reset functions, evalPollTimer cleanup, and eval timeout UX
- MODIFIED: Test infrastructure — resolved as Vitest with jsdom and manual chrome mock (task 0.1 added to plan)
- MODIFIED: Circular dependency — resolved with callback pattern for phase-engine ↔ rec-button
- Plan: [v1](../docs/plans/2026-03-14-frontend-arch-fixes.md) (updated in place)

### v3 (2026-03-14) — Round 2 review fixes
- ADDED: BriefingData/BriefingPortrait/BriefingStrategy/BriefingObjection types co-located with PanelState in state.ts (prevents circular dep with briefing.ts)
- ADDED: Double-init guard in entry point init() — prevents duplicate event listener registration on HMR/fast panel reopen
- MODIFIED: Feature Inventory — initNewCallButton → task 1.2 (phase-engine.ts), downloadTranscript/initDownloadButton → task 2.2 (transcript.ts)
- MODIFIED: MAX_FILE_SIZE documentation corrected from 10MB to 50MB (matches backend and frontend code)
- Plan: [v1](../docs/plans/2026-03-14-frontend-arch-fixes.md) (updated in place)
