"""Integration test: full evaluation pipeline (FEAT-004)."""

import json
from unittest.mock import AsyncMock

import pytest

from backend.pipeline.evaluation_schemas import DEFAULT_CONFIG, CallEvaluation
from backend.pipeline.evaluator import evaluate_call


def _build_transcript(n: int = 5) -> list[str]:
    """Build a sample transcript as JSON strings."""
    lines = []
    for i in range(n):
        speaker = "rep" if i % 2 == 0 else "client"
        lines.append(json.dumps({"speaker": speaker, "text": f"Utterance {i}"}))
    return lines


def _build_llm_response() -> dict:
    """Build a valid CallEvaluation response from LLM."""
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
async def test_full_evaluation_pipeline() -> None:
    """Simulate full pipeline: transcript → evaluate_call → validated result."""
    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=_build_llm_response())

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

    # Verify each criterion has all required fields
    for criterion in result.criteria_results:
        assert criterion.criterion_id
        assert criterion.criterion_name
        assert criterion.reasoning
        assert 1 <= criterion.score <= 10
        assert criterion.comment
        assert criterion.recommendations

    # Verify LLM was called with correct structure
    mock_llm.evaluate.assert_called_once()
    call_args = mock_llm.evaluate.call_args
    assert call_args is not None
    assert len(call_args.args) == 3
    system_prompt = call_args.args[0]
    user_prompt = call_args.args[1]
    json_schema = call_args.args[2]

    # Verify system prompt contains expected Russian content
    assert "РОП" in system_prompt
    assert "B2B" in system_prompt or "продаж" in system_prompt

    # Verify user prompt contains expected sections
    assert "ТРАНСКРИПТ" in user_prompt
    assert "БРИФИНГ" in user_prompt
    assert "КРИТЕРИИ" in user_prompt

    # Verify schema is a dict with expected properties
    assert isinstance(json_schema, dict)
    assert "properties" in json_schema


@pytest.mark.asyncio
async def test_evaluation_with_minimal_transcript() -> None:
    """Minimal transcript should work correctly."""
    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=_build_llm_response())

    transcript = [json.dumps({"speaker": "rep", "text": "hello"})]
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
    )

    assert isinstance(result, CallEvaluation)
    assert result.verdict == "good"


@pytest.mark.asyncio
async def test_evaluation_with_bytes_transcript() -> None:
    """Transcript can be bytes (decoded to strings)."""
    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=_build_llm_response())

    transcript = [
        json.dumps({"speaker": "rep", "text": "hello"}).encode(),
        json.dumps({"speaker": "client", "text": "hi"}).encode(),
    ]
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
    )

    assert isinstance(result, CallEvaluation)


@pytest.mark.asyncio
async def test_evaluation_score_recomputation() -> None:
    """Verify score recomputation with different criterion scores."""
    # Create response where all criteria score=8
    response = _build_llm_response()
    for criterion in response["criteria_results"]:
        criterion["score"] = 8

    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=response)

    transcript = _build_transcript(10)
    result = await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
    )

    # Overall score should be 8.0 (weighted average of all 8s = 8.0)
    assert abs(result.overall_score - 8.0) < 0.01
    assert result.verdict == "excellent"


@pytest.mark.asyncio
async def test_evaluation_verdict_boundaries() -> None:
    """Verify verdict computation at score boundaries."""
    test_cases = [
        (3.0, "needs_improvement"),
        (4.0, "satisfactory"),
        (6.0, "good"),
        (8.0, "excellent"),
    ]

    for score, expected_verdict in test_cases:
        response = _build_llm_response()
        # Set all criteria to score that yields the target overall_score
        # Since all weights sum to 1.0, if all criteria have same score,
        # overall = that score
        num_criteria = len(DEFAULT_CONFIG.criteria)
        target_score = int(score)
        for criterion in response["criteria_results"]:
            criterion["score"] = target_score

        mock_llm = AsyncMock()
        mock_llm.evaluate = AsyncMock(return_value=response)

        result = await evaluate_call(
            llm_client=mock_llm,
            transcript_raw=_build_transcript(5),
            config=DEFAULT_CONFIG,
        )

        assert result.verdict == expected_verdict, (
            f"Score {result.overall_score} should have verdict {expected_verdict}, "
            f"got {result.verdict}"
        )


@pytest.mark.asyncio
async def test_evaluation_with_briefing() -> None:
    """Verify briefing is included in user prompt."""
    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=_build_llm_response())

    briefing_text = "Follow up on quarterly review"
    transcript = _build_transcript(5)
    await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
        briefing=briefing_text,
    )

    call_args = mock_llm.evaluate.call_args
    assert call_args is not None
    user_prompt = call_args.args[1]
    assert briefing_text in user_prompt


@pytest.mark.asyncio
async def test_evaluation_without_briefing() -> None:
    """Verify default briefing message when not provided."""
    mock_llm = AsyncMock()
    mock_llm.evaluate = AsyncMock(return_value=_build_llm_response())

    transcript = _build_transcript(5)
    await evaluate_call(
        llm_client=mock_llm,
        transcript_raw=transcript,
        config=DEFAULT_CONFIG,
    )

    call_args = mock_llm.evaluate.call_args
    assert call_args is not None
    user_prompt = call_args.args[1]
    assert "брифинг не предоставлен" in user_prompt
