"""Tests for Scenario model and generate_scenario (FEAT-001 Task 1.1)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Scenario Model Tests ──────────────────────────────────────────────────


class TestScenarioModel:
    """Validate Scenario Pydantic model."""

    def test_scenario_model_validates_correct_json(self):
        """Scenario parses valid JSON matching the spec structure."""
        from backend.pipeline.scenario import Scenario

        data = {
            "portrait": {
                "role": "CTO",
                "pain_points": ["высокая стоимость"],
                "motivators": ["ROI"],
                "budget": "500 000 руб.",
                "communication_style": "консервативный",
            },
            "strategy": {
                "approach": "Акцент на ROI",
                "key_messages": ["Экономия 30%"],
                "avoid": ["Не предлагать скидку первым"],
            },
            "objections": [
                {
                    "trigger": "дорого",
                    "response": "Bitrix24 на 30% дороже",
                    "source_file": "competitors.xlsx",
                    "source_detail": "строки 15-17",
                }
            ],
            "key_facts": [
                {
                    "fact": "Тариф Gold — 500 руб/мес",
                    "source_file": "tariffs.pdf",
                    "source_page": 3,
                }
            ],
            "talking_points": ["Упомянуть кейс Газпрома"],
        }

        scenario = Scenario.model_validate(data)
        assert scenario.portrait.role == "CTO"
        assert len(scenario.objections) == 1
        assert scenario.objections[0].trigger == "дорого"
        assert scenario.key_facts[0].source_page == 3
        assert len(scenario.talking_points) == 1

    def test_scenario_model_defaults_for_empty(self):
        """Empty Scenario() creates valid model with defaults."""
        from backend.pipeline.scenario import Scenario

        scenario = Scenario()
        assert scenario.portrait.role == ""
        assert scenario.objections == []
        assert scenario.key_facts == []
        assert scenario.talking_points == []

    def test_scenario_model_rejects_invalid_json(self):
        """Invalid JSON raises ValidationError."""
        from pydantic import ValidationError

        from backend.pipeline.scenario import Scenario

        with pytest.raises(ValidationError):
            Scenario.model_validate({"key_facts": [{"wrong": "field"}]})

    def test_scenario_roundtrip_json(self):
        """Scenario serializes and deserializes correctly."""
        from backend.pipeline.scenario import Scenario

        scenario = Scenario(
            talking_points=["point 1"],
        )
        json_str = scenario.model_dump_json()
        restored = Scenario.model_validate_json(json_str)
        assert restored.talking_points == ["point 1"]


# ── generate_scenario Tests ──────────────────────────────────────────────


class TestGenerateScenario:
    """Test generate_scenario LLM integration."""

    @pytest.mark.asyncio
    async def test_generate_scenario_calls_llm(self):
        """generate_scenario calls OpenRouter and parses valid response."""
        from backend.pipeline.scenario import Scenario, generate_scenario

        valid_scenario = Scenario(
            talking_points=["test point"],
        )
        valid_json = valid_scenario.model_dump_json()

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = valid_json

        with patch(
            "backend.pipeline.scenario._call_openrouter",
            new_callable=AsyncMock,
            return_value=valid_json,
        ):
            result = await generate_scenario(
                docs_text="Sample document text",
                api_key="test-key",
                model="test-model",
            )
            assert isinstance(result, Scenario)
            assert result.talking_points == ["test point"]

    @pytest.mark.asyncio
    async def test_generate_scenario_retries_on_invalid_json(self):
        """On first invalid JSON, retries once then succeeds."""
        from backend.pipeline.scenario import Scenario, generate_scenario

        valid_scenario = Scenario(talking_points=["retry success"])
        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "not valid json {{"
            return valid_scenario.model_dump_json()

        with patch(
            "backend.pipeline.scenario._call_openrouter",
            side_effect=mock_call,
        ):
            result = await generate_scenario(
                docs_text="test", api_key="key", model="model"
            )
            assert result.talking_points == ["retry success"]
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_generate_scenario_returns_empty_on_double_failure(self):
        """After two failures, returns empty Scenario()."""
        from backend.pipeline.scenario import Scenario, generate_scenario

        async def mock_call(*args, **kwargs):
            return "invalid json always"

        with patch(
            "backend.pipeline.scenario._call_openrouter",
            side_effect=mock_call,
        ):
            result = await generate_scenario(
                docs_text="test", api_key="key", model="model"
            )
            assert isinstance(result, Scenario)
            assert result.talking_points == []
            assert result.portrait.role == ""

    @pytest.mark.asyncio
    async def test_generate_scenario_timeout_returns_empty(self):
        """On asyncio.TimeoutError, returns empty Scenario()."""
        from backend.pipeline.scenario import Scenario, generate_scenario

        async def mock_call(*args, **kwargs):
            await asyncio.sleep(100)  # will be cancelled by timeout
            return ""

        with patch(
            "backend.pipeline.scenario._call_openrouter",
            side_effect=mock_call,
        ), patch(
            "backend.pipeline.scenario._SCENARIO_TIMEOUT_S",
            0.01,  # 10ms timeout
        ):
            result = await generate_scenario(
                docs_text="test", api_key="key", model="model"
            )
            assert isinstance(result, Scenario)
            assert result.talking_points == []

    def test_scenario_json_schema_is_valid(self):
        """Scenario.model_json_schema() produces valid JSON schema."""
        from backend.pipeline.scenario import Scenario

        schema = Scenario.model_json_schema()
        assert "properties" in schema
        assert "portrait" in schema["properties"]
        assert "objections" in schema["properties"]
        assert "key_facts" in schema["properties"]
