# FEAT-011: Follow-Up Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate a follow-up email draft and CRM note during post-call evaluation, with one-click Gmail compose and clipboard copy.

**Architecture:** Extend the existing evaluation Pydantic schema with two optional nested models (`FollowUpEmail`, `CrmNote`). Add a `model_validator` coercion to gracefully degrade when the LLM produces malformed follow-up objects. Extend the evaluation prompt to request follow-up generation. On the frontend, add two action buttons in Phase 4 that wire into both the WebSocket and REST polling result paths.

**Tech Stack:** Python 3.11 / Pydantic v2 / FastAPI, TypeScript (vanilla, no framework), Chrome Extension Manifest V3

**Spec:** `docs/superpowers/specs/2026-03-19-follow-up-actions-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/pipeline/evaluation_schemas.py` | Add `FollowUpEmail`, `CrmNote` models + coercion validator on `CallEvaluation` |
| Modify | `backend/pipeline/evaluator.py` | Extend `_SYSTEM_PROMPT` with follow-up generation instructions |
| Modify | `backend/pipeline/evaluator_llm.py:13` | Increase `PRIMARY_TIMEOUT_S` from 15.0 to 25.0 |
| Modify | `backend/tests/test_evaluation_schemas.py` | Add tests for new schemas + coercion validator |
| Modify | `extension/src/shared/evaluation-types.ts` | Add `FollowUpEmail`, `CrmNote` interfaces + extend `CallEvaluationResult` |
| Modify | `extension/src/sidepanel/sidepanel.html:259` | Add `#follow-up-actions` container between `#eval-summary` and `#eval-error` |
| Modify | `extension/src/sidepanel/sidepanel.css` | Add follow-up button styles |
| Modify | `extension/src/sidepanel/sidepanel.ts` | Add `handleFollowUpActions()`, wire into both result paths, add button handlers, add state reset |

---

## Progress Tracking

- [ ] Task 1: Backend — Add `FollowUpEmail` and `CrmNote` schemas
- [ ] Task 2: Backend — Add coercion validator to `CallEvaluation`
- [ ] Task 3: Backend — Extend evaluation prompt and increase timeout
- [ ] Task 4: Frontend — Add TypeScript types
- [ ] Task 5: Frontend — Add HTML + CSS for follow-up buttons
- [ ] Task 6: Frontend — Wire `handleFollowUpActions` into both result paths
- [ ] Task 7: Frontend — Add email and CRM button handlers
- [ ] Task 8: Frontend — Add state reset on new evaluation
- [ ] Task 9: Commit and verify

**Total Tasks:** 9 | **Completed:** 0 | **Remaining:** 9

**Status:** PENDING

---

### Task 1: Backend — Add `FollowUpEmail` and `CrmNote` Schemas

**Files:**
- Modify: `backend/pipeline/evaluation_schemas.py:55-84`
- Test: `backend/tests/test_evaluation_schemas.py`

- [ ] **Step 1: Write failing tests for new schemas**

Add to `backend/tests/test_evaluation_schemas.py`:

```python
def test_follow_up_email_valid():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    email = FollowUpEmail(
        subject="Итоги встречи",
        body="Добрый день, Александр! Благодарю за уделённое время.",
    )
    assert email.subject == "Итоги встречи"
    assert email.body.startswith("Добрый день")


def test_follow_up_email_empty_subject_rejected():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    with pytest.raises(ValidationError):
        FollowUpEmail(subject="", body="text")


def test_follow_up_email_empty_body_rejected():
    from backend.pipeline.evaluation_schemas import FollowUpEmail
    with pytest.raises(ValidationError):
        FollowUpEmail(subject="subj", body="")


def test_crm_note_valid():
    from backend.pipeline.evaluation_schemas import CrmNote
    note = CrmNote(
        title="2026-03-19 | Александр | Договорились о демо",
        body="Резюме: обсудили потребности, согласовали демо на пятницу.",
    )
    assert "Александр" in note.title
    assert "демо" in note.body


def test_crm_note_empty_title_rejected():
    from backend.pipeline.evaluation_schemas import CrmNote
    with pytest.raises(ValidationError):
        CrmNote(title="", body="text")


def test_crm_note_empty_body_rejected():
    from backend.pipeline.evaluation_schemas import CrmNote
    with pytest.raises(ValidationError):
        CrmNote(title="title", body="")


def test_call_evaluation_without_follow_up_fields():
    """Backwards compat: old evaluations without follow-up fields parse fine."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None
    assert ev.crm_note is None


def test_call_evaluation_with_follow_up_fields():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {
            "subject": "Итоги встречи",
            "body": "Добрый день!",
        },
        "crm_note": {
            "title": "2026-03-19 | Клиент | Демо",
            "body": "Резюме звонка.",
        },
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is not None
    assert ev.follow_up_email.subject == "Итоги встречи"
    assert ev.crm_note is not None
    assert ev.crm_note.title.startswith("2026-03-19")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_evaluation_schemas.py -v -k "follow_up or crm_note"`
Expected: FAIL — `FollowUpEmail` and `CrmNote` not defined

- [ ] **Step 3: Implement `FollowUpEmail` and `CrmNote` models**

Add to `backend/pipeline/evaluation_schemas.py` before the `CallEvaluation` class:

```python
class FollowUpEmail(BaseModel):
    """Draft follow-up email generated from call context."""

    subject: str = Field(
        min_length=1,
        max_length=200,
        description="Email subject line, concise and professional",
    )
    body: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Email body in plain text, formal business style. "
            "Keep under 1500 characters to avoid Gmail URL truncation."
        ),
    )


class CrmNote(BaseModel):
    """Structured CRM note for post-call documentation."""

    title: str = Field(
        min_length=1,
        max_length=200,
        description="Note title: date + client name + call outcome",
    )
    body: str = Field(
        min_length=1,
        max_length=3000,
        description="Structured: summary, commitments, next steps, deadlines",
    )
```

Add two optional fields to `CallEvaluation`:

```python
class CallEvaluation(BaseModel):
    # ... existing fields ...
    follow_up_email: FollowUpEmail | None = Field(
        default=None,
        description="Draft follow-up email for the client",
    )
    crm_note: CrmNote | None = Field(
        default=None,
        description="Structured CRM note for copy-paste",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_evaluation_schemas.py -v`
Expected: ALL PASS

---

### Task 2: Backend — Add Coercion Validator to `CallEvaluation`

**Files:**
- Modify: `backend/pipeline/evaluation_schemas.py` — `CallEvaluation` class
- Test: `backend/tests/test_evaluation_schemas.py`

- [ ] **Step 1: Write failing tests for coercion**

Add to `backend/tests/test_evaluation_schemas.py`:

```python
def test_coercion_partial_follow_up_email_becomes_none():
    """LLM returns partial object (missing body) → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "Hi"},  # missing body
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_partial_crm_note_becomes_none():
    """LLM returns CRM note with missing title → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "crm_note": {"body": "some text"},  # missing title
    }
    ev = CallEvaluation(**data)
    assert ev.crm_note is None


def test_coercion_empty_string_follow_up_email_becomes_none():
    """LLM returns empty subject → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "", "body": "text"},
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_non_dict_follow_up_becomes_none():
    """LLM returns a string instead of object → coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": "not a dict",
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is None


def test_coercion_valid_follow_up_preserved():
    """Valid follow-up objects are NOT coerced to None."""
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "Summary",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
        "follow_up_email": {"subject": "Re: Встреча", "body": "Добрый день!"},
        "crm_note": {"title": "2026-03-19 | Client", "body": "Summary."},
    }
    ev = CallEvaluation(**data)
    assert ev.follow_up_email is not None
    assert ev.crm_note is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest backend/tests/test_evaluation_schemas.py -v -k "coercion"`
Expected: FAIL — partial objects trigger Pydantic ValidationError instead of coercion

- [ ] **Step 3: Add `coerce_invalid_follow_ups` validator**

Add to `CallEvaluation` class in `backend/pipeline/evaluation_schemas.py`, before the existing fields:

```python
@model_validator(mode="before")
@classmethod
def coerce_invalid_follow_ups(cls, data: dict) -> dict:
    """If LLM produces malformed follow-up objects, set to None instead of failing."""
    if not isinstance(data, dict):
        return data
    for key, required_keys in (
        ("follow_up_email", {"subject", "body"}),
        ("crm_note", {"title", "body"}),
    ):
        val = data.get(key)
        if val is None:
            continue
        if not isinstance(val, dict):
            data[key] = None
        elif not required_keys.issubset(val.keys()):
            data[key] = None
        elif any(not val.get(k) for k in required_keys):
            data[key] = None
    return data
```

Note: import `model_validator` is already present in the file (line 7).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest backend/tests/test_evaluation_schemas.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest backend/tests/ -v`
Expected: ALL PASS (322+ tests)

- [ ] **Step 6: Commit backend schema changes**

```bash
git add backend/pipeline/evaluation_schemas.py backend/tests/test_evaluation_schemas.py
git commit -m "feat(eval): add FollowUpEmail and CrmNote schemas with coercion validator

FEAT-011: Follow-up actions — backend schema extension.
Adds two optional Pydantic models to CallEvaluation with a
model_validator that gracefully coerces malformed LLM output to None."
```

---

### Task 3: Backend — Extend Evaluation Prompt and Increase Timeout

**Files:**
- Modify: `backend/pipeline/evaluator.py:24-61` — `_SYSTEM_PROMPT`
- Modify: `backend/pipeline/evaluator_llm.py:13` — `PRIMARY_TIMEOUT_S`

- [ ] **Step 1: Extend `_SYSTEM_PROMPT` in `evaluator.py`**

Append the following to the end of `_SYSTEM_PROMPT` (after the analytics section):

```python
    "\n\n"
    "FOLLOW-UP ГЕНЕРАЦИЯ:\n"
    "Дополнительно сгенерируй два блока:\n"
    "1. follow_up_email — черновик делового письма клиенту:\n"
    "   - subject: краткая тема (отражает суть договорённостей)\n"
    "   - body: деловой стиль, обращение по имени из брифинга,"
    " благодарность за время, резюме договорённостей,"
    " следующие шаги с датами. Максимум 1500 символов.\n"
    "2. crm_note — заметка для CRM:\n"
    "   - title: \"YYYY-MM-DD | Имя клиента | Исход\"\n"
    "   - body: резюме, потребности, договорённости,"
    " следующие шаги с дедлайнами, возражения\n"
    "Если контекста недостаточно для персонализации,"
    " установи follow_up_email и crm_note в null."
```

- [ ] **Step 2: Increase `PRIMARY_TIMEOUT_S` in `evaluator_llm.py`**

Change `evaluator_llm.py:13`:
```python
PRIMARY_TIMEOUT_S = 25.0  # increased from 15.0 for follow-up generation
```

- [ ] **Step 3: Run existing evaluator tests to verify no regressions**

Run: `uv run pytest backend/tests/test_evaluator.py backend/tests/test_evaluator_llm.py backend/tests/test_evaluation_runner.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit prompt and timeout changes**

```bash
git add backend/pipeline/evaluator.py backend/pipeline/evaluator_llm.py
git commit -m "feat(eval): extend prompt for follow-up generation, increase timeout

FEAT-011: Add follow-up email + CRM note instructions to evaluation
system prompt. Increase PRIMARY_TIMEOUT_S 15→25s to accommodate
additional ~350-700 output tokens."
```

---

### Task 4: Frontend — Add TypeScript Types

**Files:**
- Modify: `extension/src/shared/evaluation-types.ts`

- [ ] **Step 1: Add `FollowUpEmail` and `CrmNote` interfaces**

Add before `CallEvaluationResult` in `extension/src/shared/evaluation-types.ts`:

```typescript
export interface FollowUpEmail {
  subject: string;
  body: string;
}

export interface CrmNote {
  title: string;
  body: string;
}
```

- [ ] **Step 2: Extend `CallEvaluationResult` with optional fields**

Add two optional fields to `CallEvaluationResult`:

```typescript
export interface CallEvaluationResult {
  // ... existing fields ...
  follow_up_email?: FollowUpEmail;
  crm_note?: CrmNote;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

---

### Task 5: Frontend — Add HTML + CSS for Follow-Up Buttons

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.html:259` — between `#eval-summary` and `#eval-error`
- Modify: `extension/src/sidepanel/sidepanel.css`

- [ ] **Step 1: Add HTML container in Phase 4**

In `sidepanel.html`, insert between the closing `</div>` of `#eval-summary` (line 259) and `<div id="eval-error"` (line 260):

```html
        <div id="follow-up-actions" class="follow-up-actions" hidden
             aria-label="Действия после звонка" aria-live="polite">
          <button id="followup-email-btn" class="btn-followup btn-followup-email" type="button"
                  aria-label="Открыть черновик письма в Gmail">
            Email follow-up
          </button>
          <button id="followup-crm-btn" class="btn-followup btn-followup-crm" type="button"
                  aria-label="Скопировать заметку CRM в буфер обмена">
            Копировать в CRM
          </button>
        </div>
```

- [ ] **Step 2: Add CSS styles**

Append to `sidepanel.css`:

```css
/* ── Follow-up actions (FEAT-011) ─────────────────────────────────────── */

.follow-up-actions {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
}

.btn-followup {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-followup:hover {
  background: #f5f5f5;
  border-color: #bbb;
}

.btn-followup:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-followup-email::before {
  content: "\2709\0020";
}

.btn-followup-crm::before {
  content: "\1F4CB\0020";
}

.btn-followup.copied {
  background: #e8f5e9;
  border-color: #4caf50;
}
```

- [ ] **Step 3: Verify extension builds**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

---

### Task 6: Frontend — Wire `handleFollowUpActions` into Both Result Paths

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

- [ ] **Step 1: Add module-level state and import types**

At the top of `sidepanel.ts`, ensure `FollowUpEmail` and `CrmNote` are imported:

```typescript
import type {
  CallAnalyticsWire,
  CallEvaluationResult,
  DiarizedUtterance,
  FollowUpEmail,  // NEW
  CrmNote,        // NEW
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
} from "../shared/evaluation-types";
```

Add module-level state near the other eval-related state variables (around line 623):

```typescript
let pendingFollowUpEmail: FollowUpEmail | null = null;
let pendingCrmNote: CrmNote | null = null;
```

- [ ] **Step 2: Add `handleFollowUpActions` function**

Add after `renderEvaluationSummary` function (after line 830):

```typescript
function handleFollowUpActions(evaluation: CallEvaluationResult): void {
  const container = $("follow-up-actions");
  pendingFollowUpEmail = evaluation.follow_up_email ?? null;
  pendingCrmNote = evaluation.crm_note ?? null;

  if (pendingFollowUpEmail || pendingCrmNote) {
    show(container);
  } else {
    hide(container);
  }

  const emailBtn = $("followup-email-btn");
  const crmBtn = $("followup-crm-btn");
  if (emailBtn) emailBtn.hidden = !pendingFollowUpEmail;
  if (crmBtn) crmBtn.hidden = !pendingCrmNote;
}
```

- [ ] **Step 3: Wire into WebSocket path — `handleEvaluationResult`**

In `handleEvaluationResult` (line 747), after `renderEvaluationSummary(ev, msg.session_id);`, add:

```typescript
  handleFollowUpActions(ev);
```

- [ ] **Step 4: Wire into REST poll fallback path**

In `handleEvaluationStarted` (line 717), after `renderEvaluationSummary(evalData, sid);`, add:

```typescript
        handleFollowUpActions(evalData as CallEvaluationResult);
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

---

### Task 7: Frontend — Add Email and CRM Button Handlers

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts`

- [ ] **Step 1: Add `initFollowUpButtons` function**

Add after `handleFollowUpActions`:

```typescript
function initFollowUpButtons(): void {
  // Email follow-up → opens Gmail compose
  $("followup-email-btn")?.addEventListener("click", () => {
    if (!pendingFollowUpEmail) return;
    const MAX_BODY = 1500;
    const MAX_SUBJECT = 128;
    let body = pendingFollowUpEmail.body;
    if (body.length > MAX_BODY) {
      body = body.slice(0, MAX_BODY) + "...\n\n(текст сокращён, дополните вручную)";
    }
    const subject = pendingFollowUpEmail.subject.slice(0, MAX_SUBJECT);
    const params = new URLSearchParams({ view: "cm", fs: "1", su: subject, body });
    const gmailUrl = `https://mail.google.com/mail/?${params.toString()}`;
    chrome.tabs.create({ url: gmailUrl }).catch(() => {
      const btn = $("followup-email-btn");
      if (btn) {
        btn.textContent = "Не удалось открыть Gmail";
        setTimeout(() => { btn.textContent = "Email follow-up"; }, 2000);
      }
    });
  });

  // CRM note → clipboard copy
  $("followup-crm-btn")?.addEventListener("click", async () => {
    if (!pendingCrmNote) return;
    const btn = $("followup-crm-btn") as HTMLButtonElement | null;
    if (!btn || btn.disabled) return;
    btn.disabled = true;

    const text = `${pendingCrmNote.title}\n\n${pendingCrmNote.body}`;
    try {
      await navigator.clipboard.writeText(text);
      btn.classList.add("copied");
      btn.textContent = "Скопировано!";
      setTimeout(() => {
        btn.classList.remove("copied");
        btn.textContent = "Копировать в CRM";
        btn.disabled = false;
      }, 2000);
    } catch {
      btn.textContent = "Ошибка копирования";
      setTimeout(() => {
        btn.textContent = "Копировать в CRM";
        btn.disabled = false;
      }, 2000);
    }
  });
}
```

- [ ] **Step 2: Wire `initFollowUpButtons` into `init()`**

In the `init()` function (around line 1990), add after `initNewCallButton();`:

```typescript
  initFollowUpButtons();
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

---

### Task 8: Frontend — Add State Reset on New Evaluation

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts` — `handleEvaluationStarted` function

- [ ] **Step 1: Reset follow-up state in `handleEvaluationStarted`**

In `handleEvaluationStarted` (line 672, after hiding eval-error), add:

```typescript
  // Reset follow-up state
  pendingFollowUpEmail = null;
  pendingCrmNote = null;
  hide($("follow-up-actions"));
```

- [ ] **Step 2: Also clear in `initNewCallButton`**

In `initNewCallButton` (line 1970), inside the click handler before `setPhase(2)`:

```typescript
    pendingFollowUpEmail = null;
    pendingCrmNote = null;
    hide($("follow-up-actions"));
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

---

### Task 9: Commit and Verify

**Files:** All modified files

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest backend/tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Build extension**

Run: `cd extension && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit frontend changes**

```bash
git add extension/src/shared/evaluation-types.ts extension/src/sidepanel/sidepanel.html extension/src/sidepanel/sidepanel.css extension/src/sidepanel/sidepanel.ts
git commit -m "feat(ui): add follow-up action buttons in Phase 4

FEAT-011: Email follow-up (Gmail compose) and CRM note (clipboard copy)
buttons appear after evaluation completes. Handles both WebSocket and
REST polling result paths. Includes truncation, error handling, state
reset, and accessibility attributes."
```

- [ ] **Step 4: Verify full build**

Run: `cd extension && npm run build` (if build script exists, otherwise `npx tsc --noEmit`)
Expected: Success
