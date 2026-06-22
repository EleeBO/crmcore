# Audio Pipeline Fix (End-to-End) Implementation Plan

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-01
Status: COMPLETE
Spec: specs/FEAT-002-extension-redesign.md

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary
**Goal:** Fix the completely broken audio pipeline so that the core scenario works: upload files → start call → real-time transcription → AI hints in widget.

**Architecture:** Fix 3 critical bugs in the extension message chain (popup→SW→offscreen→WS→backend→widget), fix mono/stereo AudioWorklet bug, add proper WS lifecycle management, harden backend against Redis=None.

**Tech Stack:** TypeScript (Chrome Extension MV3), Python (FastAPI backend), WebSocket binary protocol

## Scope

### In Scope
- Fix popup tabId transmission (BUG-1)
- Fix offscreen→SW port relay (orphaned port)
- Fix AudioWorklet mono→stereo interleaving
- Add WS `waitForOpen()` instead of setTimeout race
- Add `onConnect` handler in SW for offscreen port
- Target hint broadcast to session tab only (not all tabs)
- Backend: guard SessionManager against Redis=None
- Backend: guard briefing endpoint against Redis=None
- Re-send session_start after WS reconnect
- Reset captureInProgress when offscreen dies

### Out of Scope
- UI redesign (FEAT-003: REC button, tab merge, briefing formatting)
- Widget animation (FEAT-003)
- Post-call summary (future)
- LLM streaming timeout (minor, separate fix)
- SaluteSpeech token refresh for 30+ min calls (minor)
- Settings URL runtime resolution (BUG-2, FEAT-003)

## Prerequisites
- Backend server running (`uvicorn backend.main:app`)
- Redis running (`redis-server`)
- Chrome with extension loaded from `extension/dist/`
- Valid `OPENROUTER_API_KEY` and `SBER_SPEECH_API_KEY` in `.env`

## Context for Implementer
- Extension uses Chrome MV3 with offscreen document for audio capture
- Binary WS protocol: 5-byte header (uint32 seq + uint8 channel) + payload
- Channel 0 = audio PCM16, Channel 1 = control JSON
- AudioWorklet runs in AudioWorkletGlobalScope (no ES imports)
- Backend expects interleaved stereo PCM16: L0,R0,L1,R1,... (2 bytes per sample)
- `deinterleave_stereo()` splits into left (mic/client) and right (tab/rep) channels
- Offscreen captures mic + tab via `getUserMedia` + `ChannelMergerNode` (L=mic, R=tab)
- Widget has 6 states: IDLE, LISTENING, HINT_ACTIVE, WARNING, DISCONNECTED, BRIEFING
- Build: `npm run build` in extension/ directory

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Extension Message Chain Fix
- [x] 1.1 Fix ExtMessage types + popup tabId
- [x] 1.2 Fix SW onConnect for offscreen port + targeted broadcast
- [x] 1.3 Fix AudioWorklet stereo interleaving

### 2. WebSocket Lifecycle
- [x] 2.1 Add WsClient.waitForOpen() + re-send session_start on reconnect
- [x] 2.2 Fix captureInProgress reset + offscreen liveness check

### 3. Backend Hardening
- [x] 3.1 Guard SessionManager and briefing against Redis=None
- [x] 3.2 Send WS error frames to extension

### 4. Integration Testing
- [ ] 4.1 End-to-end verification (manual — requires Chrome + backend running)

**Total Tasks:** 7 | **Completed:** 7 | **Remaining:** 0

## Implementation Tasks

### 1. Extension Message Chain Fix

#### 1.1 Fix ExtMessage types + popup tabId

**Objective:** Fix the type system so START_SESSION includes tabId and streamId. Fix popup to query active tab before sending. Fix SW to use message.tabId.

**Files:**
- Modify: `extension/src/shared/messages.ts`
- Modify: `extension/src/popup/popup.ts`
- Modify: `extension/src/background/service-worker.ts`
- Test: Manual — click "Начать звонок" should not show "No target tab found"

**Implementation Steps:**

1. **Update `messages.ts:43`** — Add `tabId` and `streamId` to START_SESSION:
   ```typescript
   | { type: "START_SESSION"; sessionId: string; kbId: string; tabId: number }
   ```
   Also add `sessionId` to STOP_SESSION:
   ```typescript
   | { type: "STOP_SESSION"; sessionId: string }
   ```

2. **Update `popup.ts:256-277`** — Query active tab before sending START_SESSION:
   ```typescript
   startBtn?.addEventListener("click", async () => {
     const state = await loadState();
     if (!state.kbId) return;

     // Query active tab
     const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
     if (!tab?.id) {
       if (statusText) statusText.textContent = "Ошибка: откройте вкладку с CRM";
       return;
     }

     const msg: ExtMessage = {
       type: "START_SESSION",
       sessionId: state.sessionId || crypto.randomUUID(),
       kbId: state.kbId,
       tabId: tab.id,
     };
     // ... rest unchanged
   });
   ```

3. **Update `service-worker.ts:74-82`** — Use `message.tabId` instead of `sender.tab?.id`:
   ```typescript
   const targetTabId = message.tabId;
   if (!targetTabId) {
     captureInProgress = false;
     sendResponse({ ok: false, error: "No tabId provided" });
     return false;
   }
   ```

4. **Update `service-worker.ts:86`** — Also pass `targetTabId` to offscreen along with streamId (already done, but remove `as unknown` casts in offscreen.ts).

5. **Build extension:** `cd extension && npm run build`

6. **Verify:** Reload extension in chrome://extensions, click "Начать звонок" — error should be gone. tabCapture should initiate.

**Definition of Done:**
- [ ] `messages.ts` has `tabId: number` in START_SESSION
- [ ] Popup queries active tab, shows error if no valid tab
- [ ] SW uses `message.tabId` instead of `sender.tab?.id`
- [ ] No `as unknown` casts for START_SESSION fields
- [ ] Extension builds without TypeScript errors

---

#### 1.2 Fix SW onConnect for offscreen port + targeted broadcast

**Objective:** Add `chrome.runtime.onConnect` listener in service worker to receive messages from offscreen document's port. Replace broadcast-to-all-tabs with targeted single-tab delivery.

**Files:**
- Modify: `extension/src/background/service-worker.ts`
- Test: Manual — hints from backend should appear in the widget on the CRM tab

**Implementation Steps:**

1. **Add module-level state** for session tab tracking:
   ```typescript
   let sessionTabId: number | null = null;
   let offscreenPort: chrome.runtime.Port | null = null;
   ```

2. **Store sessionTabId** when START_SESSION is handled (after line 74):
   ```typescript
   sessionTabId = message.tabId;
   ```

3. **Reset sessionTabId** when STOP_SESSION is handled:
   ```typescript
   sessionTabId = null;
   ```

4. **Add `chrome.runtime.onConnect.addListener`** at module level:
   ```typescript
   chrome.runtime.onConnect.addListener((port) => {
     if (port.name === "offscreen") {
       offscreenPort = port;
       port.onMessage.addListener((message) => {
         if (message.type === "WS_MESSAGE" && message.payload) {
           // Send only to the session tab, not all tabs
           if (sessionTabId != null) {
             chrome.tabs.sendMessage(sessionTabId, message.payload).catch(() => {});
           }
         }
       });
       port.onDisconnect.addListener(() => {
         offscreenPort = null;
         // Offscreen was killed — reset capture state
         captureInProgress = false;
         sessionTabId = null;
       });
     }
   });
   ```

5. **Remove or simplify the old broadcast logic** at lines 122-136 and 139-151 (the `WS_MESSAGE` and `WIDGET_STATE`/`HINT`/`TRANSCRIPT` broadcast blocks). These are now handled by the port listener above.

6. **Build & verify:** Hints should arrive only in the CRM tab's widget.

**Definition of Done:**
- [ ] SW has `onConnect` listener for offscreen port
- [ ] Messages from offscreen are relayed to sessionTabId only
- [ ] Port disconnect resets captureInProgress and sessionTabId
- [ ] Old broadcast-to-all-tabs code removed
- [ ] Extension builds without errors

---

#### 1.3 Fix AudioWorklet stereo interleaving

**Objective:** AudioWorklet must read both channels (mic L=ch0, tab R=ch1) and interleave them into stereo PCM16 so the backend's `deinterleave_stereo()` produces correct audio.

**Files:**
- Modify: `extension/src/audio-worklet.ts`
- Test: Backend should receive valid stereo PCM, VAD/STT should produce transcripts

**Implementation Steps:**

1. **Update `audio-worklet.ts`** — Read both channels, interleave:
   ```typescript
   class PCMProcessor extends AudioWorkletProcessor {
     process(
       inputs: Float32Array[][],
       _outputs: Float32Array[][],
       _params: Record<string, Float32Array>
     ): boolean {
       const ch0 = inputs[0]?.[0]; // mic (L)
       const ch1 = inputs[0]?.[1]; // tab (R)
       if (!ch0 || ch0.length === 0) return true;

       // If only one channel available, duplicate it
       const right = ch1 && ch1.length > 0 ? ch1 : ch0;

       // Interleave L,R,L,R,... as Int16
       const interleaved = new Int16Array(ch0.length * 2);
       for (let i = 0; i < ch0.length; i++) {
         interleaved[i * 2] = Math.max(-32768, Math.min(32767, (ch0[i] ?? 0) * 32768));
         interleaved[i * 2 + 1] = Math.max(-32768, Math.min(32767, (right[i] ?? 0) * 32768));
       }

       this.port.postMessage(interleaved.buffer, [interleaved.buffer]);
       return true;
     }
   }

   registerProcessor("pcm-processor", PCMProcessor);
   ```

2. **Verify backend compatibility:** `deinterleave_stereo()` expects interleaved L0,R0,L1,R1,... which is exactly what we now produce. No backend changes needed.

3. **Build extension:** `cd extension && npm run build`

**Definition of Done:**
- [ ] AudioWorklet reads both channels from ChannelMergerNode
- [ ] Output is interleaved stereo PCM16 (L0,R0,L1,R1,...)
- [ ] If ch1 missing, falls back to duplicating ch0
- [ ] Extension builds without errors
- [ ] Backend `deinterleave_stereo()` produces valid separate channels

---

### 2. WebSocket Lifecycle

#### 2.1 Add WsClient.waitForOpen() + re-send session_start on reconnect

**Objective:** Replace brittle 200ms setTimeout with proper waitForOpen(). After WS reconnect, re-send session_start so backend creates a new orchestrator.

**Files:**
- Modify: `extension/src/lib/ws-client.ts`
- Modify: `extension/src/offscreen/offscreen.ts`
- Test: WS should connect reliably; reconnect should restore session

**Implementation Steps:**

1. **Add `waitForOpen()` to WsClient** (`ws-client.ts`):
   ```typescript
   waitForOpen(timeoutMs = 5000): Promise<void> {
     return new Promise((resolve, reject) => {
       if (this.ws?.readyState === WebSocket.OPEN) {
         resolve();
         return;
       }
       const timer = setTimeout(() => reject(new Error("WS open timeout")), timeoutMs);
       const origOnOpen = this.ws?.onopen;
       if (this.ws) {
         this.ws.onopen = () => {
           clearTimeout(timer);
           this.backoffMs = BACKOFF_INITIAL_MS;
           if (typeof origOnOpen === "function") origOnOpen.call(this.ws, new Event("open"));
           resolve();
         };
       }
     });
   }
   ```

2. **Add `onReconnect` callback** to WsClient constructor for session_start replay:
   ```typescript
   private onReconnect: (() => void) | null;

   constructor(onMessage: MessageHandler, url = BACKEND_WS_URL, onReconnect?: () => void) {
     this.onMessage = onMessage;
     this.url = url;
     this.onReconnect = onReconnect ?? null;
     this.connect();
   }
   ```
   In `connect()` → `onopen`, after resetting backoff, call `this.onReconnect?.()` if this is not the first connect.

3. **Update `offscreen.ts:94-97`** — Replace setTimeout with waitForOpen:
   ```typescript
   wsClient = new WsClient(handleWsMessage, BACKEND_WS_URL, () => {
     // On reconnect: re-send session_start
     wsClient?.sendControl({ type: "session_start", session_id: currentSessionId, kb_id: currentKbId });
   });
   await wsClient.waitForOpen();
   wsClient.sendControl({ type: "session_start", session_id: sessionId, kb_id: kbId });
   ```

4. **Store sessionId/kbId** in module-level variables in offscreen.ts for reconnect use.

5. **Build & verify**

**Definition of Done:**
- [ ] WsClient has `waitForOpen()` method with timeout
- [ ] No more `setTimeout(200)` hack in offscreen.ts
- [ ] After WS reconnect, session_start is re-sent automatically
- [ ] Timeout error is propagated to popup via SW response

---

#### 2.2 Fix captureInProgress reset + offscreen liveness check

**Objective:** Ensure captureInProgress is properly reset when offscreen dies. Add basic liveness check.

**Files:**
- Modify: `extension/src/background/service-worker.ts`
- Test: After offscreen crash, user can start a new session

**Implementation Steps:**

1. **Port disconnect already resets state** (from Task 1.2):
   ```typescript
   port.onDisconnect.addListener(() => {
     offscreenPort = null;
     captureInProgress = false;
     sessionTabId = null;
   });
   ```

2. **Add liveness check before START_SESSION** (in SW, before `getTabMediaStreamId`):
   ```typescript
   // If we think capture is in progress but port is dead, reset
   if (captureInProgress && offscreenPort === null) {
     captureInProgress = false;
   }
   ```

3. **Disable start button in popup immediately on click**, re-enable on error:
   ```typescript
   if (startBtn) startBtn.disabled = true;
   chrome.runtime.sendMessage(msg, (resp) => {
     if (resp?.ok) {
       // success — keep disabled, enable stop
     } else {
       if (startBtn) startBtn.disabled = false;
       // show error
     }
   });
   ```

**Definition of Done:**
- [ ] Port disconnect resets captureInProgress
- [ ] Stale captureInProgress detected and reset before new session
- [ ] Start button disabled during async operation
- [ ] User can start new session after offscreen crash

---

### 3. Backend Hardening

#### 3.1 Guard SessionManager and briefing against Redis=None

**Objective:** Prevent crashes when Redis is unavailable. SessionManager methods should no-op, briefing should return a meaningful response.

**Files:**
- Modify: `backend/session/manager.py`
- Modify: `backend/briefing/portrait.py` (if exists) or the briefing handler in `main.py`
- Test: `uv run pytest tests/` — existing tests + new edge case tests

**Implementation Steps:**

1. **Add Redis guards to SessionManager** (`session/manager.py`):
   ```python
   async def add_utterance(self, session_id: str, speaker: str, text: str) -> None:
       if self._redis is None:
           return
       # ... existing code

   async def get_context(self, session_id: str) -> SessionContext:
       if self._redis is None:
           return SessionContext()
       # ... existing code

   async def update_summary(self, session_id: str, summarise_fn: SummariseFn) -> None:
       if self._redis is None:
           return
       # ... existing code
   ```

2. **Guard briefing endpoint** — Find the briefing handler and add Redis None check. If `redis is None`, return empty briefing or error message instead of crashing.

3. **Write tests:** Test SessionManager with `redis=None` — should return empty context, not crash.

4. **Run tests:** `cd /Users/teterinsa/Projects/crmcore && uv run pytest tests/ -v`

**Definition of Done:**
- [ ] SessionManager methods return safely when redis=None
- [ ] Briefing endpoint returns 200 (with empty/fallback data) when redis=None
- [ ] New tests for Redis=None scenario
- [ ] All existing tests pass

---

#### 3.2 Send WS error frames to extension

**Objective:** When STT or LLM fails, send structured error frames to extension so the widget can show DISCONNECTED or error state.

**Files:**
- Modify: `backend/pipeline/orchestrator.py`
- Modify: `backend/main.py` (WS handler error paths)
- Test: Widget should show error state on backend failure

**Implementation Steps:**

1. **Add error frame sending to orchestrator** (`orchestrator.py:115-118`):
   ```python
   except Exception as exc:
       logger.warning("LLM stream interrupted: %r", exc)
       with contextlib.suppress(Exception):
           await self._ws.send_json({
               "type": "error",
               "code": "LLM_FAILED",
               "message": str(exc)[:100],
           })
       if not tokens:
           return
   ```

2. **Add error frame to WS handler** (`main.py`) when session_start fails:
   ```python
   except Exception as exc:
       logger.error("Session start failed: %r", exc)
       await websocket.send_json({
           "type": "error",
           "code": "SESSION_START_FAILED",
           "message": str(exc)[:100],
       })
   ```

3. **Run tests:** `uv run pytest tests/ -v`

**Definition of Done:**
- [ ] Backend sends `{"type": "error", ...}` frames on failure
- [ ] Error codes: LLM_FAILED, SESSION_START_FAILED, STT_UNAVAILABLE
- [ ] Widget receives error and can transition to appropriate state
- [ ] All existing tests pass

---

### 4. Integration Testing

#### 4.1 End-to-end verification

**Objective:** Verify the complete pipeline works: upload → start call → audio → transcription → hints in widget.

**Files:**
- No new files — verification only

**Implementation Steps:**

1. **Start backend:** `cd /Users/teterinsa/Projects/crmcore && .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000`

2. **Build extension:** `cd extension && npm run build`

3. **Reload extension** in chrome://extensions (click refresh icon)

4. **Upload test file** via popup: use `test_data/client_brief.md`

5. **Verify briefing** appears (or is fetchable via "Подготовить звонок")

6. **Open a tab with audio** (e.g., YouTube video or a SIP web-client)

7. **Click "Начать звонок"** — should NOT show "No target tab found"

8. **Check server logs** for:
   - `Session started: id=... kb=... scenario_len=...`
   - STT transcript messages
   - Hint generation

9. **Check widget** on the CRM tab:
   - Should transition to LISTENING state
   - Should show transcripts in transcript bar
   - Should display hints when LLM responds

10. **Test reconnect:** Kill backend, restart, verify WS reconnects and session_start is re-sent

11. **Run all tests:** `uv run pytest tests/ -v`

**Definition of Done:**
- [ ] Upload works (already working)
- [ ] "Начать звонок" initiates tabCapture without error
- [ ] Audio frames reach backend (visible in logs)
- [ ] STT produces transcripts
- [ ] Hints appear in widget
- [ ] WS reconnect works
- [ ] All unit tests pass (103+)

## Testing Strategy

- **Unit tests:** Backend SessionManager with redis=None, deinterleave_stereo with correct stereo input
- **Integration tests:** WS handler with mock audio frames
- **Manual verification:** Full E2E with real extension, real audio, real STT

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| SaluteSpeech API key invalid/expired | Low | High | Test with curl before E2E |
| Chrome tabCapture requires user gesture | Medium | Medium | Extension popup click IS a user gesture |
| AudioWorklet only receives 1 channel from merger | Medium | High | Fallback: duplicate ch0 if ch1 missing |
| Backend STT produces no transcripts (bad audio quality) | Medium | High | Check VAD threshold, test with clear speech |
| Offscreen document killed by Chrome mid-test | Low | Medium | Port disconnect handler resets state |

## Open Questions
- SaluteSpeech gRPC: does it handle 16kHz stereo correctly, or does it expect mono? (Check during E2E)
- Chrome tabCapture: does it work with all tab types, or only HTTP/HTTPS pages?

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
