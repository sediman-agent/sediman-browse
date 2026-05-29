"""Tests for Speed Optimizations — domcontentloaded waits, prewarm, go_back/forward/refresh."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.browser.controller import BrowserController
from sediman.browser.session import BrowserSession


class TestNavigateUsesDomContentLoaded:
    @pytest.fixture
    def ctrl(self):
        ctrl = BrowserController(headless=True)
        ctrl._page = AsyncMock()
        ctrl._started = True
        return ctrl

    @pytest.mark.asyncio
    async def test_navigate_uses_domcontentloaded(self, ctrl):
        ctrl._page.goto = AsyncMock(return_value=MagicMock(status=200))
        ctrl._page.url = "https://example.com"
        ctrl._page.wait_for_load_state = AsyncMock()

        await ctrl.navigate("https://example.com")

        call_args = ctrl._page.goto.call_args
        assert call_args.kwargs.get("wait_until") == "domcontentloaded" or \
               (call_args[1] if len(call_args) > 1 else {}).get("wait_until") == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_navigate_networkidle_timeout_short(self, ctrl):
        ctrl._page.goto = AsyncMock(return_value=MagicMock(status=200))
        ctrl._page.url = "https://example.com"

        await ctrl.navigate("https://example.com")

        ctrl._page.goto.assert_called_once()
        call_args = ctrl._page.goto.call_args
        assert call_args.kwargs.get("wait_until") == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_navigate_handles_goto_exception(self, ctrl):
        ctrl._page.goto = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await ctrl.navigate("https://example.com")

        assert "failed" in result.lower() or "error" in result.lower()


class TestGoBackForwardRefresh:
    @pytest.fixture
    def ctrl(self):
        ctrl = BrowserController(headless=True)
        ctrl._page = AsyncMock()
        ctrl._started = True
        return ctrl

    @pytest.mark.asyncio
    async def test_go_back_uses_domcontentloaded(self, ctrl):
        ctrl._page.go_back = AsyncMock()
        ctrl._page.url = "https://prev.com"
        ctrl._page.wait_for_load_state = AsyncMock()

        await ctrl.go_back()

        call_args = ctrl._page.go_back.call_args
        assert call_args.kwargs.get("wait_until") == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_go_forward_uses_domcontentloaded(self, ctrl):
        ctrl._page.go_forward = AsyncMock()
        ctrl._page.url = "https://next.com"
        ctrl._page.wait_for_load_state = AsyncMock()

        await ctrl.go_forward()

        call_args = ctrl._page.go_forward.call_args
        assert call_args.kwargs.get("wait_until") == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_refresh_uses_domcontentloaded(self, ctrl):
        ctrl._page.reload = AsyncMock()
        ctrl._page.url = "https://same.com"
        ctrl._page.wait_for_load_state = AsyncMock()

        await ctrl.refresh()

        call_args = ctrl._page.reload.call_args
        assert call_args.kwargs.get("wait_until") == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_go_back_networkidle_timeout_3s(self, ctrl):
        ctrl._page.go_back = AsyncMock()
        ctrl._page.url = "https://prev.com"
        ctrl._page.wait_for_load_state = AsyncMock()

        await ctrl.go_back()

        call_args = ctrl._page.wait_for_load_state.call_args
        assert call_args.kwargs.get("timeout") == 3000

    @pytest.mark.asyncio
    async def test_go_back_handles_networkidle_failure(self, ctrl):
        ctrl._page.go_back = AsyncMock()
        ctrl._page.url = "https://prev.com"
        ctrl._page.wait_for_load_state = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await ctrl.go_back()

        assert "Went back" in result

    @pytest.mark.asyncio
    async def test_go_forward_handles_networkidle_failure(self, ctrl):
        ctrl._page.go_forward = AsyncMock()
        ctrl._page.url = "https://next.com"
        ctrl._page.wait_for_load_state = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await ctrl.go_forward()

        assert "Went forward" in result

    @pytest.mark.asyncio
    async def test_refresh_handles_networkidle_failure(self, ctrl):
        ctrl._page.reload = AsyncMock()
        ctrl._page.url = "https://same.com"
        ctrl._page.wait_for_load_state = AsyncMock(side_effect=RuntimeError("timeout"))

        result = await ctrl.refresh()

        assert "Refreshed" in result


class TestBrowserSessionPrewarm:
    @pytest.mark.asyncio
    async def test_prewarm_calls_start(self):
        session = BrowserSession(headless=True)
        with patch.object(session, "start", new_callable=AsyncMock) as mock_start:
            await session.prewarm()
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_prewarm_idempotent(self):
        session = BrowserSession(headless=True)
        with patch.object(session, "start", new_callable=AsyncMock) as mock_start:
            await session.prewarm()
            await session.prewarm()
            assert mock_start.call_count == 2
