# FEAT-011: Follow-Up Actions (Email + CRM Note)

**Status:** DRAFT
**Date:** 2026-03-19
**Author:** AI Sales Copilot Team

## Problem

After a sales call ends, the manager must manually write a follow-up email and create a CRM note. This takes 5-15 minutes per call, content quality varies, and key commitments from the call are often forgotten or poorly captured.

## Solution

Generate a draft follow-up email and a structured CRM note automatically as part of the existing post-call evaluation. The LLM already has full context (transcript, briefing, evaluation) — we extend it to produce follow-up content in the same API call.

## User Flow

1. Call ends → Phase 4 activates → evaluation runs (existing flow)
2. Evaluation result arrives with `follow_up_email` and `crm_note` fields
3. Two action buttons appear below the evaluation summary:
   - **"Email follow-up"** → opens Gmail compose with pre-filled subject and body
   - **"Копировать в CRM"** → copies structured note to clipboard, shows confirmation toast
4. Manager reviews/edits the email in Gmail before sending
5. Manager pastes the CRM note into their CRM system

## Architecture

### Approach

**Single LLM call** (Approach A): extend the existing evaluation prompt and schema to include follow-up fields. No new API calls, no new endpoints.

### Data Flow

```
evaluate_call() → CallEvaluation (+ follow_up_email, crm_note)
    ↓
EvaluationRunner.run() → ws.send_json({evaluation: {...}})
    ↓
Extension: handleEvaluationResult() → handleFollowUpActions() → shows buttons
    ↓  (also: REST poll fallback path → handleFollowUpActions())
    ↓
User clicks "Email follow-up" → chrome.tabs.create({url: gmail_compose_url})
User clicks "Копировать в CRM" → navigator.clipboard.writeText() → toast
```

**Important:** Both the WebSocket path (`handleEvaluationResult`) and the REST polling fallback path must call `handleFollowUpActions()` to ensure buttons appear regardless of how the evaluation result is delivered.

## Components

### Backend

#### 1. Schema Extension (`backend/pipeline/evaluation_schemas.py`)

Add two new Pydantic models and optional fields to `CallEvaluation`:

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
        description="Email body in plain text, formal business style. "
                    "Keep under 1500 characters to avoid Gmail URL truncation.",
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

class CallEvaluation(BaseModel):
    # ... existing fields unchanged ...
    follow_up_email: FollowUpEmail | None = Field(
        default=None,
        description="Draft follow-up email for the client",
    )
    crm_note: CrmNote | None = Field(
        default=None,
        description="Structured CRM note for copy-paste",
    )
```

Both fields are **optional** with `None` default for backwards compatibility.

#### 2. Defensive Coercion Validator (`backend/pipeline/evaluation_schemas.py`)

Add a `model_validator` to `CallEvaluation` that gracefully handles malformed follow-up sub-objects from the LLM, preventing a full evaluation reparse when only the follow-up fields are broken:

```python
@model_validator(mode='before')
@classmethod
def coerce_invalid_follow_ups(cls, data: dict) -> dict:
    """If LLM produces malformed follow-up objects, set to None instead of failing."""
    for key, required_keys in (
        ('follow_up_email', {'subject', 'body'}),
        ('crm_note', {'title', 'body'}),
    ):
        val = data.get(key)
        if val is None:
            continue
        if not isinstance(val, dict):
            data[key] = None
        elif not required_keys.issubset(val.keys()):
            data[key] = None
        elif any(not val.get(k) for k in required_keys):
            # Empty strings for required fields → discard
            data[key] = None
    return data
```

This ensures partial/malformed follow-up output from the LLM is silently set to `None` rather than triggering the expensive full reparse loop in `evaluator.py`.

#### 3. Prompt Extension (`backend/pipeline/evaluator.py`)

Append to `_SYSTEM_PROMPT`:

```
Дополнительно сгенерируй два блока для follow-up:

1. follow_up_email — черновик делового письма клиенту после звонка:
   - subject: краткая тема письма (отражает суть договорённостей)
   - body: текст письма (деловой стиль, обращение по имени из брифинга,
     благодарность за время, резюме ключевых договорённостей,
     конкретные следующие шаги с датами, контакты).
     Максимум 1500 символов.

2. crm_note — структурированная заметка для CRM:
   - title: "YYYY-MM-DD | Имя клиента | Исход звонка"
   - body: резюме звонка, выявленные потребности, ключевые договорённости,
     следующие шаги с дедлайнами, возражения и как были обработаны

Если брифинг не предоставлен или контекста недостаточно для персонализации,
установи follow_up_email и crm_note в null.
```

#### 4. Timeout Adjustment (`backend/pipeline/evaluator_llm.py`)

The additional follow-up output adds ~350-700 tokens (email body + CRM note). At typical LLM throughput, this adds 3-7 seconds. Increase `PRIMARY_TIMEOUT_S` from 15.0 to 25.0 to account for the additional output:

```python
PRIMARY_TIMEOUT_S = 25.0  # was 15.0, increased for follow-up generation
```

#### 5. No Other Changes to `evaluation_runner.py`

The runner already serializes the full `CallEvaluation` via `result.model_dump()` and sends it over WebSocket. New optional fields will be included automatically.

### Frontend

#### 6. TypeScript Types (`extension/src/shared/evaluation-types.ts`)

```typescript
export interface FollowUpEmail {
  subject: string;
  body: string;
}

export interface CrmNote {
  title: string;
  body: string;
}

export interface CallEvaluationResult {
  // ... existing fields unchanged ...
  follow_up_email?: FollowUpEmail;
  crm_note?: CrmNote;
}
```

Note: `recipient_hint` removed from frontend type — not used in current UI, avoids wasting LLM tokens on unused data. Can be re-added when recipient auto-fill is implemented.

#### 7. Phase 4 HTML (`extension/src/sidepanel/sidepanel.html`)

Add action buttons row between `#eval-summary` and `#eval-error`:

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

#### 8. CSS Styles (`extension/src/sidepanel/sidepanel.css`)

```css
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

#### 9. TypeScript Logic (`extension/src/sidepanel/sidepanel.ts`)

**Module-level state:**

```typescript
let pendingFollowUpEmail: FollowUpEmail | null = null;
let pendingCrmNote: CrmNote | null = null;
```

**Core handler — called from BOTH evaluation result paths:**

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

**Wiring — two call sites:**

1. In `handleEvaluationResult()` (WebSocket path), after `renderEvaluationSummary(ev, msg.session_id)`:
   ```typescript
   handleFollowUpActions(ev);
   ```

2. In the REST poll fallback success block, after `renderEvaluationSummary(evalData, sid)`:
   ```typescript
   handleFollowUpActions(evalData as CallEvaluationResult);
   ```

**State reset — in `handleEvaluationStarted()`:**

```typescript
// Reset follow-up state when new evaluation begins
pendingFollowUpEmail = null;
pendingCrmNote = null;
hide($("follow-up-actions"));
```

**Email button handler (with truncation):**

```typescript
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
```

**CRM button handler (with error handling and debounce):**

```typescript
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
```

## Error Handling

- **Malformed follow-up from LLM**: `coerce_invalid_follow_ups` validator silently sets broken fields to `None`. Evaluation report is unaffected — no expensive reparse triggered.
- **Empty follow-up fields**: `min_length=1` on Pydantic fields catches empty strings; coercion validator discards them.
- **LLM omits follow-up entirely**: Fields default to `None`, buttons are hidden. Evaluation works normally.
- **Clipboard API fails**: try/catch shows "Ошибка копирования" on the button for 2 seconds.
- **Gmail tab creation fails**: `.catch()` handler shows "Не удалось открыть Gmail" temporarily.
- **Gmail URL length limit**: Body truncated at 1500 chars, subject at 128 chars, with clear indicator text.
- **Stale state across calls**: Follow-up state reset in `handleEvaluationStarted()` before each new evaluation.

## Testing Strategy

### Backend Tests
- Unit test: `FollowUpEmail` and `CrmNote` Pydantic validation (required fields, types, min/max length)
- Unit test: `coerce_invalid_follow_ups` — partial objects → `None`, empty strings → `None`, valid objects → preserved
- Unit test: `CallEvaluation` with and without follow-up fields (backwards compat)
- Integration test: mock LLM returns evaluation JSON with follow-up fields → parsed correctly

### Frontend Tests
- `handleFollowUpActions()` shows/hides buttons based on data presence
- `handleFollowUpActions()` with `null` follow-up fields hides container
- Gmail URL construction with proper encoding and truncation
- CRM note clipboard copy success path (mock `navigator.clipboard`)
- CRM note clipboard copy error path
- State reset: `handleEvaluationStarted()` clears follow-up state
- Double-click debounce on CRM button (disabled guard)

## Out of Scope

- Email provider selection (Gmail only for now)
- CRM API integration (clipboard-based for MVP)
- Email recipient auto-fill (can be added later with `recipient_hint` field)
- Follow-up template customization
- Tracking whether follow-up was actually sent
- Feature flag for follow-up generation (add if timeout regressions observed)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM generates poor email | User sends bad email | Email opens as draft — user reviews before sending |
| Gmail URL length limit | Email body truncated | Truncate at 1500 chars with indicator; `max_length=2000` on Pydantic field |
| Evaluation becomes slower | Longer wait for results | ~350-700 extra output tokens; timeout increased 15→25s |
| Malformed follow-up JSON | Full eval reparse triggered | `coerce_invalid_follow_ups` validator silently sets to `None` |
| No follow-up in old results | Buttons not shown | Fields are optional, graceful degradation |
| Fallback LLM model issues | Nested schema too complex | Coercion validator handles partial output gracefully |
| Empty briefing context | Generic unpersonalized email | Prompt instructs LLM to set follow-up to `null` when context insufficient |

## Review Findings Addressed

| Finding | Source | Resolution |
|---------|--------|------------|
| `handleFollowUpActions` never called | All 3 reviewers | Added explicit wiring to both WS and REST poll paths |
| Follow-up state not reset on new call | All 3 reviewers | Reset in `handleEvaluationStarted()` |
| Partial LLM output triggers full reparse | Backend | Added `coerce_invalid_follow_ups` model_validator |
| Empty strings pass validation | Backend | Added `min_length=1` to all content fields |
| Timeout budget underestimated | Backend | Increased `PRIMARY_TIMEOUT_S` to 25s |
| Clipboard error handler missing | Frontend, Arch | Added try/catch with error feedback |
| Gmail URL truncation not in code | Frontend, Arch | Added MAX_BODY/MAX_SUBJECT truncation in handler |
| No accessibility | Frontend | Added `aria-label`, `aria-live` to container and buttons |
| Non-null assertions `!` | Frontend | Replaced with `$()` helper pattern |
| `recipient_hint` unused tokens | Architect | Removed from schema; re-add when recipient auto-fill is built |
| Gmail tab creation failure | Frontend | Added `.catch()` handler |
| Double-click on CRM button | Frontend | Added `btn.disabled` debounce guard |
