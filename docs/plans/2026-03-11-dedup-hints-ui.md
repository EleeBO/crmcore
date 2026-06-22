# Dedup + Interactive Hints + UI Split Layout

> **IMPORTANT:** Start with fresh context. Run `/clear` before `/implement`.

Created: 2026-03-11
Status: VERIFIED

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented (set by /implement)
> - VERIFIED: Rules supervisor passed (set automatically)

## Summary

**Goal:** Fix transcript duplicates from Yandex STT, add interactive negotiation hints for both speakers, and redesign the Phase 3 UI with a split layout (transcript top + fixed hints panel bottom).

**Architecture:**
- Backend: Add `utterance_id` to `Transcript`, handle `final` → `final_refinement` replacement in `stt.py`, extend `orchestrator.py` to run pipeline on both speakers with different prompts.
- Frontend: Add `utterance_id` to `WsTranscript`, implement replace-by-id logic in `handleTranscript()`, split Phase 3 into two flex zones (transcript + hints panel), keep collapsed briefing sections.

**Tech Stack:** Python (FastAPI, dataclasses), TypeScript (vanilla DOM), Yandex SpeechKit gRPC, OpenRouter LLM

## Scope

### In Scope
- Fix duplicate transcripts from Yandex SpeechKit `final` + `final_refinement`
- Add `utterance_id` tracking through STT → WS → UI
- Generate hints on rep speech (coaching) in addition to client speech (analysis)
- Use separate system prompts for client vs rep hints
- Pass structured scenario data (objections, strategy) to LLM instead of plain text
- Use `coaching` field from LLM response
- Redesign Phase 3 layout: transcript (flex:1, auto-scroll) top + fixed hints panel (~150px) bottom
- Keep collapsed briefing sections (Портрет, Стратегия, Возражения) as reference
- Update `WsMessage` types in `messages.ts`

### Out of Scope
- React migration (stay vanilla TS)
- Phase 0/1/2/4 UI changes
- Scenario generation changes (`scenario.py`)
- STT provider switching (Deepgram, SaluteSpeech paths)
- Audio pipeline changes

## Prerequisites
- Yandex STT is the active provider (tested manually against their API)
- Backend tests pass: `cd backend && python -m pytest`
- Extension builds: `cd extension && npm run build`

## Context for Implementer

### Codebase Conventions
- Backend: Python 3.11+, dataclasses for DTOs, `logger` from `backend.logger`, async/await
- Extension: Vanilla TS, `$()` helper for getElementById, `show()`/`hide()` for visibility, RAF batching for streaming updates
- Tests: pytest + AsyncMock, capture WS messages via `capture_send` pattern

### Key Files
| File | Purpose |
|------|---------|
| `backend/pipeline/stt.py:44-50` | `Transcript` dataclass |
| `backend/pipeline/stt.py:590-603` | Yandex `final`/`final_refinement` handler |
| `backend/pipeline/orchestrator.py` | Pipeline orchestration (183 lines) |
| `backend/pipeline/llm.py` | LLM client + prompts (161 lines) |
| `backend/pipeline/scenario.py` | Scenario model (Pydantic) |
| `extension/src/shared/messages.ts` | WS message type definitions |
| `extension/src/sidepanel/sidepanel.ts:517-584` | `handleTranscript()` |
| `extension/src/sidepanel/sidepanel.ts:462-511` | Hint handlers |
| `extension/src/sidepanel/sidepanel.html:156-189` | Phase 3 HTML |
| `extension/src/sidepanel/sidepanel.css:577-701` | Hint + transcript CSS |

### Data Flow
```
Audio → STT (Yandex) → Transcript{speaker, text, is_final, utterance_id}
  → orchestrator.handle_transcript()
    → WS: {type: "transcript", ...}  → sidepanel: handleTranscript()
    → if final: _run_pipeline(text, speaker)
      → LLM (with structured scenario) → streaming hint
      → WS: hint_start → hint_chunk* → hint_end → sidepanel: hint panel
```

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

### 1. Fix Transcript Duplicates (Backend)
- [x] 1.1 Add `utterance_id` to Transcript and implement final→refinement dedup in STT
- [x] 1.2 Pass `utterance_id` through orchestrator to WebSocket

### 2. Fix Transcript Duplicates (Frontend)
- [x] 2.1 Update `WsTranscript` type and implement replace-by-id in `handleTranscript()`

### 3. Interactive Hints (Backend)
- [x] 3.1 Extend orchestrator to trigger pipeline on rep speech with speaker-aware prompts
- [x] 3.2 Add structured scenario context and coaching field to LLM pipeline

### 4. UI Split Layout (Frontend)
- [x] 4.1 Redesign Phase 3 HTML/CSS with split layout (transcript top + hints panel bottom)
- [x] 4.2 Implement new hint panel rendering with coaching support

**Total Tasks:** 6 | **Completed:** 6 | **Remaining:** 0

## Implementation Tasks

### 1. Fix Transcript Duplicates (Backend)

#### 1.1 Add `utterance_id` to Transcript and implement final→refinement dedup in STT

**Objective:** Each Yandex utterance gets a unique `utterance_id`. When `final` arrives, emit it immediately. When `final_refinement` arrives, emit it with the same `utterance_id` so the frontend can replace the text in-place instead of creating a duplicate entry.

**Files:**
- Modify: `backend/pipeline/stt.py` (Transcript dataclass + Yandex handler)
- Test: `backend/tests/test_stt.py`

**Implementation Steps:**

1. **Write failing test** — `test_transcript_has_utterance_id`:
   ```python
   def test_transcript_has_utterance_id() -> None:
       from backend.pipeline.stt import Transcript
       t = Transcript(speaker="client", text="Hello", is_final=True, utterance_id="utt-1")
       assert t.utterance_id == "utt-1"

   def test_transcript_utterance_id_defaults_empty() -> None:
       from backend.pipeline.stt import Transcript
       t = Transcript(speaker="client", text="Hello")
       assert t.utterance_id == ""
   ```

2. **Add `utterance_id` field** to `Transcript` dataclass (`stt.py:44-50`):
   ```python
   @dataclass
   class Transcript:
       speaker: str
       text: str
       is_final: bool = False
       utterance_id: str = ""  # NEW: links final → final_refinement
   ```

3. **Write failing test** — `test_yandex_dedup_final_and_refinement`:
   ```python
   @pytest.mark.asyncio
   async def test_yandex_final_and_refinement_share_utterance_id() -> None:
       """final and final_refinement for same utterance share utterance_id."""
       # Mock Yandex stream that sends final then final_refinement
       # Verify both Transcript objects have same utterance_id
       # Verify final has is_final=True, refinement has is_final=True
   ```

4. **Modify Yandex handler** (`stt.py:590-603`) to track `utterance_id`:
   - Add a per-channel counter `_utterance_counters: dict[str, int]` to `YandexSpeechKitSTT`
   - On `final` event: increment counter, generate `utterance_id = f"{channel}-{counter}"`, emit Transcript with this id
   - On `final_refinement` event: use the SAME counter value (don't increment), emit Transcript with same `utterance_id`

   Key change in the handler:
   ```python
   elif event == "final":
       alts = resp.final.alternatives
       text = alts[0].text if alts else ""
       if text and self.on_transcript:
           self._utterance_counters[channel] = self._utterance_counters.get(channel, 0) + 1
           utt_id = f"{channel}-{self._utterance_counters[channel]}"
           await self.on_transcript(
               Transcript(speaker=speaker, text=text, is_final=True, utterance_id=utt_id)
           )
   elif event == "final_refinement":
       update = resp.final_refinement.normalized_text
       alts = update.alternatives
       text = alts[0].text if alts else ""
       if text and self.on_transcript:
           utt_id = f"{channel}-{self._utterance_counters.get(channel, 0)}"
           await self.on_transcript(
               Transcript(speaker=speaker, text=text, is_final=True, utterance_id=utt_id)
           )
   ```

**Definition of Done:**
- [ ] All tests pass (`python -m pytest backend/tests/test_stt.py -v`)
- [ ] Transcript dataclass has `utterance_id` field with default `""`
- [ ] Yandex handler generates consistent `utterance_id` for final/final_refinement pairs
- [ ] Deepgram and SaluteSpeech paths are unaffected (they don't set `utterance_id`)

---

#### 1.2 Pass `utterance_id` through orchestrator to WebSocket

**Objective:** The orchestrator must include `utterance_id` in the transcript WS message so the frontend can identify which entry to replace.

**Files:**
- Modify: `backend/pipeline/orchestrator.py` (line 45-52)
- Test: `backend/tests/test_pipeline.py`

**Implementation Steps:**

1. **Write failing test:**
   ```python
   @pytest.mark.asyncio
   async def test_transcript_includes_utterance_id(
       mock_llm_client, mock_session_manager
   ) -> None:
       """WS transcript message includes utterance_id field."""
       ws_messages = []
       async def capture_send(msg): ws_messages.append(msg)
       ws = AsyncMock()
       ws.send_json = capture_send
       orch = PipelineOrchestrator(ws=ws, session_id="s1", llm_client=mock_llm_client,
                                    session_manager=mock_session_manager, scenario_text="")
       t = Transcript(speaker="client", text="Hi", is_final=True, utterance_id="client-1")
       await orch.handle_transcript(t)
       transcript_msg = [m for m in ws_messages if m["type"] == "transcript"][0]
       assert transcript_msg["utterance_id"] == "client-1"
   ```

2. **Add `utterance_id` to WS send** in `orchestrator.py:45-52`:
   ```python
   await self._ws.send_json({
       "type": "transcript",
       "speaker": transcript.speaker,
       "text": transcript.text,
       "is_final": transcript.is_final,
       "utterance_id": transcript.utterance_id,  # NEW
   })
   ```

**Definition of Done:**
- [ ] Test passes
- [ ] WS transcript messages include `utterance_id`
- [ ] Existing tests still pass

---

### 2. Fix Transcript Duplicates (Frontend)

#### 2.1 Update `WsTranscript` type and implement replace-by-id in `handleTranscript()`

**Objective:** When a transcript with a known `utterance_id` arrives, find the existing DOM entry and update its text instead of creating a new entry. This eliminates duplicates from final→final_refinement.

**Files:**
- Modify: `extension/src/shared/messages.ts`
- Modify: `extension/src/sidepanel/sidepanel.ts` (handleTranscript function)
- No automated tests (vanilla TS, manual verification)

**Implementation Steps:**

1. **Add `utterance_id` to `WsTranscript`** in `messages.ts:20-25`:
   ```typescript
   export interface WsTranscript {
     type: "transcript";
     speaker: string;
     text: string;
     is_final: boolean;
     utterance_id?: string;  // NEW: links final → refinement
   }
   ```

2. **Modify `handleTranscript()`** in `sidepanel.ts:517-584`:

   Add `data-utterance-id` attribute to transcript entries. When a new transcript arrives with a non-empty `utterance_id`, search for existing entry with same id and update text in-place.

   Key logic:
   ```typescript
   function handleTranscript(msg: WsTranscript): void {
     const list = $("transcript-list");
     if (!list) return;
     const isAtBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 30;

     // NEW: Check if this is a refinement of an existing utterance
     let existingEntry: HTMLElement | null = null;
     if (msg.utterance_id) {
       existingEntry = list.querySelector(`[data-utterance-id="${msg.utterance_id}"]`);
     }

     if (existingEntry) {
       // REPLACE text in existing entry (final_refinement replaces final)
       const textEl = existingEntry.querySelector(".transcript-text");
       if (textEl) textEl.textContent = msg.text;
       // Flash to indicate update
       existingEntry.classList.add("flash");
       setTimeout(() => existingEntry!.classList.remove("flash"), 600);
     } else {
       // Existing interim/new entry logic (unchanged)
       const lastEntry = list.lastElementChild as HTMLElement | null;
       const isUpdate = lastEntry?.classList.contains("interim") &&
                        lastEntry?.dataset.speaker === msg.speaker;
       // ... rest of existing logic
       // ADD data-utterance-id to new entries:
       if (msg.utterance_id) entry.dataset.utteranceId = msg.utterance_id;
     }
     // ... auto-scroll logic unchanged
   }
   ```

3. **Build extension** to verify:
   ```bash
   cd extension && npm run build
   ```

**Definition of Done:**
- [ ] `WsTranscript` includes optional `utterance_id`
- [ ] `handleTranscript()` finds existing entry by `utterance_id` and replaces text
- [ ] New entries get `data-utterance-id` attribute
- [ ] Interim → final flow still works for non-Yandex providers (no `utterance_id`)
- [ ] Extension builds without errors

---

### 3. Interactive Hints (Backend)

#### 3.1 Extend orchestrator to trigger pipeline on rep speech with speaker-aware prompts

**Objective:** Currently `_run_pipeline` only fires when `transcript.speaker == "client"`. Extend it to also fire on `"rep"` speech, passing the speaker to the pipeline so the LLM can generate appropriate hints (analysis for client, coaching for rep).

**Files:**
- Modify: `backend/pipeline/orchestrator.py`
- Modify: `backend/tests/test_pipeline.py`

**Implementation Steps:**

1. **Write failing test:**
   ```python
   @pytest.mark.asyncio
   async def test_rep_speech_triggers_pipeline(
       mock_session_manager,
   ) -> None:
       """Rep (manager) speech triggers pipeline with speaker='rep'."""
       captured_ctx = []
       async def capture_stream(ctx):
           captured_ctx.append(ctx)
           yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'
       llm = MagicMock()
       llm._cancel_current = MagicMock()
       llm.generate_hint_stream = capture_stream
       ws = AsyncMock()
       orch = PipelineOrchestrator(ws=ws, session_id="s1", llm_client=llm,
                                    session_manager=mock_session_manager, scenario_text="test")
       t = Transcript(speaker="rep", text="Наш продукт", is_final=True)
       await orch.handle_transcript(t)
       assert len(captured_ctx) == 1
       assert captured_ctx[0].speaker == "rep"
   ```

2. **Modify `handle_transcript()`** in `orchestrator.py:56-64`:

   Change the condition from `if transcript.speaker == "client"` to trigger for both speakers:
   ```python
   if transcript.is_final:
       # ... add_utterance logic (unchanged)
       await self._run_pipeline(transcript.text, transcript.speaker)
   ```

3. **Update `_run_pipeline` signature** to accept `speaker`:
   ```python
   async def _run_pipeline(self, query: str, speaker: str = "client") -> None:
   ```

   Pass speaker to `HintContext`:
   ```python
   hint_ctx = HintContext(
       utterance=query,
       speaker=speaker,  # was hardcoded "client"
       rag_context=[self._scenario_text] if self._scenario_text else [],
       session_summary=summary,
   )
   ```

4. **Update existing test** `test_rep_transcript_no_pipeline` — this test asserts rep speech does NOT trigger pipeline. It should now be updated to expect hint generation for rep speech.

**Definition of Done:**
- [ ] All tests pass
- [ ] Rep speech triggers pipeline with `speaker="rep"`
- [ ] Client speech still triggers pipeline with `speaker="client"`
- [ ] `HintContext.speaker` reflects actual speaker

---

#### 3.2 Add structured scenario context and coaching field to LLM pipeline

**Objective:** Improve hint quality by (1) using different system prompts for client vs rep speech, (2) passing structured scenario data (objections, strategy) instead of plain text, (3) parsing and forwarding the `coaching` field from LLM response.

**Files:**
- Modify: `backend/pipeline/llm.py` (prompts, HintResponse, HintContext)
- Modify: `backend/pipeline/orchestrator.py` (pass structured data, send coaching in hint_end)
- Test: `backend/tests/test_llm.py`, `backend/tests/test_pipeline.py`

**Implementation Steps:**

1. **Write failing tests:**
   ```python
   # test_llm.py
   def test_hint_response_includes_coaching() -> None:
       from backend.pipeline.llm import HintResponse
       raw = '{"hint": "tip", "source": "f.pdf", "sentiment": "neutral", "color": "blue", "coaching": "говорите медленнее"}'
       resp = HintResponse.from_json(raw)
       assert resp.coaching == "говорите медленнее"

   def test_hint_response_coaching_optional() -> None:
       from backend.pipeline.llm import HintResponse
       raw = '{"hint": "tip", "source": "f.pdf", "sentiment": "neutral", "color": "blue"}'
       resp = HintResponse.from_json(raw)
       assert resp.coaching == ""
   ```

2. **Add `coaching` field** to `HintResponse` (`llm.py:27-51`):
   ```python
   @dataclass
   class HintResponse:
       hint: str
       source: str
       sentiment: str
       color: str
       coaching: str = ""  # NEW

       @classmethod
       def from_json(cls, raw: str) -> HintResponse:
           # ... existing parsing ...
           return cls(
               hint=data["hint"],
               source=data.get("source", ""),
               sentiment=data.get("sentiment", "neutral"),
               color=data.get("color", "blue"),
               coaching=data.get("coaching", ""),  # NEW
           )
   ```

3. **Create speaker-specific system prompts** (`llm.py`):

   Add `_SYSTEM_PROMPT_CLIENT` (analyze objections, suggest counter-strategy) and `_SYSTEM_PROMPT_REP` (coaching — tone, pace, errors, encouragement). Keep existing `_SYSTEM_PROMPT` as fallback/base.

   ```python
   _SYSTEM_PROMPT_CLIENT = (
       "Ты — реал-тайм ассистент продаж.\n"
       "Клиент только что высказался. Проанализируй его реплику.\n"
       "Правила:\n"
       "  1) Определи тип: возражение, вопрос, интерес, согласие.\n"
       "  2) Если возражение — предложи контр-аргумент из СЦЕНАРИЯ.\n"
       "  3) Укажи источник факта (файл, страница).\n"
       "  4) Оцени настроение: POSITIVE / NEUTRAL / NEGATIVE.\n"
       "  5) В поле coaching — посоветуй менеджеру тон и темп ответа.\n"
       "Отвечай ТОЛЬКО валидным JSON."
   )

   _SYSTEM_PROMPT_REP = (
       "Ты — реал-тайм коуч продаж.\n"
       "Менеджер только что высказался. Оцени его реплику.\n"
       "Правила:\n"
       "  1) Если менеджер допустил ошибку — WARNING + совет.\n"
       "  2) Если хорошо ответил — подбодри кратко.\n"
       "  3) Предложи следующий шаг по СЦЕНАРИЮ.\n"
       "  4) В поле coaching — рекомендация по тону/темпу.\n"
       "  5) Используй ТОЛЬКО факты из СЦЕНАРИЯ.\n"
       "Отвечай ТОЛЬКО валидным JSON."
   )
   ```

4. **Select prompt based on speaker** in `generate_hint_stream()`:
   ```python
   async def generate_hint_stream(self, ctx: HintContext) -> AsyncGenerator[str, None]:
       system_prompt = _SYSTEM_PROMPT_REP if ctx.speaker == "rep" else _SYSTEM_PROMPT_CLIENT
       messages = [
           {"role": "system", "content": system_prompt},
           {"role": "user", "content": _USER_TEMPLATE.format(...)},
       ]
       # ... rest unchanged
   ```

5. **Pass structured scenario** in orchestrator. Modify `PipelineOrchestrator.__init__` to accept optional `scenario_json: str` (the full Scenario JSON, not just text). In `_run_pipeline`, include structured data:
   ```python
   hint_ctx = HintContext(
       utterance=query,
       speaker=speaker,
       rag_context=[self._scenario_text] if self._scenario_text else [],
       session_summary=summary,
   )
   ```
   (Note: scenario_text already contains full JSON from Redis. The LLM prompt already references СЦЕНАРИЙ РАЗГОВОРА. This is sufficient — the structured Scenario model is used for briefing display, not for LLM context.)

6. **Send `coaching` in `hint_end`** in orchestrator `_stream_hint()`:
   ```python
   await self._ws.send_json({
       "type": "hint_end",
       "hint": resp.hint,
       "source": resp.source,
       "sentiment": resp.sentiment,
       "color": resp.color,
       "coaching": resp.coaching,  # NEW
   })
   ```

**Definition of Done:**
- [ ] `HintResponse.coaching` field works (with default `""`)
- [ ] Client speech uses `_SYSTEM_PROMPT_CLIENT`
- [ ] Rep speech uses `_SYSTEM_PROMPT_REP`
- [ ] `hint_end` WS message includes `coaching` field
- [ ] All tests pass

---

### 4. UI Split Layout (Frontend)

#### 4.1 Redesign Phase 3 HTML/CSS with split layout

**Objective:** Restructure Phase 3 so transcript takes the top portion (flex: 1, scrollable) and a fixed hints panel (~150px) sits at the bottom, always visible. Collapsed briefing sections remain between transcript and hints panel.

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.html` (Phase 3 section, lines 156-189)
- Modify: `extension/src/sidepanel/sidepanel.css`

**Implementation Steps:**

1. **Modify Phase 3 HTML** (`sidepanel.html:156-189`):

   Current structure:
   ```
   phase-3 → hint-area (sticky top) → transcript-area → briefing-collapsed
   ```

   New structure:
   ```
   phase-3 (flex column, height 100%)
   ├── transcript-area (flex: 1, overflow-y: auto)
   │   ├── transcript-header
   │   ├── transcript-list
   │   └── jump-pill
   ├── briefing-collapsed (collapsed details, no flex-shrink)
   └── hints-panel (fixed height ~150px, no flex-shrink)
       ├── hint-text (main hint)
       ├── coaching-text (coaching advice)
       └── hint-source (source badge)
   ```

   New HTML for Phase 3:
   ```html
   <section id="phase-3" class="phase">
     <!-- Transcript (top, scrollable) -->
     <div id="transcript-area" class="transcript-area">
       <div class="transcript-header">
         <span>Транскрипт</span>
         <span id="transcript-live-dot" class="live-dot">live</span>
       </div>
       <div id="transcript-list" class="transcript-list"></div>
       <button id="jump-to-latest" class="jump-pill" hidden>К последнему</button>
     </div>

     <!-- Collapsed briefing (reference) -->
     <div id="briefing-collapsed" class="briefing-collapsed">
       <details class="briefing-section" id="collapsed-portrait">
         <summary>Портрет клиента</summary>
         <div id="collapsed-portrait-text" class="briefing-section-body"></div>
       </details>
       <details class="briefing-section" id="collapsed-strategy">
         <summary>Стратегия</summary>
         <div id="collapsed-strategy-text" class="briefing-section-body"></div>
       </details>
       <details class="briefing-section" id="collapsed-objections">
         <summary>Возражения</summary>
         <div id="collapsed-objections-text" class="briefing-section-body"></div>
       </details>
     </div>

     <!-- Hints panel (bottom, fixed height) -->
     <div id="hints-panel" class="hints-panel">
       <div id="hint-text" class="hint-panel-text">Ожидание подсказок...</div>
       <div id="coaching-text" class="coaching-text" hidden></div>
       <span id="hint-source" class="hint-source" hidden></span>
     </div>
   </section>
   ```

2. **Add CSS for split layout**:
   ```css
   /* Phase 3: Split layout */
   #phase-3.active {
     display: flex;
     flex-direction: column;
     height: 100%;
     min-height: 0;
   }

   /* Transcript takes remaining space */
   #phase-3 .transcript-area {
     flex: 1;
     min-height: 0;
     display: flex;
     flex-direction: column;
   }

   #phase-3 .transcript-list {
     flex: 1;
     overflow-y: auto;
     min-height: 80px;
     max-height: none;  /* Remove old 400px max */
   }

   /* Briefing collapsed — doesn't shrink */
   #phase-3 .briefing-collapsed {
     flex-shrink: 0;
   }

   /* Hints panel — fixed at bottom */
   .hints-panel {
     flex-shrink: 0;
     min-height: 100px;
     max-height: 180px;
     overflow-y: auto;
     background: #FFF8E1;
     border-top: 2px solid #f59e0b;
     border-radius: 6px 6px 0 0;
     padding: 10px 12px;
     font-size: 13px;
     color: #1a1a1a;
     line-height: 1.5;
   }

   .hints-panel[data-color="green"] { border-top-color: #22c55e; }
   .hints-panel[data-color="blue"] { border-top-color: #3b82f6; }
   .hints-panel[data-color="red"] { border-top-color: #ef4444; }
   .hints-panel[data-color="orange"] { border-top-color: #f59e0b; }

   .hint-panel-text {
     white-space: pre-wrap;
     word-break: break-word;
   }

   .coaching-text {
     margin-top: 6px;
     padding-top: 6px;
     border-top: 1px solid rgba(0,0,0,0.08);
     font-size: 12px;
     color: #92400e;
     font-style: italic;
   }
   ```

3. **Remove old `hint-area`** styles (`.hint-area` CSS at lines 577-610 in sidepanel.css) and the old `#hint-area` element from HTML.

4. **Build extension:**
   ```bash
   cd extension && npm run build
   ```

**Definition of Done:**
- [ ] Phase 3 uses flex column layout
- [ ] Transcript area takes remaining space with auto-scroll
- [ ] Hints panel fixed at bottom, always visible
- [ ] Collapsed briefing sections between transcript and hints
- [ ] Old `hint-area` (sticky top) removed
- [ ] Extension builds without errors

---

#### 4.2 Implement new hint panel rendering with coaching support

**Objective:** Update the hint handlers (`handleHintStart`, `handleHintChunk`, `handleHintEnd`) to render into the new `hints-panel` element instead of old `hint-area`. Add support for displaying the `coaching` field.

**Files:**
- Modify: `extension/src/shared/messages.ts` (add coaching to WsHintEnd)
- Modify: `extension/src/sidepanel/sidepanel.ts` (hint handlers)

**Implementation Steps:**

1. **Add `coaching` to `WsHintEnd`** in `messages.ts`. First check `types.ts` for `HintPayload`:
   ```typescript
   // In types.ts or messages.ts — wherever HintPayload is defined:
   export interface HintPayload {
     hint: string;
     source: string;
     sentiment: string;
     color: string;
     coaching?: string;  // NEW
   }
   ```

2. **Update hint handlers** in `sidepanel.ts`:

   Replace references from `$("hint-area")` to `$("hints-panel")`:

   ```typescript
   function handleHintStart(msg: WsHintStart): void {
     const panel = $("hints-panel");
     const hintText = $("hint-text");
     const coachingText = $("coaching-text");

     if (panel) {
       panel.setAttribute("data-color", msg.color || "orange");
     }
     if (hintText) hintText.textContent = "";
     if (coachingText) { coachingText.textContent = ""; hide(coachingText); }
     hide($("hint-source"));

     hintPendingText = "";
     hintRafPending = false;
   }

   function handleHintChunk(msg: WsHintChunk): void {
     // Same RAF batching logic, targeting #hint-text (unchanged)
     hintPendingText += msg.text;
     if (!hintRafPending) {
       hintRafPending = true;
       requestAnimationFrame(() => {
         hintRafPending = false;
         const hintText = $("hint-text");
         if (hintText) hintText.textContent += hintPendingText;
         hintPendingText = "";
       });
     }
   }

   function handleHintEnd(msg: WsHintEnd): void {
     hintPendingText = "";

     // Replace streamed text with parsed hint
     const hintText = $("hint-text");
     if (hintText && msg.hint) {
       hintText.textContent = msg.hint;
     }

     // Show coaching if present
     const coachingText = $("coaching-text");
     if (coachingText && msg.coaching) {
       coachingText.textContent = `🎯 ${msg.coaching}`;
       show(coachingText);
     }

     // Source badge
     const hintSource = $("hint-source");
     if (hintSource && msg.source) {
       hintSource.textContent = `📎 ${msg.source}`;
       show(hintSource);
     }
   }
   ```

3. **Build and verify:**
   ```bash
   cd extension && npm run build
   ```

**Definition of Done:**
- [ ] Hints render in bottom `hints-panel` instead of old sticky `hint-area`
- [ ] `coaching` field displayed below hint text when present
- [ ] Source badge still works
- [ ] Color coding (data-color attribute) works on hints-panel
- [ ] Extension builds without errors

---

## Testing Strategy

- **Unit tests**: pytest for Transcript dataclass, orchestrator routing, LLM prompt selection, HintResponse.coaching
- **Integration tests**: Full pipeline flow with mock LLM — verify WS messages include utterance_id and coaching
- **Manual verification**:
  1. Start call with Yandex STT, speak — verify no duplicates in transcript
  2. Speak as client → verify hint appears with counter-strategy
  3. Speak as rep → verify coaching hint appears
  4. Verify hints panel always visible at bottom
  5. Verify transcript auto-scrolls, collapsed briefing sections work

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Yandex may not always send `final_refinement` | Low | Med | `final` still creates entry; if no refinement, entry stays with raw text |
| Double LLM calls increase costs | Med | Med | Debounce still active (500ms), can increase for rep to save tokens |
| LLM may not follow speaker-specific prompts | Low | Low | Test prompts manually, iterate on wording |
| CSS flex layout breaks in narrow sidepanel | Low | Med | Test at min sidepanel width (~350px), use min-height |

## Open Questions
- Should debounce be different for rep vs client? (e.g., 500ms for client, 2s for rep to reduce costs)
- Should coaching hints have a different color scheme than analysis hints?

---
**USER: Please review this plan. Edit any section directly, then confirm to proceed.**
