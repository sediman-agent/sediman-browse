from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sediman.agent.tools.misc import _handle_web_search
from sediman.agent.tool_dispatch import ToolResult


class TestWebSearchEmptyQuery:
    @pytest.mark.asyncio
    async def test_rejects_empty_query(self):
        result = await _handle_web_search(query="")
        assert result.success is False
        assert "required" in result.output.lower()

    @pytest.mark.asyncio
    async def test_rejects_whitespace_query(self):
        result = await _handle_web_search(query="   ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_rejects_none_query(self):
        result = await _handle_web_search(query=None)
        assert result.success is False


class TestWebSearchSuccess:
    @pytest.mark.asyncio
    async def test_returns_content_on_success(self):
        mock_result = {
            "content": "Python is a programming language",
            "stats": {"method": "http", "title": "Python"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await _handle_web_search(query="python")

        assert result.success is True
        assert "Python" in result.output
        assert result.data["query"] == "python"
        assert "google.com/search" in result.data["url"]

    @pytest.mark.asyncio
    async def test_encodes_query_in_url(self):
        mock_result = {
            "content": "results",
            "stats": {"method": "http"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result) as mock_extract:
            await _handle_web_search(query="hello world & special<>chars")

        call_url = mock_extract.call_args.kwargs.get("url", "")
        assert "hello+world" in call_url
        assert "%26" in call_url

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_query(self):
        mock_result = {
            "content": "results",
            "stats": {"method": "http"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result) as mock_extract:
            result = await _handle_web_search(query="  python  ")

        assert result.success is True
        call_url = mock_extract.call_args.kwargs.get("url", "")
        assert "python" in call_url


class TestWebSearchFailure:
    @pytest.mark.asyncio
    async def test_returns_failure_on_empty_content(self):
        mock_result = {
            "content": "",
            "stats": {"method": "http"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await _handle_web_search(query="python")

        assert result.success is False
        assert "failed" in result.output.lower()

    @pytest.mark.asyncio
    async def test_returns_failure_on_method_failed(self):
        mock_result = {
            "content": "error page",
            "stats": {"method": "failed"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await _handle_web_search(query="python")

        assert result.success is False

    @pytest.mark.asyncio
    async def test_returns_failure_on_exception(self):
        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, side_effect=ConnectionError("network down")):
            result = await _handle_web_search(query="python")

        assert result.success is False
        assert "network down" in result.output

    @pytest.mark.asyncio
    async def test_data_has_delegated_false_on_failure(self):
        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            result = await _handle_web_search(query="test")

        assert result.data["delegated"] is False

    @pytest.mark.asyncio
    async def test_data_has_chars_on_success(self):
        mock_result = {
            "content": "x" * 500,
            "stats": {"method": "http"},
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await _handle_web_search(query="test")

        assert result.data["chars"] == 500
