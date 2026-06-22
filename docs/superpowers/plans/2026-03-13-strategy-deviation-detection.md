# Strategy Deviation Detection — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Detect when sales rep goes off-strategy (talks about unrelated topics) and surface red warning hints to redirect them back.

**Architecture:** SGR Cascade (Schema-Guided Reasoning) — force the LLM to reason about relevance BEFORE generating the hint by ordering JSON fields: `reasoning` → `relevance` → `hint`. Add explicit topic perimeter ("ТЕМА РАЗГОВОРА") as the first section in the briefing, giving the LLM a clear boundary for comparison. Priority-ordered rules in the system prompt ensure deviation detection is checked first.

**Tech Stack:** Python (backend pipeline), TypeScript (Chrome extension frontend)

---

## What's Already Done

The following changes have been made but NOT yet committed:

### Backend (tests passing — 41/41):

1. **`backend/pipeline/prompt_formatter.py`** — Added `_add_topic_perimeter()` that generates `## ТЕМА РАЗГОВОРА` section as the FIRST section in the briefing. Extracts topic boundary from `strategy.approach`, `strategy.key_messages`, `portrait.pain_points`.

2. **`backend/pipeline/llm.py`** — Changes:
   - `HintResponse`: Added `relevance: str = "on_topic"` and `reasoning: str = ""` fields.
   - `_SYSTEM_PROMPT_REP`: Rewritten with priority-ordered rules (ОТКЛОНЕНИЕ → ОШИБКА → ХОРОШО → НЕЙТРАЛЬНО) and SGR cascade JSON format.
   - `_SYSTEM_PROMPT_CLIENT`: Updated with relevance detection + SGR cascade.
   - `_USER_TEMPLATE`: Updated with SGR cascade fields (`reasoning`, `relevance` before `hint`).

3. **`backend/pipeline/orchestrator.py`** — Added `relevance` field to `hint_end` WebSocket message.

4. **`backend/tests/test_llm.py`** — Added tests: `test_hint_response_off_topic`, `test_rep_prompt_has_deviation_detection`, `test_user_template_has_sgr_cascade`. Updated existing tests for new fields.

5. **`backend/tests/test_prompt_formatter.py`** — Added tests: `test_format_scenario_includes_topic_perimeter`, `test_format_scenario_no_perimeter_without_data`.

### Known Limitation (out of scope for this plan):

The 15-second hint cooldown (`_HINT_COOLDOWN_S`) applies uniformly — off-topic warnings during cooldown are suppressed. A future improvement could use a shorter cooldown (e.g. 5s) for off-topic hints. This requires refactoring `_run_pipeline` to do a two-pass approach (generate first, then check cooldown based on relevance), which is a separate task.

---

## Chunk 1: Fix Review Issues + Commit Backend

### Task 1: Add relevance validation in HintResponse

**Review issue:** `relevance` accepts any string from LLM — could be `"off-topic"` (hyphen), Russian text, etc. Frontend CSS `[data-relevance="off_topic"]` silently fails on variants.

**Files:**
- Modify: `backend/pipeline/llm.py:36-55` (HintResponse.from_json)
- Modify: `backend/tests/test_llm.py`

- [ ] **Step 1: Write failing test for invalid relevance validation**

Add to `backend/tests/test_llm.py`:

```python
def test_hint_response_invalid_relevance_defaults_to_on_topic() -> None:
    """Invalid relevance values fall back to on_topic."""
    from backend.pipeline.llm import HintResponse

    for bad_value in ["off-topic", "ОТКЛОНЕНИЕ", "", "partially_relevant"]:
        raw = (
            '{"hint": "tip", "source": "", '
            f'"sentiment": "neutral", "color": "blue", "relevance": "{bad_value}"}}'
        )
        resp = HintResponse.from_json(raw)
        assert resp.relevance == "on_topic", f"'{bad_value}' should fall back to on_topic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest backend/tests/test_llm.py::test_hint_response_invalid_relevance_defaults_to_on_topic -v`
Expected: FAIL (no validation yet)

- [ ] **Step 3: Add validation in from_json**

In `backend/pipeline/llm.py`, in `HintResponse.from_json`, replace:
```python
relevance=data.get("relevance", "on_topic"),
```
with:
```python
relevance=data.get("relevance", "on_topic") if data.get("relevance") in ("on_topic", "off_topic") else "on_topic",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest backend/tests/test_llm.py::test_hint_response_invalid_relevance_defaults_to_on_topic -v`
Expected: PASS

### Task 2: Enforce color=red when relevance=off_topic

**Review issue:** LLM may return inconsistent values (e.g. `relevance="off_topic"` + `color="green"`). Server-side enforcement ensures off-topic always shows red.

**Files:**
- Modify: `backend/pipeline/llm.py:36-55` (HintResponse.from_json)
- Modify: `backend/tests/test_llm.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_llm.py`:

```python
def test_hint_response_off_topic_forces_red_color() -> None:
    """Off-topic relevance must enforce color=red regardless of LLM output."""
    from backend.pipeline.llm import HintResponse

    raw = (
        '{"reasoning": "off topic", "relevance": "off_topic", '
        '"hint": "tip", "source": "", '
        '"sentiment": "neutral", "color": "green"}'
    )
    resp = HintResponse.from_json(raw)
    assert resp.color == "red", "off_topic must force color=red"
```

- [ ] **Step 2: Run test — should FAIL**

Run: `uv run pytest backend/tests/test_llm.py::test_hint_response_off_topic_forces_red_color -v`
Expected: FAIL

- [ ] **Step 3: Implement enforcement**

In `HintResponse.from_json`, after creating the instance, add enforcement:

```python
        hint = cls(
            hint=data["hint"],
            ...
        )
        # Enforce: off_topic always uses red
        if hint.relevance == "off_topic":
            hint.color = "red"
        return hint
```

- [ ] **Step 4: Run test — should PASS**

Run: `uv run pytest backend/tests/test_llm.py -v`
Expected: All pass

### Task 3: Commit all backend changes

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest backend/tests/test_llm.py backend/tests/test_prompt_formatter.py backend/tests/test_pipeline.py -v`
Expected: All pass

- [ ] **Step 2: Commit**

```bash
git add backend/pipeline/prompt_formatter.py backend/pipeline/llm.py backend/pipeline/orchestrator.py backend/tests/test_llm.py backend/tests/test_prompt_formatter.py
git commit -m "feat(hints): add strategy deviation detection with SGR cascade

- Add ТЕМА РАЗГОВОРА topic perimeter section to briefing (first position)
- Rewrite _SYSTEM_PROMPT_REP with priority rules (deviation checked first)
- Add reasoning/relevance fields to HintResponse (SGR cascade pattern)
- Validate relevance values, enforce color=red for off_topic
- Update _USER_TEMPLATE with cascade JSON (reasoning → relevance → hint)
- Forward relevance field in hint_end WebSocket message
- Add tests for off-topic detection, validation, deviation rules"
```

---

## Chunk 2: Frontend Type Update + Visual Indicator

### Task 4: Update frontend TypeScript types for `relevance`

`WsHintEnd` extends `HintPayload` in `messages.ts` — adding `relevance` to `HintPayload` automatically flows through to `WsHintEnd`. No changes to `messages.ts` needed.

**Files:**
- Modify: `extension/src/shared/types.ts:1-8` (HintPayload interface)

- [ ] **Step 1: Add `relevance` to HintPayload interface**

```typescript
/** Structured hint from LLM. */
export interface HintPayload {
  hint: string;
  source: string;
  sentiment: "positive" | "neutral" | "negative";
  color: "green" | "blue" | "red";
  coaching?: string;
  relevance?: "on_topic" | "off_topic";
}
```

`relevance` is optional for backward compatibility.

- [ ] **Step 2: Verify TypeScript compiles and `msg.relevance` is accessible in renderHint**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

### Task 5: Add visual distinction for off-topic hints

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts` (renderHint function, ~line 736)
- Modify: `extension/src/sidepanel/sidepanel.css` (hints-panel styles, ~line 590)

- [ ] **Step 1: Add `data-relevance` attribute in renderHint()**

In `renderHint()` in `sidepanel.ts`, after the line `panel.setAttribute("data-color", msg.color || "orange");`:

```typescript
    panel.setAttribute("data-relevance", msg.relevance || "on_topic");
```

- [ ] **Step 2: Add CSS for off-topic visual indicator**

In `sidepanel.css`, after the existing `.hints-panel[data-color="gray"]` rule:

```css
/* Off-topic deviation warning */
.hints-panel[data-relevance="off_topic"] {
  background: rgba(239, 68, 68, 0.08);
  border-bottom-width: 3px;
  animation: pulse-warn 1.5s ease-in-out 2;
}

@keyframes pulse-warn {
  0%, 100% { background: rgba(239, 68, 68, 0.08); }
  50% { background: rgba(239, 68, 68, 0.15); }
}
```

- [ ] **Step 3: Build extension**

Run: `cd extension && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add extension/src/shared/types.ts extension/src/sidepanel/sidepanel.ts extension/src/sidepanel/sidepanel.css
git commit -m "feat(ui): add relevance type and visual warning for off-topic hints"
```

---

## Chunk 3: Integration Test

### Task 6: Add integration test for off-topic hint_end message

**Files:**
- Modify: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write integration test**

Add to `backend/tests/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_hint_end_includes_relevance_field(
    mock_session_manager: AsyncMock,
) -> None:
    """hint_end WebSocket message must include relevance field from LLM response."""
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.stt import Transcript

    async def off_topic_stream(ctx):
        yield (
            '{"reasoning": "менеджер говорит про погоду, не про CRM", '
            '"relevance": "off_topic", '
            '"hint": "Вернитесь к теме CRM", '
            '"source": "", "sentiment": "negative", "color": "red", '
            '"coaching": ""}'
        )

    llm = MagicMock()
    llm._cancel_current = MagicMock()
    llm.generate_hint_stream = off_topic_stream

    ws_messages: list[dict] = []

    async def capture_send(msg: dict) -> None:
        ws_messages.append(msg)

    ws = AsyncMock()
    ws.send_json = capture_send

    orch = PipelineOrchestrator(
        ws=ws,
        session_id="s-offtopic",
        llm_client=llm,
        session_manager=mock_session_manager,
        scenario_text='{"strategy": {"approach": "CRM продажа"}}',
    )

    t = Transcript(speaker="rep", text="А вот сегодня погода хорошая", is_final=True)
    await orch.handle_transcript(t)

    hint_msgs = [m for m in ws_messages if m.get("type") == "hint_end"]
    assert len(hint_msgs) == 1
    assert hint_msgs[0]["relevance"] == "off_topic"
    assert hint_msgs[0]["color"] == "red"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest backend/tests/test_pipeline.py::test_hint_end_includes_relevance_field -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_pipeline.py
git commit -m "test(pipeline): add integration test for relevance field in hint_end"
```

---

## Progress Tracking

- [x] Task 1: Add relevance validation in HintResponse
- [x] Task 2: Enforce color=red when relevance=off_topic
- [x] Task 3: Commit all backend changes
- [x] Task 4: Update frontend TypeScript types for relevance
- [x] Task 5: Add visual distinction for off-topic hints
- [x] Task 6: Add integration test for off-topic hint_end message

**Total Tasks:** 6 | **Completed:** 6 | **Remaining:** 0
