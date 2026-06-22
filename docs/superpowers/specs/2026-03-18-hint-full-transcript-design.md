# FEAT-010: Full Conversation History for Hint Generation

**Status:** DRAFT
**Date:** 2026-03-18
**Author:** Claude

## Problem

The hint generation pipeline currently sends only the **current utterance** to the LLM, with no conversation history. The `session_summary` field is always empty because `update_summary()` is never called. This means the LLM generates hints without knowing what was said earlier in the call, reducing hint accuracy and relevance.

## Solution

Pass the conversation transcript (from `eval_transcript:{session_id}`) into the LLM prompt so hints are context-aware. Add a configurable parameter `hint_context_utterances` to control how many past utterances are included (default: 50).

## Design

### 1. New Setting

**File:** `backend/config.py`

Add to `Settings`:
```python
hint_context_utterances: int = 50  # 0 = all, N = last N utterances
```

Controllable via env var `HINT_CONTEXT_UTTERANCES`. Default 50 balances context quality vs token cost. Set to 0 for unbounded history (operator's choice).

### 2. HintContext Changes

**File:** `backend/pipeline/types.py`

Add field to `HintContext`:
```python
@dataclass
class HintContext:
    utterance: str
    speaker: str
    rag_context: list[str]
    session_summary: str = ""  # kept for backward compat, no longer populated
    conversation_history: list[dict[str, str]] = field(default_factory=list)
```

`conversation_history` is a list of `{"speaker": "rep"|"client", "text": "..."}` dicts — the same format already stored in Redis.

### 3. SessionManager: New Method

**File:** `backend/session/manager.py`

Add a method to read conversation history from `eval_transcript` (the full, untrimmed list). This keeps Redis access encapsulated in the session layer — the orchestrator does not need a direct Redis reference.

```python
async def get_conversation_history(
    self, session_id: str, limit: int = 0, exclude_last: bool = False,
) -> list[dict[str, str]]:
    """Read conversation history from eval_transcript.

    Args:
        session_id: Session identifier.
        limit: Max utterances to return. 0 = all.
        exclude_last: If True, exclude the last entry (to avoid duplicating
                      the current utterance which was already appended).
    """
    if self._redis is None:
        return []
    end = -2 if exclude_last else -1
    if limit == 0:
        raw: list[bytes] = await self._redis.lrange(
            eval_transcript(session_id), 0, end
        )
    else:
        start = -(limit + (1 if exclude_last else 0))
        raw = await self._redis.lrange(
            eval_transcript(session_id), start, end
        )
    history: list[dict[str, str]] = []
    for item in raw:
        try:
            history.append(json.loads(item))
        except json.JSONDecodeError:
            logger.warning("Session %s: corrupt eval_transcript entry skipped", session_id)
    return history
```

**Key detail — `exclude_last=True`:** In `handle_transcript()` (orchestrator.py), `add_utterance()` runs **before** `_run_pipeline()`. The current utterance is already in `eval_transcript` by the time history is read. Using `exclude_last=True` (LRANGE end=-2) prevents the current utterance from appearing twice in the prompt — once in history and once as `Реплика: «{utterance}»`.

### 4. Orchestrator Changes

**File:** `backend/pipeline/orchestrator.py`

**Constructor:** Add `hint_context_utterances: int = 50` parameter, store as `self._hint_context_utterances`.

**`_run_pipeline()`:** Replace the `get_context()` call with `get_conversation_history()`. Remove the dead `summary` variable.

```python
async def _run_pipeline(self, query: str, speaker: str = "client") -> None:
    # ... cooldown check ...

    try:
        history = await self._session.get_conversation_history(
            self._session_id,
            limit=self._hint_context_utterances,
            exclude_last=True,
        )
    except Exception:
        history = []

    hint_ctx = HintContext(
        utterance=query,
        speaker=speaker,
        rag_context=[self._formatted_scenario] if self._formatted_scenario else [],
        conversation_history=history,
    )
    # ... generate hint ...
```

**Wiring in `ws/handler.py`:** Pass `hint_context_utterances=cfg.hint_context_utterances` when constructing `PipelineOrchestrator`.

**Cleanup:** Remove the dead `get_context()` call and `summary` variable from `_run_pipeline()`. This eliminates one wasted Redis LRANGE + GET per pipeline invocation.

### 5. LLM Prompt Changes

**File:** `backend/pipeline/llm.py`

Update `_USER_TEMPLATE`:

```python
_USER_TEMPLATE = (
    "Говорит: {speaker}\n"
    "Реплика: «{utterance}»\n\n"
    "БРИФИНГ:\n{rag_context}\n\n"
    "ИСТОРИЯ РАЗГОВОРА:\n{conversation_history}\n\n"
    "JSON (заполняй поля в этом порядке):\n"
    '{{"reasoning": "кратко: тема реплики vs ТЕМА РАЗГОВОРА", '
    '"relevance": "on_topic|off_topic", '
    '"hint": "краткая подсказка", "source": "файл, стр.", '
    '"sentiment": "positive|neutral|negative", "color": "green|blue|red", '
    '"coaching": "совет по тону (опционально)"}}'
)
```

Update `.format()` call in `generate_hint_stream()`:

```python
content=_USER_TEMPLATE.format(
    speaker=ctx.speaker,
    utterance=ctx.utterance,
    rag_context="\n".join(ctx.rag_context),
    conversation_history=_format_history(ctx.conversation_history),
),
```

Add module-level helper:

```python
def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(начало разговора)"
    return "\n".join(f"{u['speaker']}: {u['text']}" for u in history)
```

### 6. Data Flow

```
eval_transcript:{session_id}  (Redis list, all utterances)
         │
         │ SessionManager.get_conversation_history()
         │ LRANGE 0 -2  (exclude last = current utterance)
         │   or LRANGE -N -2  (last N, exclude current)
         ▼
  orchestrator._run_pipeline()
         │
         │ builds HintContext with conversation_history
         ▼
  llm.generate_hint_stream()
         │
         │ _format_history() → "rep: ...\nclient: ..."
         │ inserted into _USER_TEMPLATE
         ▼
  LLM generates context-aware hint
```

### 7. Token Budget Consideration

System prompt: ~500 tokens. Briefing: ~500-2000 tokens. Each utterance: ~10-50 tokens.

| Call duration | ~Utterances | History tokens (all) | History tokens (limit=50) |
|---------------|-------------|---------------------|--------------------------|
| 5 min         | 20-40       | 200-2000            | 200-2000                 |
| 15 min        | 60-100      | 600-5000            | 500-2500                 |
| 30 min        | 100-200     | 1000-10000          | 500-2500                 |
| 60 min        | 200-400     | 2000-20000          | 500-2500                 |

Default limit=50 keeps history under ~2500 tokens for any call length. With `llm_primary_timeout_ms=1000`, this is safe for Gemini 2.5 Flash.

Setting `HINT_CONTEXT_UTTERANCES=0` removes the limit — suitable for operators with generous token budgets who want maximum accuracy on long calls.

### 8. What Changes

| File | Change |
|------|--------|
| `backend/config.py` | Add `hint_context_utterances: int = 50` |
| `backend/pipeline/types.py` | Add `conversation_history` field to `HintContext` |
| `backend/session/manager.py` | Add `get_conversation_history()` method |
| `backend/pipeline/orchestrator.py` | Add `hint_context_utterances` constructor param; replace `get_context()` with `get_conversation_history()` in `_run_pipeline()` |
| `backend/pipeline/llm.py` | Update `_USER_TEMPLATE`; add `_format_history()` helper; update `.format()` call |
| `backend/ws/handler.py` | Pass `hint_context_utterances` to orchestrator constructor |
| `backend/tests/test_pipeline.py` | Update tests for new orchestrator param and history loading |
| `backend/tests/test_llm.py` | Update tests for new prompt template |

### 9. What Does NOT Change

- `eval_transcript:{session_id}` storage — already works correctly
- `SessionManager.add_utterance()` — no changes needed
- Extension/frontend — no changes
- Evaluation pipeline — no changes

### 10. Cleanup (part of this change)

- Remove dead `get_context()` call from `_run_pipeline()` (saves 2 Redis ops per hint)
- `session_summary` field in `HintContext` kept with default `""` for backward compat but no longer populated

### 11. Risks

- **Increased token usage**: Mitigated by default limit=50 and configurable setting.
- **Increased latency**: ~50 utterances add ~100-300ms input processing. Within 1s primary timeout for flash models.
- **Redis read overhead**: `LRANGE` on <1000 items is sub-millisecond. No concern.
- **Timeout interaction**: Large history + `llm_primary_timeout_ms=1000` may cause systematic fallbacks on very long calls with `limit=0`. Operators should increase timeout or keep default limit.

### 12. Testing

**Concrete test cases:**

1. **History loading — happy path**: Mock `redis.lrange` returning 3 JSON items → `get_conversation_history` returns 3 dicts
2. **History loading — empty**: Mock `redis.lrange` returning `[]` → returns `[]`
3. **History loading — corrupt JSON**: Mock with 3 items, 1 corrupt → returns 2 dicts, logs warning
4. **History loading — Redis is None**: `SessionManager(redis=None)` → returns `[]`
5. **History loading — limit=2**: Verify `lrange` called with `(-3, -2)` args (limit + exclude_last offset)
6. **History loading — exclude_last**: Verify `lrange` end index is `-2`
7. **Prompt formatting**: `_format_history([{"speaker":"rep","text":"hi"}])` → `"rep: hi"`
8. **Prompt formatting — empty**: `_format_history([])` → `"(начало разговора)"`
9. **LLM template**: `HintContext` with `conversation_history` produces prompt containing `"ИСТОРИЯ РАЗГОВОРА:\nrep: hi"`
10. **Orchestrator integration**: `_run_pipeline()` calls `session.get_conversation_history()` and passes result to `HintContext`
