from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.executor import execute_skill


class TestExecuteSkillSuccess:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "test-skill", "steps": ["step 1", "step 2"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("done", [])):
            result = await execute_skill(skill, browser, llm)

        assert result == "done"

    @pytest.mark.asyncio
    async def test_builds_task_from_steps(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "my-skill", "steps": ["open page", "click button"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await execute_skill(skill, browser, llm)
            call_args = mock_run.call_args
            task = call_args[0][0] if call_args[0] else call_args.kwargs["task"]
            assert "my-skill" in task
            assert "1. open page" in task
            assert "2. click button" in task

    @pytest.mark.asyncio
    async def test_skill_with_no_steps(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "empty", "steps": []}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("done", [])):
            result = await execute_skill(skill, browser, llm)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_skill_with_missing_steps_key(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "no-steps"}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("done", [])):
            result = await execute_skill(skill, browser, llm)
        assert result == "done"


class TestExecuteSkillError:
    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "fail-skill", "steps": ["do thing"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, side_effect=RuntimeError("crash")):
            result = await execute_skill(skill, browser, llm)

        assert "crash" in result

    @pytest.mark.asyncio
    async def test_retries_with_healing_on_error_result(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "heal-skill", "steps": ["step"]}

        call_count = 0

        async def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("Error: page not found", [])
            return ("success after heal", [])

        healed_skill = {"name": "heal-skill", "steps": ["fixed step"]}

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed_skill):
            result = await execute_skill(skill, browser, llm)

        assert result == "success after heal"

    @pytest.mark.asyncio
    async def test_no_retry_when_max_retries_zero(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "no-retry", "steps": ["step"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            result = await execute_skill(skill, browser, llm, max_retries=0)

        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_returns_no_output_message_when_empty(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "empty-result", "steps": []}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("", [])):
            result = await execute_skill(skill, browser, llm)

        assert result == "unknown error"

    @pytest.mark.asyncio
    async def test_error_in_first_100_chars_triggers_retry(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "error-skill", "steps": ["step"]}

        call_count = 0

        async def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("Error: something went wrong", [])
            return ("healed result", [])

        healed_skill = {"name": "error-skill", "steps": ["healed step"]}

        with patch("sediman.skills.executor.run_browser_task", side_effect=mock_run), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=healed_skill):
            result = await execute_skill(skill, browser, llm)

        assert result == "healed result"

    @pytest.mark.asyncio
    async def test_healing_returns_none_proceeds_without_retry(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "unhealable", "steps": ["step"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, return_value=("Error: bad stuff", [])), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=None):
            result = await execute_skill(skill, browser, llm, max_retries=0)

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_exception_then_heal_fail(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "broken", "steps": ["step"]}

        with patch("sediman.skills.executor.run_browser_task", new_callable=AsyncMock, side_effect=Exception("fatal")), \
             patch("sediman.skills.executor.heal_skill", new_callable=AsyncMock, return_value=None):
            result = await execute_skill(skill, browser, llm)

        assert "fatal" in result
