from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.browser.controller import (
    BrowserController,
    ElementInfo,
    PageSnapshot,
    format_snapshot,
)


class TestBrowserControllerLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        ctrl = BrowserController(headless=True)
        assert not ctrl.is_started
        # Mock playwright to avoid needing actual browser
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            mock_browser.pages = [mock_page]
            mock_playwright.chromium.launch_persistent_context.return_value = mock_browser
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            await ctrl.start()
            assert ctrl.is_started

            mock_browser.close = AsyncMock()
            mock_playwright.stop = AsyncMock()
            await ctrl.stop()
            assert not ctrl.is_started

    @pytest.mark.asyncio
    async def test_start_creates_page_if_none(self):
        ctrl = BrowserController(headless=True)
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_browser.pages = []
            mock_new_page = AsyncMock()
            mock_browser.new_page = AsyncMock(return_value=mock_new_page)
            mock_playwright.chromium.launch_persistent_context.return_value = mock_browser
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            await ctrl.start()
            assert ctrl.is_started
            mock_browser.new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_double_start_noop(self):
        ctrl = BrowserController(headless=True)
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_playwright = AsyncMock()
            mock_browser = AsyncMock()
            mock_browser.pages = [AsyncMock()]
            mock_playwright.chromium.launch_persistent_context.return_value = mock_browser
            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright)

            await ctrl.start()
            await ctrl.start()  # second should be noop
            mock_playwright.chromium.launch_persistent_context.assert_called_once()


class TestBrowserControllerActions:
    @pytest.fixture
    def mock_controller(self):
        ctrl = BrowserController(headless=True)
        ctrl._page = AsyncMock()
        ctrl._started = True
        return ctrl

    @pytest.mark.asyncio
    async def test_navigate(self, mock_controller):
        mock_controller._page.goto = AsyncMock(
            return_value=MagicMock(status=200)
        )
        mock_controller._page.url = "https://example.com"
        result = await mock_controller.navigate("https://example.com")
        assert "Navigated to https://example.com" in result
        assert "200" in result

    @pytest.mark.asyncio
    async def test_navigate_failure(self, mock_controller):
        mock_controller._page.goto = AsyncMock(side_effect=RuntimeError("Timeout"))
        result = await mock_controller.navigate("https://fail.com")
        assert "Failed" in result

    @pytest.mark.asyncio
    async def test_click(self, mock_controller):
        mock_element = AsyncMock()
        mock_controller._page.query_selector = AsyncMock(return_value=mock_element)
        mock_element.evaluate = AsyncMock(side_effect=["button", "Submit"])
        result = await mock_controller.click(1)
        assert "Clicked element [ref_id=1]" in result
        assert "button" in result.lower()

    @pytest.mark.asyncio
    async def test_click_not_found(self, mock_controller):
        mock_controller._page.query_selector = AsyncMock(return_value=None)
        result = await mock_controller.click(999)
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_type_text(self, mock_controller):
        mock_element = AsyncMock()
        mock_controller._page.query_selector = AsyncMock(return_value=mock_element)
        mock_element.evaluate = AsyncMock(return_value="input")
        result = await mock_controller.type_text(1, "hello world")
        assert "Typed 'hello world'" in result
        mock_element.fill.assert_called_once_with("hello world")

    @pytest.mark.asyncio
    async def test_type_text_with_submit(self, mock_controller):
        mock_element = AsyncMock()
        mock_controller._page.query_selector = AsyncMock(return_value=mock_element)
        mock_element.evaluate = AsyncMock(return_value="input")
        await mock_controller.type_text(1, "hello", submit=True)
        mock_element.press.assert_called_once_with("Enter")

    @pytest.mark.asyncio
    async def test_scroll(self, mock_controller):
        mock_controller._page.evaluate = AsyncMock()
        result = await mock_controller.scroll("down", 500)
        assert "Scrolled down" in result
        mock_controller._page.evaluate.assert_called_once_with("window.scrollBy(0, 500)")

    @pytest.mark.asyncio
    async def test_scroll_bottom(self, mock_controller):
        mock_controller._page.evaluate = AsyncMock()
        result = await mock_controller.scroll("bottom")
        assert "Scrolled bottom" in result

    @pytest.mark.asyncio
    async def test_scroll_invalid(self, mock_controller):
        result = await mock_controller.scroll("sideways")
        assert "Unknown scroll direction" in result

    @pytest.mark.asyncio
    async def test_press_key(self, mock_controller):
        mock_controller._page.keyboard.press = AsyncMock()
        result = await mock_controller.press_key("Enter")
        assert "Pressed key: Enter" in result

    @pytest.mark.asyncio
    async def test_go_back(self, mock_controller):
        mock_controller._page.go_back = AsyncMock()
        mock_controller._page.url = "https://prev.com"
        result = await mock_controller.go_back()
        assert "Went back to https://prev.com" in result

    @pytest.mark.asyncio
    async def test_screenshot(self, mock_controller):
        mock_controller._page.screenshot = AsyncMock(return_value=b"fake_jpeg")
        result = await mock_controller.screenshot()
        assert result is not None
        # Should be base64 of fake_jpeg
        import base64
        assert result == base64.b64encode(b"fake_jpeg").decode("utf-8")

    @pytest.mark.asyncio
    async def test_screenshot_failure(self, mock_controller):
        mock_controller._page.screenshot = AsyncMock(side_effect=RuntimeError("crash"))
        result = await mock_controller.screenshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_url(self, mock_controller):
        mock_controller._page.url = "https://test.com"
        assert await mock_controller.get_url() == "https://test.com"

    @pytest.mark.asyncio
    async def test_get_title(self, mock_controller):
        mock_controller._page.title = AsyncMock(return_value="Test Page")
        assert await mock_controller.get_title() == "Test Page"

    @pytest.mark.asyncio
    async def test_extract_text(self, mock_controller):
        mock_controller._page.evaluate = AsyncMock(return_value="Hello World")
        result = await mock_controller.extract_text()
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_extract_by_selector(self, mock_controller):
        mock_el = AsyncMock()
        mock_el.evaluate = AsyncMock(return_value="Found text")
        mock_controller._page.query_selector_all = AsyncMock(return_value=[mock_el])
        result = await mock_controller.extract_by_selector(".content")
        assert "Found text" in result

    @pytest.mark.asyncio
    async def test_wait_for_selector(self, mock_controller):
        mock_controller._page.wait_for_selector = AsyncMock()
        result = await mock_controller.wait_for_selector("#loading")
        assert "appeared" in result


class TestBrowserControllerNotStarted:
    @pytest.fixture
    def stopped_controller(self):
        return BrowserController(headless=True)

    @pytest.mark.asyncio
    async def test_navigate_not_started(self, stopped_controller):
        result = await stopped_controller.navigate("https://example.com")
        assert result == "Browser not started."

    @pytest.mark.asyncio
    async def test_click_not_started(self, stopped_controller):
        result = await stopped_controller.click(1)
        assert result == "Browser not started."

    @pytest.mark.asyncio
    async def test_snapshot_not_started(self, stopped_controller):
        snapshot = await stopped_controller.snapshot()
        assert snapshot.url == ""
        assert snapshot.elements == []


class TestFormatSnapshot:
    def test_empty_elements(self):
        snapshot = PageSnapshot(url="https://x.com", title="X", elements=[])
        text = format_snapshot(snapshot)
        assert "URL: https://x.com" in text
        assert "No interactive elements" in text

    def test_with_elements(self):
        elements = [
            ElementInfo(ref_id=1, tag="button", text="Submit", role="button"),
            ElementInfo(ref_id=2, tag="input", placeholder="Email", type="email"),
        ]
        snapshot = PageSnapshot(
            url="https://example.com",
            title="Example",
            elements=elements,
            text_preview="Welcome to example",
        )
        text = format_snapshot(snapshot)
        assert "role=button" in text
        assert '"Submit"' in text
        assert "placeholder=" in text
        assert "type=email" in text
        assert "Welcome to example" in text

    def test_limits_elements(self):
        elements = [ElementInfo(ref_id=i, tag="div", text=f"Item {i}") for i in range(1, 100)]
        snapshot = PageSnapshot(url="https://x.com", title="X", elements=elements)
        text = format_snapshot(snapshot)
        lines = [l for l in text.split("\n") if l.startswith("  [")]
        assert len(lines) <= 50

    def test_href_and_src(self):
        elements = [
            ElementInfo(ref_id=1, tag="a", text="Link", href="https://go.com"),
            ElementInfo(ref_id=2, tag="img", alt="Pic", src="https://img.png"),
        ]
        snapshot = PageSnapshot(url="https://x.com", title="X", elements=elements)
        text = format_snapshot(snapshot)
        assert "href=https://go.com" in text
        assert "src=https://img.png" in text


class TestBrowserControllerCallbacks:
    @pytest.mark.asyncio
    async def test_on_step_callback(self):
        calls = []

        def on_step(action, detail):
            calls.append((action, detail))

        ctrl = BrowserController(headless=True, on_step=on_step)
        ctrl._page = AsyncMock()
        ctrl._started = True
        ctrl._page.goto = AsyncMock(return_value=MagicMock(status=200))
        ctrl._page.url = "https://example.com"

        await ctrl.navigate("https://example.com")
        assert len(calls) == 1
        assert calls[0][0] == "navigate"
