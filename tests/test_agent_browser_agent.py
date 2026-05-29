from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.browser_agent import BrowserSubagent, BrowserResult


@pytest.fixture
def browser_agent():
    browser = MagicMock()
    llm = MagicMock()
    return BrowserSubagent(browser_session=browser, llm_provider=llm)


class TestBrowserResult:
    def test_attributes(self):
        br = BrowserResult(text="result", actions=[{"action": "click"}])
        assert br.text == "result"
        assert len(br.actions) == 1


class TestBrowserSubagentInit:
    def test_default_max_steps(self):
        browser = MagicMock()
        llm = MagicMock()
        agent = BrowserSubagent(browser_session=browser, llm_provider=llm)
        assert agent.max_steps == 50

    def test_custom_max_steps(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock(), max_steps=20)
        assert agent.max_steps == 20

    def test_flash_mode_default(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock())
        assert agent.flash_mode is True

    def test_flash_mode_false(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock(), flash_mode=False)
        assert agent.flash_mode is False

    def test_conversation_default(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock())
        assert agent._conversation == []

    def test_conversation_custom(self):
        conv = [{"role": "user", "content": "hello"}]
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock(), conversation=conv)
        assert agent._conversation == conv

    def test_on_browser_step_none(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock())
        assert agent._on_browser_step is None


class TestBrowserSubagentRun:
    @pytest.mark.asyncio
    async def test_returns_browser_result(self, browser_agent):
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("done", [])):
            result = await browser_agent.run("test task")
            assert isinstance(result, BrowserResult)
            assert result.text == "done"

    @pytest.mark.asyncio
    async def test_returns_actions(self, browser_agent):
        actions = [{"action": "navigate"}, {"action": "click"}]
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("done", actions)):
            result = await browser_agent.run("test")
            assert len(result.actions) == 2

    @pytest.mark.asyncio
    async def test_passes_task_to_browser(self, browser_agent):
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("my specific task")
            call_args = mock_run.call_args
            kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
            task = kwargs.get("task") or call_args[0][0]
            assert "my specific task" in task

    @pytest.mark.asyncio
    async def test_passes_llm_provider(self, browser_agent):
        browser_agent.llm.get_browser_use_llm.return_value = "mock_llm"
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("task")
            kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else mock_run.call_args[1]
            browser_agent.llm.get_browser_use_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_system_prompt(self, browser_agent):
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("task")
            kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else mock_run.call_args[1]
            assert "system_prompt" in kwargs

    @pytest.mark.asyncio
    async def test_with_conversation_context(self, browser_agent):
        browser_agent._conversation = [
            {"role": "user", "content": "previous task"},
            {"role": "assistant", "content": "previous result"},
        ]
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("follow up")
            kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else mock_run.call_args[1]
            sp = kwargs.get("system_prompt", "")
            assert "<conversation_context>" in sp

    @pytest.mark.asyncio
    async def test_no_conversation_no_context_tag(self, browser_agent):
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("task")
            kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else mock_run.call_args[1]
            sp = kwargs.get("system_prompt", "")
            assert "<conversation_context>" not in sp

    @pytest.mark.asyncio
    async def test_skill_summaries_included(self, browser_agent):
        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await browser_agent.run("task", skill_summaries="- skill1: does x")
            kwargs = mock_run.call_args.kwargs if mock_run.call_args.kwargs else mock_run.call_args[1]
            sp = kwargs.get("system_prompt", "")
            assert "skill1" in sp
