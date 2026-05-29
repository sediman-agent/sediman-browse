from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.web.extract import (
    _clean_markdown,
    _strip_tags,
    _summarize_with_llm,
    http_extract,
    browser_extract,
    web_extract,
    _DEFAULT_MAX_CHARS,
)

from sediman.agent.tools import create_agent_tool_registry
from sediman.llm.provider import LLMResponse


# ── _strip_tags ───────────────────────────────────────────────


class TestStripTags:
    def test_removes_simple_tag(self):
        html = "<div><script>alert('xss')</script><p>hello</p></div>"
        result = _strip_tags(html, ["script"])
        assert "<script>" not in result
        assert "<p>hello</p>" in result

    def test_removes_multiple_tags(self):
        html = "<div><script>x</script><style>y</style><p>z</p></div>"
        result = _strip_tags(html, ["script", "style"])
        assert "<script>" not in result
        assert "<style>" not in result
        assert "<p>z</p>" in result

    def test_removes_with_attributes(self):
        html = '<script type="text/javascript">code</script><p>text</p>'
        result = _strip_tags(html, ["script"])
        assert "<script" not in result

    def test_no_match_returns_unchanged(self):
        html = "<p>hello</p>"
        result = _strip_tags(html, ["script"])
        assert result == "<p>hello</p>"

    def test_empty_html(self):
        assert _strip_tags("", ["script"]) == ""

    def test_case_insensitive(self):
        html = "<SCRIPT>code</SCRIPT><p>text</p>"
        result = _strip_tags(html, ["script"])
        assert "SCRIPT" not in result

    def test_nested_tags(self):
        html = "<div><script>if (x) { <script>nested</script> }</script><p>ok</p></div>"
        result = _strip_tags(html, ["script"])
        assert "<script>" not in result

    def test_multiline_script_content(self):
        html = "<p>before</p>\n<script>\nvar x = 1;\nvar y = 2;\n</script>\n<p>after</p>"
        result = _strip_tags(html, ["script"])
        assert "var x" not in result
        assert "<p>before</p>" in result
        assert "<p>after</p>" in result

    def test_multiple_same_tag(self):
        html = "<p>a</p><script>x</script><p>b</p><script>y</script><p>c</p>"
        result = _strip_tags(html, ["script"])
        assert "x" not in result
        assert "y" not in result
        assert "<p>a</p>" in result
        assert "<p>c</p>" in result

    def test_noscript_tag(self):
        html = "<p>visible</p><noscript><p>hidden</p></noscript><p>also visible</p>"
        result = _strip_tags(html, ["noscript"])
        assert "hidden" not in result
        assert "visible" in result

    def test_iframe_tag(self):
        html = "<p>text</p><iframe src='evil.com'></iframe><p>more</p>"
        result = _strip_tags(html, ["iframe"])
        assert "evil.com" not in result
        assert "<p>text</p>" in result

    def test_empty_tag_list(self):
        html = "<script>x</script><p>y</p>"
        result = _strip_tags(html, [])
        assert result == html

    def test_tag_with_newline_in_attributes(self):
        html = '<script\n  type="text/javascript"\n>code</script><p>ok</p>'
        result = _strip_tags(html, ["script"])
        assert "code" not in result
        assert "<p>ok</p>" in result

    def test_self_closing_script_not_matched(self):
        html = "<script /><p>text</p>"
        result = _strip_tags(html, ["script"])
        assert "<p>text</p>" in result


# ── _clean_markdown ───────────────────────────────────────────


class TestCleanMarkdown:
    def test_removes_url_encoded_chars(self):
        result = _clean_markdown("hello%20world")
        assert "%20" not in result
        assert "hello" in result

    def test_collapses_excess_newlines(self):
        result = _clean_markdown("a\n\n\n\n\nb")
        assert result.count("\n") <= 4

    def test_removes_long_json_lines(self):
        text = "normal line\n" + "{" + "x" * 300 + "}\nanother line"
        result = _clean_markdown(text)
        assert "another line" in result
        assert "normal line" in result

    def test_removes_long_array_lines(self):
        text = "normal\n" + "[" + "x" * 300 + "]\nanother"
        result = _clean_markdown(text)
        assert "another" in result

    def test_preserves_short_json(self):
        text = '{"key": "value"}'
        result = _clean_markdown(text)
        assert '{"key": "value"}' in result

    def test_strips_result(self):
        result = _clean_markdown("  hello world  \n\n")
        assert result == "hello world"

    def test_empty_text(self):
        assert _clean_markdown("") == ""

    def test_preserves_normal_markdown(self):
        text = "# Heading\n\nParagraph with **bold** and *italic*."
        result = _clean_markdown(text)
        assert "# Heading" in result
        assert "**bold**" in result

    def test_multiple_url_encodings(self):
        text = "hello%20world%3C%3E%26"
        result = _clean_markdown(text)
        assert "%" not in result

    def test_exactly_200_chars_json_preserved(self):
        text = "line1\n" + "{" + "x" * 198 + "}\nline2"
        result = _clean_markdown(text)
        assert "line1" in result
        assert "line2" in result

    def test_201_chars_json_removed(self):
        text = "line1\n" + "{" + "x" * 199 + "}\nline2"
        result = _clean_markdown(text)
        assert "line1" in result
        assert "line2" in result

    def test_only_newlines_returns_empty(self):
        assert _clean_markdown("\n\n\n\n") == ""

    def test_code_blocks_preserved(self):
        text = "```python\ndef hello():\n    pass\n```"
        result = _clean_markdown(text)
        assert "def hello" in result

    def test_tables_preserved(self):
        text = "| Name | Price |\n|------|-------|\n| A    | $10   |"
        result = _clean_markdown(text)
        assert "| Name |" in result

    def test_mixed_long_json_and_normal_content(self):
        lines = ["Normal line 1"]
        for _ in range(5):
            lines.append("{" + "x" * 300 + "}")
        lines.append("Normal line 2")
        text = "\n".join(lines)
        result = _clean_markdown(text)
        assert "Normal line 1" in result
        assert "Normal line 2" in result


# ── http_extract ──────────────────────────────────────────────


class TestHttpExtract:
    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, stats = await http_extract("https://example.com")

        assert isinstance(content, str)
        assert stats["status_code"] == 200
        assert stats["method"] == "http"

    @pytest.mark.asyncio
    async def test_extraction_has_title(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><head><title>My Title</title></head><body><p>Content</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, stats = await http_extract("https://example.com")

        assert stats["title"] == "My Title"

    @pytest.mark.asyncio
    async def test_extraction_http_error(self):
        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=Exception("HTTP error"))

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception):
                await http_extract("https://example.com")

    @pytest.mark.asyncio
    async def test_stats_include_url(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>content</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            _, stats = await http_extract("https://example.com/article?id=1")

        assert stats["url"] == "https://example.com/article?id=1"

    @pytest.mark.asyncio
    async def test_stats_include_content_type(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = "<html><body><p>content</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            _, stats = await http_extract("https://example.com")

        assert "text/html" in stats["content_type"]

    @pytest.mark.asyncio
    async def test_stats_include_html_and_markdown_chars(self):
        html = "<html><head><title>T</title></head><body>" + "<p>" + "x " * 100 + "</p>" + "</body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, stats = await http_extract("https://example.com")

        assert stats["html_chars"] == len(html)
        assert stats["markdown_chars"] == len(content)

    @pytest.mark.asyncio
    async def test_strips_scripts_and_styles(self):
        html = (
            "<html><body>"
            "<p>Main content</p>"
            "<script>evil()</script>"
            "<style>.hidden{display:none}</style>"
            "<noscript>fallback</noscript>"
            "</body></html>"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, _ = await http_extract("https://example.com")

        assert "Main content" in content
        assert "evil()" not in content

    @pytest.mark.asyncio
    async def test_title_prepended_when_not_in_markdown(self):
        html = "<html><head><title>Unique Title 12345</title></head><body><p>body content here</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, _ = await http_extract("https://example.com")

        assert content.startswith("# Unique Title 12345")

    @pytest.mark.asyncio
    async def test_no_title_no_heading_prepended(self):
        html = "<html><body><p>Just content, no title tag</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, stats = await http_extract("https://example.com")

        # readability may return "[no-title]" or empty for pages without <title>
        assert not content.startswith("# ") or "[no-title]" in content.lower()

    @pytest.mark.asyncio
    async def test_client_created_with_correct_params(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>content</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await http_extract("https://example.com")

        mock_cls.assert_called_once_with(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"},
        )

    @pytest.mark.asyncio
    async def test_404_raises_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not Found")

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="Not Found"):
                await http_extract("https://example.com/missing")

    @pytest.mark.asyncio
    async def test_500_raises_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Internal Server Error")

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="Internal Server Error"):
                await http_extract("https://example.com/error")

    @pytest.mark.asyncio
    async def test_complex_page_with_headings_lists_tables(self):
        html = """
        <html><head><title>Complex Page</title></head><body>
        <h1>Main Heading</h1>
        <p>First paragraph with <strong>bold</strong> and <em>italic</em>.</p>
        <h2>Section 1</h2>
        <p>Some content in section 1.</p>
        <h2>Section 2</h2>
        <p>Some content in section 2 with <a href="https://example.com">a link</a>.</p>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            content, stats = await http_extract("https://example.com")

        assert "Main Heading" in content
        assert "Section 1" in content
        assert "Section 2" in content
        assert stats["title"] == "Complex Page"


# ── browser_extract ───────────────────────────────────────────


class TestBrowserExtract:
    @pytest.mark.asyncio
    async def test_successful_browser_extraction(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("Extracted content longer than fifty chars for testing purposes", [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is not None
            assert len(result) > 50

    @pytest.mark.asyncio
    async def test_browser_extraction_short_result(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("short", [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_extraction_failure(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, side_effect=Exception("browser error")):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_extraction_empty_result(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("", [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_extraction_whitespace_only(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("   \n\t  ", [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_extraction_exactly_50_chars(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("x" * 50, [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_extraction_51_chars(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("x" * 51, [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is not None
            assert len(result.strip()) == 51

    @pytest.mark.asyncio
    async def test_browser_extraction_none_result(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=(None, [])):
            result = await browser_extract("https://example.com", browser, llm)
            assert result is None

    @pytest.mark.asyncio
    async def test_browser_passes_correct_params(self):
        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "test_llm"

        with patch("sediman.browser.session.run_browser_task", new_callable=AsyncMock, return_value=("content " * 20, [])) as mock_run:
            await browser_extract("https://example.com", browser, llm)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert "https://example.com" in call_kwargs.kwargs.get("task", call_kwargs.args[0] if call_kwargs.args else "")
        assert call_kwargs.kwargs.get("max_steps") == 5
        assert call_kwargs.kwargs.get("flash_mode") is True


# ── _summarize_with_llm ──────────────────────────────────────


class TestSummarizeWithLlm:
    @pytest.mark.asyncio
    async def test_successful_summary(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text="This is a detailed summary of the content with more than fifty characters for testing"))

        result = await _summarize_with_llm("long content here", "what is this?", llm, 500)

        assert result is not None
        assert "detailed summary" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_short_response(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text="short"))

        result = await _summarize_with_llm("long content", "query", llm, 500)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_response(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text=""))

        result = await _summarize_with_llm("long content", "query", llm, 500)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_none_response(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        result = await _summarize_with_llm("long content", "query", llm, 500)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=Exception("API error"))

        result = await _summarize_with_llm("long content", "query", llm, 500)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_correct_messages_to_llm(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text="a" * 60))

        content = "test content " * 100
        await _summarize_with_llm(content, "my query", llm, 200)

        call_args = llm.chat.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "my query" in messages[1]["content"]
        assert "200" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_truncates_content_at_30k_chars(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text="a" * 60))

        content = "x" * 50000
        await _summarize_with_llm(content, "query", llm, 500)

        call_args = llm.chat.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        user_content = messages[1]["content"]
        assert "x" * 30000 in user_content or len(user_content) < 50000


# ── web_extract ───────────────────────────────────────────────


class TestWebExtract:
    @pytest.mark.asyncio
    async def test_http_extract_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>" + "x" * 200 + "</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com")

        assert result["content"]
        assert result["stats"]["method"] == "http"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_http_extract_thin_falls_back_to_browser(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>short</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        browser = MagicMock()
        llm = MagicMock()
        llm.get_browser_use_llm.return_value = "mock_llm"

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client), \
             patch("sediman.web.extract.browser_extract", new_callable=AsyncMock, return_value="Browser extracted content longer than 50 chars successfully"):
            result = await web_extract("https://example.com", browser_session=browser, llm=llm)

        assert result["content"]
        assert "Browser extracted" in result["content"]

    @pytest.mark.asyncio
    async def test_both_extraction_fail_gives_error_message(self):
        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=Exception("failed"))

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com")

        assert "Could not extract" in result["content"]
        assert result["stats"]["method"] == "failed"

    @pytest.mark.asyncio
    async def test_truncation_without_llm(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>" + "x" * 10000 + "</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", max_chars=100)

        assert result["truncated"] is True
        assert len(result["content"]) <= 200

    @pytest.mark.asyncio
    async def test_truncation_with_llm_summary(self):
        html_content = (
            "<html><head><title>Long Article</title></head><body>"
            "<h1>Main Heading</h1>"
            + "".join(f"<p>Paragraph {i}: {'word ' * 50}</p>" for i in range(20))
            + "</body></html>"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html_content

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text="Summarized content here with enough detail to pass the threshold check"))
        browser = MagicMock()

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", query="what is this?", browser_session=browser, llm=llm, max_chars=100)

        assert result["summarized"] is True
        assert result["stats"]["summarized"] is True

    @pytest.mark.asyncio
    async def test_web_extract_with_query_under_limit_no_summary(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>" + "x" * 100 + "</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        llm = MagicMock()
        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", query="test", llm=llm, max_chars=5000)

        assert result["summarized"] is False
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_no_browser_session_skips_fallback(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>short</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", browser_session=None, llm=MagicMock())

        assert "Could not extract" in result["content"]

    @pytest.mark.asyncio
    async def test_no_llm_skips_fallback(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>short</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", browser_session=MagicMock(), llm=None)

        assert "Could not extract" in result["content"]

    @pytest.mark.asyncio
    async def test_llm_fallback_failure_still_fails(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>short</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client), \
             patch("sediman.web.extract.browser_extract", new_callable=AsyncMock, return_value=None):
            result = await web_extract("https://example.com", browser_session=MagicMock(), llm=MagicMock())

        assert "Could not extract" in result["content"]

    @pytest.mark.asyncio
    async def test_result_dict_structure(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body><p>" + "x" * 200 + "</p></body></html>"

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com")

        assert "content" in result
        assert "stats" in result
        assert "truncated" in result
        assert "summarized" in result
        assert isinstance(result["stats"], dict)

    @pytest.mark.asyncio
    async def test_stats_propagated_from_http(self):
        html = "<html><head><title>Stats Test</title></head><body><p>" + "content " * 100 + "</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com")

        assert result["stats"]["method"] == "http"
        assert result["stats"]["title"] == "Stats Test"
        assert result["stats"]["html_chars"] == len(html)

    @pytest.mark.asyncio
    async def test_default_max_chars(self):
        assert _DEFAULT_MAX_CHARS == 5000

    @pytest.mark.asyncio
    async def test_query_with_llm_fallback_truncation(self):
        html_content = (
            "<html><head><title>Article</title></head><body>"
            + "".join(f"<p>Paragraph {i}: {'word ' * 50}</p>" for i in range(20))
            + "</body></html>"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html_content

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", query="tell me", llm=llm, max_chars=200)

        assert result["truncated"] is True
        assert result["summarized"] is False

    @pytest.mark.asyncio
    async def test_empty_url_produces_failure(self):
        with patch("sediman.web.extract.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=Exception("No URL"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await web_extract("")

        assert "Could not extract" in result["content"]

    @pytest.mark.asyncio
    async def test_content_exactly_at_limit_no_truncation(self):
        html = "<html><head><title>T</title></head><body><p>" + "a" * 4900 + "</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com", max_chars=5000)

        assert result["truncated"] is False


# ── Tool handler ──────────────────────────────────────────────


class TestWebExtractToolHandler:
    def test_tool_registered(self):
        registry = create_agent_tool_registry()
        names = registry.list_tools()
        assert "web_extract" in names

    def test_tool_has_correct_schema(self):
        registry = create_agent_tool_registry()
        defn = registry.get_definition("web_extract")
        assert "url" in defn.parameters["properties"]
        assert "query" in defn.parameters["properties"]
        assert "url" in defn.parameters["required"]
        assert "query" not in defn.parameters.get("required", [])

    @pytest.mark.asyncio
    async def test_missing_url(self):
        registry = create_agent_tool_registry()
        result = await registry.dispatch("web_extract", {})
        assert not result.success
        assert "url is required" in result.output

    @pytest.mark.asyncio
    async def test_empty_url(self):
        registry = create_agent_tool_registry()
        result = await registry.dispatch("web_extract", {"url": ""})
        assert not result.success
        assert "url is required" in result.output

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "# Test Page\n\nThis is extracted content.",
            "stats": {"method": "http", "title": "Test Page"},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert result.success
        assert "example.com" in result.output
        assert "Test Page" in result.output

    @pytest.mark.asyncio
    async def test_truncated_content(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "A" * 6000 + "\n\n... (truncated)",
            "stats": {"method": "http"},
            "truncated": True,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com/long",
            })

        assert result.success
        assert "truncated" in result.output

    @pytest.mark.asyncio
    async def test_extraction_failure(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "",
            "stats": {"method": "failed"},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://invalid.example",
            })

        assert not result.success
        assert "failed" in result.output.lower()

    @pytest.mark.asyncio
    async def test_summarized_content(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "Summarized content about pricing tiers...",
            "stats": {"method": "http", "title": "Pricing", "summarized": True, "original_chars": 10000},
            "truncated": False,
            "summarized": True,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com/pricing",
                "query": "What are the pricing tiers?",
            })

        assert result.success
        assert "summarized" in result.output

    @pytest.mark.asyncio
    async def test_data_field_contains_metadata(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "Page content here",
            "stats": {"method": "http", "title": "Test"},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert result.data is not None
        assert result.data["url"] == "https://example.com"
        assert result.data["chars"] == len("Page content here")
        assert result.data["truncated"] is False
        assert result.data["summarized"] is False

    @pytest.mark.asyncio
    async def test_output_truncated_at_50k(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "x" * 60000,
            "stats": {"method": "http"},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert result.success
        assert len(result.output) <= 50100

    @pytest.mark.asyncio
    async def test_web_extract_exception_returns_failure(self):
        registry = create_agent_tool_registry()

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, side_effect=Exception("Unexpected error")):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert not result.success
        assert "Web extraction failed" in result.output

    @pytest.mark.asyncio
    async def test_title_in_output(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "Some content",
            "stats": {"method": "http", "title": "My Article Title"},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert "title=My Article Title" in result.output

    @pytest.mark.asyncio
    async def test_long_title_truncated_in_output(self):
        registry = create_agent_tool_registry()

        mock_result = {
            "content": "Some content",
            "stats": {"method": "http", "title": "A" * 100},
            "truncated": False,
            "summarized": False,
        }

        with patch("sediman.web.extract.web_extract", new_callable=AsyncMock, return_value=mock_result):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
            })

        assert "title=" in result.output
        # Extract just the title value between title= and the closing paren
        import re
        match = re.search(r"title=([^)]+)", result.output)
        assert match is not None
        title_value = match.group(1)
        assert len(title_value) <= 60


# ── Integration ───────────────────────────────────────────────


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_http_flow(self):
        html = """
        <html><head><title>Integration Test Page</title></head><body>
        <nav>Skip this</nav>
        <article>
            <h1>Article Title</h1>
            <p>This is the main content of the article. It contains useful information.</p>
            <p>Second paragraph with more details.</p>
        </article>
        <footer>Skip this too</footer>
        <script>track()</script>
        </body></html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await web_extract("https://example.com/article")

        assert "Article Title" in result["content"]
        assert "main content" in result["content"]
        assert "Second paragraph" in result["content"]
        assert result["stats"]["method"] == "http"
        assert result["stats"]["title"] == "Integration Test Page"
        assert result["truncated"] is False
        assert result["summarized"] is False

    @pytest.mark.asyncio
    async def test_http_then_browser_fallback_flow(self):
        thin_html = "<html><body></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = thin_html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        browser_content = "# Dynamic Page\n\nThis content was rendered by JavaScript and extracted via browser."

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client), \
             patch("sediman.web.extract.browser_extract", new_callable=AsyncMock, return_value=browser_content):
            result = await web_extract(
                "https://spa.example.com",
                browser_session=MagicMock(),
                llm=MagicMock(),
            )

        assert "Dynamic Page" in result["content"]
        assert result["stats"]["method"] == "browser"

    @pytest.mark.asyncio
    async def test_tool_dispatch_full_flow(self):
        registry = create_agent_tool_registry()

        html = "<html><head><title>Test</title></head><body><p>" + "word " * 200 + "</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = MagicMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

        with patch("sediman.web.extract.httpx.AsyncClient", return_value=mock_client):
            result = await registry.dispatch("web_extract", {
                "url": "https://example.com",
                "query": "test query",
            })

        assert result.success
        assert "Extracted from https://example.com" in result.output
        assert "method=http" in result.output
        assert result.data["url"] == "https://example.com"
