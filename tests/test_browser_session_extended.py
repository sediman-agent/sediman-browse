from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.browser.session import BrowserSession, extract_result, run_browser_task


class TestBrowserSessionInit:
    def test_default_values(self):
        with patch("sediman.browser.session.DATA_DIR", Path("/tmp")):
            bs = BrowserSession()
        assert bs.headless is False
        assert "browser-profile" in bs.user_data_dir
        assert bs._browser is None
        assert bs._started is False

    def test_headless_true(self):
        bs = BrowserSession(headless=True)
        assert bs.headless is True

    def test_custom_user_data_dir(self):
        bs = BrowserSession(user_data_dir="/custom/path")
        assert bs.user_data_dir == "/custom/path"

    def test_on_screenshot_callback(self):
        callback = MagicMock()
        bs = BrowserSession(on_screenshot=callback)
        assert bs.on_screenshot == callback

    def test_is_started_false_initially(self):
        bs = BrowserSession()
        assert bs.is_started is False

    def test_browser_property_none_initially(self):
        bs = BrowserSession()
        assert bs.browser is None


class TestBrowserSessionStart:
    @pytest.mark.asyncio
    async def test_start_sets_started(self):
        bs = BrowserSession(headless=True)
        with patch("browser_use.Browser") as MockBrowser:
            MockBrowser.return_value = MagicMock()
            await bs.start()
            assert bs._started is True
            assert bs._browser is not None

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        with patch("browser_use.Browser", return_value=mock_browser):
            await bs.start()
            await bs.start()
            assert bs._started is True
            mock_browser.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_creates_browser_with_args(self):
        bs = BrowserSession(headless=True, user_data_dir="/tmp/test-profile")
        with patch("browser_use.Browser") as MockBrowser:
            await bs.start()
            MockBrowser.assert_called_once_with(
                headless=True,
                highlight_elements=True,
                user_data_dir="/tmp/test-profile",
                keep_alive=True,
            )


class TestBrowserSessionStop:
    @pytest.mark.asyncio
    async def test_stop_closes_browser(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()

        with patch("browser_use.Browser", return_value=mock_browser):
            await bs.start()
            await bs.stop()
            mock_browser.close.assert_called_once()
            assert bs._started is False
            assert bs._browser is None

    @pytest.mark.asyncio
    async def test_stop_noop_when_not_started(self):
        bs = BrowserSession(headless=True)
        await bs.stop()

    @pytest.mark.asyncio
    async def test_stop_handles_close_error(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        mock_browser.close = AsyncMock(side_effect=Exception("close error"))

        with patch("browser_use.Browser", return_value=mock_browser):
            await bs.start()
            await bs.stop()


class TestBrowserSessionTakeScreenshot:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_started(self):
        bs = BrowserSession()
        result = await bs.take_screenshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(side_effect=Exception("browser error"))

        with patch("browser_use.Browser", return_value=mock_browser):
            await bs.start()
            result = await bs.take_screenshot()
            assert result is None


class TestBrowserSessionSaveLoadState:
    @pytest.mark.asyncio
    async def test_save_state_handles_exception(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(side_effect=Exception("fail"))

        with patch("browser_use.Browser", return_value=mock_browser), \
             patch("sediman.browser.session.SESSION_DIR", Path("/tmp/test_sessions")):
            await bs.start()
            await bs.save_state("test")

    @pytest.mark.asyncio
    async def test_load_state_returns_false_when_no_file(self):
        bs = BrowserSession(headless=True)
        with patch("sediman.browser.session.SESSION_DIR", Path("/tmp/nonexistent")):
            result = await bs.load_state("test")
            assert result is False

    @pytest.mark.asyncio
    async def test_load_state_handles_exception(self):
        bs = BrowserSession(headless=True)
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(side_effect=Exception("fail"))

        with patch("browser_use.Browser", return_value=mock_browser), \
             patch("sediman.browser.session.SESSION_DIR", Path("/tmp/test_sessions")):
            await bs.start()
            result = await bs.load_state("test")
            assert result is False


class TestExtractResult:
    def test_none_result(self):
        result = extract_result(None)
        assert "could not extract" in result.lower()

    def test_empty_string(self):
        result = extract_result("")
        assert "could not extract" in result.lower()

    def test_valid_string(self):
        result = extract_result("hello world")
        assert result == "hello world"

    def test_string_with_whitespace(self):
        result = extract_result("  \n  ")
        assert "could not extract" in result.lower()

    def test_raw_result_with_final_result(self):
        raw = MagicMock()
        raw.final_result = "final output"
        result = extract_result(raw)
        assert result == "final output"

    def test_raw_result_callable_final_result(self):
        raw = MagicMock()
        raw.final_result = lambda: "callable result"
        result = extract_result(raw)
        assert result == "callable result"

    def test_raw_result_with_empty_final_result(self):
        raw = MagicMock()
        raw.final_result = ""
        raw.all_results = []
        raw.all_model_outputs = None
        result = extract_result(raw)
        assert "could not extract" in result.lower()

    def test_raw_result_none_final_result(self):
        raw = MagicMock()
        raw.final_result = None
        raw.all_results = []
        raw.all_model_outputs = None
        result = extract_result(raw)
        assert "could not extract" in result.lower()

    def test_raw_result_with_extracted_content(self):
        raw = MagicMock()
        raw.final_result = None

        r1 = MagicMock()
        r1.extracted_content = "content 1"
        r1.long_term_memory = None
        r2 = MagicMock()
        r2.extracted_content = "content 2"
        r2.long_term_memory = None
        raw.all_results = [r1, r2]
        raw.all_model_outputs = None

        result = extract_result(raw)
        assert "content 1" in result
        assert "content 2" in result

    def test_raw_result_with_long_term_memory(self):
        raw = MagicMock()
        raw.final_result = None
        raw.all_results = []

        r = MagicMock()
        r.extracted_content = None
        r.long_term_memory = "mem content"
        raw.all_results = [r]
        raw.all_model_outputs = None

        result = extract_result(raw)
        assert "mem content" in result

    def test_raw_result_with_model_outputs(self):
        raw = MagicMock()
        raw.final_result = None
        raw.all_results = []
        raw.all_model_outputs = [{"action": "click"}]

        result = extract_result(raw)
        assert "click" in result

    def test_final_result_exception_safe(self):
        raw = MagicMock()
        raw.final_result = MagicMock(side_effect=Exception("fail"))
        raw.all_results = []
        raw.all_model_outputs = None

        result = extract_result(raw)
        assert "could not extract" in result.lower()


class TestRunBrowserTask:
    @pytest.mark.asyncio
    async def test_returns_result_and_actions(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        llm = MagicMock()

        with patch("browser_use.Agent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock()
            mock_agent.run.return_value = MagicMock()
            mock_agent.run.return_value.final_result = "task done"
            MockAgent.return_value = mock_agent

            with patch("sediman.browser.session._extract_actions", return_value=[]):
                with patch("sediman.browser.session.extract_result", return_value="task done"):
                    result, actions = await run_browser_task("test task", browser, llm)

        assert result == "task done"

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        llm = MagicMock()

        with patch("browser_use.Agent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=Exception("browser error"))
            MockAgent.return_value = mock_agent

            result, actions = await run_browser_task("fail task", browser, llm)
            assert "browser error" in result
            assert actions == []

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        llm = MagicMock()

        with patch("browser_use.Agent") as MockAgent:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock()
            mock_agent.run.return_value = MagicMock()
            MockAgent.return_value = mock_agent

            with patch("sediman.browser.session._extract_actions", return_value=[]):
                with patch("sediman.browser.session.extract_result", return_value="ok"):
                    await run_browser_task("t", browser, llm, system_prompt="custom system prompt")

            call_kwargs = MockAgent.call_args.kwargs
            assert "override_system_message" in call_kwargs
            assert call_kwargs["override_system_message"] == "custom system prompt"


class TestExtractActions:
    def test_all_model_outputs(self):
        raw = MagicMock()
        raw.all_model_outputs = [{"action": "click"}, {"action": "type"}]
        from sediman.browser.session import _extract_actions
        actions = _extract_actions(raw)
        assert len(actions) == 2

    def test_no_outputs(self):
        raw = MagicMock()
        raw.all_model_outputs = None
        from sediman.browser.session import _extract_actions
        actions = _extract_actions(raw)
        assert actions == []

    def test_empty_outputs(self):
        raw = MagicMock()
        raw.all_model_outputs = []
        from sediman.browser.session import _extract_actions
        actions = _extract_actions(raw)
        assert actions == []

    def test_non_dict_outputs(self):
        raw = MagicMock()
        raw.all_model_outputs = ["string", 123]
        from sediman.browser.session import _extract_actions
        actions = _extract_actions(raw)
        assert actions == []
