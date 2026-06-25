# FEAT-007: Side Panel Migration

Status: ACTIVE
Created: 2026-03-08
Last Modified: 2026-03-09

## Overview

Мигрировать Chrome-расширение AI Sales Copilot с popup + content-script widget на единый Chrome Side Panel. Popup полностью заменяется side panel. Content-script widget удаляется — хинты и транскрипт переезжают в side panel. Клик по иконке расширения открывает side panel вместо popup.

## Dependencies

- **FEAT-006** (SaluteSpeech SSL + Preflight) — ACTIVE, provides `/api/v1/preflight` endpoint used in side panel
- **FEAT-002** (Audio Pipeline Fix) — ACTIVE, provides working audio pipeline

## Current State

### Components

| File | Purpose |
|------|---------|
| `extension/manifest.json` | sidePanel permission, `side_panel` key, no popup/content_scripts |
| `extension/src/sidepanel/sidepanel.html` | Side panel HTML — 5 phases, header, control bar, settings overlay |
| `extension/src/sidepanel/sidepanel.css` | Side panel styles — phases, hints, transcript, briefing |
| `extension/src/sidepanel/sidepanel.ts` | Side panel logic — phase engine, Port, upload, briefing, live session |
| `extension/src/background/service-worker.ts` | Port routing (sidepanel + offscreen), badge, hint buffer, handshake |
| `extension/src/offscreen/offscreen.ts` | AUDIO_LEVEL 15Hz throttle, WS_RECONNECTED/WS_STATUS notifications |
| `extension/src/shared/messages.ts` | ExtMessage union with GET_SESSION_STATE, SESSION_STATE, SESSION_ABORTED, WS_RECONNECTED, WS_STATUS |
| `extension/src/shared/types.ts` | WidgetState removed, HintPayload retained |

### Removed Files

- `extension/src/popup/popup.html` — replaced by sidepanel.html
- `extension/src/popup/popup.ts` — replaced by sidepanel.ts
- `extension/src/popup/popup.css` — replaced by sidepanel.css
- `extension/src/content/widget.ts` — replaced by side panel hint/transcript display
- `extension/src/content/widget.css` — empty, removed
- `extension/src/content/state-machine.ts` — replaced by 5-phase model

## Architecture

### Message Routing (Port-based)

Side panel uses named Port (`"sidepanel"`) instead of broadcast `runtime.sendMessage`:

```
┌────────────┐    Port: "offscreen"    ┌─────────────┐
│  Offscreen  │◄──────────────────────►│   Service    │
│  Document   │  WS_MESSAGE,           │   Worker     │
│  (audio,WS) │  AUDIO_LEVEL,          │              │
│             │  WS_RECONNECTED,       │              │
│             │  WS_STATUS             │              │
└────────────┘                         └──────┬───────┘
                                              │ Port: "sidepanel"
                                              │ (WS_MESSAGE, AUDIO_LEVEL,
                                              │  SESSION_STATE, SESSION_ABORTED,
                                              │  WS_RECONNECTED, WS_STATUS)
                                       ┌──────▼───────┐
                                       │  Side Panel   │
                                       │  (UI, state)  │
                                       └──────────────┘
```

### Side Panel Scope

Per-tab via `chrome.sidePanel.setOptions({ tabId })`. Opens on icon click via `setPanelBehavior({ openPanelOnActionClick: true })`.

### Recording Indicator

Badge on extension icon: `chrome.action.setBadgeText({ text: "REC" })` with red background.

### Hint Buffering

SW buffers last in-flight hint sequence (hint_start + chunks + hint_end). On panel reconnect (GET_SESSION_STATE), buffer is replayed.

### AUDIO_LEVEL Throttling

Two-layer strategy:
- Layer 1: Offscreen caps at 15Hz (66ms timestamp gate via `performance.now()`)
- Layer 2: Side panel batches via `requestAnimationFrame`

## UI Layout — Phase-Based

### Phase 0: Upload drop zone, REC disabled
### Phase 1: Upload stepper (3-step progress)
### Phase 2: Briefing expanded + file strip + REC enabled
### Phase 3: Live call — hint area (amber) + transcript + collapsed briefing
### Phase 4: Call ended — completion strip + full transcript

### Settings

Full-body overlay via gear icon. Mic, backend URL, URL pattern.

## Behavior

### Panel Open/Reopen Handshake
1. Panel connects Port `"sidepanel"`
2. Sends `GET_SESSION_STATE`
3. SW responds with `SESSION_STATE { capturing, sessionId, kbId, wsConnected }`
4. Panel restores to correct phase

### Session Start/Stop
- Uses `chrome.runtime.sendMessage` (not Port) for START/STOP because SW needs `sendResponse`
- Badge set on start, cleared on stop

### SESSION_ABORTED
- SW sends on offscreen disconnect during capture
- Panel shows error banner for 5 seconds, resets to Phase 0

## Acceptance Criteria

### AC-1: Side panel opens on extension icon click
### AC-2: Upload + Briefing works in side panel
### AC-3: Live session — hints and transcript in side panel
### AC-4: Panel close/reopen preserves state
### AC-5: Content-script widget removed
### AC-6: AUDIO_LEVEL throttled

## Edge Cases

1. Panel closed mid-hint-stream → SW hint buffer replays on reconnect
2. Offscreen killed mid-session → SESSION_ABORTED sent to panel
3. Tab switch during recording → panel hides, audio continues
4. Extension update mid-session → storage clears, panel reloads to Phase 0
5. 15+ objections → max-height 240px with overflow-y: auto
6. WS reconnect → temporary "Переподключено" badge

## Out of Scope

- Post-call summary generation UI (separate FEAT)
- Deepgram STT removal
- Backend API changes
- HTTPS/WSS for backend

## Change History

### v1 (2026-03-08) — Initial specification
- ADDED: Full migration spec from popup+widget to side panel
- ADDED: Multi-agent review findings (architect, backend, frontend, product)
- Source: FEAT-006 Out of Scope item + brainstorming session

### v2 (2026-03-09) — Implementation complete
- ADDED: Side panel HTML/CSS/TS with 5-phase UI
- ADDED: Port-based routing (sidepanel + offscreen ports)
- ADDED: Hint buffering in SW for panel reconnect
- ADDED: Badge recording indicator
- ADDED: GET_SESSION_STATE handshake
- ADDED: AUDIO_LEVEL 15Hz throttle in offscreen
- ADDED: WS_RECONNECTED and WS_STATUS notifications
- MODIFIED: service-worker.ts — complete rewrite for Port routing
- MODIFIED: offscreen.ts — added throttle and WS notifications
- MODIFIED: messages.ts — added 5 new message types, removed WIDGET_STATE
- MODIFIED: types.ts — removed WidgetState
- REMOVED: popup (popup.html, popup.ts, popup.css)
- REMOVED: content-script widget (widget.ts, widget.css, state-machine.ts)
- Plan: [v1](../docs/plans/FEAT-007-side-panel-migration.md)
