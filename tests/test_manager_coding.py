from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.manager import ManagerAgent, ManagerPlan
from sediman.agent.state import Strategy


class TestIsStrongCodingTask:
    def _make_manager(self):
        return ManagerAgent(llm=MagicMock())

    def test_npm_install(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("npm install lodash") is True

    def test_pip_install(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("pip install requests") is True

    def test_cargo_build(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("cargo build the project") is True

    def test_pytest(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("run pytest on the project") is True

    def test_git_commit(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("git commit my changes") is True

    def test_run_tests(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("run the tests") is True

    def test_non_coding_task(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("go to google and search for cats") is False

    def test_conversational_task(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("hello how are you") is False

    def test_too_long_task(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("pip install " + "x" * 500) is False

    def test_case_insensitive(self):
        m = self._make_manager()
        assert m._is_strong_coding_task("Run the tests") is True


class TestIsExplicitUrlTask:
    def _make_manager(self):
        return ManagerAgent(llm=MagicMock())

    def test_go_to_url(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("go to https://example.com") is True

    def test_navigate_to_url(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("navigate to https://example.com/page") is True

    def test_open_url(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("open https://amazon.com") is True

    def test_raw_url(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("https://news.ycombinator.com") is True

    def test_non_url_task(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("search for cats on google") is False

    def test_install_not_url(self):
        m = self._make_manager()
        assert m._is_explicit_url_task("npm install express") is False


class TestClassifyTask:
    def _make_manager(self, classification_response: str = "code"):
        m = ManagerAgent(llm=MagicMock())
        m.llm.chat = AsyncMock(return_value=MagicMock(text=classification_response))
        return m

    @pytest.mark.asyncio
    async def test_classify_code_task(self):
        m = self._make_manager("code")
        result = await m._classify_task("refactor the auth module")
        assert result == "code"

    @pytest.mark.asyncio
    async def test_classify_browser_task(self):
        m = self._make_manager("browser")
        result = await m._classify_task("compare prices on Amazon")
        assert result == "browser"

    @pytest.mark.asyncio
    async def test_classify_conversational(self):
        m = self._make_manager("conversational")
        result = await m._classify_task("what can you do?")
        assert result == "conversational"

    @pytest.mark.asyncio
    async def test_classify_unclear_returns_conversational(self):
        m = self._make_manager("some random text not matching")
        result = await m._classify_task("do something")
        assert result == "conversational"

    @pytest.mark.asyncio
    async def test_classify_error_returns_conversational(self):
        m = ManagerAgent(llm=MagicMock())
        m.llm.chat = AsyncMock(side_effect=Exception("LLM error"))
        result = await m._classify_task("any task")
        assert result == "conversational"


class TestCodingFastPath:
    @pytest.mark.asyncio
    async def test_strong_coding_task_gets_delegate_strategy(self):
        m = ManagerAgent(llm=MagicMock())
        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)):
            plan = await m.plan("npm install express", conversation=[])
        assert plan.strategy == Strategy.DELEGATE
        assert plan.use_subagent == "code"
        assert plan.subtasks == ["npm install express"]

    @pytest.mark.asyncio
    async def test_strong_coding_task_has_subtasks(self):
        m = ManagerAgent(llm=MagicMock())
        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)):
            plan = await m.plan("run the tests", conversation=[])
        assert plan.subtasks is not None
        assert len(plan.subtasks) == 1

    @pytest.mark.asyncio
    async def test_llm_classified_coding_task(self):
        m = ManagerAgent(llm=MagicMock(text="code"))
        m.llm.chat = AsyncMock(return_value=MagicMock(text="code"))
        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)):
            plan = await m.plan("refactor the authentication module to use async", conversation=[])
        assert plan.strategy == Strategy.DELEGATE
        assert plan.use_subagent == "code"

    @pytest.mark.asyncio
    async def test_llm_classified_browser_task(self):
        m = ManagerAgent(llm=MagicMock(text="browser"))
        m.llm.chat = AsyncMock(return_value=MagicMock(text="browser"))
        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)):
            plan = await m.plan("find the best laptop deals", conversation=[])
        assert plan.strategy == Strategy.DIRECT

    @pytest.mark.asyncio
    async def test_llm_classified_conversational(self):
        m = ManagerAgent(llm=MagicMock(text="conversational"))
        m.llm.chat = AsyncMock(return_value=MagicMock(text="conversational"))
        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)):
            plan = await m.plan("what's the weather like?", conversation=[])
        assert plan.strategy == Strategy.CONVERSATIONAL

    @pytest.mark.asyncio
    async def test_coding_fast_path_skipped_with_conversation(self):
        m = ManagerAgent(llm=MagicMock())
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_dumps_response(
            strategy="delegate", browser_task="build", subtasks=["build"]
        )
        m.llm.chat = AsyncMock(return_value=mock_response)

        with patch.object(m._regex_planner, "plan", return_value=MagicMock(schedule=None)), \
             patch.object(m, "_get_episodic_context", return_value=None):
            plan = await m.plan("build it", conversation=[{"role": "user", "content": "hi"}])
        assert plan.use_subagent is None or plan.use_subagent == "code"


def json_dumps_response(**overrides):
    import json
    base = {
        "strategy": "direct",
        "browser_task": "",
        "response": None,
        "skill_to_use": None,
        "subtasks": None,
        "schedule": None,
        "memory": None,
        "skill_name": None,
        "skill_description": None,
        "use_subagent": None,
    }
    base.update(overrides)
    return json.dumps(base)
