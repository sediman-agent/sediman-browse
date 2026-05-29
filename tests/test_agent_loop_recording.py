from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop
from sediman.agent.state import AgentState
from sediman.agent.manager import ManagerPlan


class TestAgentLoopGetActiveRecordingName:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    def test_no_recording_returns_none(self):
        loop = self._make_loop()
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.is_recording.return_value = False
            MockMgr.get_instance.return_value = mock_instance

            result = loop._get_active_recording_name()
            assert result is None

    def test_active_recording_returns_name(self):
        loop = self._make_loop()
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.is_recording.return_value = True
            mock_recorder = MagicMock()
            mock_recorder.session.name = "active-session"
            mock_instance.get_active_recorder.return_value = mock_recorder
            MockMgr.get_instance.return_value = mock_instance

            result = loop._get_active_recording_name()
            assert result == "active-session"

    def test_recorder_without_session_returns_none(self):
        loop = self._make_loop()
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.is_recording.return_value = True
            mock_recorder = MagicMock()
            mock_recorder.session = None
            mock_instance.get_active_recorder.return_value = mock_recorder
            MockMgr.get_instance.return_value = mock_instance

            result = loop._get_active_recording_name()
            assert result is None

    def test_exception_returns_none(self):
        loop = self._make_loop()
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            MockMgr.get_instance.side_effect = Exception("no mgr")

            result = loop._get_active_recording_name()
            assert result is None


class TestAgentLoopVerifySkill:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_verify_skill_not_found(self):
        loop = self._make_loop()
        engine = MagicMock()
        engine.read.return_value = None
        loop._skill_engine = engine

        result = await loop._verify_skill("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_skill_success(self):
        loop = self._make_loop()
        engine = MagicMock()
        engine.read.return_value = {"name": "test-skill", "steps": ["s1"]}
        loop._skill_engine = engine

        with patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, return_value="done"):
            result = await loop._verify_skill("test-skill")
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_skill_error_result(self):
        loop = self._make_loop()
        engine = MagicMock()
        engine.read.return_value = {"name": "test-skill", "steps": ["s1"]}
        loop._skill_engine = engine

        with patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, return_value="Error: timeout"):
            result = await loop._verify_skill("test-skill")
            assert result is False

    @pytest.mark.asyncio
    async def test_verify_skill_exception(self):
        loop = self._make_loop()
        engine = MagicMock()
        engine.read.return_value = {"name": "test-skill", "steps": ["s1"]}
        loop._skill_engine = engine

        with patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, side_effect=Exception("fail")):
            result = await loop._verify_skill("test-skill")
            assert result is False


class TestAgentLoopGetBrowserAgent:
    def _make_loop(self, **kwargs):
        llm = MagicMock()
        browser = MagicMock()
        defaults = dict(llm_provider=llm, browser_session=browser, max_steps=5)
        defaults.update(kwargs)
        loop = AgentLoop(**defaults)
        loop._memory = MagicMock()
        loop._memory.format_for_system_prompt.return_value = ""
        return loop

    def test_no_recording_name(self):
        loop = self._make_loop()
        agent = loop._get_browser_agent()
        assert agent._recording_name is None

    def test_with_recording_name(self):
        loop = self._make_loop()
        agent = loop._get_browser_agent(recording_name="test-rec")
        assert agent._recording_name == "test-rec"

    def test_with_on_step_callback(self):
        calls = []
        loop = self._make_loop(on_step=lambda e: calls.append(e))
        agent = loop._get_browser_agent()
        assert agent._on_browser_step is not None

        agent._on_browser_step("click", "https://x.com")
        assert len(calls) == 1
        assert calls[0].action == "click"

    def test_without_on_step_no_callback(self):
        loop = self._make_loop()
        agent = loop._get_browser_agent()
        assert agent._on_browser_step is None


class TestAgentLoopPostTaskRecording:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        loop = AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)
        loop._memory_initialized = True
        return loop

    @pytest.mark.asyncio
    async def test_post_task_drain_no_crash(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="test")
        state.result = "done"
        state.actions_taken = []
        plan = ManagerPlan(browser_task="test")

        with (
            patch.object(loop, "_save_session", new_callable=AsyncMock),
            patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock),
            patch.object(loop._memory, "on_session_end", new_callable=AsyncMock),
            patch.object(loop._memory, "should_review", return_value=False),
        ):
            await loop._post_task(state, plan, "test")

    @pytest.mark.asyncio
    async def test_post_task_records_skill(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="test")
        state.result = "done"
        state.actions_taken = [
            {"action": "navigate"},
            {"action": "click"},
            {"action": "input"},
        ]
        plan = ManagerPlan(browser_task="test")

        with (
            patch.object(loop, "_save_session", new_callable=AsyncMock),
            patch.object(loop._memory, "on_turn_start", new_callable=AsyncMock),
            patch.object(loop._memory, "on_session_end", new_callable=AsyncMock),
            patch.object(loop._memory, "should_review", return_value=False),
        ):
            engine = MagicMock()
            engine.read.return_value = None
            engine.create.return_value = True
            loop._skill_engine = engine

            with patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, return_value="ok"):
                await loop._post_task(state, plan, "test")
