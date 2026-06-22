# Side Panel Migration — Design Document

Date: 2026-03-08
Spec: [FEAT-007](../../specs/FEAT-007-side-panel-migration.md)

## Decision: Unified Side Panel

Replace popup + content-script widget with a single Chrome Side Panel (`chrome.sidePanel` API). All UI lives in one place. Content script widget is removed.

### Why Side Panel?

- Popup closes on any click outside — user loses control during calls
- Content-script widget is fragile (Shadow DOM injection, page CSP conflicts)
- Side panel persists during tab navigation, stays visible during calls
- Single codebase instead of three (popup + widget + state-machine)

### Why Not Keep Widget?

- Two UIs to maintain (side panel + widget)
- Message routing complexity (SW must relay to both)
- Widget has no access to extension storage APIs directly
- Side panel already provides persistent visibility

## Architecture

### Message Flow (Port-based)

```
Offscreen ──Port("offscreen")──► Service Worker ──Port("sidepanel")──► Side Panel
                                      │
                                      ├── chrome.action.setBadgeText("REC")
                                      └── chrome.storage.session (state backup)
```

All push messages (hints, transcripts, audio levels) flow through named Ports. No `runtime.sendMessage` broadcast. No `tabs.sendMessage` (content script removed).

### State Handshake on Panel Open

```
Panel opens → connect Port("sidepanel") → send GET_SESSION_STATE
SW responds → SESSION_STATE { capturing, sessionId, kbId, wsConnected }
Panel initializes state machine to correct phase
```

### Side Panel Scope

Per-tab: `chrome.sidePanel.setOptions({ tabId, enabled: true })` when session starts. Panel is associated with the CRM tab being captured.

### AUDIO_LEVEL Throttling

Layer 1 — Offscreen: timestamp gate, max 15 Hz (66ms between posts)
Layer 2 — Side Panel: rAF batching for DOM updates

### Hint Buffering

SW buffers the last in-flight hint sequence (hint_start + accumulated hint_chunks). On sidePanelPort reconnect, replays buffer. Buffer is at most ~2KB, bounded to current streaming hint only.

## UI Design

Phase-based layout with fixed header (96px) and scrollable content area.

| Phase | State | Content Area |
|-------|-------|-------------|
| 0 | No files | Upload drop zone |
| 1 | Uploading | Stepper (replaces drop zone) |
| 2 | Ready | Briefing expanded + REC enabled |
| 3 | Live (primary) | Sticky hint + transcript + collapsed briefing |
| 4 | Done | Completion strip + full transcript |

Settings: full-body overlay via gear icon, not a separate tab.

## Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| Remove widget | One UI, simpler routing | No on-page visual indicator (badge instead) |
| Port instead of broadcast | Reliable delivery, clean lifecycle | Slightly more complex SW code |
| Per-tab scope | Session bound to correct tab | Panel hides on tab switch |
| Phase-based UI | Optimal for each workflow stage | More complex state management |

## Reviewed By

- Architect: Per-tab scope, Port handshake, tabCapture validation
- Backend: Port routing, AUDIO_LEVEL throttling, hint buffering
- Frontend: Phase layout, sticky hint, auto-scroll, responsive width
- Product: Phase priorities, hint as "what to do next", collapsed briefing during call
