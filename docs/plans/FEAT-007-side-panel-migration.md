# FEAT-007: Side Panel Migration — Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-08
Status: COMPLETE
Spec: specs/FEAT-007-side-panel-migration.md
Design: docs/plans/2026-03-08-side-panel-migration-design.md

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Migrate Chrome extension from popup + content-script widget to a unified Chrome Side Panel with phase-based UI.

**Architecture:** Single side panel document connected to Service Worker via named Port (`"sidepanel"`). All WS messages (hints, transcripts, audio levels) flow through the Port instead of `runtime.sendMessage` broadcast or `tabs.sendMessage`. Content script widget is completely removed. Badge on extension icon replaces the on-page recording indicator.

**Tech Stack:** Chrome Side Panel API (`chrome.sidePanel`), TypeScript, CSS (no framework), Vite build.

## Scope

### In Scope
- Side panel HTML/CSS/TS with 5 phases (0-4)
- Port-based message routing (SW ↔ Side Panel)
- GET_SESSION_STATE handshake on panel open/reopen
- AUDIO_LEVEL throttling in offscreen (15 Hz cap)
- Hint buffering in SW for panel reconnect
- Badge recording indicator (replaces widget)
- Settings as full-body overlay
- Removal of popup, content-script widget, and state machine

### Out of Scope
- Post-call summary generation UI (separate FEAT)
- Deepgram STT removal
- Backend API changes (no changes needed)
- HTTPS/WSS for backend (local dev only)

## Prerequisites
- FEAT-006 (SaluteSpeech SSL + Preflight) — ACTIVE, provides `/api/v1/preflight`
- FEAT-002 (Audio Pipeline Fix) — ACTIVE, provides working audio pipeline
- Chrome 114+ (Side Panel API GA)

## Context for Implementer

- **Port pattern:** Offscreen already uses `chrome.runtime.connect({ name: "offscreen" })` — see `extension/src/offscreen/offscreen.ts:32`. Side panel will use the same pattern with name `"sidepanel"`.
- **State machine:** Widget uses a 6-state `StateMachine` class (`extension/src/content/state-machine.ts`). Side panel replaces this with a simpler 5-phase model (0-4) where phases are UI layouts, not widget states.
- **rAF batching:** Widget's `handleHintChunk()` uses `requestAnimationFrame` to batch streaming text updates — this pattern must be preserved in side panel.
- **Upload flow:** `popup.ts` has `validateFiles()`, `doUpload()`, `setStep()` — all migrate to side panel with same logic.
- **Briefing rendering:** `renderPortrait()`, `renderStrategy()`, `renderObjections()` from `popup.ts` migrate as-is.
- **VU meters:** Popup uses `AUDIO_LEVEL` messages via `runtime.onMessage`. Side panel receives via Port instead.
- **Constants:** `API_BASE`, `BACKEND_WS_URL` from `extension/src/shared/constants.ts` — reuse unchanged.
- **WsClient:** `extension/src/lib/ws-client.ts` — used by offscreen, not by side panel. Unchanged.
- **Vite config:** Uses `vite-plugin-web-extension` which auto-discovers entries from manifest. Adding `side_panel.default_path` in manifest should auto-include it. `additionalInputs` for popup can be removed.

## Feature Inventory — Files Being Replaced

| Old File | Functions/Classes | Mapped to Task |
|----------|-------------------|----------------|
| `extension/src/popup/popup.ts` | `$()`, `show()`, `hide()`, `escapeHtml()` (helpers) | 2.2 |
| | `BriefingPortrait`, `BriefingStrategy`, `BriefingObjection`, `BriefingData`, `PopupState` (interfaces) | 2.2 |
| | `loadState()`, `saveState()` (chrome.storage.session) | 2.2 |
| | `initTabs()` (tab navigation) | REMOVED — replaced by phase-based layout |
| | `checkMicPermission()`, `updateMicStatus()` (mic permission UI) | 2.2, 2.4 |
| | `MAX_FILE_SIZE`, `ALLOWED_TYPES`, `validateFiles()`, `isAllowedExtension()` (file validation) | 2.3 |
| | `setStep()`, `initUpload()`, `doUpload()` (upload flow) | 2.3 |
| | `initRecButton()` (REC toggle + VU meter listener) | 2.4 |
| | `renderPortrait()`, `renderStrategy()`, `renderObjections()` (briefing rendering) | 2.3 |
| | `fetchAndRenderBriefing()`, `initBriefing()` (briefing fetch + refresh) | 2.3 |
| | `PreflightResult`, `runPreflight()`, `initPreflight()` (preflight status) | 2.3 |
| | `initSettings()` (settings: backend URL, URL pattern, mic) | 2.4 |
| | `init()` (orchestrator) | 2.2 |
| `extension/src/popup/popup.html` | Full HTML structure (header, tabs, session, drop zone, stepper, briefing, settings) | 2.1 |
| `extension/src/popup/popup.css` | All popup styles (623 lines) | 2.1 |
| `extension/src/content/widget.ts` | `COLORS`, `WIDGET_HTML`, `WIDGET_CSS` (widget template/styles) | REMOVED — replaced by side panel CSS |
| | `CopilotWidget.constructor()`, `mount()`, `bindEvents()` (Shadow DOM injection, drag, keyboard) | REMOVED — side panel is its own document |
| | `CopilotWidget.handleHintStart()`, `handleHintChunk()`, `handleHintEnd()` (hint streaming with rAF) | 2.4 |
| | `CopilotWidget.handleTranscript()` (transcript bar with flash effect) | 2.4 |
| | `CopilotWidget.handleStatus()` (session state transitions) | 2.2 |
| | `CopilotWidget.handleBriefing()` (briefing display) | 2.3 |
| | `CopilotWidget.handleAudioLevel()` (equalizer bars) | 2.4 |
| | `CopilotWidget.toggle()`, `expand()`, `collapse()`, `applyState()` (panel visibility) | REMOVED — side panel manages phases |
| | `boot()`, `chrome.runtime.onMessage` listener | 2.2 (Port listener replaces broadcast) |
| `extension/src/content/widget.css` | Empty placeholder (styles in Shadow DOM) | REMOVED |
| `extension/src/content/state-machine.ts` | `TRANSITIONS` map, `StateMachine` class (`current()`, `onStateChange()`, `dispatch()`, `forceState()`) | REMOVED — phase model is simpler |

### Feature Mapping Verification

- [x] All old files listed above
- [x] All functions/classes identified
- [x] Every feature has a task number OR explicit "REMOVED" with justification
- [x] No features accidentally omitted

**Removed features justification:**
- `initTabs()` — tabs replaced by phase-based layout (spec decision)
- Widget Shadow DOM, drag, keyboard shortcut — side panel is a persistent Chrome-managed panel, no injection needed
- Widget state machine (6 states) — replaced by 5-phase model per spec
- Widget CSS/HTML template — completely new design per spec
- `widget.css` — empty placeholder file

## Progress Tracking

### 1. Foundation
- [x] 1.1 Update manifest, Vite config, and shared message types

### 2. Side Panel Implementation
- [x] 2.1 Create side panel HTML and CSS (all phases)
- [x] 2.2 Create side panel TS — core infrastructure (phase engine, Port, state, init)
- [x] 2.3 Implement upload + briefing features (Phases 0→1→2)
- [x] 2.4 Implement live session + settings (Phases 3→4, settings overlay)

### 3. Service Worker & Offscreen
- [x] 3.1 Refactor service-worker.ts — Port routing, badge, hint buffer, handshake
- [x] 3.2 Add AUDIO_LEVEL throttling to offscreen.ts

### 4. Cleanup
- [x] 4.1 Remove old files, verify build, final integration

**Total Tasks:** 8 | **Completed:** 8 | **Remaining:** 0

## Implementation Tasks

### 1. Foundation

#### 1.1 Update manifest, Vite config, and shared message types

**Objective:** Configure the extension build to include side panel and remove popup/widget entries. Add new message types for Port communication.

**Files:**
- Modify: `extension/manifest.json`
- Modify: `extension/vite.config.ts`
- Modify: `extension/src/shared/messages.ts`

**Implementation Steps:**

1. **`manifest.json`** — Apply all changes:
   ```json
   {
     "permissions": ["activeTab", "tabCapture", "offscreen", "storage", "tabs", "alarms", "sidePanel"],
     "side_panel": { "default_path": "src/sidepanel/sidepanel.html" }
   }
   ```
   - Add `"sidePanel"` to permissions array
   - Add `"side_panel": { "default_path": "src/sidepanel/sidepanel.html" }` top-level key
   - Remove `"action": { "default_popup": "src/popup/popup.html" }` — keep `"action": {}` (empty, needed for `chrome.action` API)
   - Remove `"content_scripts"` array entirely
   - **Keep** `"web_accessible_resources"` as-is — `offscreen.ts:99` calls `audioCtx.audioWorklet.addModule(chrome.runtime.getURL("audio-worklet.js"))` which requires this entry. The `matches: ["chrome-extension://*/*"]` scope is correct.

2. **`vite.config.ts`** — Update build entries:
   - The `vite-plugin-web-extension` reads manifest and auto-discovers entries. Since we removed popup and content_scripts from manifest, and added `side_panel`, the plugin should auto-include `src/sidepanel/sidepanel.html`.
   - Remove any popup-specific entries if referenced in `additionalInputs`.
   - Keep `src/offscreen/offscreen.html` and `src/permissions/permissions.html` in `additionalInputs`.

3. **`messages.ts`** — Modify types:
   - Remove `| { type: "WIDGET_STATE"; state: WidgetState }` from `ExtMessage` union (widget is deleted)
   - Remove `WidgetState` from the import (keep `HintPayload` — still used by `WsHintEnd`)
   - Add new message types to `ExtMessage` union:
   ```typescript
   | { type: "GET_SESSION_STATE" }
   | { type: "SESSION_STATE"; capturing: boolean; sessionId: string; kbId: string; wsConnected: boolean }
   | { type: "SESSION_ABORTED"; reason: string }
   | { type: "WS_RECONNECTED" }
   | { type: "WS_STATUS"; connected: boolean }
   ```

**Definition of Done:**
- [ ] manifest.json has `sidePanel` permission and `side_panel` key
- [ ] manifest.json has no `content_scripts` or `default_popup`
- [ ] manifest.json keeps `web_accessible_resources` for audio-worklet.js
- [ ] vite.config.ts builds sidepanel entry
- [ ] messages.ts exports new message types, `WIDGET_STATE` removed
- [ ] TypeScript compiles without errors

---

### 2. Side Panel Implementation

#### 2.1 Create side panel HTML and CSS (all phases)

**Objective:** Build the complete HTML structure and CSS for the side panel with phase-based layout: fixed header (44px) + control bar (52px, sticky) + scrollable content area.

**Files:**
- Create: `extension/src/sidepanel/sidepanel.html`
- Create: `extension/src/sidepanel/sidepanel.css`

**Implementation Steps:**

1. **`sidepanel.html`** — Structure per spec:
   ```
   Fixed Region (96px total = 44px header + 52px control bar):

   Header (44px, fixed):
     "AI Sales Copilot"    [Status Pill] [⚙ gear]

   Control Bar (52px, sticky below header):
     [● REC]  МИК ████░░  ЗВУК ███░░░
              ✓STT  ✓LLM  ✓Redis

   Content Area (scrollable, starts at top: 96px, phase-driven):
     Phase 0: Upload drop zone
     Phase 1: Upload stepper (replaces drop zone)
     Phase 2: Briefing expanded + compact file strip
     Phase 3: Sticky hint + transcript + collapsed briefing
     Phase 4: Completion strip + full transcript

   Session Error Banner (hidden, shown on SESSION_ABORTED):
     "Сессия прервана: {reason}" — auto-hides after 5s

   Settings Overlay (full-body, hidden by default):
     [← Назад]
     Mic settings, Backend URL, URL pattern
   ```

   Key elements (IDs for TS binding):
   - `#header`, `#status-pill`, `#gear-btn`
   - `#control-bar`, `#rec-btn`, `#rec-label`, `#vu-mic`, `#vu-tab`, `#preflight-status`
   - `#session-error-banner` — error banner for aborted sessions
   - `#content-area`
   - Phase containers: `#phase-0`, `#phase-1`, `#phase-2`, `#phase-3`, `#phase-4`
   - Phase 0: `#drop-zone`, `#file-input`
   - Phase 1: `#upload-stepper`, `#stepper-text`
   - Phase 2: `#briefing-content`, `#portrait-text`, `#strategy-text`, `#objections-list`, `#file-strip`
   - Phase 3: `#hint-area`, `#transcript-area`, `#briefing-collapsed`
   - Phase 4: `#completion-strip`, `#transcript-full`
   - Settings: `#settings-overlay`, `#settings-back-btn`, `#backend-url-input`, `#url-pattern-input`, `#mic-settings`

2. **`sidepanel.css`** — Styles covering:
   - Reset, body min-width: 320px, flex-based, no fixed body width
   - Header: fixed top, 44px height, flex row, blue title
   - Control bar: sticky below header, 52px, flex row with REC button + VU meters + preflight dots
   - Content area: flex-grow, overflow-y: auto, padding
   - Phase containers: only active phase visible (`.phase.active`)
   - Phase 0: drop zone (same styles as popup)
   - Phase 1: stepper (same styles as popup)
   - Phase 2: briefing cards (portrait, strategy, objections), collapsible sections, compact file strip
   - Phase 3: sticky hint area (amber bg #FFF8E1, color-coded left border), transcript area with speaker bars (blue=Вы, green=Клиент), collapsed briefing (32px disclosure triangles, max-height 240px on expand)
   - Phase 4: completion strip, full transcript
   - Settings overlay: position fixed, full size, white bg, z-index above content
   - REC button: same styles as popup (rec-idle, rec-active, rec-dot pulse)
   - VU meters: same styles as popup
   - Preflight chips: same styles as popup
   - Responsive: works at min-width 320px

**Carry forward from popup.css:**
- REC button styles (`.rec-btn`, `.rec-idle`, `.rec-active`, `.rec-dot`, `@keyframes rec-pulse`)
- VU meter styles (`.vu-row`, `.vu-track`, `.vu-fill`)
- Stepper styles (`.step`, `.step-icon`, `.step-line`, states)
- Briefing card styles (`.card`, portrait/strategy/objections styles)
- Preflight chip styles (`.preflight-row`, `.preflight-chip`, `.pf-dot`)
- Settings styles (labels, inputs, buttons)

**New styles for side panel:**
- Phase-based visibility system
- Hint area (amber bg, left border color-coded)
- Transcript list (scrollable, speaker-colored bars, auto-scroll)
- Collapsed briefing (disclosure triangles, 32px headers)
- Completion strip (Phase 4)
- Settings overlay (full-body, not a tab)

**Definition of Done:**
- [ ] sidepanel.html has complete structure for all 5 phases
- [ ] sidepanel.css covers all phase layouts
- [ ] Layout renders correctly at 320px width minimum
- [ ] Styles carried forward from popup for reused components

---

#### 2.2 Create side panel TS — core infrastructure

**Objective:** Build the core TypeScript module for the side panel: phase engine, Port connection to SW, state management via chrome.storage.session, GET_SESSION_STATE handshake, and gear icon settings overlay toggle.

**Files:**
- Create: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**

1. **Imports and helpers:**
   - Import `API_BASE` from `../shared/constants`
   - Import `ExtMessage`, `WsMessage` types from `../shared/messages`
   - Reuse `$()`, `show()`, `hide()`, `escapeHtml()` helpers from popup.ts

2. **Phase engine:**
   ```typescript
   type Phase = 0 | 1 | 2 | 3 | 4;
   let currentPhase: Phase = 0;

   function setPhase(phase: Phase): void {
     currentPhase = phase;
     document.querySelectorAll('.phase').forEach(el => {
       el.classList.toggle('active', el.id === `phase-${phase}`);
     });
     updateHeader(phase);
   }
   ```
   - Phase 0: no files — show drop zone, REC disabled
   - Phase 1: uploading — show stepper
   - Phase 2: ready — briefing expanded, REC enabled
   - Phase 3: live — hint area + transcript, REC shows СТОП
   - Phase 4: done — completion strip + full transcript

3. **Port connection to SW (with exponential backoff):**
   ```typescript
   let swPort: chrome.runtime.Port | null = null;
   let reconnectAttempts = 0;
   const MAX_RECONNECT_ATTEMPTS = 10;

   function connectPort(): void {
     if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
       // Show error state in header: "Расширение недоступно"
       updateStatusPill("error", "Расширение недоступно");
       return;
     }
     swPort = chrome.runtime.connect({ name: "sidepanel" });
     swPort.onMessage.addListener((msg) => {
       reconnectAttempts = 0; // Reset on successful message
       handlePortMessage(msg);
     });
     swPort.onDisconnect.addListener(() => {
       swPort = null;
       reconnectAttempts++;
       const delay = Math.min(1000 * 2 ** reconnectAttempts, 30_000);
       setTimeout(connectPort, delay);
     });
     // Request current state
     swPort.postMessage({ type: "GET_SESSION_STATE" });
   }
   ```

4. **Port message handler:**
   ```typescript
   function handlePortMessage(msg: any): void {
     switch (msg.type) {
       case "SESSION_STATE":
         restoreState(msg);  // Initialize phase from SW state
         break;
       case "WS_MESSAGE":
         handleWsMessage(msg.payload as WsMessage);
         break;
       case "AUDIO_LEVEL":
         updateVuMeters(msg.mic, msg.tab);
         break;
       case "SESSION_ABORTED":
         handleSessionAborted(msg.reason);  // Show error banner, reset to Phase 0
         break;
       case "WS_RECONNECTED":
         showReconnectedBadge();  // Temporary "Переподключено" in status pill
         break;
     }
   }
   ```

   **`handleSessionAborted()` implementation:**
   - Show `#session-error-banner` with the abort reason text
   - Set Phase 0 (reset to initial state)
   - Reset internal state (clear cached briefing, sessionId, kbId)
   - Auto-hide banner after 5 seconds

5. **State management (chrome.storage.session):**
   - Reuse `PopupState` interface (renamed to `PanelState`)
   - Reuse `loadState()` / `saveState()` (key changed from `"popup"` to `"panel"`)

6. **State restore from SW handshake (authoritative — overrides storage):**
   ```typescript
   let handshakeReceived = false;

   function restoreFromHandshake(state: { capturing: boolean; sessionId: string; kbId: string; wsConnected: boolean }): void {
     handshakeReceived = true;  // Prevent storage-based setPhase from overwriting
     if (state.capturing) {
       setPhase(3);  // Live call in progress
       // Update REC button to СТОП, show VU meters
     } else if (state.kbId) {
       setPhase(2);  // Briefing ready
     } else {
       setPhase(0);  // No files
     }
     // Update WS connection status in header
     updateWsStatus(state.wsConnected);
   }
   ```
   - **Race prevention:** The `init()` function loads cached state from chrome.storage.session and may call `setPhase()`. If the SW handshake arrives, it takes precedence. The `handshakeReceived` flag prevents the storage-based restore from overwriting the handshake state.

7. **Settings overlay:**
   ```typescript
   function initSettingsOverlay(): void {
     const gearBtn = $('#gear-btn');
     const overlay = $('#settings-overlay');
     const backBtn = $('#settings-back-btn');

     gearBtn?.addEventListener('click', () => show(overlay));
     backBtn?.addEventListener('click', () => hide(overlay));

     // Load saved settings
     // Save settings on change
     // Mic permission check
   }
   ```
   - Reuse `initSettings()` logic from popup.ts but without `window.close()`
   - Settings: Микрофон, URL бэкенда, URL-паттерн CRM

8. **Init function:**
   ```typescript
   async function init(): Promise<void> {
     connectPort();  // Fires GET_SESSION_STATE immediately
     initSettingsOverlay();

     // Load cached state (may be overridden by SW handshake)
     const state = await loadState();
     if (!handshakeReceived && state.briefing) {
       // Render cached briefing, set Phase 2 (only if SW hasn't responded yet)
       renderBriefingFromCache(state.briefing);
       setPhase(2);
     }
   }

   document.addEventListener('DOMContentLoaded', () => void init());
   ```

**Definition of Done:**
- [ ] Phase engine switches visible content correctly
- [ ] Port connects to SW and handles GET_SESSION_STATE
- [ ] State restored from both chrome.storage.session and SW handshake
- [ ] Settings overlay opens/closes correctly
- [ ] TypeScript compiles without errors

---

#### 2.3 Implement upload + briefing features (Phases 0→1→2)

**Objective:** Migrate file upload flow and briefing rendering from popup.ts to side panel. Phases 0 (drop zone), 1 (stepper), and 2 (briefing expanded).

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**

1. **File validation** — Carry forward from popup.ts:
   - `MAX_FILE_SIZE`, `ALLOWED_TYPES` constants
   - `validateFiles()`, `isAllowedExtension()` functions

2. **Upload flow** — Carry forward with phase transitions:
   - `initUpload()`: bind drag-and-drop on `#drop-zone`, bind file input
   - `doUpload()`: validate → `setPhase(1)` → `setStep("upload")` → POST `/api/v1/upload` → `setStep("process")` → fetch briefing → `setStep("done")` → `setPhase(2)`
   - `setStep()`: same stepper animation logic as popup.ts
   - On error: stay in Phase 0, show error

3. **Briefing rendering** — Carry forward from popup.ts:
   - `renderPortrait()`, `renderStrategy()`, `renderObjections()` — exact same logic
   - `fetchAndRenderBriefing()` — same fetch + render + cache to `saveState({ briefing })`
   - Cache briefing in chrome.storage.session for panel reopen
   - After briefing renders: `setPhase(2)`, enable REC button

4. **Briefing refresh:**
   - Compact file strip in Phase 2 with file names + [↻ Перезагрузить] + [♻ Обновить брифинг]
   - "Обновить брифинг" calls `fetchAndRenderBriefing()`
   - "Перезагрузить" shows drop zone again (setPhase(0), clear state)

5. **Preflight status** — Carry forward from popup.ts:
   - `runPreflight()` — same fetch + chip update logic
   - `initPreflight()` — click to recheck
   - Called after briefing loads
   - Chips shown in control bar area

6. **Cached briefing restore on panel open:**
   - In `init()`, check `state.briefing` — if present, render and set Phase 2
   - Same logic as popup.ts init block

**Definition of Done:**
- [ ] File drag-and-drop uploads correctly
- [ ] Stepper shows progress through phases
- [ ] Briefing renders in Phase 2 with all three sections
- [ ] Preflight chips update after briefing load
- [ ] Cached briefing restores on panel reopen
- [ ] File strip allows reload/refresh

---

#### 2.4 Implement live session + settings (Phases 3→4, settings overlay)

**Objective:** Build the live call experience (Phase 3) and call ended view (Phase 4). Phase 3 is the PRIMARY phase — optimize for this. Also finalize settings overlay.

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Implementation Steps:**

1. **REC button** — Migrate from popup.ts `initRecButton()`:
   - Click toggles between start/stop session
   - Start: send `START_SESSION` via `chrome.runtime.sendMessage` (SW handles tabCapture)
   - Stop: send `STOP_SESSION` via `chrome.runtime.sendMessage`
   - On start success: `setPhase(3)`, update button to СТОП
   - On stop: `setPhase(4)`, update button back to REC
   - Disable when no kbId or no mic permission
   - Note: Must use `chrome.runtime.sendMessage` (not Port) for START/STOP because SW needs `sendResponse`

2. **VU meters** — Receive from Port:
   ```typescript
   function updateVuMeters(mic: number, tab: number): void {
     const micPct = Math.min(100, mic * 400);
     const tabPct = Math.min(100, tab * 400);
     if (vuMic) vuMic.style.width = `${micPct}%`;
     if (vuTab) vuTab.style.width = `${tabPct}%`;
   }
   ```
   - Use rAF batching for DOM updates (Layer 2 throttling per spec)

3. **Hint display (Phase 3)** — Migrate from widget.ts with modifications:
   - Single hint area, current. New hint replaces old (fade transition)
   - Amber background (#FFF8E1), color-coded left border (green/blue/red from `hint_start.color`)
   - `handleHintStart()`: clear hint area, set border color
   - `handleHintChunk()`: rAF-batched text append (carry forward widget pattern)
   - `handleHintEnd()`: finalize text, show source badge if present
   - No auto-dismiss — hint stays until replaced by new hint or session ends
   - When no hint: area collapses to 0 height

4. **Transcript display (Phase 3)** — Upgraded from widget transcript bar:
   - Full scrollable transcript, not just latest line
   - Speaker differentiation: `[Вы]` = blue left bar, `[Клиент]` = green left bar
   - `handleTranscript()`: append new entry to transcript list
   - Auto-scroll to bottom when user is at bottom
   - On manual scroll up: show "Jump to latest" floating pill
   - "Jump to latest" pill scrolls back and dismisses
   - rAF batching for streaming text (from widget.ts pattern)

5. **Collapsed briefing (Phase 3):**
   - ▸ disclosure triangles for each section (Портрет, Стратегия, Возражения)
   - 32px per collapsed header
   - On click: expand with max-height 240px, overflow-y: auto
   - Hint can reference "См: Возражение #2" → auto-expand that section

6. **Phase 4 — Call Ended:**
   - Completion strip: "Звонок завершён — {duration}" + [Новый звонок]
   - Full transcript (scrollable from top, auto-scroll off)
   - Briefing collapsed
   - "Новый звонок" → `setPhase(2)` (ready for next call)
   - **Cleanup on Phase 3→4 transition:** Dismiss "Jump to latest" pill, stop call timer, reset scroll tracking state

7. **WS message dispatch** — Central handler:
   ```typescript
   function handleWsMessage(msg: WsMessage): void {
     switch (msg.type) {
       case "hint_start": handleHintStart(msg); break;
       case "hint_chunk": handleHintChunk(msg); break;
       case "hint_end": handleHintEnd(msg); break;
       case "transcript": handleTranscript(msg); break;
       case "error": console.error(`[Copilot] Backend error: ${msg.code}`); break;
     }
   }
   ```

8. **Settings overlay finalization:**
   - Mic permission check + grant button (opens permissions.html in new tab)
   - Backend URL input + save
   - URL pattern input + save
   - Settings saved notification
   - Listen for `chrome.storage.onChanged` for mic permission updates

9. **Timer display:**
   - In Phase 3, header shows call duration: `[● 02:34]`
   - Start timer on session start, stop on session end
   - Update every second via `setInterval`

**Definition of Done:**
- [ ] REC button starts/stops sessions correctly
- [ ] VU meters update smoothly via Port
- [ ] Hints stream with rAF batching and amber background
- [ ] Transcript appends with speaker differentiation and auto-scroll
- [ ] Collapsed briefing sections expand/collapse with max-height
- [ ] Phase 4 shows completion strip with duration
- [ ] Settings overlay fully functional
- [ ] Call timer displays in header

---

### 3. Service Worker & Offscreen

#### 3.1 Refactor service-worker.ts — Port routing, badge, hint buffer, handshake

**Objective:** Replace `tabs.sendMessage` and `runtime.sendMessage` broadcast with Port-based routing to side panel. Add badge recording indicator, hint buffering for panel reconnect, and GET_SESSION_STATE handshake.

**Files:**
- Modify: `extension/src/background/service-worker.ts`

**Implementation Steps:**

1. **Side panel Port management:**
   ```typescript
   let sidePanelPort: chrome.runtime.Port | null = null;
   let wsConnected = false;  // Tracks actual WebSocket state, not just offscreen liveness

   // In onConnect listener (alongside existing offscreen port):
   if (port.name === "sidepanel") {
     sidePanelPort = port;
     port.onMessage.addListener((msg) => {
       if (msg.type === "GET_SESSION_STATE") {
         port.postMessage({
           type: "SESSION_STATE",
           capturing: captureInProgress,
           sessionId: currentSessionId,
           kbId: currentKbId,
           wsConnected,
         });
         // Replay buffered hint if any
         if (hintBuffer && captureInProgress) {
           for (const m of hintBuffer) {
             port.postMessage({ type: "WS_MESSAGE", payload: m });
           }
         }
       }
     });
     port.onDisconnect.addListener(() => {
       sidePanelPort = null;
     });
   }
   ```

2. **Store session state in SW** for handshake:
   ```typescript
   let currentSessionId = "";
   let currentKbId = "";
   ```
   - Set `currentSessionId` and `currentKbId` from `message.sessionId` and `message.kbId` on START_SESSION
   - Clear on STOP_SESSION

   **Track WebSocket connectivity** via offscreen port messages:
   - On `offscreenPort.onMessage("WS_RECONNECTED")` → set `wsConnected = true`, forward to `sidePanelPort`
   - On `offscreenPort.onMessage("WS_STATUS")` → update `wsConnected = msg.connected`
   - On `offscreenPort.onDisconnect` → set `wsConnected = false`

3. **Replace message routing:**
   - `offscreenPort.onMessage("WS_MESSAGE")` → `sidePanelPort?.postMessage({ type: "WS_MESSAGE", payload })` instead of `tabs.sendMessage`
   - `offscreenPort.onMessage("AUDIO_LEVEL")` → `sidePanelPort?.postMessage({ type: "AUDIO_LEVEL", mic, tab })` instead of both `tabs.sendMessage` and `runtime.sendMessage`
   - Remove all `chrome.tabs.sendMessage(sessionTabId, ...)` calls
   - Remove `chrome.runtime.sendMessage(levelMsg)` broadcast

4. **Badge management:**
   ```typescript
   // On START_SESSION success:
   chrome.action.setBadgeText({ text: "REC" });
   chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });

   // On STOP_SESSION or offscreen disconnect:
   chrome.action.setBadgeText({ text: "" });
   ```

5. **Side panel behavior — open on icon click:**
   ```typescript
   // At top level:
   chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })
     .catch(console.error);
   ```

6. **Hint buffering:**
   ```typescript
   let hintBuffer: WsMessage[] | null = null;

   // In WS_MESSAGE handler:
   if (payload.type === "hint_start") {
     hintBuffer = [payload];
   } else if (payload.type === "hint_chunk" && hintBuffer) {
     hintBuffer.push(payload);
   } else if (payload.type === "hint_end" && hintBuffer) {
     hintBuffer.push(payload);
     // Keep buffer until next hint_start replaces it
   }
   ```
   - On sidePanelPort reconnect (GET_SESSION_STATE), replay buffer
   - Buffer cleared on session end

7. **SESSION_ABORTED:**
   - On offscreen port disconnect while capturing:
     ```typescript
     if (captureInProgress) {
       sidePanelPort?.postMessage({ type: "SESSION_ABORTED", reason: "Offscreen document killed" });
     }
     ```

8. **Per-tab side panel scope:**
   ```typescript
   // In START_SESSION handler, after successful capture:
   if (targetTabId) {
     chrome.sidePanel.setOptions({ tabId: targetTabId, enabled: true });
   }
   ```

**Definition of Done:**
- [ ] Side panel receives WS messages via Port (not broadcast)
- [ ] AUDIO_LEVEL forwarded via Port only (no broadcast)
- [ ] Badge shows "REC" during capture
- [ ] GET_SESSION_STATE returns current state
- [ ] Hint buffer replayed on panel reconnect
- [ ] SESSION_ABORTED sent on offscreen crash
- [ ] Side panel opens on icon click
- [ ] No `tabs.sendMessage` or `runtime.sendMessage` broadcast calls remain
- [ ] TypeScript compiles without errors

---

#### 3.2 Add AUDIO_LEVEL throttling to offscreen.ts

**Objective:** Cap AUDIO_LEVEL messages at 15 Hz (66ms between posts) in the offscreen document. Add WS_RECONNECTED notification to SW. This is Layer 1 of the two-layer throttling strategy.

**Files:**
- Modify: `extension/src/offscreen/offscreen.ts`

**Implementation Steps:**

1. **Add timestamp gate:**
   ```typescript
   const AUDIO_LEVEL_MIN_INTERVAL_MS = 66; // ~15 Hz
   let lastLevelSentAt = 0;
   ```

2. **In workletNode.port.onmessage handler** — wrap the AUDIO_LEVEL post:
   ```typescript
   } else if (data.type === "level" && swPortAlive) {
     const now = performance.now();
     if (now - lastLevelSentAt < AUDIO_LEVEL_MIN_INTERVAL_MS) return;
     lastLevelSentAt = now;
     try {
       swPort.postMessage({
         type: "AUDIO_LEVEL",
         mic: data.mic ?? 0,
         tab: data.tab ?? 0,
       });
     } catch {
       swPortAlive = false;
     }
   }
   ```

3. **Add WS_RECONNECTED notification** — In the `WsClient` `onReconnect` callback (line 133-139), after the `sendControl(session_start)` call, post a message to the SW port:
   ```typescript
   wsClient = new WsClient(handleWsMessage, BACKEND_WS_URL, () => {
     wsClient?.sendControl({
       type: "session_start",
       session_id: currentSessionId,
       kb_id: currentKbId,
     });
     // Notify SW of reconnection (for side panel status)
     if (swPortAlive) {
       try { swPort.postMessage({ type: "WS_RECONNECTED" }); } catch { swPortAlive = false; }
     }
   });
   ```

4. **Add WS open/close status notifications** — Post `WS_STATUS` on initial connect:
   - After `wsClient.waitForOpen()` succeeds: `swPort.postMessage({ type: "WS_STATUS", connected: true })`
   - In `stopCapture()` after `wsClient.close()`: `swPort.postMessage({ type: "WS_STATUS", connected: false })`

**Definition of Done:**
- [ ] AUDIO_LEVEL messages sent at max 15 Hz
- [ ] WS_RECONNECTED posted to SW on WebSocket reconnect
- [ ] WS_STATUS posted on connect/disconnect for accurate status tracking
- [ ] No functional change to other messages
- [ ] TypeScript compiles without errors

---

### 4. Cleanup

#### 4.1 Remove old files, verify build, final integration

**Objective:** Delete all popup and content-script files. Verify the extension builds and loads correctly.

**Files:**
- Delete: `extension/src/popup/popup.ts`
- Delete: `extension/src/popup/popup.html`
- Delete: `extension/src/popup/popup.css`
- Delete: `extension/src/content/widget.ts`
- Delete: `extension/src/content/widget.css`
- Delete: `extension/src/content/state-machine.ts`

**Implementation Steps:**

1. **Delete files:**
   - Remove the 6 files listed above
   - Remove `extension/src/popup/` directory if empty
   - Remove `extension/src/content/` directory if empty

2. **Clean up shared types if needed:**
   - `extension/src/shared/types.ts` — check if `WidgetState` type is still used elsewhere. If only used by deleted files, remove it. Keep `HintPayload`, `SearchResult`, `AudioFrame`, `ControlFrame` if used.

3. **Verify build:**
   ```bash
   cd extension && pnpm run build
   ```
   - Must complete with exit 0
   - `dist/` should contain `src/sidepanel/` not `src/popup/` or `src/content/`
   - `dist/manifest.json` should have `side_panel` key, no `content_scripts`

4. **Verify manifest integrity:**
   - `dist/manifest.json` has correct `side_panel.default_path`
   - No references to deleted files
   - `web_accessible_resources` removed or updated

5. **Manual load test checklist** (for developer):
   - Load unpacked extension in Chrome
   - Click extension icon → side panel opens (not popup)
   - No console errors on panel open
   - Drop zone visible in Phase 0
   - No widget injected on web pages
   - Badge area clean (no "REC" when not recording)

**Definition of Done:**
- [ ] All 6 old files deleted
- [ ] `pnpm run build` succeeds with exit 0
- [ ] No TypeScript compilation errors
- [ ] dist/ contains sidepanel files, no popup/widget files
- [ ] No dead imports or references to deleted modules

---

## Testing Strategy

**Unit tests:** Not applicable — Chrome extension code runs in browser context, no node-based test runner configured for extension code.

**Manual verification (developer):**
1. Load unpacked extension from `dist/`
2. Phase 0: Panel opens, drop zone visible, REC disabled
3. Phase 1: Drag file → stepper progresses → briefing loads
4. Phase 2: Briefing displayed, REC enabled, preflight green
5. Phase 3: Press REC → СТОП button, VU meters animate, transcript streams, hints appear
6. Close/reopen panel during recording → state restores
7. Stop recording → Phase 4 with completion strip
8. Settings overlay opens/closes correctly
9. Badge shows "REC" during recording
10. No widget on CRM pages

**Integration verification:**
- Backend running → upload file → briefing generates → REC → speak → transcript + hints flow through

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| vite-plugin-web-extension doesn't auto-discover side_panel | Medium | High | Manually add sidepanel.html to additionalInputs |
| Chrome Side Panel API not available on user's Chrome version | Low | High | Require Chrome 114+, document in README |
| Port disconnect during hint stream loses partial text | Medium | Low | SW hint buffer replays on reconnect |
| Side panel width too narrow for briefing content | Low | Medium | CSS min-width: 320px, flex-based layout |
| TabCapture still requires action click from popup context | Low | High | tabCapture works from SW with `getMediaStreamId`, not popup-dependent |

## Open Questions

- None — spec is comprehensive, all decisions made during brainstorming + multi-agent review.

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
