import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.guardrails import Budget, GLOBAL_APPROVAL
from sediman.agent.interrupt import InterruptedError, InterruptSignal
from sediman.agent.tool_dispatch import (
    ToolLoop,
    ToolRegistry,
    ToolResult,
    _py_type_to_json_type,
    _TOOL_REGISTRY,
    discover_tools,
    get_decorated_tool_definitions,
    get_decorated_tool_handlers,
    register_tool_fn,
    tool,
)
from sediman.llm.provider import LLMResponse, ToolCall, ToolDefinition


@pytest.fixture(autouse=True)
def _reset_singletons():
    saved_keys = set(_TOOL_REGISTRY.keys())
    for k in list(_TOOL_REGISTRY.keys()):
        del _TOOL_REGISTRY[k]
    InterruptSignal.reset_instance()
    orig_callback = GLOBAL_APPROVAL._callback
    GLOBAL_APPROVAL._callback = None
    yield
    for k in list(_TOOL_REGISTRY.keys()):
        del _TOOL_REGISTRY[k]
    GLOBAL_APPROVAL._callback = orig_callback
    InterruptSignal.reset_instance()


def _make_handler(success: bool = True, output: str = "ok", data: Any = None):
    async def handler(**kwargs):
        return ToolResult(success=success, output=output, data=data)
    return handler


def _make_def(name: str = "test_tool", description: str = "A test tool"):
    return ToolDefinition(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {"x": {"type": "string"}}},
    )


class TestToolResult:
    def test_defaults(self):
        r = ToolResult(success=True, output="done")
        assert r.success is True
        assert r.output == "done"
        assert r.data is None

    def test_with_data(self):
        r = ToolResult(success=True, output="ok", data={"key": 1})
        assert r.data == {"key": 1}


class TestPyTypeToJsonType:
    @pytest.mark.parametrize(
        "py_type,expected",
        [
            (str, "string"),
            (int, "integer"),
            (float, "number"),
            (bool, "boolean"),
            (list, "array"),
            (dict, "object"),
            (type(None), "null"),
        ],
    )
    def test_basic_mappings(self, py_type, expected):
        assert _py_type_to_json_type(py_type) == expected

    def test_generic_list(self):
        from typing import List
        assert _py_type_to_json_type(List[str]) == "array"

    def test_generic_dict(self):
        from typing import Dict
        assert _py_type_to_json_type(Dict[str, int]) == "object"

    def test_unknown_type_defaults_to_string(self):
        assert _py_type_to_json_type(complex) == "string"


class TestToolRegistry:
    def test_register_and_has_tool(self):
        reg = ToolRegistry()
        reg.register(_make_def("foo"), _make_handler())
        assert reg.has_tool("foo")
        assert not reg.has_tool("bar")

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(_make_def("a"), _make_handler())
        reg.register(_make_def("b"), _make_handler())
        assert sorted(reg.list_tools()) == ["a", "b"]

    def test_get_definitions(self):
        reg = ToolRegistry()
        d = _make_def("my_tool")
        reg.register(d, _make_handler())
        defs = reg.get_definitions()
        assert len(defs) == 1
        assert defs[0].name == "my_tool"

    def test_get_definition(self):
        reg = ToolRegistry()
        d = _make_def("xyz")
        reg.register(d, _make_handler())
        assert reg.get_definition("xyz") is d

    def test_get_openai_tools(self):
        reg = ToolRegistry()
        d = ToolDefinition(
            name="calc",
            description="Calculate",
            parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
        )
        reg.register(d, _make_handler())
        openai = reg.get_openai_tools()
        assert len(openai) == 1
        assert openai[0]["type"] == "function"
        assert openai[0]["function"]["name"] == "calc"
        assert openai[0]["function"]["description"] == "Calculate"
        assert openai[0]["function"]["parameters"] == d.parameters

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        reg = ToolRegistry()
        reg.register(_make_def("add"), _make_handler(success=True, output="42"))
        result = await reg.dispatch("add", {"x": "1"})
        assert result.success is True
        assert result.output == "42"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.dispatch("nonexistent", {})
        assert result.success is False
        assert "Unknown tool" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_high_risk_blocked(self):
        reg = ToolRegistry()
        reg.register(_make_def("write_file"), _make_handler())

        GLOBAL_APPROVAL.set_callback(AsyncMock(return_value=False))

        with patch("sediman.agent.tool_dispatch.assess_risk", return_value="high"):
            result = await reg.dispatch("write_file", {"path": "/tmp/x"})

        assert result.success is False
        assert "not approved" in result.output

    @pytest.mark.asyncio
    async def test_dispatch_high_risk_approved(self):
        reg = ToolRegistry()
        reg.register(_make_def("write_file"), _make_handler(output="written"))

        GLOBAL_APPROVAL.set_callback(AsyncMock(return_value=True))

        with patch("sediman.agent.tool_dispatch.assess_risk", return_value="high"):
            result = await reg.dispatch("write_file", {"path": "/tmp/x"})

        assert result.success is True
        assert result.output == "written"

    @pytest.mark.asyncio
    async def test_dispatch_handler_exception(self):
        reg = ToolRegistry()
        async def bad_handler(**kw):
            raise ValueError("boom")
        reg.register(_make_def("broken"), bad_handler)
        result = await reg.dispatch("broken", {})
        assert result.success is False
        assert "Tool error" in result.output
        assert "boom" in result.output

    def test_set_checkpoint_manager(self):
        reg = ToolRegistry()
        mgr = MagicMock()
        reg.set_checkpoint_manager(mgr)
        assert reg._checkpoint_manager is mgr

    def test_register_decorated(self):
        @tool
        def sample_tool(x: str) -> str:
            """A sample."""
            return x

        reg = ToolRegistry()
        reg.register_decorated()
        assert reg.has_tool("sample_tool")


class TestToolDecorator:
    def test_registers_function(self):
        @tool
        def my_calc(a: int, b: int) -> int:
            """Add numbers."""
            return a + b

        assert "my_calc" in _TOOL_REGISTRY

    def test_custom_name_and_description(self):
        @tool(name="custom_name", description="Custom desc")
        def _unused(x: str):
            pass

        entry = _TOOL_REGISTRY["custom_name"]
        assert entry["definition"].name == "custom_name"
        assert entry["definition"].description == "Custom desc"

    def test_schema_extraction(self):
        @tool
        def typed_fn(name: str, count: int, ratio: float, flag: bool = False) -> str:
            """Typed fn."""
            return ""

        entry = _TOOL_REGISTRY["typed_fn"]
        params = entry["definition"].parameters
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["count"]["type"] == "integer"
        assert params["properties"]["ratio"]["type"] == "number"
        assert params["properties"]["flag"]["type"] == "boolean"
        assert params["properties"]["flag"]["default"] is False
        assert "name" in params["required"]
        assert "count" in params["required"]
        assert "flag" not in params.get("required", [])

    def test_docstring_as_description(self):
        @tool
        def doc_tool(x: str):
            """This is the docstring."""
            pass

        assert _TOOL_REGISTRY["doc_tool"]["definition"].description == "This is the docstring."

    @pytest.mark.asyncio
    async def test_async_wrapper_calls_sync_fn(self):
        @tool
        def sync_fn(x: str) -> str:
            return f"result_{x}"

        handler = _TOOL_REGISTRY["sync_fn"]["handler"]
        result = await handler(x="hello")
        assert result == "result_hello"

    @pytest.mark.asyncio
    async def test_async_wrapper_calls_async_fn(self):
        @tool
        async def async_fn(x: str) -> str:
            return f"async_{x}"

        handler = _TOOL_REGISTRY["async_fn"]["handler"]
        result = await handler(x="world")
        assert result == "async_world"


class TestDiscoverTools:
    def test_discovers_registered_tools(self):
        @tool
        def disc_tool(x: str) -> str:
            """Discovery test."""
            return x

        results = discover_tools()
        names = [r[0] for r in results]
        assert "disc_tool" in names

    def test_get_decorated_definitions(self):
        @tool
        def def_tool(x: int) -> int:
            """Def test."""
            return x

        defs = get_decorated_tool_definitions()
        assert any(d.name == "def_tool" for d in defs)

    def test_get_decorated_handlers(self):
        @tool
        def handler_tool(x: str) -> str:
            return x

        handlers = get_decorated_tool_handlers()
        assert "handler_tool" in handlers

    def test_register_tool_fn(self):
        def manual_fn(**kw):
            return ToolResult(success=True, output="manual")
        d = _make_def("manual_tool")
        register_tool_fn("manual_tool", AsyncMock(return_value=ToolResult(success=True, output="manual")), d)
        assert "manual_tool" in _TOOL_REGISTRY


class TestToolLoop:
    def _make_mock_llm(self, responses: list[LLMResponse]):
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=list(responses))
        return llm

    def _make_registry_with_tool(self, name="test_tool", output="result"):
        reg = ToolRegistry()
        reg.register(_make_def(name), _make_handler(success=True, output=output))
        return reg

    @pytest.mark.asyncio
    async def test_no_tools_text_response(self):
        llm = self._make_mock_llm([
            LLMResponse(text="Hello world", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)
        result = await loop.run([{"role": "user", "content": "hi"}])
        assert result.text == "Hello world"
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_single_tool_call(self):
        llm = self._make_mock_llm([
            LLMResponse(
                text="",
                tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={"x": "hello"})],
            ),
            LLMResponse(text="Done after tool", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool(output="tool_output")
        loop = ToolLoop(llm, reg)
        result = await loop.run([{"role": "user", "content": "do it"}])
        assert result.text == "Done after tool"
        assert result.tool_calls == []
        assert llm.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_multiple_parallel_tool_calls(self):
        reg = ToolRegistry()
        reg.register(
            ToolDefinition(name="tool_a", description="A", parameters={"type": "object", "properties": {}}),
            _make_handler(success=True, output="result_a"),
        )
        reg.register(
            ToolDefinition(name="tool_b", description="B", parameters={"type": "object", "properties": {}}),
            _make_handler(success=True, output="result_b"),
        )

        llm = self._make_mock_llm([
            LLMResponse(
                text="",
                tool_calls=[
                    ToolCall(id="tc1", name="tool_a", arguments={}),
                    ToolCall(id="tc2", name="tool_b", arguments={}),
                ],
            ),
            LLMResponse(text="Both done", tool_calls=[], done=True),
        ])

        loop = ToolLoop(llm, reg)
        result = await loop.run([{"role": "user", "content": "run both"}])
        assert result.text == "Both done"

        second_call_msgs = llm.chat.call_args_list[1].kwargs.get("messages") or llm.chat.call_args_list[1][1]
        tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        outputs = {m["content"] for m in tool_msgs}
        assert "result_a" in outputs
        assert "result_b" in outputs

    @pytest.mark.asyncio
    async def test_max_rounds_exhaustion(self):
        tool_call_response = LLMResponse(
            text="",
            tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={"x": "loop"})],
        )
        llm = self._make_mock_llm([tool_call_response] * 30)
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg, max_rounds=5)
        result = await loop.run([{"role": "user", "content": "loop forever"}])
        assert "exhausted" in result.text.lower()
        assert "5 rounds" in result.text
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_budget_exhaustion(self):
        llm = self._make_mock_llm([
            LLMResponse(text="ok", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        budget = MagicMock()
        budget.is_exhausted = MagicMock(return_value=(True, "wall_time"))
        loop = ToolLoop(llm, reg, budget=budget)
        result = await loop.run([{"role": "user", "content": "hi"}])
        assert result.text == ""
        assert result.done is True
        llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_interrupt_signal(self):
        InterruptSignal.get().trigger("user cancel")
        llm = self._make_mock_llm([
            LLMResponse(text="ok", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)
        with pytest.raises(InterruptedError, match="user cancel"):
            await loop.run([{"role": "user", "content": "hi"}])
        InterruptSignal.get().clear()

    @pytest.mark.asyncio
    async def test_on_tool_call_callback(self):
        llm = self._make_mock_llm([
            LLMResponse(
                text="",
                tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={"x": "val"})],
            ),
            LLMResponse(text="final", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)
        callback = MagicMock()
        await loop.run([{"role": "user", "content": "go"}], on_tool_call=callback)
        callback.assert_called_once_with("test_tool", {"x": "val"})

    @pytest.mark.asyncio
    async def test_system_message_prepended(self):
        llm = self._make_mock_llm([
            LLMResponse(text="response", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)
        await loop.run([{"role": "user", "content": "hi"}], system="You are helpful.")
        first_call_msgs = llm.chat.call_args_list[0].kwargs.get("messages") or llm.chat.call_args_list[0][1]
        assert first_call_msgs[0] == {"role": "system", "content": "You are helpful."}

    @pytest.mark.asyncio
    async def test_tool_results_fed_back(self):
        llm = self._make_mock_llm([
            LLMResponse(
                text="",
                tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={"x": "in"})],
            ),
            LLMResponse(text="final answer", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool(output="computed_result")
        loop = ToolLoop(llm, reg)
        await loop.run([{"role": "user", "content": "go"}])
        second_call_msgs = llm.chat.call_args_list[1].kwargs.get("messages") or llm.chat.call_args_list[1][1]
        assistant_msgs = [m for m in second_call_msgs if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_msgs) == 1
        tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["content"] == "computed_result"
        assert tool_msgs[0]["tool_call_id"] == "tc1"

    @pytest.mark.asyncio
    async def test_no_system_when_none(self):
        llm = self._make_mock_llm([
            LLMResponse(text="ok", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)
        await loop.run([{"role": "user", "content": "hi"}], system=None)
        first_call_msgs = llm.chat.call_args_list[0].kwargs.get("messages") or llm.chat.call_args_list[0][1]
        assert first_call_msgs[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_budget_not_exhausted_allows_execution(self):
        llm = self._make_mock_llm([
            LLMResponse(text="budget ok", tool_calls=[], done=True),
        ])
        reg = self._make_registry_with_tool()
        budget = MagicMock()
        budget.is_exhausted = MagicMock(return_value=(False, ""))
        loop = ToolLoop(llm, reg, budget=budget)
        result = await loop.run([{"role": "user", "content": "hi"}])
        assert result.text == "budget ok"
        llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_interrupt_after_tool_dispatch(self):
        call_count = 0

        async def chat_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    text="",
                    tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={"x": "a"})],
                )
            InterruptSignal.get().trigger("post-tool interrupt")
            return LLMResponse(text="should not reach", tool_calls=[], done=True)

        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=chat_side_effect)
        reg = self._make_registry_with_tool()
        loop = ToolLoop(llm, reg)

        with pytest.raises(InterruptedError, match="post-tool interrupt"):
            await loop.run([{"role": "user", "content": "go"}])
        InterruptSignal.get().clear()
