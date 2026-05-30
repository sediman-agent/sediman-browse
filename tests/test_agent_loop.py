from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop, AgentResult, StepEvent


class TestStepEvent:
    def test_attributes(self):
        event = StepEvent(step=1, action="click", observation="clicked")
        assert event.step == 1
        assert event.action == "click"


class TestAgentResult:
    def test_default_values(self):
        result = AgentResult(task="t", result="r")
        assert result.steps == []
        assert result.skill_created is None
        assert result.scheduled_job_id is None


class TestAgentLoop:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_run_returns_agent_result(self, tmp_sediman_dir):
        from sediman.agent.manager import ManagerPlan
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        plan = ManagerPlan(browser_task="test task")

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_session_end", new_callable=AsyncMock), \
             patch("sediman.agent.progress.ProgressTracker") as mock_tracker:
            mock_tracker.return_value = MagicMock()
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="Task completed successfully. The browser navigated to the page and extracted the data.", actions=[{"action": "done"}]))
            mock_get_ba.return_value = mock_ba
            result = await loop.run("test task")

        assert isinstance(result, AgentResult)
        assert result.task == "test task"
        assert "completed" in result.result.lower() or "Task" in result.result

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_run_with_empty_result(self, tmp_sediman_dir):
        from sediman.agent.manager import ManagerPlan
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        plan = ManagerPlan(browser_task="do stuff")

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_session_end", new_callable=AsyncMock), \
             patch.object(loop, "_reflect_on_step") as mock_reflect:
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="", actions=[]))
            mock_get_ba.return_value = mock_ba

            from sediman.agent.state import Reflection
            mock_reflect.return_value = Reflection(
                task_complete=True,
                confidence=0.3,
                reasoning="Empty result accepted",
            )
            result = await loop.run("do stuff")

        assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_save_session_handles_errors(self, tmp_sediman_dir):
        loop = self._make_loop()

        with patch("sediman.memory.sessions.save_session", new_callable=AsyncMock, side_effect=Exception("db error")):
            await loop._save_session("task", "result", [])

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_run_sets_skill_created(self, tmp_sediman_dir):
        from sediman.agent.manager import ManagerPlan
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        plan = ManagerPlan(
            browser_task="test task",
            skill_name="auto-skill",
            skill_description="a test skill",
        )

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_session_end", new_callable=AsyncMock), \
             patch.object(loop, "_reflect_on_step", new_callable=AsyncMock) as mock_reflect:
            from sediman.agent.state import Reflection
            mock_reflect.return_value = Reflection(
                task_complete=True, confidence=0.9, reasoning="skill created"
            )
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="done", actions=[{"action": "navigate"}, {"action": "click"}, {"action": "extract"}]))
            mock_get_ba.return_value = mock_ba
            result = await loop.run("test task")

        assert result.skill_created == "auto-skill"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_run_schedules_when_plan_has_schedule(self, tmp_sediman_dir):
        from sediman.agent.manager import ManagerPlan
        from sediman.agent.planner import ScheduleIntent
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()

        plan = ManagerPlan(
            browser_task="get nvidia stock price",
            schedule=ScheduleIntent(cron="*/5 * * * *", task="get nvidia stock price"),
        )

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, return_value=plan), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop, "_create_scheduled_job", return_value="abc123def456"), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_session_end", new_callable=AsyncMock), \
             patch.object(loop._regex_planner, "plan", return_value=MagicMock(schedule=None, browser_task="get nvidia stock price")), \
             patch.object(loop, "_reflect_on_step", new_callable=AsyncMock) as mock_reflect:
            from sediman.agent.state import Reflection
            mock_reflect.return_value = Reflection(
                task_complete=True, confidence=0.9, reasoning="scheduled"
            )
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(return_value=BrowserResult(text="NVDA: $131.00 as of today", actions=[{"action": "done"}]))
            mock_get_ba.return_value = mock_ba
            result = await loop.run("get nvidia stock price every 5 minutes")

        assert result.scheduled_job_id == "abc123def456"
        assert result.schedule_cron == "*/5 * * * *"
        assert "scheduled" in result.result.lower()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="requires full agent stack with real LLM mocks")
    async def test_conversation_persisted_across_runs(self, tmp_sediman_dir):
        from sediman.agent.manager import ManagerPlan
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()

        plan1 = ManagerPlan(browser_task="go to amazon")
        plan2 = ManagerPlan(browser_task="go to ebay instead")

        with patch.object(loop, "_get_browser_agent") as mock_get_ba, \
             patch.object(loop._manager, "plan", new_callable=AsyncMock, side_effect=[plan1, plan2]), \
             patch.object(loop, "_save_session", new_callable=AsyncMock), \
             patch.object(loop._memory, "initialize", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock), \
             patch.object(loop._memory, "on_session_end", new_callable=AsyncMock):
            mock_ba = MagicMock()
            mock_ba.run = AsyncMock(side_effect=[
                BrowserResult(text="Navigated to Amazon and found the product page successfully.", actions=[{"action": "done"}]),
                BrowserResult(text="Navigated to eBay and found the listing successfully.", actions=[{"action": "done"}]),
            ])
            mock_get_ba.return_value = mock_ba

            await loop.run("go to amazon and buy xyz")
            assert len(loop._conversation) == 2

            await loop.run("ah sorry should be ebay")
            assert len(loop._conversation) == 4
            assert loop._conversation[2]["content"] == "ah sorry should be ebay"
            assert "eBay" in loop._conversation[3]["content"] or "completed" in loop._conversation[3]["content"].lower() or "Task" in loop._conversation[3]["content"]

    @pytest.mark.asyncio
    async def test_build_task_with_context_empty(self, tmp_sediman_dir):
        loop = self._make_loop()
        assert loop._build_task_with_context("hello") == "hello"

    @pytest.mark.asyncio
    async def test_build_task_with_context_has_history(self, tmp_sediman_dir):
        loop = self._make_loop()
        loop._conversation = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ]
        task = loop._build_task_with_context("follow up")
        assert "Previous conversation context" in task
        assert "follow up" in task
