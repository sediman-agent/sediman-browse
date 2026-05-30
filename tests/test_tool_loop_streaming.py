from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.tool_dispatch import ToolLoop, ToolRegistry, ToolResult
from sediman.llm.provider import LLMResponse, ToolCall, ToolDefinition


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="terminal", description="run cmd", parameters={}),
        AsyncMock(return_value=ToolResult(success=True, output="ok")),
    )
    registry.register(
        ToolDefinition(name="read_file", description="read", parameters={}),
        AsyncMock(return_value=ToolResult(success=True, output="file contents")),
    )
    return registry


def _make_loop(registry=None) -> ToolLoop:
    llm = MagicMock()
    return ToolLoop(llm=llm, registry=registry or _make_registry(), max_rounds=5)


class TestToolLoopRunStreaming:
    @pytest.mark.asyncio
    async def test_text_only_response(self):
        loop = _make_loop()
        response = LLMResponse(text="Hello!", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(return_value=response)

        result = await loop.run_streaming(
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful.",
        )
        assert result.text == "Hello!"
        assert result.done is True

    @pytest.mark.asyncio
    async def test_streaming_callback_called(self):
        loop = _make_loop()
        tokens = []
        response = LLMResponse(text="Hello!", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(return_value=response)

        await loop.run_streaming(
            messages=[{"role": "user", "content": "hi"}],
            on_streaming_text=lambda t: tokens.append(t),
        )
        loop.llm.chat_stream_with_tools.assert_called_once()
        call_kwargs = loop.llm.chat_stream_with_tools.call_args
        assert call_kwargs.kwargs.get("on_token") is not None or (
            len(call_kwargs.args) > 3
        )

    @pytest.mark.asyncio
    async def test_tool_calls_dispatched(self):
        loop = _make_loop()
        tc = ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})
        response_with_tools = LLMResponse(
            text=None, tool_calls=[tc], done=False
        )
        final_response = LLMResponse(text="Here are the files.", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(
            side_effect=[response_with_tools, final_response]
        )

        result = await loop.run_streaming(
            messages=[{"role": "user", "content": "list files"}],
        )
        assert result.text == "Here are the files."
        assert result.done is True
        assert loop.llm.chat_stream_with_tools.call_count == 2

    @pytest.mark.asyncio
    async def test_on_tool_call_callback(self):
        loop = _make_loop()
        tool_calls_log = []
        tc = ToolCall(id="tc1", name="terminal", arguments={"command": "echo hello"})
        response_with_tools = LLMResponse(
            text=None, tool_calls=[tc], done=False
        )
        final_response = LLMResponse(text="done", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(
            side_effect=[response_with_tools, final_response]
        )

        await loop.run_streaming(
            messages=[{"role": "user", "content": "echo"}],
            on_tool_call=lambda name, args: tool_calls_log.append((name, args)),
        )
        assert len(tool_calls_log) == 1
        assert tool_calls_log[0][0] == "terminal"

    @pytest.mark.asyncio
    async def test_system_prompt_prepended_to_messages(self):
        loop = _make_loop()
        response = LLMResponse(text="ok", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(return_value=response)

        await loop.run_streaming(
            messages=[{"role": "user", "content": "hi"}],
            system="You are a coding agent.",
        )
        call_kwargs = loop.llm.chat_stream_with_tools.call_args.kwargs
        msgs = call_kwargs.get("messages", [])
        assert msgs[0] == {"role": "system", "content": "You are a coding agent."}
        assert msgs[1] == {"role": "user", "content": "hi"}

    @pytest.mark.asyncio
    async def test_max_rounds_exhausted(self):
        loop = _make_loop()
        tc = ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})
        loop.llm.chat_stream_with_tools = AsyncMock(
            return_value=LLMResponse(text=None, tool_calls=[tc], done=False)
        )

        result = await loop.run_streaming(
            messages=[{"role": "user", "content": "run forever"}],
        )
        assert "exhausted" in result.text.lower()
        assert result.done is True

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_round(self):
        loop = _make_loop()
        tc1 = ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})
        tc2 = ToolCall(id="tc2", name="read_file", arguments={"path": "test.py"})
        response_with_tools = LLMResponse(
            text=None, tool_calls=[tc1, tc2], done=False
        )
        final_response = LLMResponse(text="done", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(
            side_effect=[response_with_tools, final_response]
        )

        tool_calls_log = []
        result = await loop.run_streaming(
            messages=[{"role": "user", "content": "do stuff"}],
            on_tool_call=lambda name, args: tool_calls_log.append(name),
        )
        assert result.text == "done"
        assert len(tool_calls_log) == 2
        assert "terminal" in tool_calls_log
        assert "read_file" in tool_calls_log

    @pytest.mark.asyncio
    async def test_messages_accumulated_across_rounds(self):
        loop = _make_loop()
        tc = ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})
        response1 = LLMResponse(text="", tool_calls=[tc], done=False)
        response2 = LLMResponse(text="all done", tool_calls=[], done=True)
        loop.llm.chat_stream_with_tools = AsyncMock(
            side_effect=[response1, response2]
        )

        await loop.run_streaming(
            messages=[{"role": "user", "content": "list"}],
        )
        second_call_kwargs = loop.llm.chat_stream_with_tools.call_args_list[1]
        second_msgs = second_call_kwargs.kwargs.get("messages") or second_call_kwargs[1].get("messages")
        assert second_msgs is not None
