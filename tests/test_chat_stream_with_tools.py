from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from sediman.llm.provider import (
    LLMResponse,
    ToolCall,
    ToolDefinition,
    OpenAICompatibleProvider,
)


def _make_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(model="gpt-4o", api_key="test-key")


def _text_delta(text: str) -> MagicMock:
    delta = MagicMock()
    delta.content = text
    delta.tool_calls = None
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = None
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _tool_call_delta(index: int, tc_id: str = "", name: str = "", arguments: str = "") -> MagicMock:
    tc_delta = MagicMock()
    tc_delta.index = index
    tc_delta.id = tc_id
    tc_delta.function = MagicMock()
    tc_delta.function.name = name
    tc_delta.function.arguments = arguments

    delta = MagicMock()
    delta.content = None
    delta.tool_calls = [tc_delta]

    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = None

    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _finish_chunk(reason: str = "stop") -> MagicMock:
    choice = MagicMock()
    choice.delta = MagicMock(content=None, tool_calls=None)
    choice.finish_reason = reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


async def _fake_stream(chunks):
    for c in chunks:
        yield c


class TestChatStreamWithTools:
    @pytest.mark.asyncio
    async def test_text_only_stream(self):
        provider = _make_provider()
        chunks = [
            _text_delta("Hello"),
            _text_delta(" world"),
            _finish_chunk("stop"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert isinstance(result, LLMResponse)
        assert result.text == "Hello world"
        assert result.tool_calls == []
        assert result.done is True

    @pytest.mark.asyncio
    async def test_text_only_with_on_token(self):
        provider = _make_provider()
        tokens = []
        chunks = [
            _text_delta("A"),
            _text_delta("B"),
            _text_delta("C"),
            _finish_chunk("stop"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            on_token=lambda t: tokens.append(t),
        )
        assert tokens == ["A", "B", "C"]
        assert result.text == "ABC"

    @pytest.mark.asyncio
    async def test_tool_call_stream(self):
        provider = _make_provider()
        chunks = [
            _tool_call_delta(0, tc_id="tc_1", name="terminal", arguments='{"co'),
            _tool_call_delta(0, arguments='mmand": "ls"}'),
            _finish_chunk("tool_calls"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "run ls"}],
            tools=[ToolDefinition(name="terminal", description="run cmd", parameters={})],
        )
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.id == "tc_1"
        assert tc.name == "terminal"
        assert tc.arguments == {"command": "ls"}
        assert result.done is False

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self):
        provider = _make_provider()
        chunks = [
            _tool_call_delta(0, tc_id="tc_1", name="terminal", arguments='{"command":"ls"}'),
            _tool_call_delta(1, tc_id="tc_2", name="read_file", arguments='{"path":"a.py"}'),
            _finish_chunk("tool_calls"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "do stuff"}],
            tools=[
                ToolDefinition(name="terminal", description="run", parameters={}),
                ToolDefinition(name="read_file", description="read", parameters={}),
            ],
        )
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "terminal"
        assert result.tool_calls[1].name == "read_file"

    @pytest.mark.asyncio
    async def test_mixed_text_and_tool_calls(self):
        provider = _make_provider()
        tokens = []
        chunks = [
            _text_delta("I'll run that for you."),
            _tool_call_delta(0, tc_id="tc_1", name="terminal", arguments='{"command":"make"}'),
            _finish_chunk("tool_calls"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "build it"}],
            tools=[ToolDefinition(name="terminal", description="run", parameters={})],
            on_token=lambda t: tokens.append(t),
        )
        assert tokens == ["I'll run that for you."]
        assert result.text == "I'll run that for you."
        assert len(result.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_system_message_prepended(self):
        provider = _make_provider()
        chunks = [_text_delta("ok"), _finish_chunk("stop")]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            system="You are a coder.",
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        msgs = call_kwargs["messages"]
        assert msgs[0] == {"role": "system", "content": "You are a coder."}

    @pytest.mark.asyncio
    async def test_tools_passed_in_format(self):
        provider = _make_provider()
        chunks = [_text_delta("ok"), _finish_chunk("stop")]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        tools = [ToolDefinition(name="terminal", description="run", parameters={"type": "object", "properties": {}})]
        await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["tools"][0]["type"] == "function"

    @pytest.mark.asyncio
    async def test_empty_stream(self):
        provider = _make_provider()

        async def _empty(**kwargs):
            return
            yield

        provider.client.chat.completions.create = AsyncMock(
            return_value=_empty()
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        assert result.text is None or result.text == ""
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_on_token_exception_ignored(self):
        provider = _make_provider()
        call_count = [0]

        def bad_token(t):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("callback error")

        chunks = [_text_delta("A"), _text_delta("B"), _finish_chunk("stop")]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            on_token=bad_token,
        )
        assert result.text == "AB"
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_malformed_tool_arguments_handled(self):
        provider = _make_provider()
        chunks = [
            _tool_call_delta(0, tc_id="tc_1", name="terminal", arguments="not-json"),
            _finish_chunk("tool_calls"),
        ]
        provider.client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(chunks)
        )

        result = await provider.chat_stream_with_tools(
            messages=[{"role": "user", "content": "run"}],
            tools=[ToolDefinition(name="terminal", description="run", parameters={})],
        )
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments == {}
