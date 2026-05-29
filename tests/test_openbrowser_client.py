from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.openbrowser.client import OpenBrowserClient


@pytest.fixture
def mock_response():
    def _make(data: dict[str, Any], status: int = 200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = data
        resp.text = json.dumps(data)
        return resp
    return _make


class TestOpenBrowserClient:
    @pytest.mark.asyncio
    async def test_health_ok(self, mock_response):
        client = OpenBrowserClient(base_url="http://localhost:7788")
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response({"status": "ok"})
            assert await client.health() is True
        await client.close()

    @pytest.mark.asyncio
    async def test_health_fail(self):
        client = OpenBrowserClient(base_url="http://localhost:7788")
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("connection refused")
            assert await client.health() is False
        await client.close()

    @pytest.mark.asyncio
    async def test_navigate(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"ok": True})
            result = await client.navigate("https://example.com")
            assert result["ok"] is True
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "navigate" in call_kwargs[0][0]
        await client.close()

    @pytest.mark.asyncio
    async def test_semantic_tree(self, mock_response):
        client = OpenBrowserClient()
        tree = {"role": "document", "children": []}
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response(tree)
            result = await client.semantic_tree()
            assert result["role"] == "document"
        await client.close()

    @pytest.mark.asyncio
    async def test_click(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"ok": True})
            result = await client.click(element_id=3)
            assert result["ok"] is True
        await client.close()

    @pytest.mark.asyncio
    async def test_type_text(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"ok": True})
            result = await client.type_text(value="hello", element_id=1)
            assert result["ok"] is True
        await client.close()

    @pytest.mark.asyncio
    async def test_scroll(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"ok": True})
            result = await client.scroll("down")
            assert result["ok"] is True
        await client.close()

    @pytest.mark.asyncio
    async def test_get_cookies(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response({"cookies": [{"name": "sid", "value": "abc"}]})
            result = await client.get_cookies()
            assert len(result["cookies"]) == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_set_cookie(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"ok": True})
            result = await client.set_cookie("sid", "abc", "example.com")
            assert result["ok"] is True
        await client.close()

    @pytest.mark.asyncio
    async def test_error_response(self, mock_response):
        client = OpenBrowserClient()
        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response({"error": "not found"}, status=404)
            result = await client.click(element_id=99)
            assert result["ok"] is False
            assert "not found" in result["error"]
        await client.close()
