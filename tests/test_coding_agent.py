from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.coding_agent import CodingAgent, CodingResult, create_coding_tool_registry
from sediman.agent.coding_agent.types import ProjectInfo
from sediman.agent.coding_agent.hooks import HookPipeline
from sediman.agent.tool_dispatch import ToolRegistry, ToolLoop
from sediman.llm.provider import LLMResponse, ToolDefinition


class TestCodingResult:
    def test_defaults(self):
        r = CodingResult(text="done")
        assert r.text == "done"
        assert r.actions == []
        assert r.success is True
        assert r.iterations == 0
        assert r.tool_calls == []
        assert r.files_edited == []

    def test_with_tool_calls(self):
        r = CodingResult(text="ok", tool_calls=["terminal", "write_file"])
        assert len(r.tool_calls) == 2

    def test_with_files_edited(self):
        r = CodingResult(
            text="done",
            files_edited=["src/app.py", "tests/test_app.py"],
            verifications_passed=2,
            verifications_failed=0,
        )
        assert len(r.files_edited) == 2
        assert r.verifications_passed == 2


class TestCreateCodingToolRegistry:
    def test_returns_registry_with_coding_tools(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()
        assert "terminal" in names
        assert "read_file" in names
        assert "write_file" in names

    def test_excludes_browser_tools(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()
        assert "browser_navigate" not in names
        assert "browser_click" not in names
        assert "browser_type" not in names

    def test_has_new_tools(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()
        assert "glob" in names
        assert "git_status" in names
        assert "git_diff" in names
        assert "git_log" in names
        assert "git_commit" in names
        assert "git_branch" in names
        assert "web_fetch" in names

    def test_has_planning_tools(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()
        assert "clarify" in names
        assert "todo" in names


class TestCodingAgent:
    def _make_agent(self, **kwargs):
        llm = MagicMock()
        return CodingAgent(
            llm_provider=llm,
            auto_discover_project=False,
            enable_hooks=False,
            **kwargs,
        )

    @pytest.mark.asyncio
    async def test_run_returns_coding_result(self):
        agent = self._make_agent()
        response = LLMResponse(text="Installed express successfully.", tool_calls=[], done=True)

        with patch("sediman.agent.coding_agent.agent.ToolLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run_streaming = AsyncMock(return_value=response)
            result = await agent.run("npm install express")

        assert isinstance(result, CodingResult)
        assert "express" in result.text
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_uses_streaming(self):
        agent = self._make_agent()
        response = LLMResponse(text="Built project.", tool_calls=[], done=True)

        with patch("sediman.agent.coding_agent.agent.ToolLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run_streaming = AsyncMock(return_value=response)
            await agent.run("build the project")

            mock_loop.run_streaming.assert_called_once()
            call_kwargs = mock_loop.run_streaming.call_args
            assert call_kwargs.kwargs.get("system") is not None

    @pytest.mark.asyncio
    async def test_on_step_callback_called(self):
        steps = []
        agent = self._make_agent(on_step=lambda action, detail="": steps.append(action))
        response = LLMResponse(text="Done.", tool_calls=[], done=True)

        with patch("sediman.agent.coding_agent.agent.ToolLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run_streaming = AsyncMock(return_value=response)
            await agent.run("test task")

        assert len(steps) >= 2
        assert any("starting" in s or "analyzing" in s for s in steps)
        assert any("done" in s for s in steps)

    @pytest.mark.asyncio
    async def test_on_tool_call_tracks_files(self):
        agent = self._make_agent()
        captured_callback = None

        async def mock_run_streaming(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("on_tool_call")
            return LLMResponse(text="Done.", tool_calls=[], done=True)

        with patch.object(ToolLoop, "run_streaming", side_effect=mock_run_streaming):
            result = await agent.run("list and create file")

            if captured_callback:
                await captured_callback("terminal", {"command": "ls"})
                await captured_callback("write_file", {"path": "/tmp/test.py"})
                await captured_callback("patch", {"path": "/tmp/config.py", "old": "x", "new": "y"})

        assert len(result.files_edited) == 2
        assert "/tmp/test.py" in result.files_edited

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        agent = self._make_agent()

        with patch("sediman.agent.coding_agent.agent.ToolLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run_streaming = AsyncMock(side_effect=RuntimeError("LLM error"))
            result = await agent.run("bad task")

        assert "failed" in result.text.lower()
        assert result.success is False
        assert len(result.errors_encountered) > 0

    @pytest.mark.asyncio
    async def test_custom_tool_registry(self):
        custom_registry = ToolRegistry()
        custom_registry.register(
            ToolDefinition(name="custom_tool", description="custom", parameters={}),
            AsyncMock(return_value=MagicMock(success=True, output="ok")),
        )
        agent = CodingAgent(
            llm_provider=MagicMock(),
            tool_registry=custom_registry,
            auto_discover_project=False,
            enable_hooks=False,
        )
        assert agent.registry is custom_registry
        assert "custom_tool" in agent.registry.list_tools()

    @pytest.mark.asyncio
    async def test_project_info_injected_with_project(self):
        project = ProjectInfo(
            project_type="Python",
            language="Python",
            lint_commands=["ruff check ."],
            test_commands=["pytest"],
            build_commands=["make"],
        )
        agent = self._make_agent(project_info=project)
        response = LLMResponse(text="ok", tool_calls=[], done=True)

        with patch("sediman.agent.coding_agent.agent.ToolLoop") as MockLoop:
            mock_loop = MockLoop.return_value
            mock_loop.run_streaming = AsyncMock(return_value=response)
            await agent.run("test")

            call_kwargs = mock_loop.run_streaming.call_args
            system_prompt = call_kwargs.kwargs.get("system", "")
            assert "Project Context" in system_prompt
            assert "Python" in system_prompt
            assert "ruff check" in system_prompt
            assert "pytest" in system_prompt

    @pytest.mark.asyncio
    async def test_on_tool_call_tracks_files(self):
        agent = self._make_agent()

        async def mock_run_streaming(**kwargs):
            on_tc = kwargs.get("on_tool_call")
            if on_tc:
                await on_tc("write_file", {"path": "/tmp/test.py"})
                await on_tc("patch", {"path": "/tmp/config.py", "old": "x", "new": "y"})
            return LLMResponse(text="Done.", tool_calls=[], done=True)

        with patch.object(ToolLoop, "run_streaming", side_effect=mock_run_streaming):
            result = await agent.run("list and create file")

        assert len(result.files_edited) == 2
        assert "/tmp/test.py" in result.files_edited
        assert "/tmp/config.py" in result.files_edited

    @pytest.mark.asyncio
    async def test_on_tool_call_tracks_tool_names(self):
        agent = self._make_agent()

        async def mock_run_streaming(**kwargs):
            on_tc = kwargs.get("on_tool_call")
            if on_tc:
                await on_tc("terminal", {"command": "ls"})
                await on_tc("search_files", {"query": "def main"})
            return LLMResponse(text="Done.", tool_calls=[], done=True)

        with patch.object(ToolLoop, "run_streaming", side_effect=mock_run_streaming):
            result = await agent.run("search and list")

        assert "terminal" in result.tool_calls
        assert "search_files" in result.tool_calls

    @pytest.mark.asyncio
    async def test_hooks_disabled_by_default_in_tests(self):
        agent = self._make_agent()
        assert agent._hook_pipeline is None

    def test_hooks_can_be_enabled(self):
        pipeline = HookPipeline()
        agent = CodingAgent(
            llm_provider=MagicMock(),
            auto_discover_project=False,
            hooks=pipeline,
        )
        assert agent._hook_pipeline is pipeline

    @pytest.mark.asyncio
    async def test_verify_after_edits_configurable(self):
        agent = self._make_agent(verify_after_edits=False)
        assert agent._verify_after_edits is False


class TestCodingSubagentBackwardCompat:
    def test_coding_subagent_is_coding_agent(self):
        from sediman.agent.coding_agent import CodingAgent, CodingSubagent
        assert CodingSubagent is CodingAgent
