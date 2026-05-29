from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.browser_agent import BrowserSubagent


class TestBrowserSubagentRecordingName:
    def test_recording_name_default_none(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock())
        assert agent._recording_name is None

    def test_recording_name_set(self):
        agent = BrowserSubagent(
            browser_session=MagicMock(),
            llm_provider=MagicMock(),
            recording_name="my-recording",
        )
        assert agent._recording_name == "my-recording"


class TestBrowserSubagentGetRecordingCallback:
    def test_no_recording_name_returns_none(self):
        agent = BrowserSubagent(browser_session=MagicMock(), llm_provider=MagicMock())
        assert agent._get_recording_callback() is None

    def test_recording_manager_not_recording_returns_none(self):
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.create_on_step_callback.return_value = None
            MockMgr.get_instance.return_value = mock_instance

            agent = BrowserSubagent(
                browser_session=MagicMock(),
                llm_provider=MagicMock(),
                recording_name="inactive",
            )
            result = agent._get_recording_callback()
            assert result is None

    def test_recording_manager_returns_callback(self):
        def _noop(action, url):
            pass
        cb = _noop
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.create_on_step_callback.return_value = cb
            MockMgr.get_instance.return_value = mock_instance

            agent = BrowserSubagent(
                browser_session=MagicMock(),
                llm_provider=MagicMock(),
                recording_name="active-rec",
            )
            result = agent._get_recording_callback()
            assert result is cb

    def test_exception_returns_none(self):
        with patch("sediman.agent.recording_manager.RecordingManager") as MockMgr:
            MockMgr.get_instance.side_effect = Exception("no manager")

            agent = BrowserSubagent(
                browser_session=MagicMock(),
                llm_provider=MagicMock(),
                recording_name="fail-rec",
            )
            result = agent._get_recording_callback()
            assert result is None


class TestBrowserSubagentRunWithRecording:
    @pytest.mark.asyncio
    async def test_recording_callback_merged_with_on_step(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        original_calls = []
        recording_calls = []

        def original_step(action, url):
            original_calls.append((action, url))

        def recording_cb(action, url):
            recording_calls.append((action, url))

        agent = BrowserSubagent(
            browser_session=browser,
            llm_provider=llm,
            on_browser_step=original_step,
            recording_name="test-rec",
        )

        with patch.object(agent, "_get_recording_callback", return_value=recording_cb):
            with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
                await agent.run("task")

                kwargs = mock_run.call_args.kwargs
                on_step = kwargs.get("on_step")
                assert on_step is not None

                on_step("navigate", "https://x.com")
                assert len(original_calls) == 1
                assert original_calls[0] == ("navigate", "https://x.com")
                assert len(recording_calls) == 1
                assert recording_calls[0] == ("navigate", "https://x.com")

    @pytest.mark.asyncio
    async def test_recording_callback_without_on_step(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        recording_calls = []

        def recording_cb(action, url):
            recording_calls.append((action, url))

        agent = BrowserSubagent(
            browser_session=browser,
            llm_provider=llm,
            on_browser_step=None,
            recording_name="test-rec",
        )

        with patch.object(agent, "_get_recording_callback", return_value=recording_cb):
            with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
                await agent.run("task")

                kwargs = mock_run.call_args.kwargs
                on_step = kwargs.get("on_step")
                assert on_step is not None

                on_step("click", "https://y.com")
                assert len(recording_calls) == 1

    @pytest.mark.asyncio
    async def test_no_recording_no_callback(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        agent = BrowserSubagent(
            browser_session=browser,
            llm_provider=llm,
            recording_name=None,
        )

        with patch.object(agent, "_get_recording_callback", return_value=None):
            with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
                await agent.run("task")

                kwargs = mock_run.call_args.kwargs
                on_step = kwargs.get("on_step")
                assert on_step is None


class TestBrowserSubagentPromptBuilding:
    @pytest.mark.asyncio
    async def test_system_prompt_includes_memory(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            agent = BrowserSubagent(browser_session=browser, llm_provider=llm)
            await agent.run("task")

            kwargs = mock_run.call_args.kwargs
            sp = kwargs.get("system_prompt", "")
            assert len(sp) > 0

    @pytest.mark.asyncio
    async def test_conversation_context_appended(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        conv = [
            {"role": "user", "content": "search for python"},
            {"role": "assistant", "content": "found 10 results"},
        ]

        with patch("sediman.agent.browser_agent.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            agent = BrowserSubagent(
                browser_session=browser,
                llm_provider=llm,
                conversation=conv,
            )
            await agent.run("now search for rust")

            kwargs = mock_run.call_args.kwargs
            sp = kwargs.get("system_prompt", "")
            assert "<conversation_context>" in sp
            assert "search for python" in sp
