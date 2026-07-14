# FEAT-003: Dedup + Interactive Hints + UI Split Layout

Date: 2026-03-11

## What Was Done

1. **Transcript Dedup**: Added `utterance_id` field to `Transcript` dataclass. Yandex STT `final` increments counter, `final_refinement` reuses same counter. Frontend replaces DOM entry in-place via `data-utterance-id` attribute.

2. **Both-Speaker Hints**: Removed `if transcript.speaker == "client"` guard in orchestrator. Added separate system prompts: `_SYSTEM_PROMPT_CLIENT` (analysis) and `_SYSTEM_PROMPT_REP` (coaching). Added `coaching` field to `HintResponse`.

3. **UI Split Layout**: Phase 3 now uses flex column: transcript (flex:1) + collapsed briefing + hints-panel (fixed bottom). Removed old sticky `hint-area`.

## Key Files Modified

- `backend/pipeline/stt.py` — Transcript.utterance_id, Yandex dedup counters
- `backend/pipeline/orchestrator.py` — both-speaker pipeline, coaching in hint_end
- `backend/pipeline/llm.py` — speaker-specific prompts, HintResponse.coaching
- `extension/src/shared/messages.ts` — WsTranscript.utterance_id
- `extension/src/shared/types.ts` — HintPayload.coaching
- `extension/src/sidepanel/sidepanel.ts` — handleTranscript dedup, hint handlers
- `extension/src/sidepanel/sidepanel.html` — Phase 3 restructured
- `extension/src/sidepanel/sidepanel.css` — hints-panel, coaching-text styles

## Gotchas

- **Debounce in tests**: The 500ms debounce (`_HINT_DEBOUNCE_S`) causes back-to-back pipeline calls in tests to be skipped. Fix: reset `orch._last_hint_time = 0.0` between calls.
- **CWD matters for hooks**: Running `cd extension && npm run build` changes CWD, which breaks TDD enforcer hook paths. Always `cd` back to project root.
- **Edit uniqueness**: `stt.py` has multiple `__init__` methods across classes. Provide enough surrounding context to uniquely match.
- **Edge case tests**: `test_edge_cases.py` had tests asserting rep speech does NOT trigger pipeline. After changing behavior, these need updating — not deleting.
- **_async_iter helper**: Tests use `_async_iter()` to create async generators from lists for mocking `generate_hint_stream`.
- **Extension has no test infra**: TDD hook warns on `.ts` edits but allows retry. No automated tests exist for the extension.
