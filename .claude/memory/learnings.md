# Project Learnings

## FEAT-005: Extension Bugfixes (2026-03-07)

### Key Changes

1. **Briefing Persistence (popup.ts)**
   - Extended `PopupState` interface to include `briefing: BriefingData | null`
   - Cache briefing after `fetchAndRenderBriefing()` with `saveState({ briefing: data })`
   - Restore briefing in `init()` on popup reopen
   - Clear briefing on new upload with `saveState({ briefing: null })`

2. **Widget Drag (widget.ts)**
   - Added drag state fields: `isDragging`, `dragStartX/Y`, `hostStartX/Y`, `dragMoved`
   - Implemented `convertToTopLeft()` to convert bottom/right to top/left positioning
   - Replaced click with mousedown/mousemove/mouseup pattern
   - Added 5px movement threshold to distinguish drag from click
   - Added CSS cursor: `grab` / `grabbing`

3. **Orchestrator Error Logging (orchestrator.py)**
   - Removed all `contextlib.suppress(Exception)` patterns
   - Added proper try/except with `logger.warning()` and `logger.error()`
   - Added pipeline start logging: `logger.info("Пайплайн запущен: session=%s query=%s", ...)`
   - Send error to WS on hint pipeline failure with code `HINT_PIPELINE_FAILED`
   - Send empty `hint_end` when LLM returns no tokens

4. **VAD Threshold (config.py, vad.py)**
   - Changed `vad_threshold` default from 0.5 to 0.3
   - Added info-level logging when speech is detected

5. **Widget Error Logging (widget.ts)**
   - Added `console.error()` for backend error messages
   - Fixed AUDIO_LEVEL type handling (moved outside WsMessage switch)

### Gotchas

- Chrome extension popup state is destroyed on close - use `chrome.storage.session` for persistence
- Widget drag needs bottom/right → top/left conversion for correct positioning
- `contextlib.suppress(Exception)` hides critical errors - always use try/except with logging
- VAD energy-based formula: `sum(abs(s)) / n / 10000.0` gives ~0.2-0.4 for normal speech, so 0.5 threshold is too high
- `WsMessage` type doesn't include internal extension messages like `AUDIO_LEVEL` - handle separately
