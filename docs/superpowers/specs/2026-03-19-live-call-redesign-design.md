# FEAT-013: Live Call Panel Redesign — Design Spec

**Status:** DRAFT
**Date:** 2026-03-19
**Depends on:** FEAT-012 (Brief Panel Redesign — merged)

## Goal

Extract Phase 3 (live call) from the `sidepanel.ts` monolith into isolated Preact components with Preact Signals for real-time state management. Replace the backend hint dataclass with a Pydantic SGR schema. Add backend-side talk ratio tracking with waveform visualization.

## Architecture Overview

Three layers change in lockstep:

| Layer | What changes |
|-------|-------------|
| **Frontend** (`extension/src/sidepanel/live-call/`) | New Preact component tree with signals-based state |
| **Backend** (`backend/pipeline/`) | SGR schema for hints + TalkRatioTracker module |
| **WebSocket contract** (`shared/messages.ts`) | Updated `hint_end` v2, new `talk_ratio` message |

### Strangler Fig Pattern

Same approach as FEAT-012 (Brief Panel). `sidepanel.ts` retains phase routing, WebSocket dispatch, and `PanelState` persistence. For Phase 3, it calls `mountLiveCall(container)` once and updates Preact Signals directly on WebSocket messages. No `updateLiveCall(patch)` — signals drive granular re-renders.

### State Management: Preact Signals

**Why signals, not patch-and-rerender:** Interim transcripts arrive every ~200ms. A full Preact tree reconciliation at 5 updates/sec with 100+ transcript entries causes frame drops in the Chrome extension's single UI thread. Signals give each component its own subscription — `TranscriptFeed` re-renders when `transcriptSignal` changes; `AIHintCard` and `TalkRatioBar` are untouched.

```
sidepanel.ts                          live-call/store.ts
─────────────                         ──────────────────
On WS "transcript"  ──────────────►   transcriptSignal.value = [...]
On WS "hint_end"    ──────────────►   hintSignal.value = { ... }
On WS "talk_ratio"  ──────────────►   talkRatioSignal.value = { ... }
On recording state   ──────────────►  recordingSignal.value = { ... }
On tab change        ◄──────────────  activeTabSignal (callback to sidepanel)
```

### Data Ownership

| Data | Owner | How live-call/ accesses it |
|------|-------|---------------------------|
| `transcript: TranscriptItem[]` | sidepanel.ts (module-level array) | Via `transcriptSignal` |
| `currentHint: AIHint` | sidepanel.ts (from WS) | Via `hintSignal` |
| `talkRatio: TalkRatio` | sidepanel.ts (from WS) | Via `talkRatioSignal` |
| `briefData: BriefData` | sidepanel.ts (`PanelState.briefing`) | NOT in LiveCallState. ContextTabs "Briefing" shows/hides existing `#briefing-collapsed` container |
| `recording state` | sidepanel.ts | Via `recordingSignal` |
| Phase 4 transcript | sidepanel.ts passes `transcript[]` snapshot on phase transition | N/A — Phase 4 is vanilla TS |

---

## Frontend Components

### File Structure

```
extension/src/sidepanel/live-call/
├── store.ts                    ← Preact signals (shared state)
├── mount.ts                    ← mount/unmount bridge
├── types.ts                    ← TypeScript contracts (mirrors SGR)
├── LiveCallPanel.tsx           ← root component
├── RecordingBar.tsx
├── ConnectionStatus.tsx
├── AIHintCard.tsx              ← coaching | success | warning | null
├── TalkRatioBar.tsx            ← bar + waveform + text hint
├── ContextTabs.tsx             ← horizontal pills
├── TranscriptFeed.tsx          ← scrollable message list
├── TranscriptMessage.tsx       ← single speaker message
├── live-call.css               ← all component styles
├── hooks/
│   ├── useAutoScroll.ts        ← sticky-to-bottom logic
│   └── useHintCooldown.ts      ← 8s display min + success auto-dismiss
└── __tests__/
    ├── AIHintCard.test.tsx
    ├── TalkRatioBar.test.tsx
    ├── TranscriptFeed.test.tsx
    └── useHintCooldown.test.ts
```

### store.ts — Preact Signals

```typescript
import { signal } from "@preact/signals";
import type { AIHint, TalkRatio, TranscriptItem, ContextTab, RecordingState } from "./types";
import type { BriefData } from "../brief/types";

export const transcriptSignal = signal<TranscriptItem[]>([]);
export const hintSignal = signal<AIHint | null>(null);
export const talkRatioSignal = signal<TalkRatio>({
  managerPercent: 0, clientPercent: 100, waveform: []
});
export const recordingSignal = signal<RecordingState>({
  isRecording: false, elapsedSeconds: 0, micLevel: 0
});
export const activeTabSignal = signal<ContextTab>("hints");
export const wsConnectedSignal = signal<boolean>(false);
export const sttActiveSignal = signal<boolean>(true);
export const briefDataSignal = signal<BriefData | null>(null);
```

### mount.ts — Bridge

```typescript
import { render, h } from "preact";
import { LiveCallPanel } from "./LiveCallPanel";
import "./live-call.css";

let mountedContainer: HTMLElement | null = null;

export interface LiveCallCallbacks {
  onStopRecording: () => void;
  onTabChange: (tab: ContextTab) => void;
  onBriefingTabActive: (active: boolean) => void; // show/hide #briefing-collapsed
}

export function mountLiveCall(
  container: HTMLElement,
  callbacks: LiveCallCallbacks,
): void {
  mountedContainer = container;
  render(h(LiveCallPanel, { callbacks }), container);
}

export function unmountLiveCall(): void {
  if (mountedContainer) {
    render(null, mountedContainer);
    mountedContainer = null;
  }
}
```

### types.ts — Frontend Contracts

```typescript
/** Mirrors backend HintResponseV2 SGR schema. */

export type HintType = "coaching" | "success" | "warning";

export interface AIHint {
  id: string;
  hintType: HintType;
  headline: string;     // max ~80 chars
  detail: string;       // max ~150 chars
  coaching: string;     // tone/tempo advice (footnote line)
  source: string;       // knowledge base reference
  timestamp: number;    // unix ms
}

export interface WaveSegment {
  speaker: "manager" | "client";
  amplitude: number;    // 0.0..1.0
}

export interface TalkRatio {
  managerPercent: number;   // 0..100
  clientPercent: number;    // 0..100
  waveform: WaveSegment[];  // last ~60 segments
}

export interface RecordingState {
  isRecording: boolean;
  elapsedSeconds: number;   // format as MM:SS
  micLevel: number;         // 0.0..1.0
}

export type ContextTab = "hints" | "objections" | "briefing" | "strategy";

// ── Transcript ──

export interface TranscriptMessage {
  type: "message";
  id: string;
  speaker: "manager" | "client";
  text: string;
  timestamp: string;        // "03:42" — pre-formatted
  isInterim?: boolean;      // true = still recognizing, italic
}

export type TranscriptItem = TranscriptMessage;
// NOTE: TranscriptEvent is out of scope for MVP.
// When added later, this becomes: TranscriptItem = TranscriptMessage | TranscriptEvent
```

### Component Contracts

#### LiveCallPanel.tsx
Root container. Reads all signals. Renders child components.
```tsx
interface LiveCallPanelProps {
  callbacks: LiveCallCallbacks;
}
```

#### RecordingBar.tsx
```tsx
// Reads: recordingSignal
// Props: onStop callback
// Renders: СТОП button (pulsing dot) + mic visualizer (5 bars) + MM:SS timer
```

#### ConnectionStatus.tsx
```tsx
// Reads: wsConnectedSignal, sttActiveSignal
// Renders: green/red dots for WS and STT status
```

#### AIHintCard.tsx
```tsx
// Reads: hintSignal (via useHintCooldown hook)
// Renders one of 4 states:
//   coaching → amber card with label "ПОДСКАЗКА" + headline + detail + coaching footnote
//   success  → green card with checkmark icon + headline + detail
//   warning  → red card with label "ВНИМАНИЕ" + headline + detail
//   null     → gray placeholder "Слушаю разговор..."
```

#### TalkRatioBar.tsx
```tsx
// Reads: talkRatioSignal
// Renders:
//   labels: "Вы {N}%" | "{M}% Клиент"
//   progress bar: blue fill = managerPercent, green track = client territory
//   waveform: 60 bars, blue=manager, teal=client, opacity 0.4
//   text hint: >65% → "Дайте клиенту больше говорить" (amber)
//              <35% → "Перехватите инициативу" (amber)
//              35-65% → "Отличный баланс" (green)
```

#### ContextTabs.tsx
```tsx
// Reads: activeTabSignal
// Props: onTabChange, onBriefingTabActive
// Renders: horizontal pills — Подсказки | Возражения | Брифинг | Стратегия
// "Briefing" tab: calls onBriefingTabActive(true/false) to show/hide
//   the existing #briefing-collapsed container managed by sidepanel.ts
```

#### TranscriptFeed.tsx
```tsx
// Reads: transcriptSignal, recordingSignal.value.isRecording (for LIVE badge)
// Uses: useAutoScroll hook
// Renders:
//   header: "Транскрипт" + LIVE badge (pulsing red dot)
//   message list: TranscriptMessage components
//   jump-to-latest pill when user scrolls up
```

#### TranscriptMessage.tsx
```tsx
// Props: speaker, text, timestamp, isInterim
// Renders:
//   meta row: speaker label (blue=Вы, teal=Клиент) + timestamp
//   content: colored vertical bar + text
//   interim: italic + tertiary color
```

### Hooks

#### useAutoScroll(containerRef)
- Tracks if user scrolled up
- Auto-scrolls to bottom on new items unless user scrolled
- Returns `{ isAtBottom, scrollToBottom }`

#### useHintCooldown(rawHint: Signal<AIHint | null>)
- 8-second minimum display time between hint switches
- Queues incoming hints during cooldown
- Success hints auto-dismiss after 4 seconds → revert to last coaching hint
- Returns `displayedHint: AIHint | null`

---

## Visual Spec

### Shared Design Tokens (inherited from Brief Panel)

| Token | Value |
|-------|-------|
| Font | System sans-serif, 13px base |
| Dividers | 0.5px solid `#e5e7eb` |
| Card radius | 12px |
| Section padding | 16px horizontal |
| Width | 100% (adaptive to side panel) |

### RecordingBar

| Element | Spec |
|---------|------|
| СТОП button | border: 1.5px solid `#E24B4A`, 12px/500, color: `#E24B4A`, bg: transparent, radius: 8px. Square dot 8×8px `#E24B4A` radius: 2px, pulse: opacity 1→0.4→1 1.2s ease-in-out infinite |
| Mic visualizer | 5 bars, width: 2px, radius: 1px, color: `#2563eb`. Heights [6,10,14,10,6]px idle. Bounce: scaleY(0.4→1→0.4) 0.6s infinite, stagger 0.1s |
| Timer | 13px/500, `#1f2937`, font-variant-numeric: tabular-nums, format MM:SS |
| Layout | flex, center, gap: 12px, padding: 10px 16px |

### ConnectionStatus

| Element | Spec |
|---------|------|
| Row | flex centered, gap: 12px, 11px, color: `#9ca3af`, padding: 6px 16px, border-bottom: 0.5px |
| Dot (connected) | 6×6px, radius: 50%, `#5DCAA5` |
| Dot (disconnected) | `#E24B4A`, text opacity: 0.5 |

### AIHintCard

#### Coaching (amber)

| Property | Value |
|----------|-------|
| Background | `#FFF8F0` |
| Border-left | 3px solid `#EF9F27` |
| Label "ПОДСКАЗКА" | 11px/500 uppercase, letter-spacing: 0.5px, `#854F0B` |
| Headline | 14px/500, `#633806` |
| Detail | 12px/400, `#854F0B` |
| Coaching footnote | 11px, `#9ca3af`, italic, margin-top: 8px |
| Padding | 14px 16px |

#### Success (green)

| Property | Value |
|----------|-------|
| Background | `#EAF3DE` |
| Border-left | 3px solid `#639922` |
| Icon | Circle 24×24px, bg: `#639922`, checkmark SVG stroke: #fff, width: 2 |
| Layout | flex, center, gap: 8px (icon + text block) |
| Headline | 14px/500, `#27500A` |
| Detail | 12px/400, `#3B6D11` |
| Auto-dismiss | After 4 seconds, revert to last coaching hint |

#### Warning (red)

| Property | Value |
|----------|-------|
| Background | `#FEF5F5` |
| Border-left | 3px solid `#E24B4A` |
| Label "ВНИМАНИЕ" | 11px/500, `#791F1F` |
| Headline | 14px/500, `#501313` |
| Detail | 12px/400, `#791F1F` |

#### Null state (no hint)

| Property | Value |
|----------|-------|
| Background | `#f9fafb` |
| No border-left | |
| Text | 12px, `#9ca3af`, centered: "Слушаю разговор..." / "Подсказки появятся автоматически" |

#### Hint transitions

- Coaching → Coaching: text swap, no container animation
- Coaching → Success: background + border-color transition 200ms
- Success auto-dismiss: after 4s, revert to last coaching (no animation)
- Warning: stays until backend sends new hint

### TalkRatioBar

| Element | Spec |
|---------|------|
| Track | height: 6px, radius: 3px, bg: `#EAF3DE` |
| Fill | height: 100%, radius: 3px, bg: `#2563eb`, transition: width 0.8s ease |
| Labels | flex space-between. "Вы **68%**" — "Вы" 11px tertiary, percent 12px/500 primary |
| Waveform | flex, gap: 1px, height: 16px, ~60 bars, width: 2px, radius: 1px. Manager: `#2563eb`, Client: `#5DCAA5`. Height: `3 + amplitude * 13`px. Opacity: 0.4 |
| Text hint | center, 11px. >65%: "Дайте клиенту больше говорить" `#854F0B`. <35%: "Перехватите инициативу" `#854F0B`. 35-65%: "Отличный баланс" `#3B6D11` |
| Padding | 12px 16px |

### ContextTabs

| Element | Spec |
|---------|------|
| Layout | flex, gap: 6px, padding: 0 16px 12px, overflow-x: auto |
| Pill (inactive) | 11px, padding: 4px 10px, radius: 20px, border: 0.5px solid `#e5e7eb`, bg: white, color: `#6b7280` |
| Pill (active) | bg: `#E6F1FB`, color: `#2563eb`, border: transparent |
| Hover | bg: `#f9fafb` |
| Transition | all 0.15s |

Tabs: `Подсказки` | `Возражения` | `Брифинг` | `Стратегия`

Tab content:
- **Подсказки** → AIHintCard with current hint
- **Возражения** → Reads `briefDataSignal.value.objections` (compact ObjectionCards). If a success-type hint was received, show it as the top card above the objections list.
- **Брифинг** → Shows/hides existing `#briefing-collapsed` container (managed by sidepanel.ts)
- **Стратегия** → Reads `briefDataSignal.value.focusPoints`, displays top-3 FocusPoints (compact list)

**BriefData access:** `sidepanel.ts` sets `briefDataSignal.value` from `PanelState.briefing` when Phase 3 starts. This is a read-only copy — the Brief Panel remains the owner. The signal is defined in `store.ts`:

```typescript
export const briefDataSignal = signal<BriefData | null>(null);
```

### TranscriptFeed

| Element | Spec |
|---------|------|
| Header | flex space-between, padding: 12px 16px 0. "Транскрипт" 12px/500. LIVE badge: 11px/500 `#E24B4A`, pulsing dot 6×6px |
| Container | flex-1, overflow-y: auto |

### TranscriptMessage

| Element | Spec |
|---------|------|
| Container | padding: 8px 0, border-bottom: 0.5px |
| Speaker label | 11px/500. "Вы" → `#2563eb`. "Клиент" → `#1D9E75` |
| Timestamp | 11px, `#9ca3af` |
| Vertical bar | width: 3px, radius: 1.5px, min-height: 12px, self-stretch. "Вы" → `#2563eb`. "Клиент" → `#1D9E75` |
| Text | 13px/400, `#1f2937`, line-height: 1.45 |
| Interim | color: `#9ca3af`, font-style: italic |

### Animations

All wrapped in `@media (prefers-reduced-motion: no-preference)`.

| Element | Animation | Params |
|---------|-----------|--------|
| СТОП dot | Pulse opacity | 1→0.4→1, 1.2s ease-in-out infinite |
| Mic bars | Bounce scaleY | 0.4→1→0.4, 0.6s infinite, stagger 0.1s |
| LIVE dot | Pulse opacity | Same as СТОП |
| Talk ratio fill | Width | transition: width 0.8s ease |
| Hint card type change | Background + border | transition: 200ms |
| Context pill | Background + color | transition: all 150ms |

---

## Backend Changes

### SGR Schema: `pipeline/schemas.py` (NEW)

```python
from pydantic import BaseModel, Field
from typing import Literal

class HintResponseV2(BaseModel):
    """SGR schema for real-time coaching hints.

    Field order is intentional: reasoning before hint_type
    warms up model context for better classification.
    """
    reasoning: str = Field(
        description="1-line: utterance summary + client emotion"
    )
    hint_type: Literal["coaching", "success", "warning"] = Field(
        description=(
            "coaching = what the rep should do next; "
            "success = objection handled or good technique; "
            "warning = client losing interest or off-topic"
        )
    )
    headline: str = Field(
        max_length=80,
        description="Main coaching text, ≤80 chars, readable in 1 second"
    )
    detail: str = Field(
        default="",
        max_length=150,
        description="Supporting context or explanation"
    )
    coaching: str = Field(
        default="",
        description="Tone/tempo advice: 'slow down', 'show empathy', etc."
    )
    source: str = Field(
        default="",
        description="Knowledge base reference, e.g. 'Brief, p.3'"
    )
```

### TalkRatioTracker: `pipeline/talk_ratio.py` (NEW)

```python
from pydantic import BaseModel, Field
from typing import Literal

class WaveSegment(BaseModel):
    speaker: Literal["manager", "client"]
    amplitude: float = Field(ge=0.0, le=1.0)

class TalkRatioTracker:
    """Tracks speaking balance and builds waveform ring buffer."""

    BUFFER_SIZE = 60
    NORMALIZATION_MAX = 30  # fixed max words for amplitude normalization

    def on_utterance(self, speaker: str, text: str, is_final: bool) -> None:
        """Update word counts. On final utterance, append waveform segment."""

    def get_state(self) -> dict:
        """Return { managerPercent, clientPercent, waveform: list[WaveSegment] }"""
```

Amplitude normalization: fixed max of 30 words per utterance (not dynamic). Utterances longer than 30 words cap at amplitude 1.0. This prevents historical segments from rescaling.

### Orchestrator Changes

- Import `HintResponseV2` from `pipeline/schemas.py`
- `_collect_and_send_hint()`: use `HintResponseV2.model_validate_json()` instead of `HintResponse.from_json()`
- Send `hint_end` v2 format: `{ type, hint_type, headline, detail, coaching, source, v: 2 }`
- Create `TalkRatioTracker` instance per session
- On each final transcript: call `tracker.on_utterance()`
- Send `talk_ratio` WS message after each final utterance (not periodic timer)

### LLM Prompt Changes

Update `_SYSTEM_PROMPT_CLIENT` and `_SYSTEM_PROMPT_REP` in `llm.py`:
- Replace `sentiment` + `color` fields with `hint_type: coaching|success|warning`
- Replace `hint` field with `headline` (max 80 chars) and `detail` (max 150 chars)
- Keep `reasoning` as first field (SGR warm-up)
- Keep `coaching` and `source` fields

### Fallback Update

`LLMClient._generate_fallback()` returns `HintResponseV2`:
```python
return HintResponseV2(
    reasoning="Fallback: primary LLM timed out",
    hint_type="coaching",
    headline="Уточните детали у клиента",
    detail="",
    coaching="",
    source="fallback",
)
```

### HintResponse Deprecation

`HintResponse` dataclass in `pipeline/types.py` is kept but marked deprecated with a comment. Existing tests that use it continue to work. New code uses `HintResponseV2`.

---

## WebSocket Contract Changes

### hint_end v2

```typescript
interface WsHintEndV2 {
  type: "hint_end";
  v: 2;                                    // version marker
  hint_type: "coaching" | "success" | "warning";
  headline: string;
  detail: string;
  coaching: string;
  source: string;
}
```

No `generated_at` field — the frontend generates its own `Date.now()` timestamp when constructing `AIHint`. The backend `time.monotonic()` clock is meaningless across process boundaries.

Replaces old fields: `hint`, `sentiment`, `color`, `relevance`. Old `WsHintStart` and `WsHintChunk` are already no-ops — can be removed.

The `v: 2` field allows the service worker to discard stale v1 cached messages on replay.

### talk_ratio (NEW)

```typescript
interface WsTalkRatio {
  type: "talk_ratio";
  managerPercent: number;   // 0..100
  clientPercent: number;    // 0..100
  waveform: Array<{ speaker: "manager" | "client"; amplitude: number }>;
}
```

Sent after each final utterance.

### transcript (UNCHANGED)

```typescript
interface WsTranscript {
  type: "transcript";
  speaker: "rep" | "client";  // note: "rep" on wire, mapped to "manager" in UI
  text: string;
  is_final: boolean;
  utterance_id?: string;
}
```

**Speaker mapping** (in sidepanel.ts transcript handler):
```typescript
const speaker = msg.speaker === "rep" ? "manager" : "client";
```

### Removed messages

- `WsHintStart` — already no-op, remove
- `WsHintChunk` — already no-op, remove

### Updated WsMessage union type

In `shared/messages.ts`, update the union:

```typescript
// Old:
export type WsMessage = WsHintStart | WsHintChunk | WsHintEnd | WsTranscript | WsError;

// New (keep existing evaluation types):
export type WsMessage =
  | WsHintEndV2 | WsTalkRatio | WsTranscript | WsError
  | WsEvaluationStarted | WsEvaluationResult | WsEvaluationError;
```

### ExtMessage cleanup

Remove the old `{ type: "HINT"; hint: WsHintEnd }` from `ExtMessage` in `shared/messages.ts`. This message type was used for service worker → sidepanel forwarding but is no longer needed — `WsHintEndV2` goes directly through the WebSocket handler.

---

## sidepanel.ts Changes

### Deleted code (~400 lines)

- `Splitter` class (lines 40-164) — replaced by tabs
- `sentimentHistory[]` + `updateSentimentDots()` (lines 952-971)
- `repWordCount`, `clientWordCount`, `updateTalkRatio()` (lines 973-1001) — moved to backend
- `handleHintStart()`, `handleHintChunk()` (lines 1003-1011) — remove no-ops
- `handleHintEnd()`, `flushPendingHint()`, `renderHint()` (lines 1013-1094) — moved to Preact
- `handleTranscript()` (lines 1100-1187) — rewritten as signal updater
- `initTranscriptScroll()` (lines 1189-1199) — moved to useAutoScroll hook
- `initPhase3Splitter()` (lines 168-172) — removed

### New code

```typescript
import { mountLiveCall, unmountLiveCall } from "./live-call/mount";
import {
  transcriptSignal, hintSignal, talkRatioSignal,
  recordingSignal, wsConnectedSignal, sttActiveSignal,
} from "./live-call/store";
import type { AIHint, TranscriptItem } from "./live-call/types";

// Module-level transcript array (single source of truth)
let transcriptItems: TranscriptItem[] = [];

// WS message handler (in the switch block):
case "hint_end":
  if (msg.v !== 2) break; // discard v1 cached messages
  const hint: AIHint = {
    id: crypto.randomUUID(),
    hintType: msg.hint_type,
    headline: msg.headline,
    detail: msg.detail,
    coaching: msg.coaching,
    source: msg.source,
    timestamp: Date.now(),
  };
  hintSignal.value = hint;
  break;

case "talk_ratio":
  talkRatioSignal.value = {
    managerPercent: msg.managerPercent,
    clientPercent: msg.clientPercent,
    waveform: msg.waveform,
  };
  break;

case "transcript":
  const speaker = msg.speaker === "rep" ? "manager" : "client";
  // ... build TranscriptMessage with mapped speaker, append to transcriptItems
  transcriptSignal.value = [...transcriptItems];
  break;

// Phase 3 enter:
mountLiveCall($("phase-3-live-call")!, {
  onStopRecording: () => { /* existing stop logic */ },
  onTabChange: (tab) => { /* update activeTabSignal */ },
  onBriefingTabActive: (active) => {
    const bc = $("briefing-collapsed");
    active ? show(bc) : hide(bc);
  },
});

// Phase 4 transition:
// Pass transcriptItems snapshot to Phase 4 renderer
// unmountLiveCall();
```

### handleCaptureStarted() update

When `handleCaptureStarted()` fires (existing Phase 3 entry point in sidepanel.ts):
1. Clear previous state: reset all live-call signals (same logic as the signal-reset block in `resetForNewCall()` below)
2. Set `wsConnectedSignal.value = true`
3. Set `sttActiveSignal.value = true`
4. Call `mountLiveCall(container, callbacks)`

### sttActiveSignal data source

`sttActiveSignal` is set from WS status:
- `wsConnectedSignal.value = true` on WebSocket `open` event
- `wsConnectedSignal.value = false` on WebSocket `close`/`error` events
- `sttActiveSignal.value` toggles based on incoming `transcript` messages: if transcripts arrive → `true`; if no transcript for 10s → `false` (simple heartbeat check via `setTimeout`)

### resetForNewCall() — full merged version

```typescript
function resetForNewCall(): void {
  // --- Existing resets (keep) ---
  phase = "idle";
  panelState.evaluation = null;
  panelState.followUpActions = null;
  // ... other existing PanelState resets ...

  // --- New: clear live-call signals ---
  transcriptItems = [];
  transcriptSignal.value = [];
  hintSignal.value = null;
  talkRatioSignal.value = { managerPercent: 0, clientPercent: 100, waveform: [] };
  recordingSignal.value = { isRecording: false, elapsedSeconds: 0, micLevel: 0 };
  wsConnectedSignal.value = false;
  sttActiveSignal.value = true;
  activeTabSignal.value = "hints";

  // --- New: unmount Preact tree ---
  unmountLiveCall();
}
```

### Cooldown interaction: backend 15s vs frontend 8s

Two independent cooldowns serve different purposes:
- **Backend 15s** (`_HINT_COOLDOWN_S` in `orchestrator.py`): Rate-limits LLM calls. Prevents excessive API usage. The backend simply skips `_run_pipeline()` if less than 15s since last hint.
- **Frontend 8s** (`useHintCooldown` hook): Minimum display time for the user to read the hint card. Queues incoming hints if one is being displayed.

**Interaction:** The backend sends hints at most every 15s. The frontend guarantees each is displayed for at least 8s. Since 15s > 8s, the frontend cooldown rarely triggers — it exists as a safety net for bursts (e.g., when the backend cooldown resets and two hints arrive in quick succession). No synchronization needed between the two.

### Phase 4 Transcript Sharing

Phase 4 receives `transcriptItems` (the array) as a snapshot at transition time. The existing `renderDiarizedTranscript()` function (for post-call diarized transcript from evaluation) replaces the live transcript when `evaluation_result` arrives. No DOM cloning needed.

---

## Dependencies

### New npm package

Add to `extension/package.json`:
```json
"@preact/signals": "^1.3.0"
```

### Test file naming

Follow existing project convention — test files use PascalCase matching the component: `AIHintCard.test.tsx`, `TalkRatioBar.test.tsx`, etc.

---

## Out of Scope

- **Dark mode** — separate feature, no CSS custom properties for dark in this spec
- **TranscriptEvent** (inline events in transcript feed) — needs separate approach (keyword-matching, not hint-derived). Visual design is shown in mockup for reference
- **Phase 4 extraction** — remains vanilla TS
- **Full service health monitoring** — only WS connected + STT active indicators
- **Transcript virtualization** (react-window) — add later if performance requires it
- **Transcript persistence** to `chrome.storage.local` — accepted limitation: panel close loses transcript

---

## Acceptance Criteria

1. [ ] `LiveCallPanel` renders via `mountLiveCall()` — no hint/transcript rendering in sidepanel.ts
2. [ ] RecordingBar shows MM:SS timer with tabular-nums, pulsing СТОП dot, animated mic bars
3. [ ] AIHintCard correctly renders 3 types: coaching (amber), success (green), warning (red)
4. [ ] AIHintCard null state shows "Слушаю разговор..." placeholder (no border-left)
5. [ ] Success hint auto-dismisses after 4 seconds, reverts to last coaching
6. [ ] Hint display cooldown (8s minimum) works via useHintCooldown hook
7. [ ] TalkRatioBar updates smoothly (transition 0.8s), waveform renders ~60 bars
8. [ ] Talk ratio text hint changes dynamically by threshold (35% / 65%)
9. [ ] ContextTabs switch content; "Briefing" tab shows/hides existing `#briefing-collapsed`
10. [ ] TranscriptFeed auto-scrolls to bottom (sticky-to-bottom), shows "Jump to Latest" on scroll up
11. [ ] Interim transcript updates in-place (italic, tertiary color)
12. [ ] Backend `HintResponseV2` Pydantic schema validates hint output
13. [ ] Backend `TalkRatioTracker` sends `talk_ratio` WS messages with waveform data
14. [ ] WsHintEnd v2 format used end-to-end (backend sends, frontend consumes)
15. [ ] Old hint-related code deleted from sidepanel.ts (~400 lines removed)
16. [ ] All animations wrapped in `@media (prefers-reduced-motion: no-preference)`
17. [ ] Each Preact component has unit tests
18. [ ] Coaching footnote line: 11px, italic, margin-top: 8px (visual footnote, not third content line)
19. [ ] Extension builds and runs without errors
20. [ ] Backend tests pass with new SGR schema
