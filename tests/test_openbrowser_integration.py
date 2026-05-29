from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.openbrowser.controller import OpenBrowserController
from sediman.openbrowser.session import OpenBrowserSession


class TestOpenBrowserController:
    @pytest.mark.asyncio
    async def test_start(self):
        client = MagicMock()
        client.health = AsyncMock(return_value=True)
        client.close = AsyncMock()
        ctrl = OpenBrowserController(client=client)
        await ctrl.start()
        assert ctrl.is_started
        client.health.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate(self):
        client = MagicMock()
        client.navigate = AsyncMock(return_value={"ok": True})
        client.current_page = AsyncMock(return_value={"url": "https://example.com", "title": "Example"})
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.navigate("https://example.com")
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_click(self):
        client = MagicMock()
        client.click = AsyncMock(return_value={"ok": True})
        client.current_page = AsyncMock(return_value={"url": "https://example.com/page2"})
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.click(3)
        assert "3" in result

    @pytest.mark.asyncio
    async def test_type_text(self):
        client = MagicMock()
        client.type_text = AsyncMock(return_value={"ok": True})
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.type_text(1, "hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_scroll(self):
        client = MagicMock()
        client.scroll = AsyncMock(return_value={"ok": True})
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.scroll("down")
        assert "down" in result

    @pytest.mark.asyncio
    async def test_refresh(self):
        client = MagicMock()
        client.reload = AsyncMock(return_value={"ok": True})
        client.current_page = AsyncMock(return_value={"url": "https://example.com"})
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.refresh()
        assert "example.com" in result

    @pytest.mark.asyncio
    async def test_screenshot_returns_none(self):
        client = MagicMock()
        ctrl = OpenBrowserController(client=client)
        ctrl._started = True
        result = await ctrl.screenshot()
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_semantic_elements(self):
        client = MagicMock()
        ctrl = OpenBrowserController(client=client)
        tree = {
            "role": "document",
            "children": [
                {
                    "role": "link",
                    "element_id": 1,
                    "tag": "a",
                    "text": "Click me",
                    "action": "navigate",
                    "href": "https://example.com/page2",
                    "children": [],
                },
                {
                    "role": "button",
                    "element_id": 2,
                    "tag": "button",
                    "text": "Submit",
                    "action": "click",
                    "children": [],
                },
                {
                    "role": "heading",
                    "tag": "h1",
                    "text": "Title",
                    "children": [],
                },
            ],
        }
        elements = ctrl._parse_semantic_elements(tree)
        assert len(elements) == 2
        assert elements[0].ref_id == 1
        assert elements[0].tag == "a"
        assert elements[0].text == "Click me"
        assert elements[1].ref_id == 2
        assert elements[1].tag == "button"


class TestOpenBrowserSession:
    @pytest.mark.asyncio
    async def test_connect_to_existing_server(self):
        with patch("sediman.openbrowser.session.OpenBrowserProcess") as MockProcess, \
             patch("sediman.openbrowser.session.OpenBrowserClient") as MockClient:
            mock_process = MagicMock()
            mock_process.start = AsyncMock()
            mock_process.stop = AsyncMock()
            MockProcess.return_value = mock_process

            mock_client = MagicMock()
            mock_client.health = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            session = OpenBrowserSession()
            await session.start()
            assert session.is_started

            await session.stop()
            assert not session.is_started

    @pytest.mark.asyncio
    async def test_browser_property(self):
        session = OpenBrowserSession()
        session._client = MagicMock()
        assert session.browser is session._client

    @pytest.mark.asyncio
    async def test_get_controller_before_start(self):
        session = OpenBrowserSession()
        assert session.get_controller() is None
