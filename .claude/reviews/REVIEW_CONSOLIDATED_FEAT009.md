# Consolidated Review — FEAT-009: Frontend Architecture Fixes (Round 2)

Plan: `docs/plans/2026-03-14-frontend-arch-fixes.md`
Spec: `specs/FEAT-009-frontend-arch-fixes.md`
Date: 2026-03-14
Verdict: **NEEDS REVISION**

## Summary

- **Architect:** CONDITIONAL PASS (2 BLOCKERS, 3 MAJOR, 5 MINOR → 10 issues)
- **Backend:** PASS (0 blockers, 3 observations)
- **Frontend:** CONDITIONAL PASS (3 BLOCKERS, 4 MAJOR → 7 issues)
- **Total issues (deduplicated):** 4 (0 blockers, 1 major, 3 minor)

### Note on Previously Resolved Issues — Critical

The Architect and Frontend agents flagged multiple issues as **BLOCKERS** that are **already resolved** in the updated plan. This happened because agents received plan summaries, not the full 636-line plan text. The following items from Round 1 are **confirmed resolved**:

- ~~B1: Test infrastructure~~ ✅ Task 0.1 has full vitest.config.ts, setup.ts with chrome mock, smoke test
- ~~B2: Cross-module state (resetHintState, resetAutoScroll, resetBalanceError)~~ ✅ All specified in tasks 2.1/2.2 with dependency graph edges
- ~~M1: phase-engine ↔ rec-button circular dep~~ ✅ Callback pattern fully specified in task 1.2
- ~~M2: evalPollTimer not cleared on resetSessionState~~ ✅ registerResetCallback(stopEvalPolling) in task 2.2 step 3b
- ~~M3: Backend integration points undocumented~~ ✅ Full table with 5 endpoints added
- ~~M4: evalToken scope~~ ✅ SSRF posture section added
- ~~M5: Eval poll timeout~~ ✅ "Оценка недоступна" in #eval-error, task 2.2 step 4b
- ~~M6: Form validation (error element, scheme check)~~ ✅ #backend-url-error, ws:/wss: validation in task 3.1
- ~~M7: Accessibility (eval-loading, hint fade, recBtn)~~ ✅ All addressed in task 3.1 step 3
- ~~m1: Dependency graph edges~~ ✅ capture→hint, capture→transcript, briefing→preflight all in graph
- ~~m2: Error boundary coverage~~ ✅ showFatalError in helpers.ts, void .catch(console.error) specified
- ~~Reconnect-in-progress state~~ ✅ Task 2.1 step 4c: "Переподключение..." status pill
- ~~Empty transcript check~~ ✅ Task 2.2 step 2: check #transcript-full-list empty

**12 of 16 agent-flagged issues are false positives** due to incomplete plan context in review prompts.

---

## All Issues (deduplicated — genuinely new from Round 2)

### BLOCKERS

None.

### MAJOR

**M1. BriefingData type location not specified**
*Flagged by: Architect (MAJOR-3)*

`PanelState` references `BriefingData`. After the split, both must be in the same module or one must import from the other. If `BriefingData` stays in `briefing.ts` and `PanelState` is in `state.ts`, then `state.ts → briefing.ts` creates a dependency edge that conflicts with the intended direction (`briefing → state`). This would be a circular dependency.

**Fix:** Specify that `BriefingData`, `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection` interfaces move to `state.ts` alongside `PanelState` (since `PanelState` owns the reference). Add to task 1.2 implementation steps.

---

### MINOR

**m1. MAX_FILE_SIZE documentation error in Backend Integration Points table**
*Flagged by: Backend (Observation 1)*

The plan table says `MAX_FILE_SIZE=10MB`. The actual backend limit is **50 MB** (`backend/main.py:204`). The frontend constant is also 50 MB. Documentation-only error — runtime behavior is correct.

**Fix:** Update plan table entry from `10MB` to `50MB`.

---

**m2. `initNewCallButton` module assignment unspecified**
*Flagged by: Architect (MINOR-2), Frontend (Observation 1)*

`initNewCallButton()` (lines 1852-1857) simply calls `setPhase(2)`. Not explicitly assigned to any module. The entry-point sketch imports it from `phase-engine.ts`, which is correct by concern. The Feature Inventory lists it under task 2.4.

**Fix:** Clarify in plan: `initNewCallButton` lives in `phase-engine.ts` (confirmed by entry-point import). Update Feature Inventory row for lines 1815-1857 to split: `downloadTranscript`/`initDownloadButton` → task 2.2 (transcript.ts), `initNewCallButton` → task 1.2 (phase-engine.ts).

---

**m3. Double-init guard missing in entry point**
*Flagged by: Architect (EC-1, MINOR-5), Frontend (EC-3)*

No `let initialized = false` guard in `init()`. If sidepanel triggers `DOMContentLoaded` twice (HMR, fast panel reopen), all event listeners are registered twice.

**Fix:** Add `let initialized = false; if (initialized) return; initialized = true;` at the top of `init()` in task 2.5.

---

## Edge Cases by Category

### State

- **handshakeReceived flag access:** After split, entry point must read `handshakeReceived` from `port.ts` via live ESM binding. Current code works because everything is in one file. Document this as intentional in task 2.5. *(Frontend EC-4)*
- **Splitter restore() rAF timing:** `phase-engine.ts` must retain the `requestAnimationFrame` wrapper when calling `splitter.restore()`. Document in task 1.2 that this pattern is preserved. *(Architect EC-4, Frontend EC-5)*

### Data

- **BriefingData circular dep risk:** If types are not co-located with PanelState, circular import between state.ts and briefing.ts. *(Architect — M1 above)*

### UX

- **Splitter keyboard accessibility:** No `keydown` handlers on `.splitter-handle` elements. Pre-existing WCAG A issue. Out of scope for this refactor (consistent with spec Out of Scope). *(Frontend)*
- **#transcript-list aria-live noise:** Every interim transcript update triggers announcement. Consider `aria-atomic="false"`. *(Frontend)*

### Integration

- **MAX_FILE_SIZE plan table says 10MB, code says 50MB:** Documentation-only discrepancy. *(Backend — m1 above)*

---

## Recommended Actions

1. **[MAJOR] Specify BriefingData type location** — Move BriefingData and related interfaces to `state.ts`. Add to task 1.2.
2. **[MINOR] Fix MAX_FILE_SIZE in plan table** — Change 10MB to 50MB.
3. **[MINOR] Clarify initNewCallButton assignment** — Document in task 1.2 (phase-engine.ts). Fix Feature Inventory.
4. **[MINOR] Add double-init guard** — Add to task 2.5.

---

*Review complete. Resolve 1 MAJOR issue before proceeding to /implement.*
