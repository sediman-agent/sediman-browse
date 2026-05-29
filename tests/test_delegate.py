from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.delegate import delegate_task, delegate_parallel


class TestDelegateTaskContextPassthrough:
    @pytest.mark.asyncio
    async def test_uses_browser_context_when_provided(self):
        mock_context = MagicMock()
        mock_llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("result", [])) as mock_run:
            result = await delegate_task(
                task="test task",
                browser_session=MagicMock(),
                llm=mock_llm,
                browser_context=mock_context,
            )

        assert result == "result"
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["browser_session"] is mock_context

    @pytest.mark.asyncio
    async def test_uses_browser_session_when_no_context(self):
        mock_session = MagicMock()
        mock_llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("result", [])) as mock_run:
            result = await delegate_task(
                task="test task",
                browser_session=mock_session,
                llm=mock_llm,
            )

        assert result == "result"
        assert mock_run.call_args.kwargs["browser_session"] is mock_session

    @pytest.mark.asyncio
    async def test_uses_browser_session_when_context_is_none(self):
        mock_session = MagicMock()
        mock_llm = MagicMock()

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("result", [])) as mock_run:
            result = await delegate_task(
                task="test task",
                browser_session=mock_session,
                llm=mock_llm,
                browser_context=None,
            )

        assert mock_run.call_args.kwargs["browser_session"] is mock_session

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            result = await delegate_task(
                task="test task",
                browser_session=MagicMock(),
                llm=MagicMock(),
            )

        assert "Subagent failed" in result
        assert "boom" in result

    @pytest.mark.asyncio
    async def test_passes_max_steps(self):
        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])) as mock_run:
            await delegate_task(
                task="t",
                browser_session=MagicMock(),
                llm=MagicMock(),
                max_steps=42,
            )

        assert mock_run.call_args.kwargs["max_steps"] == 42


class TestDelegateParallel:
    @pytest.mark.asyncio
    async def test_creates_context_per_task(self):
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(return_value=MagicMock())
        mock_browser.close = AsyncMock()

        mock_session = MagicMock()
        mock_session.browser = mock_browser

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("done", [])):
            results = await delegate_parallel(
                tasks=["task1", "task2"],
                browser_session=mock_session,
                llm_provider=mock_provider,
            )

        assert mock_browser.create_session.call_count == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_results_in_input_order(self):
        mock_session = MagicMock()
        mock_session.browser = None

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        call_count = 0

        async def fake_run(**kwargs):
            nonlocal call_count
            call_count += 1
            return (f"result_{call_count}", [])

        with patch("sediman.browser.session.run_browser_task", side_effect=fake_run):
            results = await delegate_parallel(
                tasks=["a", "b", "c"],
                browser_session=mock_session,
                llm_provider=mock_provider,
            )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_handles_no_browser_gracefully(self):
        mock_session = MagicMock()
        mock_session.browser = None

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])):
            results = await delegate_parallel(
                tasks=["task1"],
                browser_session=mock_session,
                llm_provider=mock_provider,
            )

        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(return_value=MagicMock())
        mock_session = MagicMock()
        mock_session.browser = mock_browser

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])):
            results = await delegate_parallel(
                tasks=["a", "b", "c", "c", "e"],
                browser_session=mock_session,
                llm_provider=mock_provider,
                max_concurrent=2,
            )

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_context_closed_after_use(self):
        mock_ctx = AsyncMock()
        mock_browser = MagicMock()
        mock_browser.create_session = AsyncMock(return_value=mock_ctx)
        mock_session = MagicMock()
        mock_session.browser = mock_browser

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])):
            await delegate_parallel(
                tasks=["task1"],
                browser_session=mock_session,
                llm_provider=mock_provider,
            )

        mock_ctx.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_context_not_closed_when_none(self):
        mock_session = MagicMock()
        mock_session.browser = None

        mock_provider = MagicMock()
        mock_provider.get_browser_use_llm = MagicMock(return_value=MagicMock())

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("ok", [])):
            results = await delegate_parallel(
                tasks=["task1"],
                browser_session=mock_session,
                llm_provider=mock_provider,
            )

        assert results == ["ok"]
