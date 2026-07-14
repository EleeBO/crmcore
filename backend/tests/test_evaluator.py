"""Tests for evaluate_call (FEAT-004)."""
import json
from unittest.mock import AsyncMock

import pytest

from backend.pipeline.evaluation_schemas import (
    DEFAULT_CONFIG,
    CallEvaluation,
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
    lines = ["x" * 200 for _ in range(300)]
    result = _truncate_transcript(lines)
    assert len(result) < 60_000


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
        "overall_score": 1.0,
        "verdict": "needs_improvement",
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
    assert abs(result.overall_score - 7.0) < 0.01
    assert result.verdict == "good"
