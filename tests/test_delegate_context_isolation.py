"""Tests for Browser Context Isolation — delegate_parallel with isolated contexts."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.delegate import delegate_parallel


class TestDelegateParallelContextIsolation:
    @pytest.mark.asyncio
    async def test_creates_browser_context_per_task(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        mock_context = AsyncMock()
        browser.browser.create_session = AsyncMock(return_value=mock_context)
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            return f"result-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["a", "b"], browser, llm_provider)

        assert results == ["result-a", "result-b"]
        assert browser.browser.create_session.call_count == 2

    @pytest.mark.asyncio
    async def test_closes_context_after_task(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        mock_context = AsyncMock()
        browser.browser.create_session = AsyncMock(return_value=mock_context)
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            return f"result-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            await delegate_parallel(["a"], browser, llm_provider)

        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_context_creation_failure(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        browser.browser.create_session = AsyncMock(side_effect=RuntimeError("no slots"))
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            return f"result-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["a"], browser, llm_provider)

        assert results == ["result-a"]

    @pytest.mark.asyncio
    async def test_context_close_error_swallowed(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        mock_context = AsyncMock()
        mock_context.close = AsyncMock(side_effect=RuntimeError("already closed"))
        browser.browser.create_session = AsyncMock(return_value=mock_context)
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            return "ok"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["a"], browser, llm_provider)

        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        import asyncio

        browser = MagicMock()
        browser.browser = MagicMock()
        browser.browser.create_session = AsyncMock(return_value=AsyncMock())
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        active = {"count": 0, "max": 0}

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            await asyncio.sleep(0.05)
            active["count"] -= 1
            return f"result-{task}"

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            await delegate_parallel(["a", "b", "c", "d"], browser, llm_provider, max_concurrent=2)

        assert active["max"] <= 2

    @pytest.mark.asyncio
    async def test_returns_no_result_for_none(self):
        browser = MagicMock()
        browser.browser = MagicMock()
        browser.browser.create_session = AsyncMock(side_effect=RuntimeError("skip"))
        llm_provider = MagicMock()
        llm_provider.get_browser_use_llm.return_value = MagicMock()

        async def fake_delegate(task, bs, llm, max_steps=30, **kwargs):
            return None

        with patch("sediman.agent.delegate.delegate_task", side_effect=fake_delegate):
            results = await delegate_parallel(["a"], browser, llm_provider)

        assert results == ["No result"]
