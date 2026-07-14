"""Tests for shared LLM utility (call_llm_simple)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCallLlmSimple:
    @pytest.mark.asyncio
    async def test_passes_prompt_and_system_prompt(self) -> None:
        from backend.pipeline.shared_llm import call_llm_simple

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="result"))
        ]

        with patch(
            "backend.pipeline.shared_llm.AsyncOpenAI"
        ) as MockClient:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            MockClient.return_value = client

            result = await call_llm_simple(
                prompt="test prompt",
                system_prompt="test system",
                api_key="key-123",
                model="gpt-4",
            )

            assert result == "result"
            client.chat.completions.create.assert_called_once()
            call_args = client.chat.completions.create.call_args
            assert call_args.kwargs["model"] == "gpt-4"
            messages = call_args.kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "test system"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "test prompt"

    @pytest.mark.asyncio
    async def test_uses_openrouter_base_url(self) -> None:
        from backend.pipeline.shared_llm import call_llm_simple

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="ok"))
        ]

        with patch(
            "backend.pipeline.shared_llm.AsyncOpenAI"
        ) as MockClient:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            MockClient.return_value = client

            await call_llm_simple(
                prompt="p",
                system_prompt="s",
                api_key="k",
                model="m",
            )

            MockClient.assert_called_once_with(
                api_key="k",
                base_url="https://openrouter.ai/api/v1",
            )

    @pytest.mark.asyncio
    async def test_returns_empty_on_none_content(self) -> None:
        from backend.pipeline.shared_llm import call_llm_simple

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=None))
        ]

        with patch(
            "backend.pipeline.shared_llm.AsyncOpenAI"
        ) as MockClient:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            MockClient.return_value = client

            result = await call_llm_simple(
                prompt="p",
                system_prompt="s",
                api_key="k",
                model="m",
            )

            assert result == ""

    @pytest.mark.asyncio
    async def test_stream_false(self) -> None:
        from backend.pipeline.shared_llm import call_llm_simple

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="ok"))
        ]

        with patch(
            "backend.pipeline.shared_llm.AsyncOpenAI"
        ) as MockClient:
            client = AsyncMock()
            client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            MockClient.return_value = client

            await call_llm_simple(
                prompt="p",
                system_prompt="s",
                api_key="k",
                model="m",
            )

            call_args = client.chat.completions.create.call_args
            assert call_args.kwargs["stream"] is False


class TestPortraitUsesSharedLlm:
    def test_no_local_call_llm(self) -> None:
        """portrait.py should not define its own _call_llm."""
        import inspect

        from backend.briefing import portrait

        source = inspect.getsource(portrait)
        # Should import from shared_llm, not define locally
        assert "from backend.pipeline.shared_llm import" in source
        assert "async def _call_llm" not in source


class TestCallSummaryUsesSharedLlm:
    def test_no_local_call_llm(self) -> None:
        """call_summary.py should not define its own _call_llm."""
        import inspect

        from backend.summarize import call_summary

        source = inspect.getsource(call_summary)
        assert "from backend.pipeline.shared_llm import" in source
        assert "async def _call_llm" not in source
