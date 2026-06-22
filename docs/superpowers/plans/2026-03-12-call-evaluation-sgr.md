# FEAT-004: Call Evaluation SGR — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic sales call evaluation after session_end using Schema-Guided Reasoning (SGR) with configurable criteria, premium dark settings/report UI pages.

**Architecture:** Single-Pass SGR — one non-streaming LLM call with Pydantic `response_format=json_schema`, Cascade pattern (reasoning→score→comment). Backend recomputes overall_score. Extension displays summary in Phase 4 + full report in new tab.

**Tech Stack:** Python 3.11 (Pydantic v2, FastAPI, AsyncOpenAI), TypeScript (Chrome Extension MV3), Redis, OpenRouter API.

**Spec:** `docs/superpowers/specs/2026-03-12-call-evaluation-sgr-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/pipeline/evaluation_schemas.py` | Pydantic schemas: `EvaluationCriterion`, `EvaluationConfig`, `CriterionResult`, `CallEvaluation`, `DEFAULT_CRITERIA` |
| `backend/pipeline/evaluator_llm.py` | `EvaluatorLLMClient` — non-streaming LLM client with `response_format=json_schema`, primary/fallback |
| `backend/pipeline/evaluator.py` | `evaluate_call()` — prompt formatting, LLM call, reparse, score recomputation |
| `backend/api/evaluation.py` | FastAPI Router: CRUD config + GET evaluation result with token auth |
| `backend/tests/test_evaluation_schemas.py` | Tests for Pydantic schemas |
| `backend/tests/test_evaluator_llm.py` | Tests for EvaluatorLLMClient |
| `backend/tests/test_evaluator.py` | Tests for evaluate_call |
| `backend/tests/test_evaluation_api.py` | Tests for REST API endpoints |
| `extension/src/shared/evaluation-types.ts` | TypeScript interfaces for evaluation WS messages and data |
| `extension/src/report/report.html` | Full evaluation report page |
| `extension/src/report/report.css` | Report styles (premium dark) |
| `extension/src/report/report.ts` | Report logic — fetch + render |
| `extension/src/settings/evaluation-settings.html` | Criteria settings page |
| `extension/src/settings/evaluation-settings.css` | Settings styles (premium dark) |
| `extension/src/settings/evaluation-settings.ts` | Settings logic — CRUD criteria |

### Modified Files

| File | Change |
|------|--------|
| `backend/session/manager.py:46-54` | Dual-write: add `eval_transcript:{session_id}` alongside existing utterance key |
| `backend/pipeline/orchestrator.py:24-41,82-89` | Add `_evaluation_task`, `_evaluation_started`, `on_session_end()`, isolate from teardown |
| `backend/main.py:612-614,631-636` | Replace `session_end` break → evaluation trigger; await eval task in finally |
| `backend/main.py` (create_app) | Register evaluation router |
| `extension/src/shared/messages.ts:34-39` | Add evaluation types to `WsMessage` union |
| `extension/src/background/service-worker.ts:63-65,103-108,277-291` | Buffer `lastEvaluationResult`, forward eval messages, replay on reconnect |
| `extension/src/sidepanel/sidepanel.ts:453-472` | Handle `evaluation_started`, `evaluation_result`, `evaluation_error` in switch |
| `extension/src/sidepanel/sidepanel.html:192-219` | Add evaluation summary container in Phase 4 |
| `extension/src/sidepanel/sidepanel.css` | Evaluation summary styles |
| `extension/manifest.json` | Add report.html, evaluation-settings.html to web_accessible_resources |

---

## Chunk 1: Backend Core (Tasks 1–6)

### Task 1: Evaluation Schemas

**Files:**
- Create: `backend/pipeline/evaluation_schemas.py`
- Test: `backend/tests/test_evaluation_schemas.py`

- [ ] **Step 1: Write failing tests for schemas**

```python
# backend/tests/test_evaluation_schemas.py
"""Tests for evaluation SGR schemas (FEAT-004)."""
import pytest
from pydantic import ValidationError


def test_criterion_weight_bounds():
    from backend.pipeline.evaluation_schemas import EvaluationCriterion
    with pytest.raises(ValidationError):
        EvaluationCriterion(id="x", name="X", description="d", weight=1.5)
    with pytest.raises(ValidationError):
        EvaluationCriterion(id="x", name="X", description="d", weight=-0.1)


def test_config_weight_sum_validation():
    from backend.pipeline.evaluation_schemas import EvaluationConfig, EvaluationCriterion
    c = EvaluationCriterion(id="a", name="A", description="d", weight=0.3)
    with pytest.raises(ValidationError, match="1.0"):
        EvaluationConfig(criteria=[c])


def test_config_valid():
    from backend.pipeline.evaluation_schemas import EvaluationConfig, EvaluationCriterion
    c = EvaluationCriterion(id="a", name="A", description="d", weight=1.0)
    cfg = EvaluationConfig(criteria=[c])
    assert len(cfg.criteria) == 1


def test_default_criteria_valid():
    from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG
    assert abs(sum(c.weight for c in DEFAULT_CONFIG.criteria) - 1.0) < 0.01
    assert len(DEFAULT_CONFIG.criteria) == 7


def test_criterion_result_score_bounds():
    from backend.pipeline.evaluation_schemas import CriterionResult
    with pytest.raises(ValidationError):
        CriterionResult(
            criterion_id="x", criterion_name="X",
            reasoning="r", score=11, comment="c",
            recommendations=["a"],
        )


def test_call_evaluation_verdict_literal():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    data = {
        "call_summary": "s",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "invalid_value",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    with pytest.raises(ValidationError):
        CallEvaluation(**data)


def test_call_evaluation_json_schema_export():
    from backend.pipeline.evaluation_schemas import CallEvaluation
    schema = CallEvaluation.model_json_schema()
    assert "properties" in schema
    assert "call_summary" in schema["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluation_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.evaluation_schemas'`

- [ ] **Step 3: Implement evaluation_schemas.py**

```python
# backend/pipeline/evaluation_schemas.py
"""SGR schemas for call evaluation (FEAT-004)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class EvaluationCriterion(BaseModel):
    """One evaluation criterion."""

    id: str = Field(description="Unique ID: greeting, needs_discovery, etc.")
    name: str = Field(description="Criterion name in Russian")
    description: str = Field(description="Detailed description of what is evaluated")
    weight: float = Field(
        ge=0.0, le=1.0,
        description="Criterion weight (0.0–1.0, all must sum to 1.0)",
    )


class EvaluationConfig(BaseModel):
    """Evaluation config — stored in Redis, editable via UI."""

    criteria: Annotated[
        list[EvaluationCriterion], Field(min_length=1, max_length=10)
    ]
    model: str = Field(default="google/gemini-2.5-flash")

    @model_validator(mode="after")
    def validate_weights_sum(self) -> EvaluationConfig:
        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > 0.01:
            msg = f"Сумма весов критериев должна быть 1.0, получено: {total:.2f}"
            raise ValueError(msg)
        return self


class CriterionResult(BaseModel):
    """Single criterion evaluation result. Cascade: reasoning → score → comment."""

    criterion_id: str
    criterion_name: str
    reasoning: str = Field(
        description="Transcript analysis for this criterion — BEFORE scoring",
    )
    score: int = Field(ge=1, le=10, description="Score 1-10, assigned AFTER analysis")
    comment: str = Field(description="Brief conclusion for UI (1-2 sentences)")
    recommendations: list[str] = Field(
        min_length=1, max_length=3,
        description="Specific improvement recommendations (1-3 items)",
    )


class CallEvaluation(BaseModel):
    """Full call evaluation. Cascade: summary → criteria → overall → verdict."""

    call_summary: str = Field(description="Brief call summary (3-5 sentences)")
    criteria_results: list[CriterionResult] = Field(
        description="Evaluation per criterion",
    )
    overall_score: float = Field(
        ge=1.0, le=10.0,
        description="Computed on backend, NOT trusted from LLM",
    )
    verdict: Literal["excellent", "good", "satisfactory", "needs_improvement"] = Field(
        description="Computed on backend by overall_score",
    )
    strengths: list[str] = Field(
        min_length=2, max_length=4,
        description="Manager strengths in this call",
    )
    growth_areas: list[str] = Field(
        min_length=2, max_length=4,
        description="Growth areas — what manager can improve",
    )
    action_plan: list[str] = Field(
        min_length=3, max_length=5,
        description="Concrete steps for skill development",
    )


# ── Default B2B criteria ────────────────────────────────────────────────────

_DEFAULT_CRITERIA = [
    EvaluationCriterion(
        id="greeting",
        name="Приветствие и установление контакта",
        description=(
            "Менеджер представился (имя, компания), озвучил цель звонка, "
            "согласовал повестку, обращается к клиенту по имени, создал позитивный настрой"
        ),
        weight=0.10,
    ),
    EvaluationCriterion(
        id="needs_discovery",
        name="Выявление потребностей",
        description=(
            "Задавал открытые вопросы, выявил 3-4 проблемы/потребности, "
            "соотношение говорит/слушает близко к 43/57, активное слушание"
        ),
        weight=0.25,
    ),
    EvaluationCriterion(
        id="value_presentation",
        name="Презентация ценности",
        description=(
            "Привязал решение к выявленным потребностям, говорил о выгодах "
            "а не характеристиках, использовал цифры и кейсы"
        ),
        weight=0.15,
    ),
    EvaluationCriterion(
        id="objection_handling",
        name="Работа с возражениями",
        description=(
            "Выслушал возражение полностью, сделал паузу, признал точку зрения клиента, "
            "привёл аргумент с доказательствами, проверил снято ли возражение"
        ),
        weight=0.20,
    ),
    EvaluationCriterion(
        id="closing",
        name="Закрытие и следующие шаги",
        description=(
            "Предложил конкретный следующий шаг с привязкой ко времени, "
            "зафиксировал взаимные обязательства, подвёл итог разговора"
        ),
        weight=0.15,
    ),
    EvaluationCriterion(
        id="communication",
        name="Коммуникативные навыки",
        description=(
            "Ясная речь, подходящий темп, эмпатия, уверенность без высокомерия, "
            "адаптация к стилю собеседника"
        ),
        weight=0.10,
    ),
    EvaluationCriterion(
        id="strategy_adherence",
        name="Следование стратегии",
        description=(
            "Использовал тезисы из брифинга, работал по портрету клиента, "
            "применял подготовленные ответы на возражения"
        ),
        weight=0.05,
    ),
]

DEFAULT_CONFIG = EvaluationConfig(criteria=_DEFAULT_CRITERIA)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluation_schemas.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/evaluation_schemas.py backend/tests/test_evaluation_schemas.py
git commit -m "feat(eval): add SGR evaluation Pydantic schemas and defaults"
```

---

### Task 2: EvaluatorLLMClient

**Files:**
- Create: `backend/pipeline/evaluator_llm.py`
- Test: `backend/tests/test_evaluator_llm.py`
- Reference: `backend/pipeline/llm.py:92-110` (existing LLMClient pattern)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_evaluator_llm.py
"""Tests for EvaluatorLLMClient (FEAT-004)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.evaluator_llm import (
    EvalLLMTimeoutError,
    EvalLLMUnavailableError,
    EvaluatorLLMClient,
)


@pytest.fixture
def client():
    return EvaluatorLLMClient(api_key="test-key")


def _mock_response(content: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_evaluate_returns_parsed_json(client):
    payload = {"call_summary": "test", "score": 8}
    with patch.object(
        client._client.chat.completions, "create",
        new_callable=AsyncMock,
        return_value=_mock_response(payload),
    ):
        result = await client.evaluate("sys", "usr", {"type": "object"})
    assert result == payload


@pytest.mark.asyncio
async def test_evaluate_falls_back_on_timeout(client):
    payload = {"fallback": True}
    call_count = 0

    async def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await asyncio.sleep(100)  # simulate timeout
        return _mock_response(payload)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_side_effect,
    ):
        result = await client.evaluate("sys", "usr", {"type": "object"})
    assert result == payload
    assert call_count == 2


@pytest.mark.asyncio
async def test_evaluate_uses_response_format(client):
    schema = {"type": "object", "properties": {}}
    payload = {"ok": True}
    captured_kwargs = {}

    async def _capture(**kwargs):
        captured_kwargs.update(kwargs)
        return _mock_response(payload)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_capture,
    ):
        await client.evaluate("sys", "usr", schema)

    rf = captured_kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == schema
    assert captured_kwargs["stream"] is False


@pytest.mark.asyncio
async def test_evaluate_raises_timeout_when_both_fail(client):
    async def _always_timeout(**kwargs):
        await asyncio.sleep(100)

    with patch.object(
        client._client.chat.completions, "create",
        side_effect=_always_timeout,
    ):
        with pytest.raises(EvalLLMTimeoutError):
            await client.evaluate("sys", "usr", {"type": "object"})


@pytest.mark.asyncio
async def test_evaluate_raises_unavailable_on_non_timeout_error(client):
    with patch.object(
        client._client.chat.completions, "create",
        side_effect=RuntimeError("API 500"),
    ):
        with pytest.raises(EvalLLMUnavailableError):
            await client.evaluate("sys", "usr", {"type": "object"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluator_llm.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement evaluator_llm.py**

```python
# backend/pipeline/evaluator_llm.py
"""Non-streaming LLM client for call evaluation (FEAT-004)."""
from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI

from backend.logger import logger

PRIMARY_MODEL = "google/gemini-2.5-flash"
PRIMARY_TIMEOUT_S = 15.0
FALLBACK_MODEL = "openai/gpt-4.1-mini"
FALLBACK_TIMEOUT_S = 30.0


class EvalLLMTimeoutError(Exception):
    """Both primary and fallback LLM timed out."""


class EvalLLMUnavailableError(Exception):
    """LLM returned a non-timeout error (429, 500, etc.)."""


class EvaluatorLLMClient:
    """Non-streaming LLM client with response_format=json_schema."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def evaluate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> dict:
        """Single blocking call with json_schema response_format.

        Primary model: 15s timeout. On timeout → fallback model: 30s.
        Raises EvalLLMTimeoutError if both models time out.
        Raises EvalLLMUnavailableError on non-timeout LLM errors.
        """
        try:
            return await self._call_llm(
                PRIMARY_MODEL,
                system_prompt,
                user_prompt,
                json_schema,
                PRIMARY_TIMEOUT_S,
            )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("Primary eval model timeout, switching to fallback")
            try:
                return await self._call_llm(
                    FALLBACK_MODEL,
                    system_prompt,
                    user_prompt,
                    json_schema,
                    FALLBACK_TIMEOUT_S,
                )
            except (asyncio.TimeoutError, TimeoutError) as exc:
                raise EvalLLMTimeoutError("Both models timed out") from exc
            except Exception as exc:
                raise EvalLLMUnavailableError(str(exc)) from exc
        except Exception as exc:
            # Non-timeout error from primary → try fallback
            logger.warning("Primary eval model error: %r, trying fallback", exc)
            try:
                return await self._call_llm(
                    FALLBACK_MODEL,
                    system_prompt,
                    user_prompt,
                    json_schema,
                    FALLBACK_TIMEOUT_S,
                )
            except (asyncio.TimeoutError, TimeoutError) as fb_exc:
                raise EvalLLMTimeoutError("Fallback timed out") from fb_exc
            except Exception as fb_exc:
                raise EvalLLMUnavailableError(str(fb_exc)) from fb_exc

    async def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
        timeout_s: float,
    ) -> dict:
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "CallEvaluation",
                        "schema": json_schema,
                    },
                },
                stream=False,
            ),
            timeout=timeout_s,
        )
        return json.loads(response.choices[0].message.content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluator_llm.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/evaluator_llm.py backend/tests/test_evaluator_llm.py
git commit -m "feat(eval): add EvaluatorLLMClient with json_schema response_format"
```

---

### Task 3: Evaluator (prompt + score recomputation)

**Files:**
- Create: `backend/pipeline/evaluator.py`
- Test: `backend/tests/test_evaluator.py`
- Reference: `backend/pipeline/evaluation_schemas.py`, `backend/pipeline/evaluator_llm.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_evaluator.py
"""Tests for evaluate_call (FEAT-004)."""
import json
from unittest.mock import AsyncMock

import pytest

from backend.pipeline.evaluation_schemas import (
    DEFAULT_CONFIG,
    CallEvaluation,
    EvaluationConfig,
)
from backend.pipeline.evaluator import (
    _compute_overall_score,
    _compute_verdict,
    _format_criteria_list,
    _truncate_transcript,
    evaluate_call,
)


def test_compute_overall_score():
    config = DEFAULT_CONFIG
    # Build fake results matching default criteria
    scores = {
        "greeting": 8, "needs_discovery": 7, "value_presentation": 6,
        "objection_handling": 9, "closing": 5, "communication": 7,
        "strategy_adherence": 8,
    }
    results = [
        type("R", (), {"criterion_id": cid, "score": s})()
        for cid, s in scores.items()
    ]
    overall = _compute_overall_score(results, config)
    expected = sum(
        scores[c.id] * c.weight for c in config.criteria
    )
    assert abs(overall - expected) < 0.01


def test_compute_verdict():
    assert _compute_verdict(8.5) == "excellent"
    assert _compute_verdict(7.0) == "good"
    assert _compute_verdict(5.0) == "satisfactory"
    assert _compute_verdict(3.0) == "needs_improvement"


def test_format_criteria_list():
    config = DEFAULT_CONFIG
    text = _format_criteria_list(config)
    assert "Приветствие" in text
    assert "10%" in text


def test_truncate_transcript_short():
    lines = [f"line {i}" for i in range(10)]
    result = _truncate_transcript(lines)
    assert len(result.split("\n")) == 10


def test_truncate_transcript_long():
    # Create transcript exceeding ~12K tokens (~48K chars)
    lines = ["x" * 200 for _ in range(300)]
    result = _truncate_transcript(lines)
    assert len(result) < 60_000  # must be truncated


@pytest.mark.asyncio
async def test_evaluate_call_recomputes_score():
    """evaluate_call must recompute overall_score, not trust LLM."""
    llm_response = {
        "call_summary": "Test call",
        "criteria_results": [
            {
                "criterion_id": c.id,
                "criterion_name": c.name,
                "reasoning": "ok",
                "score": 7,
                "comment": "ok",
                "recommendations": ["improve"],
            }
            for c in DEFAULT_CONFIG.criteria
        ],
        "overall_score": 1.0,  # LLM lies
        "verdict": "needs_improvement",  # LLM lies
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }
    mock_llm = AsyncMock()
    mock_llm.evaluate.return_value = llm_response

    transcript = [json.dumps({"speaker": "rep", "text": "Hello"})]
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
        briefing="Test briefing",
    )

    assert isinstance(result, CallEvaluation)
    # All scores are 7 → overall must be 7.0, not 1.0 (LLM's lie)
    assert abs(result.overall_score - 7.0) < 0.01
    assert result.verdict == "good"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement evaluator.py**

```python
# backend/pipeline/evaluator.py
"""Call evaluator: prompt formatting, LLM call, score recomputation (FEAT-004)."""
from __future__ import annotations

import json
from typing import Any

from backend.logger import logger
from backend.pipeline.evaluation_schemas import (
    CallEvaluation,
    CriterionResult,
    EvaluationConfig,
)
from backend.pipeline.evaluator_llm import EvaluatorLLMClient


class EvalParseFailedError(Exception):
    """JSON from LLM failed Pydantic validation after reparse."""

_MAX_TRANSCRIPT_CHARS = 48_000  # ~12K tokens (chars // 4)
_HEAD_CHARS = 16_000  # first ~4K tokens
_TAIL_CHARS = 32_000  # last ~8K tokens

_SYSTEM_PROMPT = (
    "Ты — опытный руководитель отдела продаж (РОП) с 10+ годами опыта в B2B-продажах.\n"
    "Твоя задача — оценить качество телефонного разговора менеджера по продажам.\n\n"
    "Правила оценки:\n"
    "- Анализируй ТОЛЬКО то, что есть в транскрипте. Не додумывай.\n"
    "- Для каждого критерия СНАЧАЛА проведи анализ (reasoning), ПОТОМ выставляй оценку.\n"
    "- Оценка 1-10: 1-3 = плохо, 4-5 = ниже среднего, 6-7 = хорошо, 8-9 = отлично, 10 = идеально.\n"
    "- Рекомендации должны быть конкретными и actionable, не общими фразами.\n"
    "- Если критерий неприменим к данному звонку, поставь 5 и укажи в reasoning что оценка нейтральная.\n"
    "- Учитывай брифинг: оценивай насколько менеджер следовал подготовленной стратегии.\n"
    "- Все ответы на русском языке.\n\n"
    "Бенчмарки (данные Gong, 519K+ звонков):\n"
    "- Оптимальное соотношение говорит/слушает: 43%/57%\n"
    "- Оптимальное количество выявленных проблем: 3-4\n"
    "- Успешные менеджеры делают паузу перед ответом на возражение\n"
    "- Конкретный next step повышает конверсию в 2.7 раза"
)

_USER_TEMPLATE = (
    "ТРАНСКРИПТ ЗВОНКА:\n{transcript}\n\n"
    "БРИФИНГ (подготовка к звонку):\n{briefing}\n\n"
    "КРИТЕРИИ ОЦЕНКИ:\n{criteria_list}\n\n"
    "Оцени звонок по каждому критерию. Ответ — ТОЛЬКО валидный JSON по схеме CallEvaluation."
)


def _format_criteria_list(config: EvaluationConfig) -> str:
    """Format criteria as numbered list for LLM prompt."""
    lines: list[str] = []
    for i, c in enumerate(config.criteria, 1):
        pct = int(c.weight * 100)
        lines.append(f"{i}. {c.name} (вес: {pct}%) — {c.description}")
    return "\n".join(lines)


def _truncate_transcript(raw_lines: list[str]) -> str:
    """Join transcript lines and truncate to ~12K tokens if needed."""
    parsed_lines: list[str] = []
    for line in raw_lines:
        try:
            item = json.loads(line)
            parsed_lines.append(f"{item['speaker']}: {item['text']}")
        except (json.JSONDecodeError, KeyError):
            parsed_lines.append(str(line))

    full = "\n".join(parsed_lines)
    if len(full) <= _MAX_TRANSCRIPT_CHARS:
        return full

    head = full[:_HEAD_CHARS]
    tail = full[-_TAIL_CHARS:]
    return f"{head}\n\n[... часть транскрипта пропущена ...]\n\n{tail}"


def _compute_overall_score(
    results: list[Any],
    config: EvaluationConfig,
) -> float:
    """Recompute overall_score as weighted average. Do NOT trust LLM."""
    weight_map = {c.id: c.weight for c in config.criteria}
    total = 0.0
    for r in results:
        w = weight_map.get(r.criterion_id, 0.0)
        total += r.score * w
    return round(total, 2)


def _compute_verdict(score: float) -> str:
    """Compute verdict from overall_score."""
    if score >= 8.0:
        return "excellent"
    if score >= 6.0:
        return "good"
    if score >= 4.0:
        return "satisfactory"
    return "needs_improvement"


async def evaluate_call(
    *,
    llm_client: EvaluatorLLMClient,
    transcript_raw: list[str | bytes],
    config: EvaluationConfig,
    briefing: str = "",
) -> CallEvaluation:
    """Run full evaluation pipeline: format → LLM → validate → recompute."""
    lines = [
        line.decode() if isinstance(line, bytes) else line
        for line in transcript_raw
    ]
    transcript_text = _truncate_transcript(lines)
    criteria_list = _format_criteria_list(config)

    user_prompt = _USER_TEMPLATE.format(
        transcript=transcript_text,
        briefing=briefing or "(брифинг не предоставлен)",
        criteria_list=criteria_list,
    )

    schema = CallEvaluation.model_json_schema()

    raw = await llm_client.evaluate(_SYSTEM_PROMPT, user_prompt, schema)

    # Try to parse; on failure, reparse once with error feedback
    try:
        evaluation = CallEvaluation.model_validate(raw)
    except Exception as first_err:
        logger.warning("First parse failed: %s — attempting reparse", first_err)
        reparse_prompt = (
            f"Предыдущий JSON не прошёл валидацию: {first_err!s}\n"
            "Исправь: 1) проверь типы, 2) проверь обязательные поля, "
            "3) верни ТОЛЬКО JSON.\n\n"
            f"Исходный запрос:\n{user_prompt}"
        )
        raw = await llm_client.evaluate(_SYSTEM_PROMPT, reparse_prompt, schema)
        try:
            evaluation = CallEvaluation.model_validate(raw)
        except Exception as second_err:
            raise EvalParseFailedError(
                f"Reparse also failed: {second_err}"
            ) from second_err

    # Recompute score — do NOT trust LLM
    evaluation.overall_score = _compute_overall_score(
        evaluation.criteria_results, config,
    )
    evaluation.verdict = _compute_verdict(evaluation.overall_score)

    return evaluation
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/evaluator.py backend/tests/test_evaluator.py
git commit -m "feat(eval): add evaluate_call with prompt formatting and score recomputation"
```

---

### Task 4: REST API for evaluation config + result

**Files:**
- Create: `backend/api/__init__.py` (empty, if missing)
- Create: `backend/api/evaluation.py`
- Test: `backend/tests/test_evaluation_api.py`
- Modify: `backend/main.py` (register router — Task 6)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_evaluation_api.py
"""Tests for evaluation REST API (FEAT-004)."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.delete = AsyncMock()
    return r


@pytest.fixture
def app(mock_redis):
    a = FastAPI()
    a.state.redis = mock_redis
    from backend.api.evaluation import router as eval_router
    a.include_router(eval_router, prefix="/api/v1")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_get_config_returns_default(client, mock_redis):
    mock_redis.get.return_value = None
    resp = client.get("/api/v1/evaluation-config")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["criteria"]) == 7


def test_put_config_saves(client, mock_redis):
    payload = DEFAULT_CONFIG.model_dump()
    resp = client.put("/api/v1/evaluation-config", json=payload)
    assert resp.status_code == 200
    mock_redis.set.assert_called_once()


def test_put_config_invalid_weights(client, mock_redis):
    payload = DEFAULT_CONFIG.model_dump()
    payload["criteria"][0]["weight"] = 0.99  # sum > 1.0
    resp = client.put("/api/v1/evaluation-config", json=payload)
    assert resp.status_code == 422


def test_reset_config(client, mock_redis):
    resp = client.post("/api/v1/evaluation-config/reset")
    assert resp.status_code == 200
    mock_redis.delete.assert_called_once()


def test_get_evaluation_requires_token(client, mock_redis):
    resp = client.get("/api/v1/evaluation/test-session")
    assert resp.status_code == 403


def test_get_evaluation_invalid_token(client, mock_redis):
    mock_redis.get.side_effect = lambda k: (
        b"real-token" if "eval_token" in k else None
    )
    resp = client.get("/api/v1/evaluation/test-session?token=wrong")
    assert resp.status_code == 403


def test_get_evaluation_success(client, mock_redis):
    eval_data = {
        "call_summary": "test",
        "criteria_results": [],
        "overall_score": 7.0,
        "verdict": "good",
        "strengths": ["a", "b"],
        "growth_areas": ["a", "b"],
        "action_plan": ["a", "b", "c"],
    }

    async def _get(key):
        if "eval_token" in key:
            return b"valid-token"
        if "eval:" in key:
            return json.dumps(eval_data).encode()
        return None

    mock_redis.get = AsyncMock(side_effect=_get)
    resp = client.get("/api/v1/evaluation/test-session?token=valid-token")
    assert resp.status_code == 200
    assert resp.json()["call_summary"] == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluation_api.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement evaluation API**

```python
# backend/api/__init__.py
```

```python
# backend/api/evaluation.py
"""REST API for evaluation config and results (FEAT-004)."""
from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, EvaluationConfig

_CONFIG_KEY = "eval_config:default"

router = APIRouter()


def _get_redis(request: Request) -> Any:
    """FastAPI dependency: get Redis from app.state."""
    return getattr(request.app.state, "redis", None)


async def _load_config(redis: Any) -> EvaluationConfig:
    if redis is None:
        return DEFAULT_CONFIG
    raw = await redis.get(_CONFIG_KEY)
    if raw is None:
        return DEFAULT_CONFIG
    data = json.loads(raw)
    return EvaluationConfig.model_validate(data)


@router.get("/evaluation-config")
async def get_config(redis: Any = Depends(_get_redis)) -> dict:
    config = await _load_config(redis)
    return config.model_dump()


@router.put("/evaluation-config")
async def put_config(
    payload: EvaluationConfig,
    redis: Any = Depends(_get_redis),
) -> dict:
    if redis is not None:
        await redis.set(_CONFIG_KEY, payload.model_dump_json())
    return payload.model_dump()


@router.post("/evaluation-config/reset")
async def reset_config(redis: Any = Depends(_get_redis)) -> dict:
    if redis is not None:
        await redis.delete(_CONFIG_KEY)
    return DEFAULT_CONFIG.model_dump()


@router.get("/evaluation/{session_id}")
async def get_evaluation(
    session_id: str,
    token: str = Query(default=""),
    redis: Any = Depends(_get_redis),
) -> dict:
    if not token:
        raise HTTPException(status_code=403, detail="Token required")
    if redis is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    stored_token = await redis.get(f"eval_token:{session_id}")
    if stored_token is None:
        raise HTTPException(status_code=403, detail="Invalid token")

    stored_str = (
        stored_token.decode()
        if isinstance(stored_token, bytes)
        else stored_token
    )
    if not hmac.compare_digest(stored_str, token):
        raise HTTPException(status_code=403, detail="Invalid token")

    raw = await redis.get(f"eval:{session_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    data = json.loads(raw)
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluation_api.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/api/__init__.py backend/api/evaluation.py backend/tests/test_evaluation_api.py
git commit -m "feat(eval): add REST API for evaluation config and results"
```

---

### Task 5: SessionManager dual-write

**Files:**
- Modify: `backend/session/manager.py:46-54`
- Test: `backend/tests/test_session_manager_eval.py` (new test file)

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_session_manager_eval.py
"""Tests for SessionManager eval_transcript dual-write (FEAT-004)."""
import pytest
from unittest.mock import AsyncMock, call


@pytest.mark.asyncio
async def test_add_utterance_writes_eval_transcript():
    """add_utterance must write to eval_transcript:{sid} without ltrim."""
    from backend.session.manager import SessionManager

    mock_redis = AsyncMock()
    pipe = AsyncMock()
    pipe.execute = AsyncMock(return_value=[])
    mock_redis.pipeline.return_value = pipe

    mgr = SessionManager(redis=mock_redis)
    await mgr.add_utterance("sess-1", "rep", "Hello")

    mock_redis.pipeline.assert_called_once()
    # Check that both keys are written
    rpush_calls = [c for c in pipe.rpush.call_args_list]
    assert len(rpush_calls) == 2
    keys_written = {c.args[0] for c in rpush_calls}
    assert "session:sess-1:utterances" in keys_written
    assert "eval_transcript:sess-1" in keys_written

    # Check ltrim only on session key (not eval key)
    ltrim_calls = pipe.ltrim.call_args_list
    assert len(ltrim_calls) == 1
    assert ltrim_calls[0].args[0] == "session:sess-1:utterances"

    # Check eval key gets 24h TTL
    expire_calls = pipe.expire.call_args_list
    eval_expire = [c for c in expire_calls if c.args[0] == "eval_transcript:sess-1"]
    assert len(eval_expire) == 1
    assert eval_expire[0].args[1] == 86400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_session_manager_eval.py -v`
Expected: FAIL — assertion on `pipeline` usage (current code uses individual calls, not pipeline)

- [ ] **Step 3: Modify SessionManager.add_utterance()**

In `backend/session/manager.py`, replace the `add_utterance` method (lines 46-55):

```python
    async def add_utterance(self, session_id: str, speaker: str, text: str) -> None:
        """Append utterance to Redis list, keeping last _MAX_UTTERANCES.

        Also writes to eval_transcript:{session_id} (no trim) for evaluation.
        """
        if self._redis is None:
            return
        utter_key = self._utter_key(session_id)
        eval_key = f"eval_transcript:{session_id}"
        payload = json.dumps({"speaker": speaker, "text": text})

        pipe = self._redis.pipeline()
        pipe.rpush(utter_key, payload)
        pipe.ltrim(utter_key, -_MAX_UTTERANCES, -1)
        pipe.expire(utter_key, _TTL_SECONDS)
        pipe.rpush(eval_key, payload)          # no ltrim for eval
        pipe.expire(eval_key, 86400)           # 24h TTL
        await pipe.execute()
        logger.debug("Session %s: added utterance from %s", session_id, speaker)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_session_manager_eval.py -v`
Expected: PASS

Also run existing SessionManager tests to check no regression:
Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/ -k "session" -v`

- [ ] **Step 5: Commit**

```bash
git add backend/session/manager.py backend/tests/test_session_manager_eval.py
git commit -m "feat(eval): dual-write eval_transcript in SessionManager"
```

---

### Task 6: Orchestrator + main.py integration

**Files:**
- Modify: `backend/pipeline/orchestrator.py:24-41,82-89`
- Modify: `backend/main.py:612-614,631-636`
- Test: `backend/tests/test_orchestrator_eval.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_orchestrator_eval.py
"""Tests for orchestrator evaluation integration (FEAT-004)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.orchestrator import PipelineOrchestrator


@pytest.fixture
def orch():
    ws = AsyncMock()
    llm = MagicMock()
    session = AsyncMock()
    return PipelineOrchestrator(
        ws=ws,
        session_id="test-123",
        llm_client=llm,
        session_manager=session,
        eval_api_key="test-key",
    )


def test_evaluation_started_flag_default(orch):
    assert orch._evaluation_started is False
    assert orch._evaluation_task is None


@pytest.mark.asyncio
async def test_on_session_end_sets_flag(orch):
    """on_session_end should set _evaluation_started and create task."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    with patch.object(orch, "_redis", redis, create=True):
        await orch.on_session_end("test-123", orch._ws, redis)
    assert orch._evaluation_started is True
    assert orch._evaluation_task is not None


@pytest.mark.asyncio
async def test_on_session_end_idempotent(orch):
    """Second call to on_session_end should be a no-op."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    with patch.object(orch, "_redis", redis, create=True):
        await orch.on_session_end("test-123", orch._ws, redis)
        task1 = orch._evaluation_task
        await orch.on_session_end("test-123", orch._ws, redis)
        task2 = orch._evaluation_task
    assert task1 is task2


@pytest.mark.asyncio
async def test_teardown_does_not_cancel_evaluation(orch):
    """teardown() must NOT cancel _evaluation_task."""
    redis = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    with patch.object(orch, "_redis", redis, create=True):
        await orch.on_session_end("test-123", orch._ws, redis)
        eval_task = orch._evaluation_task
        await orch.teardown()
    # eval_task should not be cancelled by teardown
    assert eval_task is not None
    assert eval_task not in orch._background_tasks
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_orchestrator_eval.py -v`
Expected: FAIL — `_evaluation_started` / `on_session_end` not found

- [ ] **Step 3: Modify orchestrator.py**

Add to `__init__` signature — add `eval_api_key: str = ""` parameter. After line 41, add:
```python
        self._eval_api_key = eval_api_key
        self._evaluation_task: asyncio.Task | None = None
        self._evaluation_started: bool = False
```

Add new methods after `teardown()`:
```python
    async def on_session_end(
        self,
        session_id: str,
        ws: Any,
        redis: Any,
    ) -> None:
        """Trigger evaluation as a separate asyncio.Task (not in _background_tasks)."""
        if self._evaluation_started:
            return
        self._evaluation_started = True
        self._evaluation_task = asyncio.create_task(
            self._run_evaluation(session_id, ws, redis)
        )

    async def _run_evaluation(
        self,
        session_id: str,
        ws: Any,
        redis: Any,
    ) -> None:
        """Run full evaluation pipeline. Isolated from hint tasks."""
        import contextlib
        import json as _json
        import secrets

        from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, EvaluationConfig
        from backend.pipeline.evaluator import EvalParseFailedError, evaluate_call
        from backend.pipeline.evaluator_llm import (
            EvalLLMTimeoutError,
            EvalLLMUnavailableError,
            EvaluatorLLMClient,
        )

        error_code = "EVAL_INTERNAL_ERROR"
        try:
            # Load transcript from eval-specific key
            transcript_raw: list[bytes] = await redis.lrange(
                f"eval_transcript:{session_id}", 0, 3999,
            )
            if not transcript_raw:
                with contextlib.suppress(Exception):
                    await ws.send_json({
                        "type": "evaluation_error",
                        "session_id": session_id,
                        "code": "EVAL_EMPTY_TRANSCRIPT",
                        "message": "Транскрипт пуст",
                    })
                return

            # Load config
            raw_config = await redis.get("eval_config:default")
            if raw_config:
                config = EvaluationConfig.model_validate(_json.loads(raw_config))
            else:
                config = DEFAULT_CONFIG

            # Get briefing from scenario
            briefing = self._scenario_text or ""

            # Use API key passed at construction time (not re-read from Settings)
            eval_llm = EvaluatorLLMClient(api_key=self._eval_api_key)

            result = await evaluate_call(
                llm_client=eval_llm,
                transcript_raw=transcript_raw,
                config=config,
                briefing=briefing,
            )

            # Save result + token to Redis
            result_json = result.model_dump_json()
            eval_token = secrets.token_urlsafe(16)

            await redis.set(f"eval:{session_id}", result_json, ex=86400)
            await redis.set(f"eval_token:{session_id}", eval_token, ex=86400)

            # Send to client
            with contextlib.suppress(Exception):
                await ws.send_json({
                    "type": "evaluation_result",
                    "session_id": session_id,
                    "eval_token": eval_token,
                    "evaluation": result.model_dump(),
                })
            return  # success — skip error sending below

        except EvalLLMTimeoutError:
            error_code = "EVAL_LLM_TIMEOUT"
        except EvalLLMUnavailableError:
            error_code = "EVAL_LLM_UNAVAILABLE"
        except EvalParseFailedError:
            error_code = "EVAL_PARSE_FAILED"
        except Exception:
            error_code = "EVAL_INTERNAL_ERROR"

        logger.exception("Evaluation failed (%s) for session %s", error_code, session_id)
        with contextlib.suppress(Exception):
            await ws.send_json({
                "type": "evaluation_error",
                "session_id": session_id,
                "code": error_code,
                "message": "Не удалось оценить звонок",
            })
```

- [ ] **Step 4: Modify main.py — four changes**

**4a.** Pass `eval_api_key` to `PipelineOrchestrator` (around line 552-559):

```python
                            orchestrator = PipelineOrchestrator(
                                ws=websocket,
                                session_id=session_id,
                                llm_client=llm,
                                session_manager=session_mgr,
                                scenario_text=scenario_text,
                                kb_id=kb_id,
                                eval_api_key=cfg.openrouter_api_key,  # NEW
                            )
```

**4b.** Replace binary control-frame `session_end` handler (lines 612-614):

```python
                    elif ctrl_type == "session_end":
                        logger.info(f"Session end: {session_id}")
                        await websocket.send_json({
                            "type": "evaluation_started",
                            "session_id": session_id,
                        })
                        if orchestrator is not None:
                            await orchestrator.on_session_end(
                                session_id, websocket, redis_client,
                            )
                        break
```

**4c.** Also patch the text-frame fallback `session_end` path (lines 493-495):

```python
                        try:
                            if _json.loads(text).get("type") == "session_end":
                                logger.info(f"Session end (text frame): {session_id}")
                                await websocket.send_json({
                                    "type": "evaluation_started",
                                    "session_id": session_id,
                                })
                                if orchestrator is not None:
                                    await orchestrator.on_session_end(
                                        session_id, websocket, redis_client,
                                    )
                                break
                        except Exception:
                            pass
```

**4d.** Replace finally block (lines 631-636):

```python
        finally:
            if orchestrator is not None:
                await orchestrator.teardown()
                if orchestrator._evaluation_task is not None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await asyncio.wait_for(
                            orchestrator._evaluation_task, timeout=35.0,
                        )
            if stt is not None:
                await stt.close()
            logger.info(f"WebSocket cleanup done: session={session_id}")
```

**4e.** Register evaluation router in `create_app()` — before `return app` (line 638):

```python
    from backend.api.evaluation import router as evaluation_router
    app.include_router(evaluation_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_orchestrator_eval.py -v`
Expected: All 4 tests PASS

Also run all backend tests for regression:
Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/ -v`

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/main.py backend/tests/test_orchestrator_eval.py
git commit -m "feat(eval): integrate evaluation into orchestrator and main.py session_end"
```

---

## Chunk 2: Extension Types & Service Worker (Tasks 7–8)

### Task 7: TypeScript evaluation types + messages.ts

**Files:**
- Create: `extension/src/shared/evaluation-types.ts`
- Modify: `extension/src/shared/messages.ts:34-39`

- [ ] **Step 1: Create evaluation-types.ts**

```typescript
// extension/src/shared/evaluation-types.ts
/** TypeScript types for call evaluation (FEAT-004). */

export interface CriterionResultWire {
  criterion_id: string;
  criterion_name: string;
  reasoning: string;
  score: number;
  comment: string;
  recommendations: string[];
}

export interface CallEvaluationResult {
  call_summary: string;
  criteria_results: CriterionResultWire[];
  overall_score: number;
  verdict: "excellent" | "good" | "satisfactory" | "needs_improvement";
  strengths: string[];
  growth_areas: string[];
  action_plan: string[];
}

export interface WsEvaluationStarted {
  type: "evaluation_started";
  session_id: string;
}

export interface WsEvaluationResult {
  type: "evaluation_result";
  session_id: string;
  eval_token: string;
  evaluation: CallEvaluationResult;
}

export interface WsEvaluationError {
  type: "evaluation_error";
  session_id: string;
  code: string;
  message: string;
}

/** Verdict labels in Russian. */
export const VERDICT_LABELS: Record<string, string> = {
  excellent: "Отлично",
  good: "Хорошо",
  satisfactory: "Удовлетворительно",
  needs_improvement: "Требует внимания",
};

/** Verdict colors. */
export const VERDICT_COLORS: Record<string, string> = {
  excellent: "#22c55e",
  good: "#3b82f6",
  satisfactory: "#f59e0b",
  needs_improvement: "#ef4444",
};
```

- [ ] **Step 2: Update messages.ts WsMessage union**

Add imports at top of `extension/src/shared/messages.ts`:
```typescript
import type {
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
} from "./evaluation-types";
```

Extend the `WsMessage` type union (lines 34-39):
```typescript
export type WsMessage =
  | WsHintStart
  | WsHintChunk
  | WsHintEnd
  | WsTranscript
  | WsError
  | WsEvaluationStarted
  | WsEvaluationResult
  | WsEvaluationError;
```

Add to `ExtMessage` union:
```typescript
  | { type: "EVALUATION_STARTED"; sessionId: string }
  | { type: "EVALUATION_RESULT"; sessionId: string; evalToken: string; evaluation: import("./evaluation-types").CallEvaluationResult }
  | { type: "EVALUATION_ERROR"; sessionId: string; code: string; message: string }
```

- [ ] **Step 3: Build to verify TypeScript compiles**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add extension/src/shared/evaluation-types.ts extension/src/shared/messages.ts
git commit -m "feat(eval): add TypeScript evaluation types and WsMessage union"
```

---

### Task 8: Service Worker — forward + buffer evaluation messages

**Files:**
- Modify: `extension/src/background/service-worker.ts:63-65,103-108,277-291`

- [ ] **Step 1: Add evaluation buffer variable**

After `lastHintEnd` declaration (line 65), add:
```typescript
let lastEvaluationResult: WsMessage | null = null;
```

- [ ] **Step 2: Update bufferHint to also buffer evaluation**

Modify `bufferHint` function (lines 103-108) to also handle evaluation:
```typescript
function bufferHint(payload: WsMessage): void {
  if (payload.type === "hint_end") {
    lastHintEnd = payload;
  }
  if (payload.type === "evaluation_result") {
    lastEvaluationResult = payload;
  }
}
```

- [ ] **Step 3: Forward evaluation messages to Side Panel**

Find the WS message forwarding section (where `WS_MESSAGE` is posted to sidePanelPort). Ensure evaluation message types are forwarded — they should already be forwarded since they use `WS_MESSAGE` envelope. Also forward as `ExtMessage`:

In the WS `onmessage` handler, add forwarding for evaluation types:
```typescript
if (payload.type === "evaluation_started" || payload.type === "evaluation_result" || payload.type === "evaluation_error") {
  if (sidePanelPort) {
    sidePanelPort.postMessage({ type: "WS_MESSAGE", payload });
  }
}
```

- [ ] **Step 4: Replay evaluation on panel reconnect**

In `GET_SESSION_STATE` handler (lines 288-290), after hint replay, add:
```typescript
        // Replay last evaluation result on panel reconnect
        if (lastEvaluationResult) {
          port.postMessage({ type: "WS_MESSAGE", payload: lastEvaluationResult });
        }
```

- [ ] **Step 5: Clear evaluation buffer on session stop**

In the session stop handler where `lastHintEnd = null`, add:
```typescript
      lastEvaluationResult = null;
```

- [ ] **Step 6: Build to verify**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add extension/src/background/service-worker.ts
git commit -m "feat(eval): forward and buffer evaluation messages in service worker"
```

---

## Chunk 3: Side Panel Evaluation Summary (Tasks 9–10)

### Task 9: Side Panel HTML + CSS for evaluation summary

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.html:192-219`
- Modify: `extension/src/sidepanel/sidepanel.css`

- [ ] **Step 1: Add evaluation container to Phase 4 HTML**

After the `completion-strip` div (line 197) and before `transcript-full-details` (line 198), add:

```html
        <!-- Evaluation summary (FEAT-004) -->
        <div id="eval-loading" class="eval-loading" hidden>
          <div class="eval-skeleton-pulse"></div>
          <span class="eval-loading-text">Оцениваем звонок...</span>
        </div>
        <div id="eval-summary" class="eval-summary" hidden>
          <div class="eval-gauge-row">
            <svg id="eval-gauge" class="eval-gauge" viewBox="0 0 120 70" width="120" height="70">
              <path d="M10 65 A50 50 0 0 1 110 65" fill="none" stroke="#1e1e2e" stroke-width="8" stroke-linecap="round"/>
              <path id="eval-gauge-arc" d="M10 65 A50 50 0 0 1 110 65" fill="none" stroke="#3b82f6" stroke-width="8" stroke-linecap="round" stroke-dasharray="0 157"/>
              <text id="eval-gauge-score" x="60" y="55" text-anchor="middle" fill="white" font-size="20" font-weight="700"></text>
            </svg>
            <div class="eval-verdict-col">
              <span id="eval-verdict-text" class="eval-verdict-text"></span>
              <span id="eval-summary-text" class="eval-summary-brief"></span>
            </div>
          </div>
          <div id="eval-mini-bars" class="eval-mini-bars"></div>
          <button id="eval-detail-btn" class="btn-primary eval-detail-btn" type="button">Подробный отчёт</button>
        </div>
        <div id="eval-error" class="eval-error" hidden>
          <span id="eval-error-text"></span>
        </div>
```

- [ ] **Step 2: Add evaluation CSS styles**

Append to `extension/src/sidepanel/sidepanel.css`:

```css
/* ── Evaluation Summary (FEAT-004) ───────────────────────────── */

.eval-loading {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  margin: 8px 12px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}

.eval-skeleton-pulse {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1e1e2e, #2a2a3e);
  animation: evalPulse 1.5s ease-in-out infinite;
}

@keyframes evalPulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.eval-loading-text {
  color: rgba(255,255,255,0.5);
  font-size: 13px;
}

.eval-summary {
  margin: 8px 12px;
  padding: 16px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  animation: fadeIn 0.3s ease;
}

.eval-gauge-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.eval-gauge {
  flex-shrink: 0;
}

.eval-verdict-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.eval-verdict-text {
  font-size: 15px;
  font-weight: 600;
  color: white;
}

.eval-summary-brief {
  font-size: 12px;
  color: rgba(255,255,255,0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.eval-mini-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.eval-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.eval-bar-label {
  font-size: 11px;
  color: rgba(255,255,255,0.6);
  width: 140px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.eval-bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  overflow: hidden;
}

.eval-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

.eval-bar-score {
  font-size: 11px;
  color: rgba(255,255,255,0.7);
  width: 24px;
  text-align: right;
  flex-shrink: 0;
}

.eval-detail-btn {
  width: 100%;
  margin-top: 4px;
  font-size: 13px;
  padding: 8px 16px;
}

.eval-error {
  margin: 8px 12px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.2);
  color: #ef4444;
  font-size: 13px;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 3: Verify build**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add extension/src/sidepanel/sidepanel.html extension/src/sidepanel/sidepanel.css
git commit -m "feat(eval): add evaluation summary UI skeleton in Phase 4"
```

---

### Task 10: Side Panel TypeScript — handle evaluation messages

**Files:**
- Modify: `extension/src/sidepanel/sidepanel.ts:453-472`

- [ ] **Step 1: Add evaluation handler functions**

Add imports at top of sidepanel.ts:
```typescript
import type {
  CallEvaluationResult,
  WsEvaluationStarted,
  WsEvaluationResult,
  WsEvaluationError,
} from "../shared/evaluation-types";
import { VERDICT_LABELS, VERDICT_COLORS } from "../shared/evaluation-types";
```

Add handler functions (after existing handlers, before `handleWsMessage`):

```typescript
// ── Evaluation display (Phase 4) ──────────────────────────────────────────

function handleEvaluationStarted(_msg: WsEvaluationStarted): void {
  const loading = document.getElementById("eval-loading");
  const summary = document.getElementById("eval-summary");
  const error = document.getElementById("eval-error");
  if (loading) loading.hidden = false;
  if (summary) summary.hidden = true;
  if (error) error.hidden = true;
}

function handleEvaluationResult(msg: WsEvaluationResult): void {
  const loading = document.getElementById("eval-loading");
  const summary = document.getElementById("eval-summary");
  if (loading) loading.hidden = true;
  if (summary) summary.hidden = false;

  const ev = msg.evaluation;

  // Save to chrome.storage.local for report page + recovery
  chrome.storage.local.set({
    [`eval_token_${msg.session_id}`]: msg.eval_token,
    [`eval_result_${msg.session_id}`]: ev,
    last_eval_session_id: msg.session_id,
  });

  renderEvaluationSummary(ev, msg.session_id);
}

function handleEvaluationError(msg: WsEvaluationError): void {
  const loading = document.getElementById("eval-loading");
  const error = document.getElementById("eval-error");
  const errorText = document.getElementById("eval-error-text");
  if (loading) loading.hidden = true;
  if (error) error.hidden = false;
  if (errorText) errorText.textContent = msg.message || "Не удалось оценить звонок";
}

function renderEvaluationSummary(ev: CallEvaluationResult, sessionId: string): void {
  const color = VERDICT_COLORS[ev.verdict] || "#3b82f6";

  // Gauge arc
  const gaugeArc = document.getElementById("eval-gauge-arc");
  if (gaugeArc) {
    const pct = ev.overall_score / 10;
    const arcLen = 157; // approximate semicircle length
    gaugeArc.setAttribute("stroke-dasharray", `${pct * arcLen} ${arcLen}`);
    gaugeArc.setAttribute("stroke", color);
  }

  // Score text
  const scoreText = document.getElementById("eval-gauge-score");
  if (scoreText) scoreText.textContent = ev.overall_score.toFixed(1);

  // Verdict
  const verdictText = document.getElementById("eval-verdict-text");
  if (verdictText) {
    verdictText.textContent = VERDICT_LABELS[ev.verdict] || ev.verdict;
    verdictText.style.color = color;
  }

  // Summary brief
  const summaryBrief = document.getElementById("eval-summary-text");
  if (summaryBrief) {
    summaryBrief.textContent = ev.call_summary.slice(0, 120);
  }

  // Mini bars
  const barsContainer = document.getElementById("eval-mini-bars");
  if (barsContainer) {
    barsContainer.replaceChildren(); // clear
    for (const cr of ev.criteria_results) {
      const row = document.createElement("div");
      row.className = "eval-bar-row";

      const label = document.createElement("span");
      label.className = "eval-bar-label";
      label.textContent = cr.criterion_name;

      const track = document.createElement("div");
      track.className = "eval-bar-track";

      const fill = document.createElement("div");
      fill.className = "eval-bar-fill";
      fill.style.width = `${cr.score * 10}%`;
      fill.style.background = cr.score >= 7 ? "#22c55e" : cr.score >= 4 ? "#f59e0b" : "#ef4444";
      track.appendChild(fill);

      const score = document.createElement("span");
      score.className = "eval-bar-score";
      score.textContent = String(cr.score);

      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(score);
      barsContainer.appendChild(row);
    }
  }

  // Detail button
  const detailBtn = document.getElementById("eval-detail-btn");
  if (detailBtn) {
    detailBtn.onclick = () => {
      const url = chrome.runtime.getURL(`src/report/report.html?session_id=${sessionId}`);
      chrome.tabs.create({ url });
    };
  }
}
```

- [ ] **Step 2: Update handleWsMessage switch**

In `handleWsMessage` (lines 453-472), add cases:

```typescript
    case "evaluation_started":
      handleEvaluationStarted(msg);
      break;
    case "evaluation_result":
      handleEvaluationResult(msg);
      break;
    case "evaluation_error":
      handleEvaluationError(msg);
      break;
```

- [ ] **Step 3: Build to verify**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add extension/src/sidepanel/sidepanel.ts
git commit -m "feat(eval): handle evaluation messages in Side Panel Phase 4"
```

---

## Chunk 4: Settings Page & Report Page (Tasks 11–13)

### Task 11: Evaluation Settings Page

**Files:**
- Create: `extension/src/settings/evaluation-settings.html`
- Create: `extension/src/settings/evaluation-settings.css`
- Create: `extension/src/settings/evaluation-settings.ts`

- [ ] **Step 1: Create settings HTML**

```html
<!-- extension/src/settings/evaluation-settings.html -->
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Критерии оценки звонков</title>
  <link rel="stylesheet" href="evaluation-settings.css">
</head>
<body>
  <div class="settings-container">
    <header class="settings-header">
      <h1 class="settings-title">Критерии оценки звонков</h1>
      <button id="reset-btn" class="btn-secondary" type="button">Сбросить на стандартные</button>
    </header>

    <div id="criteria-list" class="criteria-list"></div>

    <button id="add-criterion-btn" class="btn-add" type="button">+ Добавить критерий</button>

    <footer class="settings-footer">
      <div id="weight-status" class="weight-status">
        <span>Сумма весов: </span>
        <span id="weight-sum">100%</span>
      </div>
      <div id="validation-error" class="validation-error" hidden></div>
      <button id="save-btn" class="btn-save" type="button">Сохранить</button>
    </footer>
  </div>

  <script src="evaluation-settings.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create settings CSS (premium dark)**

```css
/* extension/src/settings/evaluation-settings.css */
/* Premium Dark Design System (FEAT-004) */

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0a0a0f;
  color: rgba(255,255,255,0.87);
  min-height: 100vh;
  padding: 32px;
}

.settings-container {
  max-width: 640px;
  margin: 0 auto;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.settings-title {
  font-size: 22px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.btn-secondary {
  padding: 8px 16px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  background: transparent;
  color: rgba(255,255,255,0.6);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-secondary:hover {
  border-color: rgba(255,255,255,0.2);
  color: white;
}

.criteria-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.criterion-card {
  background: #12121a;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  padding: 20px;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  transition: all 0.3s ease;
  animation: cardFadeIn 0.3s ease;
}

@keyframes cardFadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.criterion-card:hover {
  border-color: rgba(99,102,241,0.3);
}

.criterion-top-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.criterion-drag {
  cursor: grab;
  color: rgba(255,255,255,0.2);
  font-size: 16px;
  user-select: none;
}

.criterion-name-input {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  padding: 8px 12px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  outline: none;
  transition: border-color 0.2s;
}
.criterion-name-input:focus {
  border-color: #6366f1;
}

.criterion-delete-btn {
  background: none;
  border: none;
  color: rgba(255,255,255,0.2);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s;
}
.criterion-delete-btn:hover {
  color: #ef4444;
  background: rgba(239,68,68,0.1);
}

.criterion-desc-textarea {
  width: 100%;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 8px;
  padding: 8px 12px;
  color: rgba(255,255,255,0.7);
  font-size: 13px;
  resize: vertical;
  min-height: 60px;
  outline: none;
  margin-bottom: 12px;
  font-family: inherit;
  transition: border-color 0.2s;
}
.criterion-desc-textarea:focus {
  border-color: #6366f1;
}

.criterion-weight-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.criterion-weight-label {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  flex-shrink: 0;
}

.criterion-weight-slider {
  flex: 1;
  -webkit-appearance: none;
  height: 6px;
  border-radius: 3px;
  background: rgba(255,255,255,0.08);
  outline: none;
}
.criterion-weight-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(99,102,241,0.4);
}

.criterion-weight-input {
  width: 56px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px;
  padding: 4px 8px;
  color: white;
  font-size: 13px;
  text-align: center;
  outline: none;
}

.btn-add {
  width: 100%;
  padding: 14px;
  margin-top: 12px;
  border: 2px dashed rgba(255,255,255,0.08);
  border-radius: 16px;
  background: transparent;
  color: rgba(255,255,255,0.3);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-add:hover {
  border-color: rgba(99,102,241,0.3);
  color: #6366f1;
}

.settings-footer {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.weight-status {
  font-size: 13px;
  color: rgba(255,255,255,0.5);
  text-align: center;
}

.weight-status.error #weight-sum {
  color: #ef4444;
}

.validation-error {
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.2);
  color: #ef4444;
  font-size: 13px;
  text-align: center;
}

.btn-save {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 16px rgba(99,102,241,0.3);
}
.btn-save:hover {
  box-shadow: 0 4px 24px rgba(99,102,241,0.5);
  transform: translateY(-1px);
}
.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
```

- [ ] **Step 3: Create settings TypeScript**

```typescript
// extension/src/settings/evaluation-settings.ts
/** Evaluation criteria settings page (FEAT-004). */

interface CriterionData {
  id: string;
  name: string;
  description: string;
  weight: number;
}

interface ConfigPayload {
  criteria: CriterionData[];
  model: string;
}

let criteria: CriterionData[] = [];
let API_BASE = "http://localhost:8000";

async function init(): Promise<void> {
  const stored = await chrome.storage.local.get(["backendUrl"]);
  API_BASE = stored.backendUrl || API_BASE;

  await loadConfig();
  renderAll();
  bindGlobalEvents();
}

async function loadConfig(): Promise<void> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/evaluation-config`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data: ConfigPayload = await resp.json();
    criteria = data.criteria;
  } catch (err) {
    console.error("Failed to load config:", err);
  }
}

function renderAll(): void {
  const list = document.getElementById("criteria-list");
  if (!list) return;
  list.replaceChildren();

  for (let i = 0; i < criteria.length; i++) {
    list.appendChild(createCard(criteria[i], i));
  }
  updateWeightStatus();
}

function createCard(c: CriterionData, index: number): HTMLElement {
  const card = document.createElement("div");
  card.className = "criterion-card";
  card.dataset.index = String(index);

  // Top row: drag + name + delete
  const topRow = document.createElement("div");
  topRow.className = "criterion-top-row";

  const drag = document.createElement("span");
  drag.className = "criterion-drag";
  drag.textContent = "\u2801\u2801\u2801";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.className = "criterion-name-input";
  nameInput.value = c.name;
  nameInput.placeholder = "Название критерия";
  nameInput.addEventListener("input", () => {
    criteria[index].name = nameInput.value;
  });

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "criterion-delete-btn";
  deleteBtn.textContent = "\ud83d\uddd1";
  deleteBtn.addEventListener("click", () => {
    if (criteria.length <= 1) return;
    criteria.splice(index, 1);
    renderAll();
  });

  topRow.appendChild(drag);
  topRow.appendChild(nameInput);
  topRow.appendChild(deleteBtn);
  card.appendChild(topRow);

  // Description textarea
  const desc = document.createElement("textarea");
  desc.className = "criterion-desc-textarea";
  desc.value = c.description;
  desc.placeholder = "Описание критерия";
  desc.addEventListener("input", () => {
    criteria[index].description = desc.value;
  });
  card.appendChild(desc);

  // Weight row
  const weightRow = document.createElement("div");
  weightRow.className = "criterion-weight-row";

  const weightLabel = document.createElement("span");
  weightLabel.className = "criterion-weight-label";
  weightLabel.textContent = "Вес:";

  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "criterion-weight-slider";
  slider.min = "0";
  slider.max = "50";
  slider.value = String(Math.round(c.weight * 100));

  const weightInput = document.createElement("input");
  weightInput.type = "number";
  weightInput.className = "criterion-weight-input";
  weightInput.min = "0";
  weightInput.max = "50";
  weightInput.value = String(Math.round(c.weight * 100));

  const pctSign = document.createElement("span");
  pctSign.className = "criterion-weight-label";
  pctSign.textContent = "%";

  slider.addEventListener("input", () => {
    const val = Number(slider.value);
    weightInput.value = String(val);
    criteria[index].weight = val / 100;
    updateWeightStatus();
  });

  weightInput.addEventListener("input", () => {
    const val = Math.min(50, Math.max(0, Number(weightInput.value)));
    slider.value = String(val);
    criteria[index].weight = val / 100;
    updateWeightStatus();
  });

  weightRow.appendChild(weightLabel);
  weightRow.appendChild(slider);
  weightRow.appendChild(weightInput);
  weightRow.appendChild(pctSign);
  card.appendChild(weightRow);

  return card;
}

function updateWeightStatus(): void {
  const total = criteria.reduce((sum, c) => sum + c.weight, 0);
  const pct = Math.round(total * 100);
  const sumEl = document.getElementById("weight-sum");
  const statusEl = document.querySelector(".weight-status");
  const saveBtn = document.getElementById("save-btn") as HTMLButtonElement | null;

  if (sumEl) sumEl.textContent = `${pct}%`;

  const isValid = Math.abs(total - 1.0) <= 0.01;
  if (statusEl) {
    statusEl.classList.toggle("error", !isValid);
  }
  if (saveBtn) saveBtn.disabled = !isValid;
}

function bindGlobalEvents(): void {
  document.getElementById("add-criterion-btn")?.addEventListener("click", () => {
    if (criteria.length >= 10) return;
    criteria.push({
      id: `custom_${Date.now()}`,
      name: "",
      description: "",
      weight: 0,
    });
    renderAll();
  });

  document.getElementById("reset-btn")?.addEventListener("click", async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/evaluation-config/reset`, {
        method: "POST",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ConfigPayload = await resp.json();
      criteria = data.criteria;
      renderAll();
    } catch (err) {
      console.error("Reset failed:", err);
    }
  });

  document.getElementById("save-btn")?.addEventListener("click", async () => {
    const total = criteria.reduce((sum, c) => sum + c.weight, 0);
    if (Math.abs(total - 1.0) > 0.01) return;

    const errEl = document.getElementById("validation-error");
    try {
      const resp = await fetch(`${API_BASE}/api/v1/evaluation-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ criteria, model: "google/gemini-2.5-flash" }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        if (errEl) {
          errEl.textContent = `Ошибка сохранения: ${detail}`;
          errEl.hidden = false;
        }
        return;
      }
      if (errEl) errEl.hidden = true;
      // Visual feedback
      const btn = document.getElementById("save-btn");
      if (btn) {
        btn.textContent = "Сохранено ✓";
        setTimeout(() => { btn.textContent = "Сохранить"; }, 2000);
      }
    } catch (err) {
      if (errEl) {
        errEl.textContent = `Ошибка: ${String(err)}`;
        errEl.hidden = false;
      }
    }
  });
}

document.addEventListener("DOMContentLoaded", init);
```

- [ ] **Step 4: Build to verify**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add extension/src/settings/evaluation-settings.html extension/src/settings/evaluation-settings.css extension/src/settings/evaluation-settings.ts
git commit -m "feat(eval): add premium dark evaluation criteria settings page"
```

---

### Task 12: Report Page

**Files:**
- Create: `extension/src/report/report.html`
- Create: `extension/src/report/report.css`
- Create: `extension/src/report/report.ts`

- [ ] **Step 1: Create report HTML**

```html
<!-- extension/src/report/report.html -->
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Отчёт об оценке звонка</title>
  <link rel="stylesheet" href="report.css">
</head>
<body>
  <div class="report-container">
    <div id="report-loading" class="report-loading">
      <div class="report-spinner"></div>
      <span>Загрузка отчёта...</span>
    </div>
    <div id="report-error" class="report-error" hidden></div>
    <div id="report-content" class="report-content" hidden>
      <!-- Header -->
      <header class="report-header">
        <div class="report-header-left">
          <h1 class="report-title">Отчёт об оценке звонка</h1>
          <span id="report-date" class="report-date"></span>
        </div>
        <div class="report-score-big">
          <span id="report-score" class="score-number"></span>
          <span id="report-verdict-badge" class="verdict-badge"></span>
        </div>
      </header>

      <!-- Summary -->
      <section class="report-card">
        <h2 class="card-title">Резюме разговора</h2>
        <p id="report-summary"></p>
      </section>

      <!-- Scorecard -->
      <section id="report-scorecard" class="report-scorecard"></section>

      <!-- Strengths -->
      <section class="report-card card-strengths">
        <h2 class="card-title">Сильные стороны</h2>
        <ul id="report-strengths" class="icon-list strengths-list"></ul>
      </section>

      <!-- Growth areas -->
      <section class="report-card card-growth">
        <h2 class="card-title">Зоны роста</h2>
        <ul id="report-growth" class="icon-list growth-list"></ul>
      </section>

      <!-- Action plan -->
      <section class="report-card card-action">
        <h2 class="card-title">План действий</h2>
        <ol id="report-action-plan" class="action-list"></ol>
      </section>

      <!-- Footer -->
      <footer class="report-footer">
        <button id="copy-btn" class="btn-copy" type="button">Скопировать как текст</button>
        <span class="report-disclaimer">Оценка сгенерирована автоматически</span>
      </footer>
    </div>
  </div>

  <script src="report.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create report CSS (premium dark)**

```css
/* extension/src/report/report.css */
/* Premium Dark Report (FEAT-004) */

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0a0a0f;
  color: rgba(255,255,255,0.87);
  min-height: 100vh;
  padding: 40px 24px;
}

.report-container {
  max-width: 720px;
  margin: 0 auto;
}

.report-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 80px 0;
  color: rgba(255,255,255,0.4);
}

.report-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255,255,255,0.1);
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.report-error {
  padding: 24px;
  border-radius: 16px;
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.2);
  color: #ef4444;
  text-align: center;
}

.report-content {
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.report-title {
  font-size: 24px;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.report-date {
  font-size: 13px;
  color: rgba(255,255,255,0.4);
  margin-top: 4px;
  display: block;
}

.report-score-big {
  text-align: right;
}

.score-number {
  font-size: 56px;
  font-weight: 800;
  line-height: 1;
  display: block;
}

.verdict-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  margin-top: 8px;
}

.report-card {
  background: #12121a;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 16px;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: rgba(255,255,255,0.9);
}

.report-card p {
  font-size: 14px;
  line-height: 1.6;
  color: rgba(255,255,255,0.7);
}

/* Scorecard */
.report-scorecard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.criterion-card {
  background: #12121a;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 16px;
  padding: 20px;
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
}

.criterion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.criterion-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255,255,255,0.9);
}

.criterion-score-badge {
  font-size: 20px;
  font-weight: 700;
}

.criterion-bar {
  height: 6px;
  background: rgba(255,255,255,0.06);
  border-radius: 3px;
  margin-bottom: 12px;
  overflow: hidden;
}

.criterion-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.8s ease;
}

.criterion-comment {
  font-size: 14px;
  line-height: 1.5;
  color: rgba(255,255,255,0.7);
  margin-bottom: 8px;
}

.criterion-recs {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.criterion-recs li {
  font-size: 13px;
  color: rgba(255,255,255,0.6);
  padding-left: 20px;
  position: relative;
}

.criterion-recs li::before {
  content: "\1F4A1";
  position: absolute;
  left: 0;
}

/* Side-striped cards */
.card-strengths { border-left: 3px solid #22c55e; }
.card-growth { border-left: 3px solid #f59e0b; }
.card-action { border-left: 3px solid #8b5cf6; }

.icon-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.icon-list li {
  font-size: 14px;
  color: rgba(255,255,255,0.7);
  padding-left: 24px;
  position: relative;
  line-height: 1.5;
}

.strengths-list li::before { content: "\2713"; position: absolute; left: 0; color: #22c55e; }
.growth-list li::before { content: "\2191"; position: absolute; left: 0; color: #f59e0b; }

.action-list {
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.action-list li {
  font-size: 14px;
  color: rgba(255,255,255,0.7);
  line-height: 1.5;
}

.action-list li::marker {
  color: #8b5cf6;
  font-weight: 700;
}

.report-footer {
  margin-top: 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-copy {
  padding: 10px 20px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  background: transparent;
  color: rgba(255,255,255,0.7);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-copy:hover {
  border-color: #6366f1;
  color: white;
}

.report-disclaimer {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
}
```

- [ ] **Step 3: Create report TypeScript**

```typescript
// extension/src/report/report.ts
/** Full evaluation report page (FEAT-004). Uses safe DOM methods only. */

interface CriterionResultWire {
  criterion_id: string;
  criterion_name: string;
  reasoning: string;
  score: number;
  comment: string;
  recommendations: string[];
}

interface CallEvaluationResult {
  call_summary: string;
  criteria_results: CriterionResultWire[];
  overall_score: number;
  verdict: "excellent" | "good" | "satisfactory" | "needs_improvement";
  strengths: string[];
  growth_areas: string[];
  action_plan: string[];
}

const VERDICT_LABELS: Record<string, string> = {
  excellent: "Отлично",
  good: "Хорошо",
  satisfactory: "Удовлетворительно",
  needs_improvement: "Требует внимания",
};

const VERDICT_COLORS: Record<string, string> = {
  excellent: "#22c55e",
  good: "#3b82f6",
  satisfactory: "#f59e0b",
  needs_improvement: "#ef4444",
};

function scoreColor(score: number): string {
  if (score >= 7) return "#22c55e";
  if (score >= 4) return "#f59e0b";
  return "#ef4444";
}

async function init(): Promise<void> {
  const sessionId = new URLSearchParams(location.search).get("session_id");
  if (!sessionId) {
    showError("session_id не указан в URL");
    return;
  }

  const stored = await chrome.storage.local.get([
    "backendUrl",
    `eval_token_${sessionId}`,
    `eval_result_${sessionId}`,
  ]);

  // Try cache first
  const cached = stored[`eval_result_${sessionId}`] as CallEvaluationResult | undefined;
  if (cached) {
    render(cached);
    return;
  }

  // Fetch from API
  const apiBase = stored.backendUrl || "http://localhost:8000";
  const token = stored[`eval_token_${sessionId}`] as string | undefined;
  if (!token) {
    showError("Токен доступа не найден. Попробуйте открыть отчёт из панели.");
    return;
  }

  try {
    const resp = await fetch(`${apiBase}/api/v1/evaluation/${sessionId}?token=${token}`);
    if (!resp.ok) {
      showError(`Ошибка загрузки: HTTP ${resp.status}`);
      return;
    }
    const data: CallEvaluationResult = await resp.json();
    render(data);
  } catch (err) {
    showError(`Ошибка: ${String(err)}`);
  }
}

function showError(msg: string): void {
  const loadingEl = document.getElementById("report-loading");
  const errorEl = document.getElementById("report-error");
  if (loadingEl) loadingEl.hidden = true;
  if (errorEl) {
    errorEl.hidden = false;
    errorEl.textContent = msg;
  }
}

function render(ev: CallEvaluationResult): void {
  const loadingEl = document.getElementById("report-loading");
  const contentEl = document.getElementById("report-content");
  if (loadingEl) loadingEl.hidden = true;
  if (contentEl) contentEl.hidden = false;

  const color = VERDICT_COLORS[ev.verdict] || "#3b82f6";

  // Date
  const dateEl = document.getElementById("report-date");
  if (dateEl) dateEl.textContent = new Date().toLocaleString("ru-RU");

  // Score
  const scoreEl = document.getElementById("report-score");
  if (scoreEl) {
    scoreEl.textContent = ev.overall_score.toFixed(1);
    scoreEl.style.color = color;
  }

  // Verdict badge
  const verdictEl = document.getElementById("report-verdict-badge");
  if (verdictEl) {
    verdictEl.textContent = VERDICT_LABELS[ev.verdict] || ev.verdict;
    verdictEl.style.background = color + "20";
    verdictEl.style.color = color;
  }

  // Summary
  const summaryEl = document.getElementById("report-summary");
  if (summaryEl) summaryEl.textContent = ev.call_summary;

  // Scorecard
  const scorecardEl = document.getElementById("report-scorecard");
  if (scorecardEl) {
    scorecardEl.replaceChildren();
    for (const cr of ev.criteria_results) {
      scorecardEl.appendChild(createCriterionCard(cr));
    }
  }

  // Strengths
  renderList("report-strengths", ev.strengths);

  // Growth areas
  renderList("report-growth", ev.growth_areas);

  // Action plan
  renderList("report-action-plan", ev.action_plan);

  // Copy button
  document.getElementById("copy-btn")?.addEventListener("click", () => {
    const text = buildPlainText(ev);
    navigator.clipboard.writeText(text).then(() => {
      const btn = document.getElementById("copy-btn");
      if (btn) {
        btn.textContent = "Скопировано!";
        setTimeout(() => { btn.textContent = "Скопировать как текст"; }, 2000);
      }
    });
  });
}

function createCriterionCard(cr: CriterionResultWire): HTMLElement {
  const card = document.createElement("div");
  card.className = "criterion-card";

  // Header
  const header = document.createElement("div");
  header.className = "criterion-header";

  const name = document.createElement("span");
  name.className = "criterion-name";
  name.textContent = cr.criterion_name;

  const scoreBadge = document.createElement("span");
  scoreBadge.className = "criterion-score-badge";
  scoreBadge.textContent = `${cr.score}/10`;
  scoreBadge.style.color = scoreColor(cr.score);

  header.appendChild(name);
  header.appendChild(scoreBadge);
  card.appendChild(header);

  // Bar
  const bar = document.createElement("div");
  bar.className = "criterion-bar";
  const fill = document.createElement("div");
  fill.className = "criterion-bar-fill";
  fill.style.width = `${cr.score * 10}%`;
  fill.style.background = scoreColor(cr.score);
  bar.appendChild(fill);
  card.appendChild(bar);

  // Comment
  const comment = document.createElement("p");
  comment.className = "criterion-comment";
  comment.textContent = cr.comment;
  card.appendChild(comment);

  // Recommendations
  if (cr.recommendations.length > 0) {
    const recList = document.createElement("ul");
    recList.className = "criterion-recs";
    for (const rec of cr.recommendations) {
      const li = document.createElement("li");
      li.textContent = rec;
      recList.appendChild(li);
    }
    card.appendChild(recList);
  }

  return card;
}

function renderList(elementId: string, items: string[]): void {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.replaceChildren();
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  }
}

function buildPlainText(ev: CallEvaluationResult): string {
  const lines: string[] = [
    `ОЦЕНКА ЗВОНКА: ${ev.overall_score.toFixed(1)}/10 (${VERDICT_LABELS[ev.verdict]})`,
    "",
    `Резюме: ${ev.call_summary}`,
    "",
    "КРИТЕРИИ:",
  ];
  for (const cr of ev.criteria_results) {
    lines.push(`  ${cr.criterion_name}: ${cr.score}/10 — ${cr.comment}`);
    for (const rec of cr.recommendations) {
      lines.push(`    - ${rec}`);
    }
  }
  lines.push("", "Сильные стороны:");
  for (const s of ev.strengths) lines.push(`  + ${s}`);
  lines.push("", "Зоны роста:");
  for (const g of ev.growth_areas) lines.push(`  ^ ${g}`);
  lines.push("", "План действий:");
  ev.action_plan.forEach((a, i) => lines.push(`  ${i + 1}. ${a}`));
  return lines.join("\n");
}

document.addEventListener("DOMContentLoaded", init);
```

- [ ] **Step 4: Build to verify**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add extension/src/report/report.html extension/src/report/report.css extension/src/report/report.ts
git commit -m "feat(eval): add premium dark evaluation report page"
```

---

### Task 13: Update manifest.json

**Files:**
- Modify: `extension/manifest.json`

- [ ] **Step 1: Add new pages to web_accessible_resources**

Add `src/report/report.html` and `src/settings/evaluation-settings.html` to the manifest's `web_accessible_resources` array (if used). Also add them as extension pages that can be opened via `chrome.tabs.create`.

Check if `esbuild` or similar bundler is configured to compile the new `.ts` files.

- [ ] **Step 2: Verify extension loads in Chrome**

Load the extension in Chrome and confirm no manifest errors.

- [ ] **Step 3: Commit**

```bash
git add extension/manifest.json
git commit -m "feat(eval): register evaluation pages in manifest"
```

---

## Chunk 5: Integration & Verification (Task 14)

### Task 14: End-to-end integration test

**Files:**
- Create: `backend/tests/test_evaluation_integration.py`

- [ ] **Step 1: Write integration test**

```python
# backend/tests/test_evaluation_integration.py
"""Integration test: full evaluation pipeline (FEAT-004)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, CallEvaluation
from backend.pipeline.evaluator import evaluate_call


def _build_transcript(n: int = 5) -> list[str]:
    lines = []
    for i in range(n):
        speaker = "rep" if i % 2 == 0 else "client"
        lines.append(json.dumps({"speaker": speaker, "text": f"Utterance {i}"}))
    return lines


def _build_llm_response() -> dict:
    return {
        "call_summary": "Менеджер провёл звонок с клиентом.",
        "criteria_results": [
            {
                "criterion_id": c.id,
                "criterion_name": c.name,
                "reasoning": f"Analysis for {c.id}",
                "score": 7,
                "comment": f"Comment for {c.id}",
                "recommendations": [f"Improve {c.id}"],
            }
            for c in DEFAULT_CONFIG.criteria
        ],
        "overall_score": 1.0,  # will be recomputed
        "verdict": "needs_improvement",  # will be recomputed
        "strengths": ["Good greeting", "Active listening"],
        "growth_areas": ["Closing technique", "Objection handling"],
        "action_plan": ["Practice closing", "Study objections", "Role-play"],
    }


@pytest.mark.asyncio
async def test_full_evaluation_pipeline():
    """Simulate full pipeline: transcript → evaluate_call → validated result."""
    mock_llm = AsyncMock()
    mock_llm.evaluate.return_value = _build_llm_response()

    transcript = _build_transcript(20)
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
        briefing="Test briefing for B2B call",
    )

    # Validate return type
    assert isinstance(result, CallEvaluation)

    # Verify score recomputation (all scores=7, weighted avg=7.0)
    assert abs(result.overall_score - 7.0) < 0.01
    assert result.verdict == "good"

    # Verify criteria count matches config
    assert len(result.criteria_results) == len(DEFAULT_CONFIG.criteria)

    # Verify LLM was called with correct structure
    mock_llm.evaluate.assert_called_once()
    call_args = mock_llm.evaluate.call_args
    assert "РОП" in call_args.args[0]  # system prompt
    assert "ТРАНСКРИПТ" in call_args.args[1]  # user prompt
    assert "properties" in call_args.args[2]  # json schema


@pytest.mark.asyncio
async def test_evaluation_with_empty_transcript():
    """Empty transcript should raise or be handled gracefully."""
    mock_llm = AsyncMock()
    # evaluate_call should still call LLM even with minimal transcript
    mock_llm.evaluate.return_value = _build_llm_response()

    transcript = [json.dumps({"speaker": "rep", "text": "hi"})]
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
    )
    assert isinstance(result, CallEvaluation)
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/test_evaluation_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full backend test suite**

Run: `cd /Users/teterinsa/Projects/crmcore && python -m pytest backend/tests/ -v`
Expected: All tests PASS, no regressions

- [ ] **Step 4: Build extension**

Run: `cd /Users/teterinsa/Projects/crmcore/extension && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_evaluation_integration.py
git commit -m "test(eval): add integration test for full evaluation pipeline"
```

---

## Progress Tracking

- [ ] Task 1: Evaluation Schemas
- [ ] Task 2: EvaluatorLLMClient
- [ ] Task 3: Evaluator (prompt + score recomputation)
- [ ] Task 4: REST API for evaluation config + result
- [ ] Task 5: SessionManager dual-write
- [ ] Task 6: Orchestrator + main.py integration
- [ ] Task 7: TypeScript evaluation types + messages.ts
- [ ] Task 8: Service Worker — forward + buffer evaluation messages
- [ ] Task 9: Side Panel HTML + CSS for evaluation summary
- [ ] Task 10: Side Panel TypeScript — handle evaluation messages
- [ ] Task 11: Evaluation Settings Page
- [ ] Task 12: Report Page
- [ ] Task 13: Update manifest.json
- [ ] Task 14: End-to-end integration test

**Total Tasks:** 14 | **Completed:** 0 | **Remaining:** 14

**Status: PENDING**
