# Hint Timing Strategy Design

**Date:** 2026-03-11
**Status:** DRAFT (post-review v2)
**Problem:** Hints flicker during active calls — 500ms debounce causes chain cancellations. Hints at bottom of panel have low visual priority.

## Research Basis

- **Balto**: Event-driven triggers, <200ms latency, Dynamic Prompts at eye level, transcript secondary
- **Visions**: 30-second metronome, max 3 sentences per cycle
- **Cresta**: Suggestions in top portion of agent desktop, hedging LLM calls
- **Groto AI Copilot Guide**: Actionable information where attention naturally falls — top of panel
- **Microsoft Copilot research**: Reducing visual scanning distance improves adoption
- **Industry consensus**: 15-30s cooldown, max 2-3 sentences, confidence threshold

## Design Principle

Hint panel = highway billboard. Calm, readable at a glance (2 seconds), changes infrequently and intentionally. Panel should feel calm — if the rep notices it is "busy", the UX has failed.

## Root Cause

Every is_final transcript (every 1-3s) triggers _run_pipeline(). Debounce 500ms too short. New speech cancels in-flight LLM via _cancel_current(). Rep sees endless "Анализирую..." flickering with 0 useful hints during active conversation.

## Architecture: Silent Generation

Replace hint_start/hint_chunk/hint_end with single hint_end. Backend generates silently, sends only complete result. Previous hint stays on screen during generation.

### Three Filtering Layers

1. **Cooldown 15s** (backend) — do not generate more than once per 15 seconds
2. **Importance filter** (backend, Phase 2) — keyword matching from scenario data
3. **Display cooldown 8s** (frontend) — do not replace hint if on screen < 8 seconds

---

## Phase 1 — Stop Flickering + Layout Flip

### Backend Changes

| Change | File | Details |
|--------|------|---------|
| Cooldown 15s | orchestrator.py | `_HINT_COOLDOWN_S = 15.0` replaces `_HINT_DEBOUNCE_S = 0.5` |
| Silent generation | orchestrator.py | Remove hint_start/hint_chunk sending. Only send hint_end |
| Smart cancel | llm.py | Track `_tokens_received`. Cancel only if 0 tokens received (`force=False` default) |
| Generation timeout 5s | orchestrator.py | If LLM >5s — discard, previous hint stays |
| Add generated_at | orchestrator.py | Include `generated_at: float` (unix timestamp) in hint_end message |

### Frontend Changes

| Change | File | Details |
|--------|------|---------|
| Layout flip | sidepanel.html + .css | Hints panel moves to top (CSS order or HTML reorder). Proportions 45% hints / 55% transcript |
| Border fix | sidepanel.css | hints-panel: border-bottom instead of border-top, adjust border-radius |
| Content area padding | sidepanel.css | Override padding: 0 on #content-area when Phase 3 active |
| Display cooldown 8s | sidepanel.ts | Track lastHintRenderedAt. Queue incoming hint_end if <8s elapsed |
| Remove loading state | sidepanel.ts | Session start: "Слушаю разговор...". Delete handleHintStart/handleHintChunk rendering |
| Fade transition 300ms | sidepanel.css | opacity transition on hint panel text for smooth replacement |
| Update SW buffer | service-worker.ts | bufferHint stores only latest hint_end (not start/chunk sequence) |

### NOT in Phase 1

- Drag-resize panels (deferred to Phase 3 as hypothesis)
- Layout presets (deferred to Phase 2)
- Keyword importance filter (Phase 2)
- Staleness indicator (Phase 2)
- Hint dismiss (Phase 2)

---

## Phase 2 — Smart Filtering + Polish

| Change | Location | Details |
|--------|----------|---------|
| Keyword importance filter | orchestrator.py | Extract keywords from scenario at session start. Generate only on keyword match |
| Suppress rep filler | orchestrator.py | speaker=="rep" and <10 words without triggers — skip |
| Staleness indicator | sidepanel.css | >90s opacity 60%, >3min fade out (uses generated_at from hint_end) |
| Hint dismiss | sidepanel.ts | Click to dismiss. Reorder HTML (not CSS order) for keyboard accessibility |
| Layout presets (hypothesis) | sidepanel.ts | Three task-based presets: "Возражения" (60/40), "Проверка" (20/80), "Стандарт" (45/55). Via settings dropdown, not header buttons |

## Phase 3 — Adaptive (only if Phase 1+2 insufficient)

| Change | Location | Details |
|--------|----------|---------|
| Transcript buffer | orchestrator.py | 20s accumulation + batch LLM |
| Confidence threshold | llm.py | Show only if confidence > 0.7 |
| Hint history | sidepanel.ts | Last 5 hints scrollable |
| Resizable panels (hypothesis) | sidepanel.ts | Drag handles with PointerEvent + setPointerCapture. Proportions in chrome.storage.local. Validate with usage data first |

---

## New Phase 3 Layout

```
┌─────────────────────────────┐
│  Подсказка (HINT)      45%  │  ← Top: highest visual priority
│  "Напомните клиенту о..."   │     flex-shrink: 0, min-height: 80px
│  coaching: "Говорите мед.." │
│  📎 scenario.pdf            │
├─────────────────────────────┤
│  ▸ Стратегия (collapsible)  │  ← Middle: reference, flex-shrink: 0
│  ▸ Возражения (collapsible) │     collapsed by default
│  ▸ Портрет (collapsible)    │
├─────────────────────────────┤
│  Транскрипт           55%   │  ← Bottom: scrollable, flex: 1
│  [10:01] Клиент: Добрый..   │     live dot, auto-scroll
│  [10:02] Менеджер: Здрав..  │
│         [К последнему ↓]    │
└─────────────────────────────┘
```

## Hint Lifecycle on Screen

```
[Session start] → "Слушаю разговор..." (neutral, top of panel)
[hint_end arrives]
  → if display cooldown (<8s since last hint): queue
  → else: cross-fade 300ms → hint visible at top
  → minimum 8s on screen
[Panel reconnect] → SW replays last hint_end → display immediately
```

## WebSocket Protocol Changes

- Removed from hot path: hint_start, hint_chunk
- Kept: hint_end — single message with complete hint + generated_at timestamp
- Frontend handlers for hint_start/hint_chunk become no-ops (backward compat)

## Service Worker Changes

- bufferHint: store only latest hint_end (single message, not sequence)
- Replay on reconnect: send single hint_end message

## Files Affected (Phase 1)

| File | Changes |
|------|---------|
| backend/pipeline/orchestrator.py | Cooldown 15s, silent gen, timeout 5s, generated_at |
| backend/pipeline/llm.py | _tokens_received, smart _cancel_current(force) |
| extension/src/sidepanel/sidepanel.html | Reorder Phase 3: hints → briefing → transcript |
| extension/src/sidepanel/sidepanel.ts | Display cooldown 8s, remove hint_start/chunk handlers, initial state |
| extension/src/sidepanel/sidepanel.css | Layout flip styles, transitions, padding fix |
| extension/src/background/service-worker.ts | Simplify bufferHint to store last hint_end |
| backend/tests/test_pipeline.py | Update cooldown tests, remove hint_chunk assertions |
| backend/tests/test_llm.py | Smart cancel test |

## Success Criteria

- 5-15 hints per 20-minute call
- No loading states, raw JSON, or blank flashes
- Each hint persists min 8 seconds at top of panel
- Panel feels calm during active conversation
- Hint is the first thing rep sees when glancing at panel
