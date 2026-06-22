# Hint Timing & Layout Flip — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop hint flickering during live calls and move hints to top of panel for maximum visual priority.

**Architecture:** Replace streaming hint delivery (hint_start/chunk/end) with silent generation — backend collects all tokens silently and sends a single `hint_end` message. Raise cooldown from 500ms to 15s. Add 8s display cooldown on frontend. Flip Phase 3 layout: hints on top (45%), transcript on bottom (55%).

**Tech Stack:** Python (orchestrator, LLM client), TypeScript (Chrome extension sidepanel, service worker), CSS

**Spec:** `docs/superpowers/specs/2026-03-11-hint-timing-strategy-design.md`

---

## Chunk 1: Backend — Silent Generation & Cooldown

### Task 1: Raise cooldown to 15s and rename constant

**Files:**
- Modify: `backend/pipeline/orchestrator.py:15` (constant), `backend/pipeline/orchestrator.py:77-87` (debounce check)
- Test: `backend/tests/test_pipeline.py:409-445`

- [ ] **Step 1: Update existing debounce test to expect new cooldown behavior**

In `backend/tests/test_pipeline.py`, rename and update the test:

```python
# Replace test_pipeline_debounce_skips_rapid_hints (line 409-445) with:
@pytest.mark.asyncio
async def test_pipeline_cooldown_skips_rapid_hints(
    mock_session_manager: AsyncMock,
) -> None:
    """Two rapid handle_transcript calls — second hint is blocked by cooldown."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    hint_count = 0

    async def counting_stream(ctx):
        nonlocal hint_count
        hint_count += 1
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = counting_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t1 = Transcript(speaker="client", text="First", is_final=True)
    t2 = Transcript(speaker="client", text="Second", is_final=True)

    await orch.handle_transcript(t1)
    await orch.handle_transcript(t2)

    assert hint_count == 1, f"Expected 1 hint (cooldown), got {hint_count}"
```

- [ ] **Step 2: Add test for hint generation after cooldown expires**

Append to `backend/tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_pipeline_cooldown_allows_after_timeout(
    mock_session_manager: AsyncMock,
) -> None:
    """After cooldown expires, next utterance triggers a hint."""
    import time
    from backend.pipeline import orchestrator as orch_mod
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    hint_count = 0

    async def counting_stream(ctx):
        nonlocal hint_count
        hint_count += 1
        yield '{"hint": "ok", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = counting_stream

    ws = AsyncMock()

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t1 = Transcript(speaker="client", text="First", is_final=True)
    await orch.handle_transcript(t1)
    assert hint_count == 1

    # Simulate cooldown elapsed
    orch._last_hint_time = time.monotonic() - orch_mod._HINT_COOLDOWN_S - 1.0

    t2 = Transcript(speaker="client", text="Second", is_final=True)
    await orch.handle_transcript(t2)
    assert hint_count == 2, "Should fire after cooldown"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py::test_pipeline_cooldown_skips_rapid_hints backend/tests/test_pipeline.py::test_pipeline_cooldown_allows_after_timeout -v`

Expected: FAIL — `_HINT_COOLDOWN_S` not defined yet.

- [ ] **Step 4: Implement cooldown constant rename**

In `backend/pipeline/orchestrator.py`, replace line 15:

```python
# Old:
_HINT_DEBOUNCE_S = 0.5  # Don't generate hints more often than every 500ms

# New:
_HINT_COOLDOWN_S = 15.0  # Minimum gap between hints (seconds)
```

Update lines 79-87 to use new name:

```python
    async def _run_pipeline(self, query: str, speaker: str = "client") -> None:
        """Execute Scenario -> LLM -> delivery for a final transcript."""
        now = time.monotonic()
        elapsed = now - self._last_hint_time
        if elapsed < _HINT_COOLDOWN_S:
            logger.debug(
                "Cooldown: skipping hint, last was %.1fs ago (cooldown=%.0fs)",
                elapsed,
                _HINT_COOLDOWN_S,
            )
            return
        self._last_hint_time = now
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py::test_pipeline_cooldown_skips_rapid_hints backend/tests/test_pipeline.py::test_pipeline_cooldown_allows_after_timeout -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/tests/test_pipeline.py
git commit -m "feat: raise hint cooldown from 500ms to 15s

Rename _HINT_DEBOUNCE_S -> _HINT_COOLDOWN_S with 15s value.
Prevents hint flickering during active conversation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Silent generation — only send hint_end

**Files:**
- Modify: `backend/pipeline/orchestrator.py:125-183` (replace `_stream_hint`)
- Test: `backend/tests/test_pipeline.py` (update assertions)

- [ ] **Step 1: Update test_llm_streaming to expect no hint_chunk**

In `backend/tests/test_pipeline.py`, update `test_llm_streaming` (line 377-406):

```python
@pytest.mark.asyncio
async def test_silent_hint_generation(
    mock_llm_client: MagicMock,
    mock_session_manager: AsyncMock,
) -> None:
    """Hint is delivered as a single hint_end — no hint_start or hint_chunk."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="sess-001",
        llm_client=mock_llm_client,
        session_manager=mock_session_manager,
        scenario_text="test scenario",
    )

    t = Transcript(speaker="client", text="Какой RTO?", is_final=True)
    await orch.handle_transcript(t)

    msg_types = {m.get("type") for m in ws_messages}
    assert "hint_end" in msg_types
    assert "hint_start" not in msg_types, "Silent generation should not send hint_start"
    assert "hint_chunk" not in msg_types, "Silent generation should not send hint_chunk"
```

- [ ] **Step 2: Update test_pipeline_full_flow assertion**

In `backend/tests/test_pipeline.py`, line 248, change:

```python
# Old:
assert "hint_chunk" in msg_types or "hint_end" in msg_types

# New:
assert "hint_end" in msg_types
assert "hint_start" not in msg_types
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py::test_silent_hint_generation backend/tests/test_pipeline.py::test_pipeline_full_flow -v`

Expected: FAIL — `hint_start` and `hint_chunk` are still being sent.

- [ ] **Step 4: Replace `_stream_hint` with silent generation**

In `backend/pipeline/orchestrator.py`, add `import time as time_mod` at the top (for `generated_at`), then replace `_stream_hint` (lines 125-183) with:

```python
    async def _generate_hint_silent(self, ctx: HintContext) -> None:
        """Generate hint silently: no hint_start/hint_chunk; only hint_end."""
        self._llm._cancel_current()

        tokens: list[str] = []
        try:
            async for token in self._llm.generate_hint_stream(ctx):
                tokens.append(token)
        except Exception as exc:
            logger.warning("LLM stream failed: %r", exc)
            if not tokens:
                return

        if not tokens:
            return

        full_json = "".join(tokens)
        try:
            resp = HintResponse.from_json(full_json)
            await self._ws.send_json(
                {
                    "type": "hint_end",
                    "hint": resp.hint,
                    "source": resp.source,
                    "sentiment": resp.sentiment,
                    "color": resp.color,
                    "coaching": resp.coaching,
                    "generated_at": time.monotonic(),
                }
            )
        except Exception as exc:
            logger.warning("Failed to parse/send hint_end: %r", exc)
```

Update the call in `_run_pipeline` (line 109):

```python
# Old:
await self._stream_hint(hint_ctx)

# New:
await self._generate_hint_silent(hint_ctx)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py -v`

Expected: ALL PASS

- [ ] **Step 6: Run ruff/mypy**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run ruff check backend/pipeline/orchestrator.py && uv run mypy backend/pipeline/orchestrator.py --ignore-missing-imports`

Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/tests/test_pipeline.py
git commit -m "feat: silent hint generation — send only hint_end

Remove hint_start/hint_chunk from pipeline. Backend collects all
tokens silently, parses JSON, and sends a single hint_end message.
Adds generated_at timestamp for future staleness tracking.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Smart cancellation — don't cancel when tokens are flowing

**Files:**
- Modify: `backend/pipeline/llm.py:113-119` (_cancel_current), `backend/pipeline/llm.py:121-149` (generate_hint_stream)
- Test: `backend/tests/test_llm.py`

- [ ] **Step 1: Write test for smart cancel**

Append to `backend/tests/test_llm.py`:

```python
@pytest.mark.asyncio
async def test_smart_cancel_skips_when_tokens_received() -> None:
    """_cancel_current(force=False) does NOT cancel when tokens_received > 0."""
    with patch("backend.pipeline.llm.AsyncOpenAI"):
        from backend.pipeline.llm import LLMClient

        client = LLMClient(
            primary_model="m", fallback_model="f", api_key="k",
            primary_timeout_ms=5000, fallback_timeout_ms=5000,
        )
        client._llm_task = asyncio.create_task(asyncio.sleep(10))
        client._tokens_received = 3
        original_task = client._llm_task

        client._cancel_current()  # force=False by default

        await asyncio.sleep(0)
        assert not original_task.cancelled(), "Should NOT cancel when tokens > 0"
        original_task.cancel()  # cleanup


@pytest.mark.asyncio
async def test_smart_cancel_force_overrides() -> None:
    """_cancel_current(force=True) cancels even when tokens_received > 0."""
    with patch("backend.pipeline.llm.AsyncOpenAI"):
        from backend.pipeline.llm import LLMClient

        client = LLMClient(
            primary_model="m", fallback_model="f", api_key="k",
            primary_timeout_ms=5000, fallback_timeout_ms=5000,
        )
        client._llm_task = asyncio.create_task(asyncio.sleep(10))
        client._tokens_received = 3

        client._cancel_current(force=True)

        await asyncio.sleep(0)
        assert client._llm_task is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_llm.py::test_smart_cancel_skips_when_tokens_received backend/tests/test_llm.py::test_smart_cancel_force_overrides -v`

Expected: FAIL — `_tokens_received` doesn't exist, `force` param doesn't exist.

- [ ] **Step 3: Implement smart cancel**

In `backend/pipeline/llm.py`:

Add `_tokens_received` to `__init__` (after line 113):

```python
        self._llm_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._tokens_received: int = 0
```

Replace `_cancel_current` (lines 115-119):

```python
    def _cancel_current(self, *, force: bool = False) -> None:
        """Cancel the currently in-flight LLM task, if any.

        If force=False (default), skip cancellation when tokens have been
        received so a nearly-complete generation is not thrown away.
        """
        if self._llm_task is None or self._llm_task.done():
            self._llm_task = None
            return
        if not force and self._tokens_received > 0:
            logger.debug(
                "Smart cancel: skipping — %d tokens already received",
                self._tokens_received,
            )
            return
        self._llm_task.cancel()
        self._llm_task = None
        self._tokens_received = 0
```

Add `_tokens_received` reset and counter in `generate_hint_stream` (lines 121-149):

```python
    async def generate_hint_stream(
        self,
        ctx: HintContext,
    ) -> AsyncGenerator[str, None]:
        """Stream raw LLM tokens for hint generation."""
        self._tokens_received = 0
        system_prompt = (
            _SYSTEM_PROMPT_REP if ctx.speaker == "rep" else _SYSTEM_PROMPT_CLIENT
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    speaker=ctx.speaker,
                    utterance=ctx.utterance,
                    rag_context="\n".join(ctx.rag_context),
                    session_summary=ctx.session_summary,
                ),
            },
        ]
        async with await self._client.chat.completions.create(
            model=self._primary_model,
            messages=messages,
            stream=True,
        ) as stream:
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    self._tokens_received += 1
                    yield content
```

- [ ] **Step 4: Run all LLM tests**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_llm.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/llm.py backend/tests/test_llm.py
git commit -m "feat: smart cancel — skip cancellation when tokens are flowing

Track _tokens_received in LLMClient. _cancel_current(force=False)
preserves in-flight generation when tokens > 0. Use force=True for
teardown scenarios.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Generation timeout (5s)

**Files:**
- Modify: `backend/pipeline/orchestrator.py` (add timeout constant, wrap generation)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write test for generation timeout**

Append to `backend/tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_hint_generation_timeout(
    mock_session_manager: AsyncMock,
) -> None:
    """Slow LLM that exceeds timeout produces no hint_end."""
    from backend.pipeline.orchestrator import (
        PipelineOrchestrator,
        _HINT_GENERATION_TIMEOUT_S,
    )
    from backend.pipeline.stt import Transcript

    async def slow_stream(ctx):
        await asyncio.sleep(_HINT_GENERATION_TIMEOUT_S + 2)
        yield '{"hint": "late", "source": "", "sentiment": "neutral", "color": "blue"}'

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = slow_stream

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s1",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text="test",
    )

    t = Transcript(speaker="client", text="Question", is_final=True)
    await asyncio.wait_for(orch.handle_transcript(t), timeout=_HINT_GENERATION_TIMEOUT_S + 3)

    hint_ends = [m for m in ws_messages if m.get("type") == "hint_end"]
    assert len(hint_ends) == 0, "Timed-out generation should not send hint_end"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py::test_hint_generation_timeout -v`

Expected: FAIL — `_HINT_GENERATION_TIMEOUT_S` not defined, test hangs or fails.

- [ ] **Step 3: Implement generation timeout**

In `backend/pipeline/orchestrator.py`, add after line 15:

```python
_HINT_GENERATION_TIMEOUT_S = 5.0  # Max time for LLM to generate a hint
```

Wrap the generation call in `_generate_hint_silent` with `asyncio.wait_for`:

```python
    async def _generate_hint_silent(self, ctx: HintContext) -> None:
        """Generate hint silently with timeout."""
        self._llm._cancel_current()

        try:
            await asyncio.wait_for(
                self._collect_and_send_hint(ctx),
                timeout=_HINT_GENERATION_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Hint generation timed out after %.0fs (session=%s)",
                _HINT_GENERATION_TIMEOUT_S,
                self._session_id,
            )

    async def _collect_and_send_hint(self, ctx: HintContext) -> None:
        """Collect all LLM tokens and send a single hint_end."""
        tokens: list[str] = []
        try:
            async for token in self._llm.generate_hint_stream(ctx):
                tokens.append(token)
        except Exception as exc:
            logger.warning("LLM stream failed: %r", exc)
            if not tokens:
                return

        if not tokens:
            return

        full_json = "".join(tokens)
        try:
            resp = HintResponse.from_json(full_json)
            await self._ws.send_json(
                {
                    "type": "hint_end",
                    "hint": resp.hint,
                    "source": resp.source,
                    "sentiment": resp.sentiment,
                    "color": resp.color,
                    "coaching": resp.coaching,
                    "generated_at": time.monotonic(),
                }
            )
        except Exception as exc:
            logger.warning("Failed to parse/send hint_end: %r", exc)
```

- [ ] **Step 4: Run all pipeline tests**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/test_pipeline.py -v`

Expected: ALL PASS

- [ ] **Step 5: Run linters**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run ruff check backend/pipeline/orchestrator.py`

Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/tests/test_pipeline.py
git commit -m "feat: add 5s generation timeout for hint pipeline

Wrap silent generation in asyncio.wait_for(5s). If LLM doesn't
respond in time, discard and keep previous hint on screen.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Frontend — Layout Flip & Display Cooldown

### Task 5: Flip Phase 3 layout — hints on top

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.html:156-190` (reorder Phase 3 children)
- Modify: `extension/src/sidepanel/sidepanel.css:576-640` (flex order, borders, padding)

- [ ] **Step 1: Reorder Phase 3 HTML — hints first, transcript last**

In `extension/src/sidepanel/sidepanel.html`, replace Phase 3 section (lines 156-190):

```html
      <!-- Phase 3: Live call (PRIMARY) — split layout -->
      <section id="phase-3" class="phase">
        <!-- Hints panel (top, highest visual priority) -->
        <div id="hints-panel" class="hints-panel">
          <div id="hint-text" class="hint-panel-text">Слушаю разговор...</div>
          <div id="coaching-text" class="coaching-text" hidden></div>
          <span id="hint-source" class="hint-source" hidden></span>
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

        <!-- Transcript (bottom, scrollable) -->
        <div id="transcript-area" class="transcript-area">
          <div class="transcript-header">
            <span>Транскрипт</span>
            <span id="transcript-live-dot" class="live-dot">live</span>
          </div>
          <div id="transcript-list" class="transcript-list"></div>
          <button id="jump-to-latest" class="jump-pill" hidden>К последнему</button>
        </div>
      </section>
```

- [ ] **Step 2: Update CSS for new layout**

In `extension/src/sidepanel/sidepanel.css`, update hints-panel styles (lines 584-627):

```css
/* Hints panel — fixed at top, 45% of space */
.hints-panel {
  flex: 0 0 45%;
  min-height: 80px;
  max-height: 50%;
  overflow-y: auto;
  background: #FFF8E1;
  border-bottom: 2px solid #f59e0b;
  border-radius: 0 0 6px 6px;
  padding: 10px 12px;
  font-size: 13px;
  color: #1a1a1a;
  line-height: 1.5;
}
```

Override `#content-area` padding for Phase 3:

```css
/* Remove padding when Phase 3 is active to maximize space */
#phase-3.active ~ #content-area,
#content-area:has(#phase-3.active) {
  padding: 0;
}

/* Phase 3 needs its own inner padding */
#phase-3 .hints-panel,
#phase-3 .briefing-collapsed,
#phase-3 .transcript-area {
  padding-left: 12px;
  padding-right: 12px;
}
```

- [ ] **Step 3: Build and verify**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit && pnpm run build`

Expected: No errors, build succeeds.

- [ ] **Step 4: Commit**

```bash
git add extension/src/sidepanel/sidepanel.html extension/src/sidepanel/sidepanel.css
git commit -m "feat: flip Phase 3 layout — hints on top, transcript on bottom

Move hints panel to top of Phase 3 for highest visual priority.
Proportions 45%/55% (hints/transcript). Briefing collapsed in middle.
Initial hint text: 'Слушаю разговор...'

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Display cooldown (8s) and fade transitions

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts:466-516` (hint handlers)
- Modify: `extension/src/sidepanel/sidepanel.css` (transitions)

- [ ] **Step 1: Add fade transition CSS**

Append to `extension/src/sidepanel/sidepanel.css` after the `.hint-source` block:

```css
/* Hint fade transitions */
.hint-panel-text,
.coaching-text,
.hint-source {
  transition: opacity 0.3s ease-in-out;
}

.hint-panel-text.fading {
  opacity: 0;
}
```

- [ ] **Step 2: Rewrite hint handlers with display cooldown**

In `extension/src/sidepanel/sidepanel.ts`, replace the hint display section (lines 466-516):

```typescript
// ── Hint display (Phase 3) ────────────────────────────────────────────────

const DISPLAY_COOLDOWN_MS = 8_000; // Min time a hint stays visible
let lastHintRenderedAt = 0;
let pendingHintEnd: WsHintEnd | null = null;
let pendingHintTimer: ReturnType<typeof setTimeout> | null = null;

function handleHintStart(_msg: WsHintStart): void {
  // Silent generation: hint_start is no longer sent by backend.
  // No-op for backward compatibility.
}

function handleHintChunk(_msg: WsHintChunk): void {
  // Silent generation: hint_chunk is no longer sent by backend.
  // No-op for backward compatibility.
}

function handleHintEnd(msg: WsHintEnd): void {
  const now = Date.now();
  const elapsed = now - lastHintRenderedAt;

  if (elapsed < DISPLAY_COOLDOWN_MS && lastHintRenderedAt > 0) {
    // Queue hint — display when cooldown expires
    pendingHintEnd = msg;
    if (!pendingHintTimer) {
      const remaining = DISPLAY_COOLDOWN_MS - elapsed;
      pendingHintTimer = setTimeout(flushPendingHint, remaining);
    }
    return;
  }

  renderHint(msg);
}

function flushPendingHint(): void {
  pendingHintTimer = null;
  if (pendingHintEnd) {
    const msg = pendingHintEnd;
    pendingHintEnd = null;
    renderHint(msg);
  }
}

function renderHint(msg: WsHintEnd): void {
  lastHintRenderedAt = Date.now();

  const panel = $("hints-panel");
  const hintText = $("hint-text");
  const coachingText = $("coaching-text");
  const hintSource = $("hint-source");

  // Set panel color
  if (panel) {
    panel.setAttribute("data-color", msg.color || "orange");
  }

  // Fade out, swap content, fade in
  if (hintText) {
    hintText.classList.add("fading");
    setTimeout(() => {
      hintText.classList.remove("loading-dots");
      if (msg.hint) {
        hintText.textContent = msg.hint;
      }
      hintText.classList.remove("fading");
    }, 300);
  }

  // Show coaching if present
  if (coachingText) {
    if (msg.coaching) {
      coachingText.textContent = msg.coaching;
      show(coachingText);
    } else {
      coachingText.textContent = "";
      hide(coachingText);
    }
  }

  // Source badge
  if (hintSource) {
    if (msg.source) {
      hintSource.textContent = `\u{1F4CE} ${msg.source}`;
      show(hintSource);
    } else {
      hide(hintSource);
    }
  }
}
```

- [ ] **Step 3: Update handleCaptureStarted to set initial state**

In `extension/src/sidepanel/sidepanel.ts`, update `handleCaptureStarted` (lines 370-378):

```typescript
  // Reset hint state for new session
  const hintText = $("hint-text");
  if (hintText) {
    hintText.textContent = "Слушаю разговор...";
    hintText.classList.remove("loading-dots", "fading");
  }
  const coachingEl = $("coaching-text");
  if (coachingEl) { coachingEl.textContent = ""; hide(coachingEl); }
  hide($("hint-source"));
  lastHintRenderedAt = 0;
  pendingHintEnd = null;
  if (pendingHintTimer) { clearTimeout(pendingHintTimer); pendingHintTimer = null; }
  isAutoScrolling = true;
```

- [ ] **Step 4: TypeScript check and build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit && pnpm run build`

Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add extension/src/sidepanel/sidepanel.ts extension/src/sidepanel/sidepanel.css
git commit -m "feat: 8s display cooldown and 300ms fade transitions for hints

Previous hint stays visible for min 8 seconds before replacement.
Incoming hints during cooldown are queued. Smooth fade-out/fade-in
transition (300ms). Session start shows 'Слушаю разговор...'.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Simplify service worker hint buffer

**Files:**
- Modify: `extension/src/background/service-worker.ts:63-112` (bufferHint), `extension/src/background/service-worker.ts:291-296` (replay)

- [ ] **Step 1: Simplify bufferHint to store last hint_end only**

In `extension/src/background/service-worker.ts`, replace lines 63-112:

```typescript
// ── Hint buffer for panel reconnect ──────────────────────────────────────

let lastHintEnd: WsMessage | null = null;

function bufferHint(payload: WsMessage): void {
  if (payload.type === "hint_end") {
    lastHintEnd = payload;
  }
  // hint_start and hint_chunk are no longer sent by backend (silent generation)
}
```

- [ ] **Step 2: Update replay on reconnect**

In `extension/src/background/service-worker.ts`, replace lines 291-296:

```typescript
        // Replay last hint on panel reconnect
        if (lastHintEnd && captureInProgress) {
          port.postMessage({ type: "WS_MESSAGE", payload: lastHintEnd });
        }
```

- [ ] **Step 3: Update any references to old `hintBuffer` variable**

Search for other references to `hintBuffer` in the file and update them. If there's a clear on session end, update to clear `lastHintEnd` instead.

- [ ] **Step 4: TypeScript check and build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit && pnpm run build`

Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add extension/src/background/service-worker.ts
git commit -m "refactor: simplify SW hint buffer — store only last hint_end

Silent generation means only hint_end messages arrive. Buffer stores
single message instead of start/chunk/end sequence. Replay on panel
reconnect sends one message.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Integration Verification

### Task 8: Full integration test

**Files:**
- Run: all backend tests, extension build

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run pytest backend/tests/ -v`

Expected: ALL PASS

- [ ] **Step 2: Run linters on all changed files**

Run: `cd /Users/teterinsa/Projects/crmcore && uv run ruff check backend/pipeline/orchestrator.py backend/pipeline/llm.py`

Expected: No errors

- [ ] **Step 3: Full extension build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck && pnpm run build`

Expected: No errors, all outputs generated

- [ ] **Step 4: Manual verification checklist**

Reload extension in `chrome://extensions/` and verify:
- [ ] Phase 3 layout: hints panel at top, transcript at bottom
- [ ] Initial state shows "Слушаю разговор..."
- [ ] Hint appears with 300ms fade-in when hint_end arrives
- [ ] Hints persist for at least 8 seconds before replacement
- [ ] No "Анализирую..." loading state visible
- [ ] Panel reconnect shows last hint

---

## Progress Tracking

- [x] Task 1: Raise cooldown to 15s
- [x] Task 2: Silent generation
- [x] Task 3: Smart cancellation
- [x] Task 4: Generation timeout
- [x] Task 5: Layout flip
- [x] Task 6: Display cooldown & fade
- [x] Task 7: SW buffer simplification
- [x] Task 8: Integration verification

**Total Tasks:** 8 | **Completed:** 8 | **Remaining:** 0

Status: VERIFIED
