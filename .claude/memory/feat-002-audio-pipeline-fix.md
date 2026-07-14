# FEAT-002: Audio Pipeline Fix — Learnings

## Extension Architecture
- Chrome MV3 extension with offscreen document for audio capture
- Binary WS protocol: 5-byte header (uint32 seq + uint8 channel) + payload
- Channel 0 = audio PCM16, Channel 1 = control JSON
- AudioWorklet runs in AudioWorkletGlobalScope (no ES imports, compiled as IIFE)
- `ChannelMergerNode` merges mic (L=ch0) and tab (R=ch1) into stereo
- Backend `deinterleave_stereo()` expects interleaved stereo: L0,R0,L1,R1,...

## Key Bugs Fixed
- **BUG-1**: Popup sends message via `chrome.runtime.sendMessage()` which sets `sender.tab` to undefined (popup has no tab). Fix: query `chrome.tabs.query()` for active tab and include `tabId` in message payload.
- **Offscreen port**: Offscreen document connects via `chrome.runtime.connect({name: "offscreen"})` but SW had no `onConnect` listener — messages were lost. Fix: added `onConnect` handler that relays to `sessionTabId` only.
- **AudioWorklet mono bug**: Was only reading `inputs[0][0]` (mono). Backend expects stereo. Fix: read both channels and interleave.
- **WS race**: `setTimeout(200)` before sending session_start was a race condition. Fix: `waitForOpen()` with proper promise resolution.

## TDD Hook with Extension Files
- TDD enforcer hook triggers for extension TypeScript files but there's no Jest/test infrastructure for the extension.
- Need to retry on TDD hook warning for extension files.
- When `cd`-ing into `extension/` dir for tsc, the TDD hook path breaks (looks for `.claude/hooks/` relative to CWD). Always `cd` back to project root.

## Testing Patterns
- Backend tests: 103 baseline + 6 new = 109 passing
- Pre-existing flaky: `test_deepgram_connect_channel_uses_async_context_manager` (async mock timing)
- Use `TestClient(app).websocket_connect("/ws")` for WS integration tests
- Extension changes verified via `npx tsc --noEmit` + `npm run build`

## Redis=None Resilience
- `SessionManager` methods now return safely (empty `SessionContext`, no-op writes)
- `generate_briefing()` returns empty `BriefingResponse()` when redis is None
- Backend already handles redis=None in upload endpoint (just doesn't persist)
