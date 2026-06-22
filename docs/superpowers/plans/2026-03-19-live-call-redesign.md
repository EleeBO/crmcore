# FEAT-013: Live Call Panel Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract Phase 3 (live call) from the `sidepanel.ts` monolith into Preact components with Preact Signals, replace backend hint dataclass with Pydantic SGR schema, add backend-side talk ratio tracking.

**Architecture:** Strangler Fig pattern — `sidepanel.ts` keeps phase routing and WebSocket dispatch, delegates Phase 3 rendering to a new `live-call/` Preact component tree driven by signals. Backend adds `HintResponseV2` Pydantic schema and `TalkRatioTracker` module. WS contract adds `hint_end` v2 and `talk_ratio` messages.

**Tech Stack:** Preact 10 + @preact/signals, Pydantic 2, TypeScript strict, Python 3.11, Vite, pnpm

**Spec:** `docs/superpowers/specs/2026-03-19-live-call-redesign-design.md`

---

## File Structure

### New files (Frontend)

| File | Responsibility |
|------|---------------|
| `extension/src/sidepanel/live-call/types.ts` | TypeScript contracts: AIHint, TalkRatio, TranscriptItem, WaveSegment, RecordingState, ContextTab |
| `extension/src/sidepanel/live-call/store.ts` | Preact Signals: transcriptSignal, hintSignal, talkRatioSignal, recordingSignal, etc. |
| `extension/src/sidepanel/live-call/mount.ts` | Mount/unmount bridge: mountLiveCall(), unmountLiveCall() |
| `extension/src/sidepanel/live-call/LiveCallPanel.tsx` | Root component — reads signals, renders children |
| `extension/src/sidepanel/live-call/RecordingBar.tsx` | СТОП button, mic visualizer, timer |
| `extension/src/sidepanel/live-call/ConnectionStatus.tsx` | WS + STT green/red dots |
| `extension/src/sidepanel/live-call/AIHintCard.tsx` | coaching/success/warning/null hint card |
| `extension/src/sidepanel/live-call/TalkRatioBar.tsx` | Progress bar + waveform + text hint |
| `extension/src/sidepanel/live-call/ContextTabs.tsx` | Horizontal pill tabs |
| `extension/src/sidepanel/live-call/TranscriptFeed.tsx` | Scrollable message list with LIVE badge |
| `extension/src/sidepanel/live-call/TranscriptMessage.tsx` | Single speaker message |
| `extension/src/sidepanel/live-call/live-call.css` | All component styles |
| `extension/src/sidepanel/live-call/hooks/useAutoScroll.ts` | Sticky-to-bottom logic |
| `extension/src/sidepanel/live-call/hooks/useHintCooldown.ts` | 8s min display + success auto-dismiss |
| `extension/src/sidepanel/live-call/__tests__/AIHintCard.test.tsx` | AIHintCard unit tests |
| `extension/src/sidepanel/live-call/__tests__/TalkRatioBar.test.tsx` | TalkRatioBar unit tests |
| `extension/src/sidepanel/live-call/__tests__/TranscriptFeed.test.tsx` | TranscriptFeed unit tests |
| `extension/src/sidepanel/live-call/__tests__/useHintCooldown.test.ts` | Hook unit tests |

### New files (Backend)

| File | Responsibility |
|------|---------------|
| `backend/pipeline/schemas.py` | `HintResponseV2` Pydantic SGR schema |
| `backend/pipeline/talk_ratio.py` | `TalkRatioTracker` + `WaveSegment` model |
| `backend/tests/test_schemas.py` | Schema validation tests |
| `backend/tests/test_talk_ratio.py` | TalkRatioTracker unit tests |

### Modified files

| File | What changes |
|------|-------------|
| `extension/package.json` | Add `@preact/signals` dependency |
| `extension/src/shared/messages.ts` | Replace WsHintStart/Chunk/End with WsHintEndV2 + WsTalkRatio, update WsMessage union, remove ExtMessage.HINT |
| `extension/src/sidepanel/sidepanel.html` | Replace Phase 3 section with single `<div id="live-call-root">` mount point + keep `#briefing-collapsed` |
| `extension/src/sidepanel/sidepanel.ts` | Delete ~400 lines (hint/transcript/splitter), add signal imports + mount bridge + WS handlers |
| `backend/pipeline/llm.py` | Update system prompts to v2 JSON format (hint_type/headline/detail), update `_generate_fallback()` |
| `backend/pipeline/orchestrator.py` | Use `HintResponseV2.model_validate_json()`, create `TalkRatioTracker`, send `talk_ratio` + v2 `hint_end` |

---

## Progress Tracking

- [x] Task 1: Backend SGR schema (`HintResponseV2`)
- [x] Task 2: Backend TalkRatioTracker
- [x] Task 3: Backend orchestrator + LLM integration
- [x] Task 4: Install @preact/signals + Vitest + update WS types (transitional)
- [x] Task 5: Frontend types + signals store
- [x] Task 6: Mount bridge + LiveCallPanel root
- [x] Task 7: AIHintCard + useHintCooldown hook
- [x] Task 8: TalkRatioBar component
- [x] Task 9: TranscriptFeed + TranscriptMessage + useAutoScroll
- [x] Task 10: RecordingBar + ConnectionStatus + ContextTabs
- [x] Task 11: CSS (live-call.css)
- [x] Task 12: HTML + sidepanel.ts integration (strangler fig wiring)
- [x] Task 13: Cleanup deleted code from sidepanel.ts

**Status: COMPLETE**

**Total Tasks:** 13 | **Completed:** 13 | **Remaining:** 0

---

### Task 1: Backend SGR Schema (`HintResponseV2`)

**Files:**
- Create: `backend/pipeline/schemas.py`
- Test: `backend/tests/test_schemas.py`

**Context:** This replaces the old `HintResponse` dataclass with a Pydantic model. The field order matters for SGR — `reasoning` before `hint_type` warms up the model's context window. See spec §Backend Changes → SGR Schema.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_schemas.py
"""Tests for HintResponseV2 Pydantic schema."""

import pytest
from pydantic import ValidationError


def test_valid_coaching_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Client raised price objection, emotional tension high",
        hint_type="coaching",
        headline="Покажите ROI за 3 месяца",
        detail="Клиент считает цену высокой — переведите в стоимость простоя",
        coaching="Замедлитесь, покажите эмпатию",
        source="Brief, p.3",
    )
    assert hint.hint_type == "coaching"
    assert len(hint.headline) <= 80


def test_valid_success_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Rep handled LAER correctly",
        hint_type="success",
        headline="Отлично отработали возражение",
        detail="",
        coaching="",
        source="",
    )
    assert hint.hint_type == "success"


def test_valid_warning_hint() -> None:
    from backend.pipeline.schemas import HintResponseV2

    hint = HintResponseV2(
        reasoning="Client losing interest, short answers",
        hint_type="warning",
        headline="Клиент теряет интерес",
        detail="Задайте открытый вопрос о боли",
    )
    assert hint.hint_type == "warning"


def test_invalid_hint_type_rejected() -> None:
    from backend.pipeline.schemas import HintResponseV2

    with pytest.raises(ValidationError):
        HintResponseV2(
            reasoning="test",
            hint_type="positive",  # invalid — not in Literal
            headline="test",
        )


def test_headline_max_length_enforced() -> None:
    from backend.pipeline.schemas import HintResponseV2

    with pytest.raises(ValidationError):
        HintResponseV2(
            reasoning="test",
            hint_type="coaching",
            headline="x" * 81,  # over 80 char limit
        )


def test_from_json_round_trip() -> None:
    from backend.pipeline.schemas import HintResponseV2

    raw = (
        '{"reasoning": "test reason", "hint_type": "coaching", '
        '"headline": "Do this", "detail": "because", '
        '"coaching": "slow down", "source": "brief"}'
    )
    hint = HintResponseV2.model_validate_json(raw)
    assert hint.hint_type == "coaching"
    assert hint.headline == "Do this"
    assert hint.coaching == "slow down"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.schemas'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/pipeline/schemas.py
"""SGR schemas for structured LLM output.

Field order is intentional: reasoning before hint_type
warms up model context for better classification (SGR pattern).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class HintResponseV2(BaseModel):
    """SGR schema for real-time coaching hints.

    Replaces the old HintResponse dataclass. Uses Pydantic for
    constrained decoding — the model physically cannot return
    invalid hint_type or oversized headline.
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
        description="Main coaching text, ≤80 chars, readable in 1 second",
    )
    detail: str = Field(
        default="",
        max_length=150,
        description="Supporting context or explanation",
    )
    coaching: str = Field(
        default="",
        description="Tone/tempo advice: 'slow down', 'show empathy', etc.",
    )
    source: str = Field(
        default="",
        description="Knowledge base reference, e.g. 'Brief, p.3'",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_schemas.py -v`
Expected: 6 passed

- [ ] **Step 5: Run ruff + mypy**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m ruff check backend/pipeline/schemas.py && python -m mypy backend/pipeline/schemas.py --ignore-missing-imports`
Expected: Clean

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/schemas.py backend/tests/test_schemas.py
git commit -m "feat(backend): add HintResponseV2 Pydantic SGR schema (FEAT-013)"
```

---

### Task 2: Backend TalkRatioTracker

**Files:**
- Create: `backend/pipeline/talk_ratio.py`
- Test: `backend/tests/test_talk_ratio.py`

**Context:** Moves talk ratio computation from frontend word-counting (sidepanel.ts:977-1001) to backend. Includes a ring buffer for waveform segments. See spec §Backend Changes → TalkRatioTracker.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_talk_ratio.py
"""Tests for TalkRatioTracker."""

import pytest


def test_initial_state_is_zero() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    state = tracker.get_state()
    assert state["managerPercent"] == 0
    assert state["clientPercent"] == 0
    assert state["waveform"] == []


def test_single_manager_utterance() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "hello world how are you", is_final=True)
    state = tracker.get_state()
    assert state["managerPercent"] == 100
    assert state["clientPercent"] == 0
    assert len(state["waveform"]) == 1
    assert state["waveform"][0]["speaker"] == "manager"


def test_balanced_conversation() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "one two three", is_final=True)
    tracker.on_utterance("client", "four five six", is_final=True)
    state = tracker.get_state()
    assert state["managerPercent"] == 50
    assert state["clientPercent"] == 50


def test_interim_utterances_ignored_for_waveform() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "interim text", is_final=False)
    state = tracker.get_state()
    assert state["waveform"] == []


def test_waveform_ring_buffer_caps_at_60() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    for i in range(70):
        speaker = "rep" if i % 2 == 0 else "client"
        tracker.on_utterance(speaker, f"word{i} extra", is_final=True)
    state = tracker.get_state()
    assert len(state["waveform"]) == 60


def test_amplitude_caps_at_1() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    # 40 words > NORMALIZATION_MAX of 30 → amplitude capped at 1.0
    long_text = " ".join(f"word{i}" for i in range(40))
    tracker.on_utterance("rep", long_text, is_final=True)
    state = tracker.get_state()
    assert state["waveform"][0]["amplitude"] == 1.0


def test_wave_segment_is_pydantic_model() -> None:
    from backend.pipeline.talk_ratio import WaveSegment

    seg = WaveSegment(speaker="manager", amplitude=0.5)
    assert seg.model_dump() == {"speaker": "manager", "amplitude": 0.5}


def test_wave_segment_rejects_invalid_speaker() -> None:
    from pydantic import ValidationError
    from backend.pipeline.talk_ratio import WaveSegment

    with pytest.raises(ValidationError):
        WaveSegment(speaker="unknown", amplitude=0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_talk_ratio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.talk_ratio'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/pipeline/talk_ratio.py
"""Real-time talk ratio tracker with waveform ring buffer.

Replaces frontend word-counting (sidepanel.ts updateTalkRatio).
Sends data via WS for TalkRatioBar visualization.
"""

from __future__ import annotations

from collections import deque
from typing import Literal

from pydantic import BaseModel, Field


class WaveSegment(BaseModel):
    """Single waveform bar in the visualization."""

    speaker: Literal["manager", "client"]
    amplitude: float = Field(ge=0.0, le=1.0)


class TalkRatioTracker:
    """Tracks speaking balance and builds waveform ring buffer."""

    BUFFER_SIZE: int = 60
    NORMALIZATION_MAX: int = 30  # fixed max words for amplitude

    def __init__(self) -> None:
        self._manager_words: int = 0
        self._client_words: int = 0
        self._waveform: deque[WaveSegment] = deque(maxlen=self.BUFFER_SIZE)

    def on_utterance(self, speaker: str, text: str, *, is_final: bool) -> None:
        """Update word counts and waveform on final utterances only.

        Interim utterances are ignored entirely — STT sends expanding
        partial text (3 → 7 → 10 words) for the same utterance, so
        counting interims would double/triple the real word count.
        """
        if not is_final:
            return

        word_count = len(text.split())
        mapped_speaker: Literal["manager", "client"] = (
            "manager" if speaker == "rep" else "client"
        )

        if mapped_speaker == "manager":
            self._manager_words += word_count
        else:
            self._client_words += word_count

        amplitude = min(word_count / self.NORMALIZATION_MAX, 1.0)
        self._waveform.append(
            WaveSegment(speaker=mapped_speaker, amplitude=amplitude)
        )

    def get_state(self) -> dict:
        """Return serializable state for WS message."""
        total = self._manager_words + self._client_words
        if total == 0:
            return {
                "managerPercent": 0,
                "clientPercent": 0,
                "waveform": [],
            }
        manager_pct = round(self._manager_words / total * 100)
        return {
            "managerPercent": manager_pct,
            "clientPercent": 100 - manager_pct,
            "waveform": [seg.model_dump() for seg in self._waveform],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_talk_ratio.py -v`
Expected: 8 passed

- [ ] **Step 5: Run ruff + mypy**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m ruff check backend/pipeline/talk_ratio.py && python -m mypy backend/pipeline/talk_ratio.py --ignore-missing-imports`

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/talk_ratio.py backend/tests/test_talk_ratio.py
git commit -m "feat(backend): add TalkRatioTracker with waveform ring buffer (FEAT-013)"
```

---

### Task 3: Backend Orchestrator + LLM Integration

**Files:**
- Modify: `backend/pipeline/orchestrator.py:226-256` (`_collect_and_send_hint`)
- Modify: `backend/pipeline/llm.py:16-96` (system prompts), `195-206` (`_generate_fallback`)
- Test: `backend/tests/test_llm.py` (update existing), `backend/tests/test_schemas.py` (add integration test)

**Context:** Wire `HintResponseV2` into the orchestrator and update LLM prompts. The orchestrator sends `hint_end` v2 format + new `talk_ratio` messages. System prompts switch from `sentiment/color/hint` to `hint_type/headline/detail`. See spec §Backend Changes → Orchestrator Changes and §LLM Prompt Changes.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_schemas.py`:

```python
def test_v2_hint_from_llm_json_format() -> None:
    """Simulate LLM output in new prompt format."""
    from backend.pipeline.schemas import HintResponseV2

    llm_output = (
        '{"reasoning": "Клиент упомянул бюджет — скрытое возражение по цене", '
        '"hint_type": "coaching", '
        '"headline": "Переведите в стоимость простоя", '
        '"detail": "Спросите: сколько теряете в день без решения?", '
        '"coaching": "замедлитесь", '
        '"source": "Brief, p.2"}'
    )
    hint = HintResponseV2.model_validate_json(llm_output)
    assert hint.hint_type == "coaching"
    assert hint.headline == "Переведите в стоимость простоя"


def test_v2_fallback_hint() -> None:
    """Fallback hint must be valid HintResponseV2."""
    from backend.pipeline.schemas import HintResponseV2

    fallback = HintResponseV2(
        reasoning="Fallback: primary LLM timed out",
        hint_type="coaching",
        headline="Уточните детали у клиента",
        detail="",
        coaching="",
        source="fallback",
    )
    assert fallback.hint_type == "coaching"
```

- [ ] **Step 2: Run tests to verify they pass** (these should pass since schema exists from Task 1)

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_schemas.py -v`

- [ ] **Step 3: Update LLM system prompts**

In `backend/pipeline/llm.py`, replace both `_SYSTEM_PROMPT_CLIENT` (lines 16-52) and `_SYSTEM_PROMPT_REP` (lines 54-96) JSON format instructions.

Old format tail (both prompts):
```
"Формат JSON (поля строго в указанном порядке — сначала думай):\n"
'{"reasoning": "...", "relevance": "on_topic|off_topic", '
'"hint": "...", "source": "...", '
'"sentiment": "positive|neutral|negative", '
'"color": "green|blue|red", "coaching": "..."}\n'
"Отвечай ТОЛЬКО валидным JSON."
```

New format tail (both prompts):
```
"Формат JSON (поля строго в указанном порядке — сначала думай):\n"
'{"reasoning": "1 предложение: суть реплики + эмоция", '
'"hint_type": "coaching|success|warning", '
'"headline": "главная подсказка, ≤80 символов", '
'"detail": "контекст или объяснение, ≤150 символов", '
'"coaching": "совет по тону/темпу", '
'"source": "файл, стр."}\n'
"Отвечай ТОЛЬКО валидным JSON."
```

Also update the decision rules in `_SYSTEM_PROMPT_CLIENT` to use `hint_type` instead of `color/sentiment`:
- `→ relevance=off_topic, color=red` becomes `→ hint_type="warning"`
- `color=green` (positive/good) becomes `→ hint_type="success"`
- `color=blue` (neutral/tip) becomes `→ hint_type="coaching"`

Same mapping for `_SYSTEM_PROMPT_REP`:
- `color=red` (error/off-track) → `hint_type="warning"`
- `color=green` (good) → `hint_type="success"`
- `color=blue` (missed opportunity, neutral) → `hint_type="coaching"`

Remove `relevance` and `sentiment` from both prompts entirely.

**CRITICAL: Also update `_USER_TEMPLATE`** (lines 101-112). The user-turn template is a stronger signal to the LLM than the system prompt. Replace the JSON scaffold:

Old (lines 107-112):
```python
'"relevance": "on_topic|off_topic", '
'"hint": "краткая подсказка", "source": "файл, стр.", '
'"sentiment": "positive|neutral|negative", "color": "green|blue|red", '
'"coaching": "совет по тону (опционально)"}}'
```

New:
```python
'"hint_type": "coaching|success|warning", '
'"headline": "главная подсказка ≤80 символов", '
'"detail": "контекст ≤150 символов", '
'"coaching": "совет по тону (опционально)", '
'"source": "файл, стр."}}'
```

- [ ] **Step 4: Update `_generate_fallback()`**

In `backend/pipeline/llm.py:195-206`, change return type and body:

```python
async def _generate_fallback(self, ctx: HintContext) -> HintResponseV2:
    """Generate a fallback hint (overrideable in tests)."""
    from backend.pipeline.schemas import HintResponseV2

    logger.warning(
        "Primary LLM timed out, using fallback: %s", self._fallback_model
    )
    _ = ctx
    return HintResponseV2(
        reasoning="Fallback: primary LLM timed out",
        hint_type="coaching",
        headline="Уточните детали у клиента",
        detail="",
        coaching="",
        source="fallback",
    )
```

Also update `generate_hint()` (line 208) return type and `_collect()` to use `HintResponseV2.model_validate_json()`.

- [ ] **Step 5: Update orchestrator `_collect_and_send_hint()`**

In `backend/pipeline/orchestrator.py:226-256`:

```python
async def _collect_and_send_hint(self, ctx: HintContext) -> None:
    """Collect all LLM tokens and send a single hint_end v2."""
    from backend.pipeline.schemas import HintResponseV2

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
        resp = HintResponseV2.model_validate_json(full_json)
        await self._ws.send_json(
            {
                "type": "hint_end",
                "v": 2,
                "hint_type": resp.hint_type,
                "headline": resp.headline,
                "detail": resp.detail,
                "coaching": resp.coaching,
                "source": resp.source,
            }
        )
    except Exception as exc:
        logger.warning("Failed to parse/send hint_end v2: %r", exc)
```

- [ ] **Step 6: Add TalkRatioTracker to orchestrator**

In `backend/pipeline/orchestrator.py`, add to `__init__`:
```python
from backend.pipeline.talk_ratio import TalkRatioTracker
self._talk_ratio = TalkRatioTracker()
```

In `handle_transcript()` (the method that processes STT results), after forwarding transcript to WS, add:
```python
self._talk_ratio.on_utterance(transcript.speaker, transcript.text, is_final=transcript.is_final)
if transcript.is_final:
    await self._ws.send_json({"type": "talk_ratio", **self._talk_ratio.get_state()})
```

- [ ] **Step 7: Update existing `test_llm.py` tests**

The following tests in `backend/tests/test_llm.py` will break and need updating:
- `test_rep_prompt_has_deviation_detection` (asserts `"relevance" in _SYSTEM_PROMPT_REP`) → change to assert `"hint_type" in _SYSTEM_PROMPT_REP`
- `test_user_template_has_sgr_cascade` (asserts `"relevance" in _USER_TEMPLATE`) → change to assert `"hint_type" in _USER_TEMPLATE`
- `test_fallback_triggers_on_primary_ttft_timeout` (returns `HintResponse`) → update to expect `HintResponseV2` from `_generate_fallback()`

Tests that use `HintResponse` directly (like `test_hint_response_parsing`, `test_hint_response_off_topic_forces_red_color`) can remain unchanged — `HintResponse` is deprecated but kept.

Also update `generate_hint()` return type to `HintResponseV2` and `_collect()` to use `HintResponseV2.model_validate_json()`.

- [ ] **Step 8: Run all backend tests**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/ -v`
Expected: All pass

- [ ] **Step 8: Run ruff + mypy on changed files**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m ruff check backend/pipeline/orchestrator.py backend/pipeline/llm.py && python -m mypy backend/pipeline/orchestrator.py backend/pipeline/llm.py --ignore-missing-imports`

- [ ] **Step 9: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/pipeline/llm.py backend/tests/test_schemas.py
git commit -m "feat(backend): integrate HintResponseV2 + TalkRatioTracker into pipeline (FEAT-013)"
```

---

### Task 4: Install @preact/signals + Vitest + Update WS Types (transitional)

**Files:**
- Modify: `extension/package.json` (add dependencies)
- Modify: `extension/src/shared/messages.ts` (ADD v2 types alongside old ones, update union)
- Modify: `extension/src/shared/types.ts` (deprecate HintPayload)

**Context:** Foundation task — installs signals + test runner, adds v2 WS types. **IMPORTANT: Keep old `WsHintEnd` type in the union during Tasks 5–11 so sidepanel.ts compiles. Task 12 atomically removes old types.** No `@ts-expect-error` anywhere.

- [ ] **Step 1: Install @preact/signals + Vitest**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm add @preact/signals && pnpm add -D vitest @testing-library/preact jsdom`

Add to `extension/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

Create `extension/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

- [ ] **Step 2: Update `shared/messages.ts`**

**ADD** v2 types alongside old ones (transitional). Keep `WsHintStart`, `WsHintChunk`, `WsHintEnd` in the union for now:

```typescript
// extension/src/shared/messages.ts
// ADD new types, KEEP old types during transition (Tasks 5-11).
// Task 12 removes old types atomically.

import type { HintPayload } from "./types";
import type {
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
  CallEvaluationResult,
} from "./evaluation-types";

// ── WebSocket message types (backend → extension) ─────────────────────────

// OLD v1 types — kept for transitional compile, removed in Task 12
export interface WsHintStart { type: "hint_start"; sentiment: string; color: string; }
export interface WsHintChunk { type: "hint_chunk"; text: string; }
export interface WsHintEnd extends HintPayload { type: "hint_end"; }

// NEW v2 types
export interface WsHintEndV2 {
  type: "hint_end";
  v: 2;
  hint_type: "coaching" | "success" | "warning";
  headline: string;
  detail: string;
  coaching: string;
  source: string;
}

export interface WsTalkRatio {
  type: "talk_ratio";
  managerPercent: number;
  clientPercent: number;
  waveform: Array<{ speaker: "manager" | "client"; amplitude: number }>;
}

export interface WsTranscript {
  type: "transcript";
  speaker: "rep" | "client";
  text: string;
  is_final: boolean;
  utterance_id?: string;
}

export interface WsError {
  type: "error";
  code: string;
  message: string;
}

// Union includes BOTH old and new during transition
export type WsMessage =
  | WsHintStart | WsHintChunk | WsHintEnd  // removed in Task 12
  | WsHintEndV2
  | WsTalkRatio
  | WsTranscript
  | WsError
  | WsEvaluationStarted
  | WsEvaluationResult
  | WsEvaluationError;

// ExtMessage: keep HINT for now, remove in Task 12
export type ExtMessage =
  | { type: "PREPARE_CAPTURE"; sessionId: string; kbId: string; tabId: number }
  | { type: "START_SESSION"; sessionId: string; kbId: string; tabId: number; streamId: string; deviceId?: string; sttProvider?: string }
  | { type: "STOP_SESSION"; sessionId: string }
  | { type: "HINT"; hint: WsHintEnd }  // removed in Task 12
  | { type: "TRANSCRIPT"; transcript: WsTranscript }
  | { type: "AUDIO_LEVEL"; mic: number; tab: number }
  | { type: "GET_SESSION_STATE" }
  | { type: "SESSION_STATE"; capturing: boolean; sessionId: string; kbId: string; wsConnected: boolean }
  | { type: "SESSION_ABORTED"; reason: string }
  | { type: "WS_RECONNECTED" }
  | { type: "WS_STATUS"; connected: boolean }
  | { type: "CAPTURE_STARTED" }
  | { type: "CAPTURE_FAILED"; error: string }
  | { type: "EVALUATION_STARTED"; sessionId: string }
  | { type: "EVALUATION_RESULT"; sessionId: string; evalToken: string; evaluation: CallEvaluationResult }
  | { type: "EVALUATION_ERROR"; sessionId: string; code: string; message: string };
```

- [ ] **Step 3: Deprecate HintPayload in `shared/types.ts`**

Add deprecation comment at top:
```typescript
/** @deprecated Use WsHintEndV2 from messages.ts instead. Kept for service worker compat. */
export interface HintPayload { ... }
```

- [ ] **Step 4: Verify TypeScript compiles cleanly**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`
Expected: Clean — old types are kept, so `sidepanel.ts` and service worker compile without changes.

- [ ] **Step 5: Verify Vitest runs**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm test`
Expected: "No test files found" (will be populated in later tasks)

- [ ] **Step 6: Commit**

```bash
git add extension/package.json extension/pnpm-lock.yaml extension/vitest.config.ts extension/src/shared/messages.ts extension/src/shared/types.ts
git commit -m "feat(extension): add @preact/signals + Vitest, add v2 WS types (FEAT-013)"
```

---

### Task 5: Frontend Types + Signals Store

**Files:**
- Create: `extension/src/sidepanel/live-call/types.ts`
- Create: `extension/src/sidepanel/live-call/store.ts`

**Context:** These are the foundational files for the live-call module. Every component imports from these. See spec §Frontend Components → types.ts and store.ts.

- [ ] **Step 1: Create types.ts**

```typescript
// extension/src/sidepanel/live-call/types.ts

/** Mirrors backend HintResponseV2 SGR schema. */

export type HintType = "coaching" | "success" | "warning";

export interface AIHint {
  id: string;
  hintType: HintType;
  headline: string;
  detail: string;
  coaching: string;
  source: string;
  timestamp: number;
}

export interface WaveSegment {
  speaker: "manager" | "client";
  amplitude: number;
}

export interface TalkRatio {
  managerPercent: number;
  clientPercent: number;
  waveform: WaveSegment[];
}

export interface RecordingState {
  isRecording: boolean;
  elapsedSeconds: number;
  micLevel: number;
}

export type ContextTab = "hints" | "objections" | "briefing" | "strategy";

// ── Transcript ──

export interface TranscriptMessage {
  type: "message";
  id: string;
  speaker: "manager" | "client";
  text: string;
  timestamp: string;
  isInterim?: boolean;
}

export type TranscriptItem = TranscriptMessage;
// NOTE: TranscriptEvent is out of scope for MVP.
```

- [ ] **Step 2: Create store.ts**

```typescript
// extension/src/sidepanel/live-call/store.ts

import { signal } from "@preact/signals";
import type { AIHint, TalkRatio, TranscriptItem, ContextTab, RecordingState } from "./types";
import type { BriefData } from "../brief/types";

export const transcriptSignal = signal<TranscriptItem[]>([]);
export const hintSignal = signal<AIHint | null>(null);
export const talkRatioSignal = signal<TalkRatio>({
  managerPercent: 0, clientPercent: 100, waveform: [],
});
export const recordingSignal = signal<RecordingState>({
  isRecording: false, elapsedSeconds: 0, micLevel: 0,
});
export const activeTabSignal = signal<ContextTab>("hints");
export const wsConnectedSignal = signal<boolean>(false);
export const sttActiveSignal = signal<boolean>(true);
export const briefDataSignal = signal<BriefData | null>(null);
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`
Expected: Clean (these files have no side effects)

- [ ] **Step 4: Commit**

```bash
git add extension/src/sidepanel/live-call/types.ts extension/src/sidepanel/live-call/store.ts
git commit -m "feat(live-call): add types and Preact Signals store (FEAT-013)"
```

---

### Task 6: Mount Bridge + LiveCallPanel Root

**Files:**
- Create: `extension/src/sidepanel/live-call/mount.ts`
- Create: `extension/src/sidepanel/live-call/LiveCallPanel.tsx`

**Context:** The mount bridge is how `sidepanel.ts` interacts with the Preact tree. Same pattern as `brief/mount.ts`. LiveCallPanel is the root component that composes all children. See spec §mount.ts and §LiveCallPanel.tsx.

- [ ] **Step 1: Create mount.ts**

```typescript
// extension/src/sidepanel/live-call/mount.ts

import { render, h } from "preact";
import { LiveCallPanel } from "./LiveCallPanel";
import type { ContextTab } from "./types";
import "./live-call.css";

let mountedContainer: HTMLElement | null = null;

export interface LiveCallCallbacks {
  onStopRecording: () => void;
  onTabChange: (tab: ContextTab) => void;
  onBriefingTabActive: (active: boolean) => void;
}

export function mountLiveCall(
  container: HTMLElement,
  callbacks: LiveCallCallbacks,
): void {
  // Guard against double-mount (e.g., WS reconnect mid-call)
  if (mountedContainer) {
    render(null, mountedContainer);
    mountedContainer = null;
  }
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

- [ ] **Step 2: Create LiveCallPanel.tsx** (skeleton with placeholders)

```tsx
// extension/src/sidepanel/live-call/LiveCallPanel.tsx

import { h } from "preact";
import type { LiveCallCallbacks } from "./mount";
import { activeTabSignal } from "./store";

interface LiveCallPanelProps {
  callbacks: LiveCallCallbacks;
}

export function LiveCallPanel({ callbacks }: LiveCallPanelProps): h.JSX.Element {
  const activeTab = activeTabSignal.value;

  return (
    <div class="lc-panel">
      {/* RecordingBar — Task 10 */}
      {/* ConnectionStatus — Task 10 */}
      {/* AIHintCard — Task 7 */}
      {/* TalkRatioBar — Task 8 */}
      {/* ContextTabs — Task 10 */}
      {/* TranscriptFeed — Task 9 */}
      <div class="lc-placeholder">LiveCallPanel mounted (active tab: {activeTab})</div>
    </div>
  );
}
```

- [ ] **Step 3: Create empty CSS file**

```css
/* extension/src/sidepanel/live-call/live-call.css */
/* Styles will be added in Task 11 */
.lc-panel { display: flex; flex-direction: column; height: 100%; }
.lc-placeholder { padding: 16px; color: #9ca3af; text-align: center; }
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`

- [ ] **Step 5: Commit**

```bash
git add extension/src/sidepanel/live-call/mount.ts extension/src/sidepanel/live-call/LiveCallPanel.tsx extension/src/sidepanel/live-call/live-call.css
git commit -m "feat(live-call): add mount bridge and LiveCallPanel root (FEAT-013)"
```

---

### Task 7: AIHintCard + useHintCooldown Hook

**Files:**
- Create: `extension/src/sidepanel/live-call/AIHintCard.tsx`
- Create: `extension/src/sidepanel/live-call/hooks/useHintCooldown.ts`
- Test: `extension/src/sidepanel/live-call/__tests__/AIHintCard.test.tsx`
- Test: `extension/src/sidepanel/live-call/__tests__/useHintCooldown.test.ts`

**Context:** The most complex component. Four visual states (coaching/success/warning/null). The useHintCooldown hook enforces 8s minimum display + success auto-dismiss after 4s. See spec §AIHintCard and §useHintCooldown.

- [ ] **Step 1: Create useHintCooldown hook**

**IMPORTANT:** Uses `signal.subscribe()` pattern instead of `useEffect` to avoid dependency array issues. Tracks `lastCoachingHint` so success auto-dismiss reverts to last coaching, not null.

```typescript
// extension/src/sidepanel/live-call/hooks/useHintCooldown.ts

import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import type { Signal } from "@preact/signals";
import type { AIHint } from "../types";

const COOLDOWN_MS = 8_000;
const SUCCESS_DISMISS_MS = 4_000;

export function useHintCooldown(rawHint: Signal<AIHint | null>): AIHint | null {
  const displayed = useSignal<AIHint | null>(null);
  const lastSwapAt = useSignal<number>(0);
  const lastCoachingHint = useSignal<AIHint | null>(null);

  // Subscribe to rawHint changes (runs ONLY when rawHint changes, not on every render)
  useEffect(() => {
    let cooldownTimer: ReturnType<typeof setTimeout> | undefined;

    const unsubscribe = rawHint.subscribe((hint) => {
      if (!hint) {
        displayed.value = null;
        return;
      }

      // Track last coaching hint for success-dismiss revert
      if (hint.hintType === "coaching") {
        lastCoachingHint.value = hint;
      }

      const now = Date.now();
      const elapsed = now - lastSwapAt.value;

      if (elapsed >= COOLDOWN_MS || displayed.value === null) {
        displayed.value = hint;
        lastSwapAt.value = now;
        if (cooldownTimer) clearTimeout(cooldownTimer);
      } else {
        // Queue: show after remaining cooldown
        if (cooldownTimer) clearTimeout(cooldownTimer);
        const remaining = COOLDOWN_MS - elapsed;
        cooldownTimer = setTimeout(() => {
          displayed.value = hint;
          lastSwapAt.value = Date.now();
        }, remaining);
      }
    });

    return () => {
      unsubscribe();
      if (cooldownTimer) clearTimeout(cooldownTimer);
    };
  }, []); // empty deps: subscribe once

  // Auto-dismiss success after 4s → revert to last coaching hint
  useEffect(() => {
    const hint = displayed.value;
    if (hint?.hintType !== "success") return;

    const timer = setTimeout(() => {
      displayed.value = lastCoachingHint.value; // revert to last coaching, not null
    }, SUCCESS_DISMISS_MS);

    return () => clearTimeout(timer);
  }, [displayed.value]); // re-run only when displayed hint changes

  return displayed.value;
}
```

- [ ] **Step 2: Create AIHintCard.tsx**

```tsx
// extension/src/sidepanel/live-call/AIHintCard.tsx

import { h } from "preact";
import { hintSignal } from "./store";
import { useHintCooldown } from "./hooks/useHintCooldown";
import type { AIHint, HintType } from "./types";

const TYPE_CONFIG: Record<HintType, { bg: string; border: string; label: string; labelColor: string; headlineColor: string; detailColor: string }> = {
  coaching: { bg: "#FFF8F0", border: "#EF9F27", label: "ПОДСКАЗКА", labelColor: "#854F0B", headlineColor: "#633806", detailColor: "#854F0B" },
  success:  { bg: "#EAF3DE", border: "#639922", label: "",          labelColor: "",        headlineColor: "#27500A", detailColor: "#3B6D11" },
  warning:  { bg: "#FEF5F5", border: "#E24B4A", label: "ВНИМАНИЕ",  labelColor: "#791F1F", headlineColor: "#501313", detailColor: "#791F1F" },
};

function renderCheckIcon(): h.JSX.Element {
  return (
    <div class="lc-hint-check-icon">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M3 7L6 10L11 4" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
  );
}

export function AIHintCard(): h.JSX.Element {
  const hint = useHintCooldown(hintSignal);

  if (!hint) {
    return (
      <div class="lc-hint-card lc-hint-null">
        <div class="lc-hint-null-text">Слушаю разговор...</div>
        <div class="lc-hint-null-sub">Подсказки появятся автоматически</div>
      </div>
    );
  }

  const cfg = TYPE_CONFIG[hint.hintType];

  return (
    <div
      class="lc-hint-card"
      style={{ background: cfg.bg, borderLeft: `3px solid ${cfg.border}` }}
    >
      {hint.hintType === "success" ? (
        <div class="lc-hint-success-row">
          {renderCheckIcon()}
          <div>
            <div class="lc-hint-headline" style={{ color: cfg.headlineColor }}>{hint.headline}</div>
            {hint.detail && <div class="lc-hint-detail" style={{ color: cfg.detailColor }}>{hint.detail}</div>}
          </div>
        </div>
      ) : (
        <>
          {cfg.label && (
            <div class="lc-hint-label" style={{ color: cfg.labelColor }}>{cfg.label}</div>
          )}
          <div class="lc-hint-headline" style={{ color: cfg.headlineColor }}>{hint.headline}</div>
          {hint.detail && <div class="lc-hint-detail" style={{ color: cfg.detailColor }}>{hint.detail}</div>}
          {hint.coaching && (
            <div class="lc-hint-coaching">{hint.coaching}</div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`

- [ ] **Step 4: Commit**

```bash
git add extension/src/sidepanel/live-call/AIHintCard.tsx extension/src/sidepanel/live-call/hooks/useHintCooldown.ts
git commit -m "feat(live-call): add AIHintCard with useHintCooldown hook (FEAT-013)"
```

---

### Task 8: TalkRatioBar Component

**Files:**
- Create: `extension/src/sidepanel/live-call/TalkRatioBar.tsx`

**Context:** Renders talk ratio progress bar + mini waveform + text hint. Reads `talkRatioSignal`. See spec §TalkRatioBar.

- [ ] **Step 1: Create TalkRatioBar.tsx**

```tsx
// extension/src/sidepanel/live-call/TalkRatioBar.tsx

import { h } from "preact";
import { talkRatioSignal } from "./store";

function getTextHint(managerPct: number): { text: string; color: string } | null {
  if (managerPct > 65) return { text: "Дайте клиенту больше говорить", color: "#854F0B" };
  if (managerPct < 35) return { text: "Перехватите инициативу", color: "#854F0B" };
  return { text: "Отличный баланс", color: "#3B6D11" };
}

export function TalkRatioBar(): h.JSX.Element {
  const ratio = talkRatioSignal.value;
  const hint = getTextHint(ratio.managerPercent);

  return (
    <div class="lc-ratio">
      <div class="lc-ratio-labels">
        <span class="lc-ratio-label">Вы <strong>{ratio.managerPercent}%</strong></span>
        <span class="lc-ratio-label"><strong>{ratio.clientPercent}%</strong> Клиент</span>
      </div>
      <div class="lc-ratio-track">
        <div
          class="lc-ratio-fill"
          style={{ width: `${ratio.managerPercent}%` }}
        />
      </div>
      {ratio.waveform.length > 0 && (
        <div class="lc-waveform">
          {ratio.waveform.map((seg, i) => (
            <div
              key={i}
              class={`lc-wave-bar lc-wave-${seg.speaker}`}
              style={{ height: `${3 + seg.amplitude * 13}px` }}
            />
          ))}
        </div>
      )}
      {hint && (
        <div class="lc-ratio-hint" style={{ color: hint.color }}>{hint.text}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`

- [ ] **Step 3: Commit**

```bash
git add extension/src/sidepanel/live-call/TalkRatioBar.tsx
git commit -m "feat(live-call): add TalkRatioBar with waveform (FEAT-013)"
```

---

### Task 9: TranscriptFeed + TranscriptMessage + useAutoScroll

**Files:**
- Create: `extension/src/sidepanel/live-call/TranscriptFeed.tsx`
- Create: `extension/src/sidepanel/live-call/TranscriptMessage.tsx`
- Create: `extension/src/sidepanel/live-call/hooks/useAutoScroll.ts`

**Context:** The transcript section with sticky-to-bottom scroll behavior. See spec §TranscriptFeed, §TranscriptMessage, §useAutoScroll.

- [ ] **Step 1: Create useAutoScroll hook**

```typescript
// extension/src/sidepanel/live-call/hooks/useAutoScroll.ts

import { useRef, useEffect, useCallback } from "preact/hooks";
import { useSignal } from "@preact/signals";

interface AutoScrollResult {
  containerRef: { current: HTMLElement | null };
  isAtBottom: boolean;       // reactive — triggers re-render on change
  scrollToBottom: () => void;
}

export function useAutoScroll(deps: unknown[]): AutoScrollResult {
  const containerRef = useRef<HTMLElement | null>(null);
  const isAtBottom = useSignal(true); // signal so scroll changes trigger re-render

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      isAtBottom.value = true;
    }
  }, []);

  // Track scroll position
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleScroll = () => {
      const threshold = 40;
      isAtBottom.value =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  // Auto-scroll on new content
  useEffect(() => {
    if (isAtBottom.value) {
      scrollToBottom();
    }
  }, deps);

  return {
    containerRef,
    isAtBottom: isAtBottom.value,
    scrollToBottom,
  };
}
```

- [ ] **Step 2: Create TranscriptMessage.tsx**

```tsx
// extension/src/sidepanel/live-call/TranscriptMessage.tsx

import { h } from "preact";
import type { TranscriptMessage as TMsg } from "./types";

const SPEAKER_LABELS: Record<string, string> = {
  manager: "Вы",
  client: "Клиент",
};

interface Props {
  message: TMsg;
}

export function TranscriptMessage({ message }: Props): h.JSX.Element {
  const isManager = message.speaker === "manager";

  return (
    <div class={`lc-msg ${message.isInterim ? "lc-msg--interim" : ""}`}>
      <div class="lc-msg-meta">
        <span class={`lc-msg-speaker ${isManager ? "lc-msg-speaker--mgr" : "lc-msg-speaker--cli"}`}>
          {SPEAKER_LABELS[message.speaker] ?? message.speaker}
        </span>
        <span class="lc-msg-time">{message.timestamp}</span>
      </div>
      <div class="lc-msg-body">
        <div class={`lc-msg-bar ${isManager ? "lc-msg-bar--mgr" : "lc-msg-bar--cli"}`} />
        <div class="lc-msg-text">{message.text}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create TranscriptFeed.tsx**

```tsx
// extension/src/sidepanel/live-call/TranscriptFeed.tsx

import { h } from "preact";
import { transcriptSignal, recordingSignal } from "./store";
import { TranscriptMessage } from "./TranscriptMessage";
import { useAutoScroll } from "./hooks/useAutoScroll";

export function TranscriptFeed(): h.JSX.Element {
  const items = transcriptSignal.value;
  const isRecording = recordingSignal.value.isRecording;
  const { containerRef, isAtBottom, scrollToBottom } = useAutoScroll([items.length]);

  return (
    <div class="lc-transcript">
      <div class="lc-transcript-header">
        <span class="lc-transcript-title">Транскрипт</span>
        {isRecording && (
          <span class="lc-live-badge">
            <span class="lc-live-dot" />
            LIVE
          </span>
        )}
      </div>
      <div class="lc-transcript-list" ref={containerRef as any}>
        {items.map((item) => (
          <TranscriptMessage key={item.id} message={item} />
        ))}
      </div>
      {!isAtBottom && (
        <button class="lc-jump-pill" onClick={scrollToBottom}>
          К последнему ↓
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`

- [ ] **Step 5: Commit**

```bash
git add extension/src/sidepanel/live-call/TranscriptFeed.tsx extension/src/sidepanel/live-call/TranscriptMessage.tsx extension/src/sidepanel/live-call/hooks/useAutoScroll.ts
git commit -m "feat(live-call): add TranscriptFeed with auto-scroll (FEAT-013)"
```

---

### Task 10: RecordingBar + ConnectionStatus + ContextTabs

**Files:**
- Create: `extension/src/sidepanel/live-call/RecordingBar.tsx`
- Create: `extension/src/sidepanel/live-call/ConnectionStatus.tsx`
- Create: `extension/src/sidepanel/live-call/ContextTabs.tsx`

**Context:** Three smaller components. See spec §RecordingBar, §ConnectionStatus, §ContextTabs.

- [ ] **Step 1: Create RecordingBar.tsx**

```tsx
// extension/src/sidepanel/live-call/RecordingBar.tsx

import { h } from "preact";
import { recordingSignal } from "./store";

interface Props {
  onStop: () => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function MicBars({ level }: { level: number }): h.JSX.Element {
  const heights = [6, 10, 14, 10, 6];
  return (
    <div class="lc-mic-bars">
      {heights.map((h, i) => (
        <div
          key={i}
          class="lc-mic-bar"
          style={{ height: `${h}px`, animationDelay: `${i * 0.1}s` }}
        />
      ))}
    </div>
  );
}

export function RecordingBar({ onStop }: Props): h.JSX.Element {
  const state = recordingSignal.value;

  return (
    <div class="lc-rec-bar">
      <button class="lc-rec-stop" onClick={onStop}>
        <span class="lc-rec-dot" />
        СТОП
      </button>
      <MicBars level={state.micLevel} />
      <span class="lc-rec-timer">{formatTime(state.elapsedSeconds)}</span>
    </div>
  );
}
```

- [ ] **Step 2: Create ConnectionStatus.tsx**

```tsx
// extension/src/sidepanel/live-call/ConnectionStatus.tsx

import { h } from "preact";
import { wsConnectedSignal, sttActiveSignal } from "./store";

export function ConnectionStatus(): h.JSX.Element {
  const ws = wsConnectedSignal.value;
  const stt = sttActiveSignal.value;

  return (
    <div class="lc-conn">
      <span class={`lc-conn-dot ${ws ? "lc-conn-dot--on" : "lc-conn-dot--off"}`} />
      <span class={ws ? "" : "lc-conn-label--off"}>WS</span>
      <span class={`lc-conn-dot ${stt ? "lc-conn-dot--on" : "lc-conn-dot--off"}`} />
      <span class={stt ? "" : "lc-conn-label--off"}>STT</span>
    </div>
  );
}
```

- [ ] **Step 3: Create ContextTabs.tsx**

```tsx
// extension/src/sidepanel/live-call/ContextTabs.tsx

import { h } from "preact";
import { activeTabSignal, briefDataSignal, hintSignal } from "./store";
import type { ContextTab } from "./types";
import type { LiveCallCallbacks } from "./mount";

const TABS: { id: ContextTab; label: string }[] = [
  { id: "hints", label: "Подсказки" },
  { id: "objections", label: "Возражения" },
  { id: "briefing", label: "Брифинг" },
  { id: "strategy", label: "Стратегия" },
];

interface Props {
  callbacks: LiveCallCallbacks;
}

export function ContextTabs({ callbacks }: Props): h.JSX.Element {
  const active = activeTabSignal.value;

  const handleClick = (tab: ContextTab) => {
    activeTabSignal.value = tab;
    callbacks.onTabChange(tab);
    callbacks.onBriefingTabActive(tab === "briefing");
  };

  return (
    <div class="lc-tabs-container">
      <div class="lc-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            class={`lc-tab ${active === tab.id ? "lc-tab--active" : ""}`}
            onClick={() => handleClick(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content (below the pills) */}
      {active === "objections" && (
        <div class="lc-tab-content">
          {(briefDataSignal.value?.objections?.length ?? 0) > 0
            ? briefDataSignal.value!.objections.map((obj, i) => (
                <div key={i} class="lc-objection">
                  <div class="lc-objection-q">{obj.question}</div>
                  <div class="lc-objection-a">{obj.answer}</div>
                </div>
              ))
            : <div class="lc-tab-empty">Нет данных о возражениях</div>
          }
        </div>
      )}

      {active === "strategy" && (
        <div class="lc-tab-content">
          {(briefDataSignal.value?.focusPoints?.length ?? 0) > 0
            ? briefDataSignal.value!.focusPoints.slice(0, 3).map((fp, i) => (
                <div key={i} class="lc-focus-point">
                  <div class="lc-focus-point-title">{fp.headline}</div>
                  {fp.detail && <div class="lc-focus-point-text">{fp.detail}</div>}
                </div>
              ))
            : <div class="lc-tab-empty">Нет данных о стратегии</div>
          }
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck`

- [ ] **Step 5: Commit**

```bash
git add extension/src/sidepanel/live-call/RecordingBar.tsx extension/src/sidepanel/live-call/ConnectionStatus.tsx extension/src/sidepanel/live-call/ContextTabs.tsx
git commit -m "feat(live-call): add RecordingBar, ConnectionStatus, ContextTabs (FEAT-013)"
```

---

### Task 11: CSS (live-call.css)

**Files:**
- Modify: `extension/src/sidepanel/live-call/live-call.css`

**Context:** All visual styles for the live-call components. Follow design tokens from Brief Panel. See spec §Visual Spec for exact values.

- [ ] **Step 1: Write complete CSS**

Replace the placeholder CSS with the full styles. Key sections:
- `.lc-panel` — root flex column
- `.lc-rec-bar` — recording bar (flex center, gap 12px)
- `.lc-rec-stop` — СТОП button (border: 1.5px solid #E24B4A, radius 8px)
- `.lc-rec-dot` — pulsing 8×8px dot (animation: pulse 1.2s infinite)
- `.lc-mic-bars` — 5 bars (2px wide, bounce animation)
- `.lc-rec-timer` — tabular-nums 13px/500
- `.lc-conn` — connection status row (flex center, gap 12px, 11px, #9ca3af)
- `.lc-conn-dot--on/--off` — 6×6px dots (green #5DCAA5 / red #E24B4A)
- `.lc-hint-card` — padding 14px 16px, radius 12px
- `.lc-hint-null` — bg #f9fafb, no border-left
- `.lc-hint-label` — 11px/500 uppercase, letter-spacing 0.5px
- `.lc-hint-headline` — 14px/500
- `.lc-hint-detail` — 12px/400
- `.lc-hint-coaching` — 11px italic #9ca3af margin-top 8px
- `.lc-hint-check-icon` — 24×24px circle bg #639922
- `.lc-hint-success-row` — flex center gap 8px
- `.lc-ratio` — padding 12px 16px
- `.lc-ratio-track` — height 6px radius 3px bg #EAF3DE
- `.lc-ratio-fill` — bg #2563eb transition width 0.8s
- `.lc-waveform` — flex gap 1px height 16px
- `.lc-wave-bar` — width 2px radius 1px opacity 0.4
- `.lc-wave-manager` — #2563eb
- `.lc-wave-client` — #5DCAA5
- `.lc-tabs` — flex gap 6px padding 0 16px 12px
- `.lc-tab` — 11px padding 4px 10px radius 20px border 0.5px solid #e5e7eb
- `.lc-tab--active` — bg #E6F1FB color #2563eb
- `.lc-transcript` — flex-1 flex column
- `.lc-transcript-list` — overflow-y auto flex-1
- `.lc-live-badge` — 11px/500 #E24B4A
- `.lc-live-dot` — 6×6px pulsing dot
- `.lc-msg` — padding 8px 0 border-bottom 0.5px
- `.lc-msg-speaker--mgr` — #2563eb
- `.lc-msg-speaker--cli` — #1D9E75
- `.lc-msg-bar--mgr/--cli` — 3px wide colored bars
- `.lc-msg--interim` — color #9ca3af italic
- `.lc-jump-pill` — sticky bottom, centered pill button
- Animations: `@media (prefers-reduced-motion: no-preference)` wrapper

All exact values are in the spec §Visual Spec section.

- [ ] **Step 2: Verify build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run build`

- [ ] **Step 3: Commit**

```bash
git add extension/src/sidepanel/live-call/live-call.css
git commit -m "feat(live-call): add complete CSS styles (FEAT-013)"
```

---

### Task 12: HTML + sidepanel.ts Integration (Strangler Fig Wiring)

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.html:145-184`
- Modify: `extension/src/sidepanel/sidepanel.ts` (multiple sections)

**Context:** The critical integration task. Replace Phase 3 HTML with a single mount point, wire signals in the WS message handler, update `handleCaptureStarted()` and `resetForNewCall()`. See spec §sidepanel.ts Changes.

- [ ] **Step 1: Update Phase 3 HTML**

In `extension/src/sidepanel/sidepanel.html`, replace lines 145-184:

Old:
```html
<!-- Phase 3: Live call (PRIMARY) — split layout -->
<section id="phase-3" class="phase">
  <!-- Hints panel + talk ratio + splitters + briefing + transcript -->
  ...all the old DOM...
</section>
```

New:
```html
<!-- Phase 3: Live call (PRIMARY) — Preact mount point -->
<section id="phase-3" class="phase">
  <div id="live-call-root"></div>
  <!-- Collapsed briefing (managed by sidepanel.ts, shown by ContextTabs) -->
  <div id="briefing-collapsed" class="briefing-collapsed" hidden>
    <!-- Preact BriefPanel (compact) mounts here -->
  </div>
</section>
```

- [ ] **Step 1b: Remove old v1 types from WS union (atomic cutover)**

Now that sidepanel.ts is being rewritten, remove the transitional types from `shared/messages.ts`:
- Remove `WsHintStart`, `WsHintChunk`, `WsHintEnd` interfaces
- Remove them from `WsMessage` union
- Remove `{ type: "HINT"; hint: WsHintEnd }` from `ExtMessage`
- Remove `import type { HintPayload } from "./types"` if unused

- [ ] **Step 2: Add imports to sidepanel.ts**

At the top of `sidepanel.ts`, add:
```typescript
import { mountLiveCall, unmountLiveCall } from "./live-call/mount";
import {
  transcriptSignal, hintSignal, talkRatioSignal,
  recordingSignal, wsConnectedSignal, sttActiveSignal,
  activeTabSignal, briefDataSignal,
} from "./live-call/store";
import type { AIHint, TranscriptItem } from "./live-call/types";
```

Add module-level variables:
```typescript
let transcriptItems: TranscriptItem[] = [];
let recordingTimerInterval: ReturnType<typeof setInterval> | null = null;
```

- [ ] **Step 3: Update handleWsMessage switch block**

In `sidepanel.ts` handleWsMessage (line 914), update the switch:

```typescript
case "hint_end": {
  const msg_ = msg as any;
  if (msg_.v !== 2) break;
  hintSignal.value = {
    id: crypto.randomUUID(),
    hintType: msg_.hint_type,
    headline: msg_.headline,
    detail: msg_.detail,
    coaching: msg_.coaching,
    source: msg_.source,
    timestamp: Date.now(),
  };
  break;
}

case "talk_ratio": {
  const msg_ = msg as any;
  talkRatioSignal.value = {
    managerPercent: msg_.managerPercent,
    clientPercent: msg_.clientPercent,
    waveform: msg_.waveform,
  };
  break;
}

case "transcript":
  handleTranscript(msg);
  break;
```

Remove `case "hint_start"` and `case "hint_chunk"` (no-ops, now deleted types).

- [ ] **Step 4: Rewrite handleTranscript to use signals**

Replace the old `handleTranscript` (lines 1100-1187) with a signal-based version.

**Key design decisions:**
- Interim dedup uses position-based strategy (not id-based), because SaluteSpeech only sends `utterance_id` on final results. Check if last entry is an interim from same speaker -> update in place.
- Final utterances also append to `#transcript-full-list` for Phase 4 (DOM clone path).
- Use `getCallDuration()` (existing function at line 459) for timestamps, NOT `formatCallTime()` which doesn't exist.

```typescript
function handleTranscript(msg: WsTranscript): void {
  const speaker = msg.speaker === "rep" ? "manager" as const : "client" as const;
  const timestamp = getCallDuration(); // existing function, returns "MM:SS"

  if (!msg.is_final) {
    // Interim: update last entry if same speaker + interim, else append
    const last = transcriptItems[transcriptItems.length - 1];
    if (last?.isInterim && last.speaker === speaker) {
      last.text = msg.text;
    } else {
      transcriptItems.push({
        type: "message",
        id: `t-${Date.now()}`,
        speaker,
        text: msg.text,
        timestamp,
        isInterim: true,
      });
    }
  } else {
    // Final: find and update last interim from same speaker, or append new
    const lastIdx = transcriptItems.length - 1;
    const last = transcriptItems[lastIdx];
    if (last?.isInterim && last.speaker === speaker) {
      transcriptItems[lastIdx] = { ...last, text: msg.text, isInterim: false };
    } else {
      transcriptItems.push({
        type: "message",
        id: msg.utterance_id ?? `t-${Date.now()}`,
        speaker,
        text: msg.text,
        timestamp,
        isInterim: false,
      });
    }

    // Also append to Phase 4 transcript DOM for post-call display
    const fullList = $("transcript-full-list");
    if (fullList) {
      const entry = document.createElement("div");
      entry.className = `transcript-entry transcript-${speaker}`;
      const label = document.createElement("span");
      label.className = "transcript-speaker";
      label.textContent = speaker === "manager" ? "Менеджер" : "Клиент";
      entry.appendChild(label);
      entry.appendChild(document.createTextNode(` ${msg.text}`));
      fullList.appendChild(entry);
    }
  }

  transcriptSignal.value = [...transcriptItems];

  // STT heartbeat
  sttActiveSignal.value = true;
}
```

- [ ] **Step 5: Update handleCaptureStarted**

Replace `handleCaptureStarted()` (lines 491-531):

```typescript
function handleCaptureStarted(): void {
  hideCapturePrompt();
  const recBtn = $<HTMLButtonElement>("rec-btn");
  const recLabel = $("rec-label");

  if (recBtn) {
    recBtn.disabled = false;
    recBtn.classList.remove("rec-idle");
    recBtn.classList.add("rec-active");
  }
  if (recLabel) recLabel.textContent = "СТОП";
  show($("vu-meters"));
  void saveState({ capturing: true });
  setPhase(3);
  startCallTimer();

  // Reset signals for new session
  transcriptItems = [];
  transcriptSignal.value = [];
  hintSignal.value = null;
  talkRatioSignal.value = { managerPercent: 0, clientPercent: 100, waveform: [] };
  recordingSignal.value = { isRecording: true, elapsedSeconds: 0, micLevel: 0 };
  wsConnectedSignal.value = true;
  sttActiveSignal.value = true;
  activeTabSignal.value = "hints";
  briefDataSignal.value = panelState.briefing ?? null;

  // Start recording timer (updates recordingSignal.elapsedSeconds every 1s)
  if (recordingTimerInterval) clearInterval(recordingTimerInterval);
  const recStart = Date.now();
  recordingTimerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - recStart) / 1000);
    recordingSignal.value = { ...recordingSignal.value, elapsedSeconds: elapsed };
  }, 1000);

  // Mount Preact tree
  const root = $("live-call-root");
  if (root) {
    mountLiveCall(root, {
      onStopRecording: () => { $<HTMLButtonElement>("rec-btn")?.click(); },
      onTabChange: () => {},
      onBriefingTabActive: (active) => {
        const bc = $("briefing-collapsed");
        if (bc) active ? show(bc) : hide(bc);
      },
    });
  }
}
```

- [ ] **Step 5b: Add AUDIO_LEVEL handler for micLevel signal**

In the existing `AUDIO_LEVEL` port message handler (around line 324 in sidepanel.ts), add:
```typescript
// Existing: updates VU meter DOM
// New: also update recording signal
recordingSignal.value = { ...recordingSignal.value, micLevel: msg.mic };
```

- [ ] **Step 6: Update resetForNewCall**

Add to `resetForNewCall()` (line 1960):

```typescript
function resetForNewCall(): void {
  void saveState({ sessionId: crypto.randomUUID(), briefing: null });

  // Unmount Preact brief panels
  const bc = $("briefing-content");
  if (bc) mountBriefPanel(bc, null);
  hide(bc);
  const bcc = $("briefing-collapsed");
  if (bcc) mountBriefPanel(bcc, null);
  const bcd = $("briefing-collapsed-done");
  if (bcd) mountBriefPanel(bcd, null);

  stopEvalPolling();
  evalReceived = false;
  pendingFollowUpEmail = null;
  pendingCrmNote = null;
  hide($("follow-up-actions"));

  // Clear transcript DOM (Phase 4 full list)
  const fullList = $("transcript-full-list");
  if (fullList) fullList.textContent = "";

  // Stop recording timer
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }

  // Reset live-call signals
  transcriptItems = [];
  transcriptSignal.value = [];
  hintSignal.value = null;
  talkRatioSignal.value = { managerPercent: 0, clientPercent: 100, waveform: [] };
  recordingSignal.value = { isRecording: false, elapsedSeconds: 0, micLevel: 0 };
  wsConnectedSignal.value = false;
  sttActiveSignal.value = true;
  activeTabSignal.value = "hints";
  briefDataSignal.value = null;

  // Unmount live-call Preact tree
  unmountLiveCall();
}
```

- [ ] **Step 7: Update LiveCallPanel to include all children**

Replace the placeholder in `LiveCallPanel.tsx`:

```tsx
export function LiveCallPanel({ callbacks }: LiveCallPanelProps): h.JSX.Element {
  const activeTab = activeTabSignal.value;

  return (
    <div class="lc-panel">
      <RecordingBar onStop={callbacks.onStopRecording} />
      <ConnectionStatus />
      {activeTab === "hints" && <AIHintCard />}
      <TalkRatioBar />
      <ContextTabs callbacks={callbacks} />
      <TranscriptFeed />
    </div>
  );
}
```

Add imports for all child components.

- [ ] **Step 8: Verify TypeScript compiles + build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck && pnpm run build`

- [ ] **Step 9: Commit**

```bash
git add extension/src/sidepanel/sidepanel.html extension/src/sidepanel/sidepanel.ts extension/src/sidepanel/live-call/LiveCallPanel.tsx
git commit -m "feat: wire live-call Preact tree into sidepanel.ts (FEAT-013)"
```

---

### Task 13: Cleanup Deleted Code from sidepanel.ts

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

**Context:** Delete the old Phase 3 code that's been replaced by the Preact components. ~400 lines removed. This is the final strangler fig step. See spec §sidepanel.ts Changes → Deleted code.

- [ ] **Step 1: Delete old variables and state**

Remove from sidepanel.ts:
- `const DISPLAY_COOLDOWN_MS = 8_000;` (line 946)
- `let lastHintRenderedAt = 0;` (line 947)
- `let pendingHintEnd: WsHintEnd | null = null;` (line 948)
- `let pendingHintTimer: ReturnType<typeof setTimeout> | null = null;` (line 949)
- `let sentimentHistory: string[] = [];` (near line 952)
- `let repWordCount = 0;` (line 974)
- `let clientWordCount = 0;` (line 975)
- `let isAutoScrolling = true;` (line 1098)

- [ ] **Step 2: Delete old functions**

Remove these functions entirely:
- `Splitter` class (lines 40-164)
- `initPhase3Splitter()` (lines 168-172)
- `updateSentimentDots()` (lines 955-971)
- `updateTalkRatio()` (lines 977-1001)
- `handleHintStart()` (lines 1003-1006)
- `handleHintChunk()` (lines 1008-1011)
- `handleHintEnd()` (lines 1013-1028)
- `flushPendingHint()` (lines 1030-1037)
- `renderHint()` (lines 1039-1094)
- `initTranscriptScroll()` (lines 1189-1207)

- [ ] **Step 3: Clean up references**

Search for any remaining references to deleted functions/variables:
- `initPhase3Splitter()` call in `setPhase()` (line ~197) — remove entire `case 3:` `requestAnimationFrame` block that calls `initPhase3Splitter()` and `phase3Splitter?.restore()`
- `phase3Splitter` variable — remove
- `initTranscriptScroll()` call — remove
- `updateHeader()` references to `$("transcript-live-dot")` — remove (LIVE badge now in TranscriptFeed)
- Any `sentimentHistory` / `updateSentimentDots` references — remove
- Any `WsHintStart` / `WsHintChunk` / `WsHintEnd` type references — update or remove
- Old `HintPayload` import if unused — remove

- [ ] **Step 4: Clean up old DOM references**

Remove any `$("hints-panel")`, `$("hint-text")`, `$("coaching-text")`, `$("hint-source")`, `$("sentiment-dots")`, `$("talk-ratio-bar")`, `$("talk-fill-rep")`, `$("talk-fill-client")`, `$("talk-pct-rep")`, `$("talk-pct-client")`, `$("transcript-list")`, `$("transcript-details")`, `$("transcript-live-dot")`, `$("jump-to-latest")` — these DOM elements no longer exist in the new HTML.

Keep: `$("briefing-collapsed")` (still managed by sidepanel.ts for ContextTabs).

- [ ] **Step 5: Verify TypeScript compiles + build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && pnpm run typecheck && pnpm run build`
Expected: Clean compilation, no errors

- [ ] **Step 6: Run full project test suite**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/ -v`
Expected: All backend tests pass

- [ ] **Step 7: Commit**

```bash
git add extension/src/sidepanel/sidepanel.ts
git commit -m "refactor: delete ~400 lines of old Phase 3 code from sidepanel.ts (FEAT-013)"
```

---

## Post-Implementation Verification

After all tasks:

1. `pnpm run build` in extension/ — must succeed
2. `pnpm run typecheck` in extension/ — must succeed
3. `python -m pytest backend/tests/ -v` — all tests pass
4. Load unpacked extension in Chrome — side panel opens without errors
5. Start a mock recording — LiveCallPanel renders with all components
6. Verify hint cards show coaching/success/warning states
7. Verify talk ratio bar updates
8. Verify transcript scrolls correctly
9. Verify "New Call" resets all state

## Feature Inventory (Migration Parity)

| Old Code (sidepanel.ts) | New Code (live-call/) | Task |
|--------------------------|----------------------|------|
| `Splitter` class | `ContextTabs.tsx` (tabs replace splitters) | Task 10 |
| `updateSentimentDots()` | Removed (sentiment dots replaced by hint_type) | Task 13 |
| `updateTalkRatio()` | `TalkRatioBar.tsx` + backend `TalkRatioTracker` | Task 2, 8 |
| `handleHintStart/Chunk` | Removed (no-ops) | Task 13 |
| `handleHintEnd/renderHint` | `AIHintCard.tsx` + `useHintCooldown` | Task 7 |
| `handleTranscript` | `TranscriptFeed.tsx` + signal updater in sidepanel.ts | Task 9, 12 |
| `initTranscriptScroll` | `useAutoScroll` hook | Task 9 |
| `HintResponse` dataclass | `HintResponseV2` Pydantic schema | Task 1 |
| Frontend word counting | Backend `TalkRatioTracker` | Task 2 |
| Old JSON format (hint/sentiment/color) | v2 format (hint_type/headline/detail) | Task 3 |
