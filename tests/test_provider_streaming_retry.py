from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.llm.provider import (
    LLMResponse,
    ToolCall,
    ToolDefinition,
    OpenAICompatibleProvider,
)


def _make_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(model="gpt-4o", api_key="test-key")


def _mock_response(
    content: str | None = "hi",
    tool_calls: list | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    message = MagicMock()
    message.content = content
    if tool_calls is not None:
        message.tool_calls = tool_calls
    else:
        message.tool_calls = None

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


async def _collect(aiter):
    out = []
    async for item in aiter:
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# 1. chat_stream
# ---------------------------------------------------------------------------


class TestChatStream:
    @pytest.mark.asyncio
    async def test_yields_tokens_from_stream(self):
        provider = _make_provider()

        chunks = []
        for text in ("Hel", "lo ", "world"):
            delta = MagicMock()
            delta.content = text
            chunk = MagicMock()
            chunk.choices = [MagicMock(delta=delta)]
            chunks.append(chunk)

        async def _fake_aiter(**kwargs):
            for c in chunks:
                yield c

        mock_ctx = AsyncMock(return_value=_fake_aiter())
        provider.client.chat.completions.create = mock_ctx

        tokens = await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
        )
        assert tokens == ["Hel", "lo ", "world"]

    @pytest.mark.asyncio
    async def test_temperature_not_passed_to_api(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="x"))])

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_system_message_prepended(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="ok"))])

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                system="You are helpful.",
            )
        )
        sent_messages = provider.client.chat.completions.create.call_args[1]["messages"]
        assert sent_messages[0] == {"role": "system", "content": "You are helpful."}
        assert sent_messages[1] == {"role": "user", "content": "hi"}

    @pytest.mark.asyncio
    async def test_tools_passed_in_correct_format(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="ok"))])

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        tools = [
            ToolDefinition(
                name="get_weather",
                description="Get weather",
                parameters={"type": "object", "properties": {"city": {"type": "string"}}},
            )
        ]

        await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=tools,
            )
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_empty_stream_no_yields(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            return
            yield

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        tokens = await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
        )
        assert tokens == []


# ---------------------------------------------------------------------------
# 2. _chat_with_retry
# ---------------------------------------------------------------------------


class TestChatWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        provider = _make_provider()
        mock_resp = _mock_response("ok")
        provider.client.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await provider._chat_with_retry({"model": "gpt-4o", "messages": []})
        assert result is mock_resp
        assert provider.client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_connection_error_retries(self):
        provider = _make_provider()
        mock_resp = _mock_response("ok")
        provider.client.chat.completions.create = AsyncMock(
            side_effect=[ConnectionError("boom"), mock_resp]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider._chat_with_retry(
                {"model": "gpt-4o", "messages": []}, max_retries=3
            )
        assert result is mock_resp
        assert provider.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_error_retries(self):
        provider = _make_provider()
        rate_limit_err = Exception("RateLimitError: 429 too many requests")
        mock_resp = _mock_response("ok")
        provider.client.chat.completions.create = AsyncMock(
            side_effect=[rate_limit_err, mock_resp]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider._chat_with_retry(
                {"model": "gpt-4o", "messages": []}, max_retries=3
            )
        assert result is mock_resp
        assert provider.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_server_error_500_retries(self):
        provider = _make_provider()
        err500 = Exception("Internal Server Error 500")
        mock_resp = _mock_response("ok")
        provider.client.chat.completions.create = AsyncMock(
            side_effect=[err500, mock_resp]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider._chat_with_retry(
                {"model": "gpt-4o", "messages": []}, max_retries=3
            )
        assert result is mock_resp

    @pytest.mark.asyncio
    async def test_server_error_502_503_504_retries(self):
        provider = _make_provider()
        mock_resp = _mock_response("ok")
        for code in ("502", "503", "504"):
            provider.client.chat.completions.create = AsyncMock(
                side_effect=[Exception(f"Bad Gateway {code}"), mock_resp]
            )
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider._chat_with_retry(
                    {"model": "gpt-4o", "messages": []}, max_retries=3
                )
            assert result is mock_resp

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self):
        provider = _make_provider()
        provider.client.chat.completions.create = AsyncMock(
            side_effect=ValueError("bad input")
        )

        with pytest.raises(ValueError, match="bad input"):
            await provider._chat_with_retry(
                {"model": "gpt-4o", "messages": []}, max_retries=3
            )
        assert provider.client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises(self):
        provider = _make_provider()
        provider.client.chat.completions.create = AsyncMock(
            side_effect=ConnectionError("down")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ConnectionError, match="down"):
                await provider._chat_with_retry(
                    {"model": "gpt-4o", "messages": []}, max_retries=2
                )
        assert provider.client.chat.completions.create.call_count == 3


# ---------------------------------------------------------------------------
# 3. get_planning_provider
# ---------------------------------------------------------------------------


class TestGetPlanningProvider:
    def test_returns_self_for_gpt4o(self):
        provider = _make_provider()
        result = provider.get_planning_provider()
        assert isinstance(result, OpenAICompatibleProvider)
        assert result.model == "gpt-4o-mini"

    def test_returns_same_instance_regardless_of_model(self):
        provider = OpenAICompatibleProvider(model="gpt-4o-mini", api_key="test-key")
        assert provider.get_planning_provider() is provider

    def test_returns_self_for_custom_model(self):
        provider = OpenAICompatibleProvider(
            model="claude-3.5-sonnet", api_key="test-key"
        )
        result = provider.get_planning_provider()
        assert isinstance(result, OpenAICompatibleProvider)
        assert result.model == "claude-3-haiku"


# ---------------------------------------------------------------------------
# 4. Temperature parameter
# ---------------------------------------------------------------------------


class TestTemperatureParameter:
    @pytest.mark.asyncio
    async def test_chat_passes_temperature(self):
        provider = _make_provider()
        mock_resp = _mock_response("warm")
        provider.client.chat.completions.create = AsyncMock(return_value=mock_resp)

        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_omits_temperature_when_none(self):
        provider = _make_provider()
        mock_resp = _mock_response("cool")
        provider.client.chat.completions.create = AsyncMock(return_value=mock_resp)

        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_stream_passes_temperature(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="t"))])

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    @pytest.mark.asyncio
    async def test_chat_stream_omits_temperature_when_none(self):
        provider = _make_provider()

        async def _fake_aiter(**kwargs):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="t"))])

        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_aiter()
        )

        await _collect(
            provider.chat_stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs


# ---------------------------------------------------------------------------
# 5. chat_with_failover
# ---------------------------------------------------------------------------


class TestChatWithFailover:
    @pytest.mark.asyncio
    async def test_success_on_primary(self):
        provider = _make_provider()
        mock_resp = _mock_response("primary ok")
        provider.client.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await provider.chat_with_failover(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert result.text == "primary ok"

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        provider = _make_provider()
        provider.client.chat.completions.create = AsyncMock(
            side_effect=Exception("primary dead")
        )

        fallback = _make_provider()
        fallback_resp = _mock_response("fallback ok")
        fallback.client.chat.completions.create = AsyncMock(return_value=fallback_resp)

        result = await provider.chat_with_failover(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            fallback_provider=fallback,
        )
        assert result.text == "fallback ok"
        fallback.client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_fallback_raises(self):
        provider = _make_provider()
        provider.client.chat.completions.create = AsyncMock(
            side_effect=Exception("primary dead")
        )

        with pytest.raises(Exception, match="primary dead"):
            await provider.chat_with_failover(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
