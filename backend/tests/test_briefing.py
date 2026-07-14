"""Tests for Task 6.1 (Pre-call Briefing) and Task 6.2 (Post-call Summary)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

# ── Task 6.1: Pre-call Briefing ───────────────────────────────────────────


class TestBriefing:
    """Tests for generate_briefing function (v2 / SGR BriefData)."""

    @pytest.fixture
    def mock_llm_briefing_response(self):
        """Valid SGR LLM response for briefing."""
        return json.dumps({
            "contact": {
                "role": "Руководитель отдела продаж",
                "company": "ООО «ТестКорп»",
                "companyDetail": "50 сотрудников",
                "budgetNote": "500 000 руб.",
            },
            "profileTags": [
                {"label": "ROI-ориентирован", "color": "blue"},
            ],
            "focusPoints": [
                {
                    "headline": "Интеграция за 2 недели",
                    "detail": "Полная настройка CRM",
                },
            ],
            "painPoints": ["Высокая стоимость интеграции"],
            "roi": {
                "value": "2.5 млн ₽",
                "description": "экономия в год",
            },
            "comparison": None,
            "objections": [
                {
                    "question": "«Слишком дорого»",
                    "answer": "Экономия 30% в год.",
                },
                {
                    "question": "«Сложно интегрировать»",
                    "answer": "Настроим за 2 недели.",
                },
            ],
            "fullBrief": "Полный текст брифинга для менеджера.",
        })

    @pytest.mark.asyncio
    async def test_briefing_returns_brief_data(
        self, mock_llm_briefing_response
    ):
        """generate_briefing returns BriefData with contact info."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=mock_llm_briefing_response),
        ):
            result = await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, BriefData)
        assert result.contact.role == "Руководитель отдела продаж"
        assert result.contact.company == "ООО «ТестКорп»"

    @pytest.mark.asyncio
    async def test_briefing_returns_objections(
        self, mock_llm_briefing_response
    ):
        """generate_briefing returns objections as BriefObjection list."""
        from backend.briefing.portrait import generate_briefing

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=mock_llm_briefing_response),
        ):
            result = await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert len(result.objections) == 2
        assert result.objections[0].question == "«Слишком дорого»"
        assert result.objections[0].answer == "Экономия 30% в год."

    @pytest.mark.asyncio
    async def test_briefing_returns_focus_points(
        self, mock_llm_briefing_response
    ):
        """generate_briefing returns focus points."""
        from backend.briefing.portrait import generate_briefing

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=mock_llm_briefing_response),
        ):
            result = await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert len(result.focus_points) == 1
        assert result.focus_points[0].headline == "Интеграция за 2 недели"

    @pytest.mark.asyncio
    async def test_briefing_latency(self, mock_llm_briefing_response):
        """generate_briefing completes in <5 seconds with mocked deps."""
        from backend.briefing.portrait import generate_briefing

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=mock_llm_briefing_response),
        ):
            result = await asyncio.wait_for(
                generate_briefing(
                    kb_id="test-kb",
                    session_id="test-session",
                    redis=mock_redis,
                    api_key="test-key",
                    model="test-model",
                ),
                timeout=5.0,
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_briefing_cached_in_redis(
        self, mock_llm_briefing_response
    ):
        """generate_briefing caches result in Redis after LLM path."""
        from backend.briefing.portrait import generate_briefing

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=mock_llm_briefing_response),
        ):
            await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        mock_redis.set.assert_called()
        mock_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_briefing_returns_v2_cached_result(self):
        """generate_briefing returns BriefData from v2 cache (has 'contact' key)."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing

        v2_cache = json.dumps({
            "contact": {"role": "CTO", "company": "Cached Corp"},
            "profileTags": [],
            "focusPoints": [],
            "painPoints": [],
            "objections": [],
            "fullBrief": "",
        })

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=v2_cache.encode())

        result = await generate_briefing(
            kb_id="test-kb",
            session_id="test-session",
            redis=mock_redis,
            api_key="test-key",
            model="test-model",
        )

        assert isinstance(result, BriefData)
        assert result.contact.role == "CTO"
        assert result.contact.company == "Cached Corp"

    @pytest.mark.asyncio
    async def test_briefing_v1_cache_triggers_regeneration(self):
        """v1 cache (has 'portrait' key, no 'contact') falls through to regeneration."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing

        v1_cache = json.dumps({
            "portrait": {"role": "CTO"},
            "strategy": {},
            "objections": [],
        })

        llm_response = json.dumps({
            "contact": {"role": "Regenerated"},
            "profileTags": [],
            "focusPoints": [{"headline": "New focus"}],
            "painPoints": [],
            "objections": [],
            "fullBrief": "",
        })

        async def redis_get(key):
            if "briefing:" in key:
                return v1_cache.encode()
            return None

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=redis_get)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(return_value=llm_response),
        ):
            result = await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, BriefData)
        assert result.contact.role == "Regenerated"

    @pytest.mark.asyncio
    async def test_briefing_scenario_path_returns_brief_data(self):
        """When scenario exists in Redis, briefing transforms it to BriefData."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing
        from backend.pipeline.scenario import BuyerPortrait, Objection, Scenario

        scenario = Scenario(
            portrait=BuyerPortrait(
                role="CTO", pain_points=["latency"]
            ),
            objections=[
                Objection(trigger="дорого", response="ROI за 3 мес")
            ],
        )
        scenario_json = scenario.model_dump_json()

        async def redis_get(key):
            if "briefing:" in key:
                return None
            if ":scenario" in key:
                return scenario_json.encode()
            return None

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=redis_get)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        result = await generate_briefing(
            kb_id="test-kb",
            session_id="test-session",
            redis=mock_redis,
            api_key="test-key",
            model="test-model",
        )

        assert isinstance(result, BriefData)
        assert result.contact.role == "CTO"
        assert result.pain_points == ["latency"]
        assert len(result.objections) == 1
        assert result.objections[0].question == "дорого"

    @pytest.mark.asyncio
    async def test_briefing_scenario_path_caches_result(self):
        """Scenario path caches the transformed BriefData to Redis."""
        from backend.briefing.portrait import generate_briefing
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        scenario = Scenario(
            portrait=BuyerPortrait(role="CTO"),
        )
        scenario_json = scenario.model_dump_json()

        async def redis_get(key):
            if "briefing:" in key:
                return None
            if ":scenario" in key:
                return scenario_json.encode()
            return None

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=redis_get)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        await generate_briefing(
            kb_id="test-kb",
            session_id="test-session",
            redis=mock_redis,
            api_key="test-key",
            model="test-model",
        )

        mock_redis.set.assert_called_once()
        mock_redis.expire.assert_called_once()
        # Verify the cached value is valid JSON with 'contact' key
        cached_json = mock_redis.set.call_args[0][1]
        cached_data = json.loads(cached_json)
        assert "contact" in cached_data

    @pytest.mark.asyncio
    async def test_briefing_redis_none_returns_empty(self):
        """generate_briefing returns empty BriefData when Redis is None."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing

        result = await generate_briefing(
            kb_id="test-kb",
            session_id="test-session",
            redis=None,
            api_key="test-key",
            model="test-model",
        )

        assert isinstance(result, BriefData)
        assert result.contact.role == ""

    @pytest.mark.asyncio
    async def test_briefing_reparser_retries_on_invalid_json(self):
        """Reparser sends one retry when first LLM response fails validation."""
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import generate_briefing

        invalid_response = "not valid json at all"
        valid_response = json.dumps({
            "contact": {"role": "Retried"},
            "profileTags": [],
            "focusPoints": [{"headline": "Works now"}],
            "painPoints": [],
            "objections": [],
            "fullBrief": "",
        })

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.expire = AsyncMock()

        call_count = 0

        async def mock_llm(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return invalid_response
            return valid_response

        with patch(
            "backend.briefing.portrait.call_llm_simple",
            AsyncMock(side_effect=mock_llm),
        ):
            result = await generate_briefing(
                kb_id="test-kb",
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, BriefData)
        assert result.contact.role == "Retried"
        assert call_count == 2


# ── Task 6.2: Post-call Summary ───────────────────────────────────────────


class TestCallSummary:
    """Tests for generate_summary function."""

    @pytest.fixture
    def sample_utterances(self):
        """Sample conversation utterances stored in Redis format."""
        return [
            json.dumps(
                {"speaker": "rep", "text": "Добрый день!"}
            ).encode(),
            json.dumps(
                {"speaker": "client", "text": "Нам нужно CRM."}
            ).encode(),
            json.dumps(
                {"speaker": "rep", "text": "50 000 руб."}
            ).encode(),
        ]

    @pytest.fixture
    def mock_llm_summary_response(self):
        """Valid LLM response for summary generation."""
        return json.dumps(
            {
                "summary": "Клиент заинтересован в CRM.",
                "key_points": ["CRM для 50 менеджеров"],
                "action_items": ["Подготовить КП"],
                "email_draft": "Уважаемый клиент, высылаю КП.",
            }
        )

    @pytest.mark.asyncio
    async def test_summary_generates_key_points(
        self, sample_utterances, mock_llm_summary_response
    ):
        """generate_summary extracts main discussion topics."""
        from backend.summarize.call_summary import CallSummary, generate_summary

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=sample_utterances)
        mock_redis.get = AsyncMock(return_value=b"")

        with patch(
            "backend.summarize.call_summary.call_llm_simple",
            AsyncMock(return_value=mock_llm_summary_response),
        ):
            result = await generate_summary(
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, CallSummary)
        assert isinstance(result.key_points, list)
        assert len(result.key_points) >= 1

    @pytest.mark.asyncio
    async def test_summary_generates_email(
        self, sample_utterances, mock_llm_summary_response
    ):
        """generate_summary produces a formatted email draft."""
        from backend.summarize.call_summary import generate_summary

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=sample_utterances)
        mock_redis.get = AsyncMock(return_value=b"")

        with patch(
            "backend.summarize.call_summary.call_llm_simple",
            AsyncMock(return_value=mock_llm_summary_response),
        ):
            result = await generate_summary(
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert result.email_draft
        assert len(result.email_draft) > 10

    @pytest.mark.asyncio
    async def test_summary_references_sources(
        self, sample_utterances, mock_llm_summary_response
    ):
        """generate_summary email draft references facts from conversation."""
        from backend.summarize.call_summary import generate_summary

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=sample_utterances)
        mock_redis.get = AsyncMock(return_value=b"")

        with patch(
            "backend.summarize.call_summary.call_llm_simple",
            AsyncMock(return_value=mock_llm_summary_response),
        ):
            result = await generate_summary(
                session_id="test-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        combined = result.summary + " " + result.email_draft
        assert any(
            keyword in combined
            for keyword in ["CRM", "КП", "клиент"]
        )

    @pytest.mark.asyncio
    async def test_summary_empty_session(self):
        """generate_summary handles empty session gracefully."""
        from backend.summarize.call_summary import CallSummary, generate_summary

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[])
        mock_redis.get = AsyncMock(return_value=b"")

        with patch(
            "backend.summarize.call_summary.call_llm_simple",
            AsyncMock(
                return_value=json.dumps(
                    {
                        "summary": "Разговор не состоялся.",
                        "key_points": [],
                        "action_items": [],
                        "email_draft": "",
                    }
                )
            ),
        ):
            result = await generate_summary(
                session_id="empty-session",
                redis=mock_redis,
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, CallSummary)


# ── FEAT-012: SGR BriefData Models ───────────────────────────────────────


class TestBriefDataModels:
    """Tests for SGR BriefData Pydantic models."""

    def test_brief_data_serializes_to_camelcase(self):
        from backend.briefing.models import BriefContact, BriefData, BriefFocusPoint

        brief = BriefData(
            contact=BriefContact(role="CTO", company="Acme"),
            focus_points=[BriefFocusPoint(headline="Test", detail="Detail")],
            pain_points=["pain1"],
        )
        data = brief.model_dump(by_alias=True)
        assert "focusPoints" in data
        assert "painPoints" in data
        assert "profileTags" in data
        assert "fullBrief" in data
        assert "focus_points" not in data

    def test_brief_profile_tag_rejects_invalid_color(self):
        from backend.briefing.models import BriefProfileTag

        with pytest.raises(Exception):
            BriefProfileTag(label="test", color="yellow")

    def test_brief_profile_tag_accepts_valid_colors(self):
        from backend.briefing.models import BriefProfileTag

        for color in ("blue", "green", "amber"):
            tag = BriefProfileTag(label="test", color=color)
            assert tag.color == color

    def test_brief_data_empty_defaults(self):
        from backend.briefing.models import BriefData

        brief = BriefData()
        data = brief.model_dump(by_alias=True)
        assert data["contact"]["role"] == ""
        assert data["profileTags"] == []
        assert data["focusPoints"] == []
        assert data["painPoints"] == []
        assert data["roi"] is None
        assert data["comparison"] is None
        assert data["objections"] == []
        assert data["fullBrief"] == ""

    def test_brief_data_schema_has_descriptions(self):
        """SGR: every field in the schema must have a description for the LLM."""
        from backend.briefing.models import (
            BriefContact,
            BriefFocusPoint,
            BriefObjection,
        )

        for model in (BriefContact, BriefFocusPoint, BriefObjection):
            schema = model.model_json_schema()
            for name, prop in schema.get("properties", {}).items():
                assert "description" in prop, f"{model.__name__}.{name} missing description"

    def test_brief_data_json_schema_for_llm(self):
        """BriefData.model_json_schema() is valid for response_format."""
        from backend.briefing.models import BriefData

        schema = BriefData.model_json_schema()
        assert "properties" in schema
        assert "contact" in schema["properties"]

    def test_brief_data_validates_llm_response(self):
        """BriefData can parse a typical LLM JSON response."""
        from backend.briefing.models import BriefData

        llm_response = {
            "contact": {"role": "CTO", "company": "Test Corp"},
            "profileTags": [{"label": "ROI-focused", "color": "blue"}],
            "focusPoints": [{"headline": "Save time", "detail": "Auto-fill CRM"}],
            "painPoints": ["Manual data entry"],
            "roi": {"value": "42M", "description": "annual revenue uplift"},
            "comparison": None,
            "objections": [{"question": "Too expensive", "answer": "30% savings"}],
            "fullBrief": "Full text here.",
        }
        brief = BriefData.model_validate(llm_response)
        assert brief.contact.role == "CTO"
        assert brief.roi is not None
        assert brief.roi.value == "42M"


# ── FEAT-012: Scenario → BriefData transformation ────────────────────────


class TestScenarioToBrief:
    """Tests for scenario_to_brief() fast-path transformation."""

    def test_maps_portrait_to_contact(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        scenario = Scenario(
            portrait=BuyerPortrait(role="CTO", budget="500K", pain_points=["latency"]),
        )
        brief = scenario_to_brief(scenario)
        assert brief.contact.role == "CTO"
        assert brief.contact.budget_note == "500K"
        assert brief.pain_points == ["latency"]

    def test_maps_trigger_to_question(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Objection, Scenario

        scenario = Scenario(
            objections=[
                Objection(trigger="дорого", response="ROI за 3 мес"),
            ]
        )
        brief = scenario_to_brief(scenario)
        assert brief.objections[0].question == "дорого"
        assert brief.objections[0].answer == "ROI за 3 мес"

    def test_maps_key_messages_to_focus_points(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Scenario, Strategy

        scenario = Scenario(strategy=Strategy(key_messages=["Fast", "Cheap", "Good"]))
        brief = scenario_to_brief(scenario)
        assert len(brief.focus_points) == 3
        assert brief.focus_points[0].headline == "Fast"

    def test_caps_at_3(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Objection, Scenario, Strategy

        scenario = Scenario(
            strategy=Strategy(key_messages=["a", "b", "c", "d", "e"]),
            objections=[
                Objection(trigger=f"t{i}", response=f"r{i}") for i in range(5)
            ],
        )
        brief = scenario_to_brief(scenario)
        assert len(brief.focus_points) == 3
        assert len(brief.objections) == 3

    def test_motivators_to_tags(self):
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import BuyerPortrait, Scenario

        scenario = Scenario(
            portrait=BuyerPortrait(motivators=["ROI-focused", "Likes data"])
        )
        brief = scenario_to_brief(scenario)
        assert len(brief.profile_tags) == 2
        assert brief.profile_tags[0].color in ("blue", "green", "amber")

    def test_empty_scenario(self):
        from backend.briefing.models import BriefData
        from backend.briefing.portrait import scenario_to_brief
        from backend.pipeline.scenario import Scenario

        brief = scenario_to_brief(Scenario())
        assert isinstance(brief, BriefData)
        assert brief.contact.role == ""
