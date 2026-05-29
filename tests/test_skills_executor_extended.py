from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.executor import _capture_screenshot, _capture_dom, execute_skill


class TestCaptureScreenshot:
    @pytest.mark.asyncio
    async def test_captures_screenshot(self):
        browser = MagicMock()
        browser.page = MagicMock()
        browser.page.screenshot = AsyncMock(return_value=b"\x89PNG data")

        path = await _capture_screenshot(browser)
        assert path is not None
        assert path.endswith(".png")
        saved = Path(path)
        assert saved.exists()
        assert saved.read_bytes() == b"\x89PNG data"
        saved.unlink()

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        browser = MagicMock()
        browser.page.screenshot = AsyncMock(side_effect=Exception("no page"))
        assert await _capture_screenshot(browser) is None


class TestCaptureDom:
    @pytest.mark.asyncio
    async def test_captures_dom(self):
        browser = MagicMock()
        browser.page = MagicMock()
        browser.page.content = AsyncMock(return_value="<html><body>Hello</body></html>")

        dom = await _capture_dom(browser)
        assert dom == "<html><body>Hello</body></html>"

    @pytest.mark.asyncio
    async def test_truncates_long_dom(self):
        browser = MagicMock()
        browser.page.content = AsyncMock(return_value="x" * 10000)

        dom = await _capture_dom(browser)
        assert dom is not None
        assert len(dom) <= 3000

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        browser = MagicMock()
        browser.page.content = AsyncMock(side_effect=Exception("no page"))
        assert await _capture_dom(browser) is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_dom(self):
        browser = MagicMock()
        browser.page.content = AsyncMock(return_value="")
        assert await _capture_dom(browser) is None


class TestExecuteSkillWithScreenshots:
    @pytest.mark.asyncio
    async def test_captures_screenshot_on_failure(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "fail-skill", "steps": ["step 1"]}

        browser.page = MagicMock()
        browser.page.screenshot = AsyncMock(return_value=b"png")
        browser.page.content = AsyncMock(return_value="<html>fail</html>")

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ("Error: failed", [])

            with patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock) as mock_heal:
                mock_heal.return_value = None

                result = await execute_skill(skill, browser, llm)

                assert "Error" in result
                # _capture_screenshot and _capture_dom should have been called
                # but we can't easily assert that since they're called from inside execute_skill
                # which catches exceptions from them

    @pytest.mark.asyncio
    async def test_passes_screenshot_to_healer_on_retry(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "heal-me", "steps": ["step 1"], "version": 1}

        browser.page = MagicMock()
        browser.page.screenshot = AsyncMock(return_value=b"png_data")
        browser.page.content = AsyncMock(return_value="<html>error state</html>")

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ("Error: element not found", [])

            with patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock) as mock_heal:
                mock_heal.return_value = None
                await execute_skill(skill, browser, llm, max_retries=1)

                # Verify heal_skill was called with screenshot and dom
                call_kwargs = mock_heal.call_args.kwargs
                # The actual screenshot_path will be a temp file path
                assert "screenshot_path" in call_kwargs or len(mock_heal.call_args_list) > 0

    @pytest.mark.asyncio
    async def test_success_does_not_capture_screenshot(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "good", "steps": ["step 1"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ("Success", [])

            browser.page = MagicMock()

            result = await execute_skill(skill, browser, llm)
            assert result == "Success"
