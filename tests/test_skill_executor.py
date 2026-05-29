from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.executor import (
    _capture_screenshot,
    _capture_dom,
    _format_steps_for_prompt,
    execute_skill,
)


class TestCaptureScreenshot:
    @pytest.mark.asyncio
    async def test_returns_path_on_success(self, tmp_path):
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"\x89PNG"
        mock_session = MagicMock()
        mock_session.page = mock_page

        with patch("sediman.skills.executor.tempfile.mktemp", return_value=str(tmp_path / "test.png")):
            result = await _capture_screenshot(mock_session)

        assert result is not None
        assert result.endswith(".png")
        mock_page.screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("no page")
        mock_session = MagicMock()
        mock_session.page = mock_page

        result = await _capture_screenshot(mock_session)
        assert result is None


class TestCaptureDom:
    @pytest.mark.asyncio
    async def test_returns_content_on_success(self):
        mock_page = AsyncMock()
        mock_page.content.return_value = "<html><body>Hello</body></html>"
        mock_session = MagicMock()
        mock_session.page = mock_page

        result = await _capture_dom(mock_session)
        assert result is not None
        assert "Hello" in result
        mock_page.content.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_truncates_long_content(self):
        mock_page = AsyncMock()
        mock_page.content.return_value = "x" * 10000
        mock_session = MagicMock()
        mock_session.page = mock_page

        result = await _capture_dom(mock_session)
        assert len(result) <= 3000

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_content(self):
        mock_page = AsyncMock()
        mock_page.content.return_value = ""
        mock_session = MagicMock()
        mock_session.page = mock_page

        result = await _capture_dom(mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        mock_page = AsyncMock()
        mock_page.content.side_effect = RuntimeError("crash")
        mock_session = MagicMock()
        mock_session.page = mock_page

        result = await _capture_dom(mock_session)
        assert result is None


class TestFormatStepsForPrompt:
    def test_string_steps(self):
        steps = ["go to google.com", "search for python"]
        result = _format_steps_for_prompt(steps)
        assert "1. go to google.com" in result
        assert "2. search for python" in result

    def test_dict_steps_with_all_fields(self):
        steps = [{
            "description": "click login",
            "url": "https://example.com/login",
            "selector": "#login-btn",
            "expected_outcome": "logged in",
        }]
        result = _format_steps_for_prompt(steps)
        assert "click login" in result
        assert "https://example.com/login" in result
        assert "#login-btn" in result
        assert "logged in" in result

    def test_dict_steps_minimal(self):
        steps = [{"description": "navigate home"}]
        result = _format_steps_for_prompt(steps)
        assert "1. navigate home" in result

    def test_empty_steps(self):
        result = _format_steps_for_prompt([])
        assert result == ""

    def test_mixed_steps(self):
        steps = ["simple step", {"description": "complex step", "url": "https://x.com"}]
        result = _format_steps_for_prompt(steps)
        assert "1. simple step" in result
        assert "2. complex step" in result


class TestExecuteSkillVerificationPreservation:
    @pytest.mark.asyncio
    async def test_verification_preserved_through_heal_retry(self):
        skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["go to google.com"],
            "verification": "page shows google logo",
        }

        call_count = 0
        captured_prompts = []

        original_run = AsyncMock(return_value=("error: timeout", []))

        async def mock_run_browser_task(**kwargs):
            nonlocal call_count
            captured_prompts.append(kwargs.get("task", ""))
            call_count += 1
            if call_count == 1:
                return ("error: timeout", [])
            return ("success", [])

        healed_skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["go to google.com", "wait for load"],
            "verification": "page shows google logo",
        }

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run_browser_task), \
             patch("sediman.skills.executor._capture_screenshot", new_callable=AsyncMock, return_value=None), \
             patch("sediman.skills.executor._capture_dom", new_callable=AsyncMock, return_value=None), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed_skill), \
             patch("sediman.skills.executor._looks_like_error", return_value=True):

            mock_llm = MagicMock()
            mock_llm.get_browser_use_llm = MagicMock(return_value=MagicMock())

            result = await execute_skill(
                skill=skill,
                browser_session=MagicMock(),
                llm=mock_llm,
                max_retries=1,
            )

        assert len(captured_prompts) == 2
        second_prompt = captured_prompts[1]
        assert "google logo" in second_prompt

    @pytest.mark.asyncio
    async def test_heal_called_with_screenshot_and_dom(self):
        skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["step 1"],
            "verification": "check ok",
        }

        async def mock_run(**kwargs):
            return ("error: failed", [])

        healed_skill = dict(skill, steps=["step 1", "step 2"])

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run), \
             patch("sediman.skills.executor._capture_screenshot", new_callable=AsyncMock, return_value="/tmp/shot.png") as mock_ss, \
             patch("sediman.skills.executor._capture_dom", new_callable=AsyncMock, return_value="<html>dom</html>") as mock_dom, \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed_skill) as mock_heal, \
             patch("sediman.skills.executor._looks_like_error", return_value=True):

            mock_llm = MagicMock()
            mock_llm.get_browser_use_llm = MagicMock(return_value=MagicMock())

            await execute_skill(
                skill=skill,
                browser_session=MagicMock(),
                llm=mock_llm,
                max_retries=1,
            )

        mock_ss.assert_awaited()
        mock_dom.assert_awaited()
        mock_heal.assert_awaited_once()
        assert mock_heal.call_args.kwargs.get("screenshot_path") == "/tmp/shot.png"
        assert mock_heal.call_args.kwargs.get("dom_snapshot") == "<html>dom</html>"

    @pytest.mark.asyncio
    async def test_returns_result_on_first_success(self):
        skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["step 1"],
            "verification": "ok",
        }

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("great result", [])), \
             patch("sediman.skills.executor._looks_like_error", return_value=False):

            mock_llm = MagicMock()
            mock_llm.get_browser_use_llm = MagicMock(return_value=MagicMock())

            result = await execute_skill(
                skill=skill,
                browser_session=MagicMock(),
                llm=mock_llm,
                max_retries=1,
            )

        assert result == "great result"

    @pytest.mark.asyncio
    async def test_exception_retry_with_screenshot_dom(self):
        skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["step 1"],
            "verification": "ok",
        }

        call_count = 0

        async def mock_run(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("browser crashed")
            return ("recovered", [])

        healed = dict(skill, steps=["fixed step"])

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run), \
             patch("sediman.skills.executor._capture_screenshot", new_callable=AsyncMock, return_value=None), \
             patch("sediman.skills.executor._capture_dom", new_callable=AsyncMock, return_value="<dom/>") as mock_dom, \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed), \
             patch("sediman.skills.executor._looks_like_error", return_value=False):

            mock_llm = MagicMock()
            mock_llm.get_browser_use_llm = MagicMock(return_value=MagicMock())

            result = await execute_skill(
                skill=skill,
                browser_session=MagicMock(),
                llm=mock_llm,
                max_retries=1,
            )

        assert result == "recovered"
        mock_dom.assert_awaited()

    @pytest.mark.asyncio
    async def test_verification_from_healed_skill_used_when_original_missing(self):
        skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["step 1"],
        }

        healed_skill = {
            "name": "test-skill",
            "description": "A test",
            "steps": ["fixed step"],
            "verification": "healed verification criteria",
        }

        captured_prompts = []
        call_count = 0

        async def mock_run(**kwargs):
            nonlocal call_count
            captured_prompts.append(kwargs.get("task", ""))
            call_count += 1
            if call_count == 1:
                return ("error", [])
            return ("ok", [])

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run), \
             patch("sediman.skills.executor._capture_screenshot", new_callable=AsyncMock, return_value=None), \
             patch("sediman.skills.executor._capture_dom", new_callable=AsyncMock, return_value=None), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed_skill), \
             patch("sediman.skills.executor._looks_like_error", side_effect=lambda t: call_count == 1):

            mock_llm = MagicMock()
            mock_llm.get_browser_use_llm = MagicMock(return_value=MagicMock())

            await execute_skill(
                skill=skill,
                browser_session=MagicMock(),
                llm=mock_llm,
                max_retries=1,
            )

        assert "healed verification criteria" in captured_prompts[1]
