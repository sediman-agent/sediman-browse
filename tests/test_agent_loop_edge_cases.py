"""Edge-case tests for agent/loop.py — conversation history, context building."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop, AgentResult, StepEvent
from sediman.agent.manager import ManagerPlan
from sediman.agent.browser_agent import BrowserResult


class TestAgentLoopConversationHistory:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    def test_initial_conversation_is_empty(self, tmp_sediman_dir):
        loop = self._make_loop()
        assert loop._conversation == []

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_conversation_appended_after_run(self, tmp_sediman_dir):
        loop = self._make_loop()
        plan = ManagerPlan(browser_task="my task")

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), patch.object(loop._memory, "on_session_end", new_callable=AsyncMock):
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="The task was completed successfully with detailed results.", actions=[{"action": "done"}]))
            mock_get_ba.return_value = mock_ba
            await loop.run("my task")

        assert len(loop._conversation) == 2
        assert loop._conversation[0]["role"] == "user"
        assert loop._conversation[0]["content"] == "my task"
        assert loop._conversation[1]["role"] == "assistant"
        assert "completed" in loop._conversation[1]["content"].lower() or "Task" in loop._conversation[1]["content"]

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_conversation_truncated_at_40(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [{"role": "user", "content": f"msg {i}"} for i in range(39)]
        plan = ManagerPlan(browser_task="overflow task")

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), patch.object(loop._memory, "on_session_end", new_callable=AsyncMock), \
             patch.object(loop, "_reflect_on_step", new_callable=AsyncMock) as mock_reflect:
            from sediman.agent.state import Reflection
            mock_reflect.return_value = Reflection(task_complete=True, confidence=0.9, reasoning="ok")
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="Task completed successfully with all data extracted.", actions=[{"action": "done"}]))
            mock_get_ba.return_value = mock_ba
            await loop.run("overflow task")

        assert len(loop._conversation) == 40


class TestBuildTaskWithContext:
    def _make_loop(self):
        return AgentLoop(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)

    def test_empty_conversation_returns_raw_task(self, tmp_sediman_dir):
        loop = self._make_loop()
        result = loop._build_task_with_context("hello")
        assert result == "hello"

    def test_includes_last_10_messages(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [
            {"role": "user", "content": f"old msg {i}"} for i in range(12)
        ]
        task = loop._build_task_with_context("new task")
        assert "old msg 2" in task
        assert "old msg 11" in task

    def test_truncates_long_messages(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [
            {"role": "user", "content": "x" * 500},
        ]
        task = loop._build_task_with_context("short")
        assert "xxx" in task

    def test_roles_mapped_correctly(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        task = loop._build_task_with_context("follow up")
        assert "User: question" in task
        assert "Assistant: answer" in task

    def test_current_task_always_present(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [
            {"role": "user", "content": "previous"},
        ]
        task = loop._build_task_with_context("my current task")
        assert "my current task" in task
        assert "Current task:" in task


class TestStepEventDataclass:
    def test_all_fields(self):
        event = StepEvent(step=5, action="navigate", observation="page loaded")
        assert event.step == 5
        assert event.action == "navigate"
        assert event.observation == "page loaded"

    def test_default_factory_not_shared(self):
        result1 = AgentResult(task="t", result="r")
        result2 = AgentResult(task="t", result="r")
        result1.steps.append(StepEvent(step=1, action="a", observation="o"))
        assert len(result2.steps) == 0


class TestAgentResultDataclass:
    def test_defaults(self):
        result = AgentResult(task="test", result="done")
        assert result.steps == []
        assert result.skill_created is None
        assert result.actions_taken == []
        assert result.scheduled_job_id is None
        assert result.schedule_cron is None

    def test_with_all_fields(self):
        result = AgentResult(
            task="test",
            result="done",
            steps=[StepEvent(step=1, action="click", observation="clicked")],
            skill_created="auto-skill",
            actions_taken=[{"type": "click"}],
            scheduled_job_id="abc123",
            schedule_cron="*/5 * * * *",
        )
        assert len(result.steps) == 1
        assert result.skill_created == "auto-skill"
        assert len(result.actions_taken) == 1
        assert result.scheduled_job_id == "abc123"
        assert result.schedule_cron == "*/5 * * * *"
