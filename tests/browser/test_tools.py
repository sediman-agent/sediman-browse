from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sediman.agent.tool_dispatch import ToolRegistry
from sediman.browser.controller import BrowserController
from sediman.browser.tools import (
    get_default_browser_controller,
    register_browser_tools,
    set_default_browser_controller,
)


@pytest.fixture
def mock_controller():
    ctrl = MagicMock(spec=BrowserController)
    ctrl.is_started = True
    return ctrl


@pytest.fixture
def registry_with_browser(mock_controller):
    set_default_browser_controller(mock_controller)
    registry = ToolRegistry()
    register_browser_tools(registry)
    return registry


class TestBrowserNavigate:
    @pytest.mark.asyncio
    async def test_navigate_success(self, registry_with_browser, mock_controller):
        mock_controller.navigate = AsyncMock(return_value="Navigated to https://x.com (HTTP 200)")
        result = await registry_with_browser.dispatch("browser_navigate", {"url": "https://x.com"})
        assert result.success is True
        assert "Navigated" in result.output

    @pytest.mark.asyncio
    async def test_navigate_not_initialized(self, registry_with_browser):
        set_default_browser_controller(None)
        result = await registry_with_browser.dispatch("browser_navigate", {"url": "https://x.com"})
        assert result.success is False
        assert "not initialized" in result.output

    @pytest.mark.asyncio
    async def test_navigate_failure(self, registry_with_browser, mock_controller):
        mock_controller.navigate = AsyncMock(return_value="Failed to navigate: timeout")
        result = await registry_with_browser.dispatch("browser_navigate", {"url": "https://fail.com"})
        assert result.success is False


class TestBrowserSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_success(self, registry_with_browser, mock_controller):
        from sediman.browser.controller import PageSnapshot
        mock_controller.snapshot = AsyncMock(
            return_value=PageSnapshot(
                url="https://example.com",
                title="Example",
                elements=[],
            )
        )
        result = await registry_with_browser.dispatch("browser_snapshot", {})
        assert result.success is True
        assert "URL: https://example.com" in result.output

    @pytest.mark.asyncio
    async def test_snapshot_not_started(self, registry_with_browser, mock_controller):
        mock_controller.is_started = False
        result = await registry_with_browser.dispatch("browser_snapshot", {})
        assert result.success is False
        assert "not started" in result.output


class TestBrowserClick:
    @pytest.mark.asyncio
    async def test_click_success(self, registry_with_browser, mock_controller):
        mock_controller.click = AsyncMock(return_value="Clicked element [ref_id=1] (button: 'OK')")
        result = await registry_with_browser.dispatch("browser_click", {"ref_id": 1})
        assert result.success is True
        assert "Clicked" in result.output

    @pytest.mark.asyncio
    async def test_click_not_found(self, registry_with_browser, mock_controller):
        mock_controller.click = AsyncMock(return_value="Element [ref_id=999] not found")
        result = await registry_with_browser.dispatch("browser_click", {"ref_id": 999})
        assert result.success is False


class TestBrowserType:
    @pytest.mark.asyncio
    async def test_type_success(self, registry_with_browser, mock_controller):
        mock_controller.type_text = AsyncMock(return_value="Typed 'hello' into [ref_id=1]")
        result = await registry_with_browser.dispatch("browser_type", {"ref_id": 1, "text": "hello"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_type_with_submit(self, registry_with_browser, mock_controller):
        mock_controller.type_text = AsyncMock(return_value="Typed 'hello' + Enter")
        result = await registry_with_browser.dispatch(
            "browser_type", {"ref_id": 1, "text": "hello", "submit": True}
        )
        mock_controller.type_text.assert_called_once_with(1, "hello", submit=True)


class TestBrowserScroll:
    @pytest.mark.asyncio
    async def test_scroll_down(self, registry_with_browser, mock_controller):
        mock_controller.scroll = AsyncMock(return_value="Scrolled down")
        result = await registry_with_browser.dispatch("browser_scroll", {"direction": "down", "amount": 500})
        assert result.success is True
        mock_controller.scroll.assert_called_once_with("down", 500)


class TestBrowserScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_success(self, registry_with_browser, mock_controller):
        mock_controller.screenshot = AsyncMock(return_value="base64data")
        result = await registry_with_browser.dispatch("browser_screenshot", {})
        assert result.success is True
        assert "base64" in result.output
        assert result.data is not None
        assert result.data["screenshot_base64"] == "base64data"

    @pytest.mark.asyncio
    async def test_screenshot_failure(self, registry_with_browser, mock_controller):
        mock_controller.screenshot = AsyncMock(return_value=None)
        result = await registry_with_browser.dispatch("browser_screenshot", {})
        assert result.success is False


class TestBrowserExtract:
    @pytest.mark.asyncio
    async def test_extract_all(self, registry_with_browser, mock_controller):
        mock_controller.extract_text = AsyncMock(return_value="Page content here")
        result = await registry_with_browser.dispatch("browser_extract", {})
        assert result.success is True
        assert "Page content" in result.output

    @pytest.mark.asyncio
    async def test_extract_selector(self, registry_with_browser, mock_controller):
        mock_controller.extract_by_selector = AsyncMock(return_value="Selected content")
        result = await registry_with_browser.dispatch("browser_extract", {"selector": ".content"})
        mock_controller.extract_by_selector.assert_called_once_with(".content")


class TestBrowserGetUrl:
    @pytest.mark.asyncio
    async def test_get_url(self, registry_with_browser, mock_controller):
        mock_controller.get_url = AsyncMock(return_value="https://current.com")
        result = await registry_with_browser.dispatch("browser_get_url", {})
        assert result.success is True
        assert result.output == "https://current.com"


class TestBrowserGoBackForward:
    @pytest.mark.asyncio
    async def test_go_back(self, registry_with_browser, mock_controller):
        mock_controller.go_back = AsyncMock(return_value="Went back")
        result = await registry_with_browser.dispatch("browser_go_back", {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_go_forward(self, registry_with_browser, mock_controller):
        mock_controller.go_forward = AsyncMock(return_value="Went forward")
        result = await registry_with_browser.dispatch("browser_go_forward", {})
        assert result.success is True


class TestBrowserPressKey:
    @pytest.mark.asyncio
    async def test_press_key(self, registry_with_browser, mock_controller):
        mock_controller.press_key = AsyncMock(return_value="Pressed key: Enter")
        result = await registry_with_browser.dispatch("browser_press_key", {"key": "Enter"})
        assert result.success is True


class TestControllerGetterSetter:
    def test_default_controller_roundtrip(self):
        ctrl = MagicMock(spec=BrowserController)
        set_default_browser_controller(ctrl)
        assert get_default_browser_controller() is ctrl
        set_default_browser_controller(None)
        assert get_default_browser_controller() is None


class TestAllToolsRegistered:
    def test_count(self):
        registry = ToolRegistry()
        register_browser_tools(registry)
        tools = registry.list_tools()
        assert "browser_navigate" in tools
        assert "browser_snapshot" in tools
        assert "browser_click" in tools
        assert "browser_type" in tools
        assert "browser_scroll" in tools
        assert "browser_press_key" in tools
        assert "browser_go_back" in tools
        assert "browser_go_forward" in tools
        assert "browser_screenshot" in tools
        assert "browser_extract" in tools
        assert "browser_get_url" in tools
        assert "browser_refresh" in tools
        assert "browser_wait_for_selector" in tools
        assert len(tools) == 13


class TestBrowserRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self, registry_with_browser, mock_controller):
        mock_controller.refresh = AsyncMock(return_value="Refreshed https://x.com")
        result = await registry_with_browser.dispatch("browser_refresh", {})
        assert result.success is True
        assert "Refreshed" in result.output

    @pytest.mark.asyncio
    async def test_refresh_failure(self, registry_with_browser, mock_controller):
        mock_controller.refresh = AsyncMock(return_value="Refresh failed: timeout")
        result = await registry_with_browser.dispatch("browser_refresh", {})
        assert result.success is False


class TestBrowserWaitForSelector:
    @pytest.mark.asyncio
    async def test_wait_success(self, registry_with_browser, mock_controller):
        mock_controller.wait_for_selector = AsyncMock(return_value="Element '.btn' appeared.")
        result = await registry_with_browser.dispatch(
            "browser_wait_for_selector", {"selector": ".btn"}
        )
        assert result.success is True
        assert "appeared" in result.output

    @pytest.mark.asyncio
    async def test_wait_timeout(self, registry_with_browser, mock_controller):
        mock_controller.wait_for_selector = AsyncMock(
            return_value="Wait timed out for '.btn': Timeout"
        )
        result = await registry_with_browser.dispatch(
            "browser_wait_for_selector", {"selector": ".btn", "timeout": 1000}
        )
        assert result.success is False
        mock_controller.wait_for_selector.assert_called_once_with(".btn", timeout=1000)
