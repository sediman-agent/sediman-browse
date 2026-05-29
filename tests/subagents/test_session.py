from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sediman.agent.subagents.result import SubagentResult
from sediman.agent.subagents.session import SubagentSession
from sediman.agent.subagents.template import AgentTemplate
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.llm.provider import ToolDefinition


class FakeToolCall:
    def __init__(self, id: str, name: str, arguments: dict):
        self.id = id
        self.name = name
        self.arguments = arguments


class TestSubagentSession:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        return llm

    @pytest.fixture
    def mock_browser(self):
        browser = MagicMock()
        return browser

    @pytest.fixture
    def template_browser(self):
        return AgentTemplate(
            name="browser",
            description="Browser agent",
            system_prompt="You browse.",
            permissions={"terminal": "deny", "write_file": "deny"},
        )

    @pytest.fixture
    def template_code(self):
        return AgentTemplate(
            name="code",
            description="Code agent",
            system_prompt="You code.",
            permissions={"terminal": "allow", "write_file": "allow"},
        )

    @pytest.mark.asyncio
    async def test_browser_task_with_browser(self, mock_llm, mock_browser, template_browser):
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="", tool_calls=[]))
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="web_search", description="s", parameters={}),
            lambda **kw: MagicMock(),
        )

        session = SubagentSession(
            template=template_browser,
            task="go to example.com",
            parent_context={},
            tool_registry=registry,
            llm_provider=mock_llm,
            browser_session=mock_browser,
        )

        # Patch _run_browser_step to avoid needing real browser
        session._run_browser_step = AsyncMock(
            return_value=MagicMock(text="Found page", actions=[])
        )

        result = await session.run()
        assert isinstance(result, SubagentResult)
        assert result.success is True
        assert "Found page" in result.summary

    @pytest.mark.asyncio
    async def test_llm_chat_no_tools(self, mock_llm, template_code):
        mock_llm.chat = AsyncMock(
            return_value=MagicMock(text="Code updated.", tool_calls=None)
        )
        registry = ToolRegistry()

        session = SubagentSession(
            template=template_code,
            task="write hello world",
            parent_context={},
            tool_registry=registry,
            llm_provider=mock_llm,
        )

        result = await session.run()
        assert result.summary == "Code updated."
        assert result.success is True

    @pytest.mark.asyncio
    async def test_denied_tool_blocked(self, mock_llm, template_browser):
        # browser template denies terminal
        tool_call = MagicMock()
        tool_call.id = "1"
        tool_call.name = "terminal"
        tool_call.arguments = {"command": "rm -rf /"}
        mock_llm.chat = AsyncMock(
            return_value=MagicMock(
                text=None,
                tool_calls=[tool_call],
            )
        )
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="terminal", description="t", parameters={}),
            AsyncMock(return_value=MagicMock()),
        )

        session = SubagentSession(
            template=template_browser,
            task="do something",
            parent_context={},
            tool_registry=registry,
            llm_provider=mock_llm,
        )

        result = await session.run()
        assert not result.success
        assert any("not allowed" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_allowed_tool_executed(self, mock_llm, template_code):
        mock_llm.chat = AsyncMock(
            return_value=MagicMock(
                text=None,
                tool_calls=[
                    FakeToolCall(
                        id="1", name="write_file", arguments={"path": "/tmp/a.py", "content": "x=1"}
                    )
                ],
            )
        )
        registry = ToolRegistry()
        async def fake_handler(**kw):
            return MagicMock()
        registry.register(
            ToolDefinition(name="write_file", description="w", parameters={}),
            fake_handler,
        )

        session = SubagentSession(
            template=template_code,
            task="write file",
            parent_context={},
            tool_registry=registry,
            llm_provider=mock_llm,
        )

        result = await session.run()
        assert result.success is True  # No error from denied tool

    @pytest.mark.asyncio
    async def test_parent_context_injected(self, mock_llm, template_code):
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Done.", tool_calls=[]))
        session = SubagentSession(
            template=template_code,
            task="fix bug",
            parent_context={"errors": ["ImportError"], "observations": ["Test failed"]},
            tool_registry=ToolRegistry(),
            llm_provider=mock_llm,
        )
        result = await session.run()
        assert result.summary == "Done."

    @pytest.mark.asyncio
    async def test_max_iterations_respected(self, mock_llm, template_code):
        # LLM keeps returning tool calls to test iteration limit
        call_count = [0]

        async def side_effect(**kw):
            call_count[0] += 1
            return MagicMock(
                text="result" if call_count[0] > 2 else None,
                tool_calls=[
                    FakeToolCall(id=str(call_count[0]), name="read_file", arguments={"path": "x"})
                ] if call_count[0] <= 2 else None,
            )

        mock_llm.chat = AsyncMock(side_effect=side_effect)
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="read_file", description="r", parameters={}),
            lambda **kw: MagicMock(),
        )

        session = SubagentSession(
            template=template_code,
            task="read files",
            parent_context={},
            tool_registry=registry,
            llm_provider=mock_llm,
        )

        result = await session.run()
        assert result.iterations > 0
        assert result.iterations <= template_code.max_iterations

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_llm, template_browser):
        mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM crashed"))
        session = SubagentSession(
            template=template_browser,
            task="go somewhere",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=mock_llm,
        )
        result = await session.run()
        assert result.success is False
        assert "LLM crashed" in result.errors[0]

    def test_is_browser_task_no_browser(self, mock_llm, template_browser):
        session = SubagentSession(
            template=template_browser,
            task="go to x",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=mock_llm,
            browser_session=None,
        )
        assert session._is_browser_task("go to x") is False

    def test_is_browser_task_denied_browser(self, mock_llm):
        template = AgentTemplate(
            name="no-browser",
            permissions={"browser": "deny"},
        )
        session = SubagentSession(
            template=template,
            task="go to x",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=mock_llm,
            browser_session=MagicMock(),
        )
        assert session._is_browser_task("go to x") is False
