from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.delegate import delegate_task, delegate_parallel


class TestDelegateTask:
    @pytest.mark.asyncio
    async def test_returns_result_text(self):
        browser = MagicMock()
        llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("task done", [])):
            result = await delegate_task("search google", browser, llm)

        assert result == "task done"

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self):
        browser = MagicMock()
        llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, side_effect=RuntimeError("browser crashed")):
            result = await delegate_task("failing task", browser, llm)

        assert "Subagent failed" in result
        assert "browser crashed" in result

    @pytest.mark.asyncio
    async def test_uses_custom_max_steps(self):
        browser = MagicMock()
        llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_task:
            await delegate_task("task", browser, llm, max_steps=10)
            mock_task.assert_called_once()
            call_kwargs = mock_task.call_args
            assert call_kwargs[1].get("max_steps") == 10 or call_kwargs.kwargs.get("max_steps") == 10

    @pytest.mark.asyncio
    async def test_returns_empty_string_result(self):
        browser = MagicMock()
        llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("", [])):
            result = await delegate_task("empty task", browser, llm)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_result_with_actions(self):
        browser = MagicMock()
        llm = MagicMock()
        actions = [{"type": "click"}, {"type": "type"}]

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("result", actions)):
            result = await delegate_task("task", browser, llm)
        assert result == "result"  # Only returns result_text, not actions


class TestDelegateParallel:
    @pytest.mark.asyncio
    async def test_returns_results_in_order(self):
        browser = MagicMock()
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, browser_context=None):
            return f"result-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["a", "b", "c"], browser, llm_provider)

        assert results == ["result-a", "result-b", "result-c"]

    @pytest.mark.asyncio
    async def test_handles_task_failure_gracefully(self):
        browser = MagicMock()
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, browser_context=None):
            if task == "fail":
                return "Subagent failed: error"
            return f"ok-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["good", "fail", "also-good"], browser, llm_provider)

        assert results[0] == "ok-good"
        assert "failed" in results[1]
        assert results[2] == "ok-also-good"

    @pytest.mark.asyncio
    async def test_empty_tasks_list(self):
        browser = MagicMock()
        llm_provider = MagicMock()

        with patch("sediman.agent.delegate.delegate_task", new_callable=AsyncMock):
            results = await delegate_parallel([], browser, llm_provider)

        assert results == []

    @pytest.mark.asyncio
    async def test_single_task(self):
        browser = MagicMock()
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        with patch("sediman.agent.delegate.delegate_task", new_callable=AsyncMock, return_value="only result"):
            results = await delegate_parallel(["solo"], browser, llm_provider)

        assert results == ["only result"]

    @pytest.mark.asyncio
    async def test_custom_max_concurrent(self):
        browser = MagicMock()
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        with patch("sediman.agent.delegate.delegate_task", new_callable=AsyncMock, return_value="r"):
            results = await delegate_parallel(
                ["a", "b"], browser, llm_provider, max_concurrent=1
            )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_replaces_none_with_no_result(self):
        browser = MagicMock()
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, browser_context=None):
            if task == "empty":
                return None
            return task

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["empty", "normal"], browser, llm_provider)

        assert results[0] == "No result"
        assert results[1] == "normal"
