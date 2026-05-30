from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.subagents.session import SubagentSession
from sediman.agent.subagents.template import AgentTemplate
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.llm.provider import LLMResponse, ToolDefinition


class TestSessionCodingDetection:
    def _code_template(self):
        return AgentTemplate(
            name="code",
            description="Code agent",
            system_prompt="You code.",
            permissions={"terminal": "allow", "browser": "deny"},
        )

    def _browser_template(self):
        return AgentTemplate(
            name="browser",
            description="Browser agent",
            system_prompt="You browse.",
            permissions={"terminal": "deny", "browser": "allow", "web_search": "allow"},
        )

    def test_code_template_detected_as_coding(self):
        session = SubagentSession(
            template=self._code_template(),
            task="install packages",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
        )
        assert session._is_coding_task("install packages") is True

    def test_browser_template_not_coding(self):
        session = SubagentSession(
            template=self._browser_template(),
            task="go to google",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
        )
        assert session._is_coding_task("go to google") is False

    def test_coding_routes_to_coding_subagent(self):
        session = SubagentSession(
            template=self._code_template(),
            task="run tests",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
        )
        assert session._is_coding_task("run tests") is True

    @pytest.mark.asyncio
    async def test_coding_session_uses_coding_subagent(self):
        session = SubagentSession(
            template=self._code_template(),
            task="run pytest",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
        )
        with patch("sediman.agent.subagents.session.CodingSubagent") as MockCS:
            mock_instance = MockCS.return_value
            mock_instance.run = AsyncMock(
                return_value=MagicMock(text="All tests pass.", tool_calls=["terminal"])
            )
            result = await session.run()

        MockCS.assert_called_once()
        assert "tests pass" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_browser_task_does_not_route_to_coding(self):
        browser = MagicMock()
        session = SubagentSession(
            template=self._browser_template(),
            task="go to google.com",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
            browser_session=browser,
        )
        assert session._is_coding_task("go to google.com") is False
        assert session._is_browser_task("go to google.com") is True

    @pytest.mark.asyncio
    async def test_streaming_callback_passed_to_coding_agent(self):
        tokens = []

        session = SubagentSession(
            template=self._code_template(),
            task="build project",
            parent_context={},
            tool_registry=ToolRegistry(),
            llm_provider=MagicMock(),
            on_streaming_text=lambda token, phase="": tokens.append(token),
        )
        with patch("sediman.agent.subagents.session.CodingSubagent") as MockCS:
            mock_instance = MockCS.return_value
            mock_instance.run = AsyncMock(
                return_value=MagicMock(text="Built.", tool_calls=[])
            )
            await session.run()

        call_kwargs = MockCS.call_args
        assert call_kwargs.kwargs.get("on_streaming_text") is not None


class TestSessionFactoryStreaming:
    @pytest.mark.asyncio
    async def test_factory_passes_streaming_to_session(self):
        from sediman.agent.subagents.factory import SubagentFactory
        from sediman.agent.subagents.registry import SubagentRegistry

        tokens = []
        registry = SubagentRegistry()
        factory = SubagentFactory(
            registry=registry,
            llm_provider=MagicMock(),
            on_streaming_text=lambda token, phase="": tokens.append(token),
        )

        template = AgentTemplate(
            name="code",
            description="Code agent",
            system_prompt="You code.",
            permissions={"terminal": "allow", "browser": "deny"},
        )
        with patch.object(registry, "get", return_value=template):
            with patch("sediman.agent.subagents.session.CodingSubagent") as MockCS:
                mock_instance = MockCS.return_value
                mock_instance.run = AsyncMock(
                    return_value=MagicMock(text="Done.", tool_calls=[])
                )
                result = await factory.spawn(agent_type="code", task="test")

        MockCS.assert_called_once()
        call_kwargs = MockCS.call_args
        assert call_kwargs.kwargs.get("on_streaming_text") is not None


class TestRpcServerStreaming:
    @pytest.mark.asyncio
    async def test_agent_run_wires_streaming_callback_during_run(self):
        from sediman.rpc_server import handle_agent_run

        notify_calls = []
        def mock_notify(method, params):
            notify_calls.append((method, params))

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.result = "done"
        mock_result.steps = []
        mock_result.skill_created = None
        mock_result.actions_taken = []
        mock_result.scheduled_job_id = None
        mock_result.schedule_cron = None
        mock_result.iterations = 0
        mock_result.strategy_used = "direct"

        streaming_was_set = [False]
        original_run = mock_agent.run

        async def fake_run(task):
            if mock_agent.on_streaming_text is not None:
                streaming_was_set[0] = True
                mock_agent.on_streaming_text("hello", "responding")
            return mock_result

        mock_agent.run = fake_run
        mock_agent.on_step = None
        mock_agent.on_streaming_text = None

        with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
             patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
            mock_interrupt.get.return_value = MagicMock()
            mock_interrupt.get.return_value.is_set.return_value = False
            mock_interrupt.get.return_value.clear = MagicMock()
            result = await handle_agent_run({"task": "test"}, notify=mock_notify)

        assert streaming_was_set[0] is True
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_streaming_notification_sent(self):
        from sediman.rpc_server import handle_agent_run

        notify_calls = []
        def mock_notify(method, params):
            notify_calls.append((method, params))

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.result = "done"
        mock_result.steps = []
        mock_result.skill_created = None
        mock_result.actions_taken = []
        mock_result.scheduled_job_id = None
        mock_result.schedule_cron = None
        mock_result.iterations = 0
        mock_result.strategy_used = "direct"

        async def fake_run(task):
            if mock_agent.on_streaming_text:
                mock_agent.on_streaming_text("hello", "responding")
            return mock_result

        mock_agent.run = fake_run
        mock_agent.on_step = None
        mock_agent.on_streaming_text = None

        with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
             patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
            mock_interrupt.get.return_value = MagicMock()
            mock_interrupt.get.return_value.is_set.return_value = False
            mock_interrupt.get.return_value.clear = MagicMock()
            result = await handle_agent_run({"task": "test"}, notify=mock_notify)

        streaming_calls = [(m, p) for m, p in notify_calls if m == "chat.streaming"]
        assert len(streaming_calls) >= 1
        assert streaming_calls[0][1]["token"] == "hello"
        assert streaming_calls[0][1]["phase"] == "responding"

    @pytest.mark.asyncio
    async def test_original_callbacks_restored_after_run(self):
        from sediman.rpc_server import handle_agent_run

        original_step = lambda e: None
        original_streaming = lambda t, p: None
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.result = "done"
        mock_result.steps = []
        mock_result.skill_created = None
        mock_result.actions_taken = []
        mock_result.scheduled_job_id = None
        mock_result.schedule_cron = None
        mock_result.iterations = 0
        mock_result.strategy_used = "direct"
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_agent.on_step = original_step
        mock_agent.on_streaming_text = original_streaming

        with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
             patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
            mock_interrupt.get.return_value = MagicMock()
            mock_interrupt.get.return_value.is_set.return_value = False
            mock_interrupt.get.return_value.clear = MagicMock()
            await handle_agent_run({"task": "test"}, notify=lambda m, p: None)

        assert mock_agent.on_step is original_step
        assert mock_agent.on_streaming_text is original_streaming

    @pytest.mark.asyncio
    async def test_progress_notifications_also_sent(self):
        from sediman.rpc_server import handle_agent_run

        notify_calls = []
        def mock_notify(method, params):
            notify_calls.append((method, params))

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.result = "done"
        mock_result.steps = []
        mock_result.skill_created = None
        mock_result.actions_taken = []
        mock_result.scheduled_job_id = None
        mock_result.schedule_cron = None
        mock_result.iterations = 0
        mock_result.strategy_used = "direct"

        async def fake_run(task):
            from sediman.agent.loop import StepEvent
            if mock_agent.on_step:
                mock_agent.on_step(StepEvent(step=1, action="navigate", observation="done"))
            return mock_result

        mock_agent.run = fake_run
        mock_agent.on_step = None
        mock_agent.on_streaming_text = None

        with patch("sediman.rpc_server._get_agent_loop", new_callable=AsyncMock, return_value=mock_agent), \
             patch("sediman.rpc_server.InterruptSignal") as mock_interrupt:
            mock_interrupt.get.return_value = MagicMock()
            mock_interrupt.get.return_value.is_set.return_value = False
            mock_interrupt.get.return_value.clear = MagicMock()
            await handle_agent_run({"task": "test"}, notify=mock_notify)

        progress_calls = [(m, p) for m, p in notify_calls if m == "chat.progress"]
        assert len(progress_calls) >= 1
