from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from markdownify import markdownify as md
from readability import Document

if TYPE_CHECKING:
    from sediman.browser.session import BrowserSession
    from sediman.llm.provider import LLMProvider

from sediman.config import DEFAULT_HTTP_TIMEOUT as _HTTP_TIMEOUT, DEFAULT_WEB_MAX_CHARS as _DEFAULT_MAX_CHARS

logger = structlog.get_logger()
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_shared_client: httpx.AsyncClient | None = None
_url_cache: dict[str, tuple[str, dict[str, Any], float]] = {}
_URL_CACHE_TTL = 300
_URL_CACHE_MAX = 50


def clear_url_cache() -> None:
    _url_cache.clear()


async def http_extract(url: str) -> tuple[str, dict[str, Any]]:
    """Fast HTTP extraction: httpx fetch -> readability -> markdownify.

    Returns (markdown_content, stats_dict).
    """
    cached = _url_cache.get(url)
    if cached and (time.time() - cached[2]) < _URL_CACHE_TTL:
        stats = dict(cached[1])
        stats["cached"] = True
        return cached[0], stats

    if len(_url_cache) > _URL_CACHE_MAX:
        oldest_key = min(_url_cache, key=lambda k: _url_cache[k][2])
        del _url_cache[oldest_key]

    stats: dict[str, Any] = {"method": "http", "url": url}

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        last_exc: Exception | None = None
        response = None
        for attempt in range(3):
            try:
                response = await client.get(url)
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 502, 503, 504) and attempt < 2:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    last_exc = e
                    continue
                raise
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    last_exc = e
                    continue
                raise

    if response is None and last_exc is not None:
        raise last_exc

    stats["status_code"] = response.status_code
    stats["content_type"] = response.headers.get("content-type", "")

    html = response.text
    stats["html_chars"] = len(html)

    doc = Document(html)
    title = doc.title() or ""
    summary_html = doc.summary()

    summary_html = _strip_tags(summary_html, ["script", "style", "noscript", "iframe"])

    markdown = md(
        summary_html,
        heading_style="ATX",
        bullets="-",
        code_language="",
        escape_asterisks=False,
        escape_underscores=False,
        escape_misc=False,
        autolinks=False,
        default_title=False,
    )

    markdown = _clean_markdown(markdown)

    if title and not markdown.startswith(f"# {title}"):
        markdown = f"# {title}\n\n{markdown}"

    stats["markdown_chars"] = len(markdown)
    stats["title"] = title

    _url_cache[url] = (markdown, dict(stats), time.time())

    return markdown, stats


def _strip_tags(html: str, tags: list[str]) -> str:
    """Remove specific HTML tags and their content."""
    for tag in tags:
        html = re.sub(
            rf"<{tag}[\s>].*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE
        )
    return html


def _clean_markdown(text: str) -> str:
    """Light cleanup of markdown output."""
    text = re.sub(r"%[0-9A-Fa-f]{2}", "", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped
            and (stripped.startswith("{") or stripped.startswith("["))
            and len(stripped) > 200
        ):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    return text.strip()


async def browser_extract(
    url: str,
    browser_session: BrowserSession,
    llm: LLMProvider,
) -> str | None:
    """Fallback extraction using Browser Use's built-in extract via the browser.

    Navigates to the URL, then uses the browser agent to extract content.
    Returns markdown content or None on failure.
    """
    try:
        from sediman.browser.session import run_browser_task

        task = (
            f"Navigate to {url} and extract ALL text content from the page as clean markdown. "
            f"Include headings, paragraphs, lists, and tables. "
            f"Output the raw content only — no commentary."
        )

        result_text, _ = await run_browser_task(
            task=task,
            browser_session=browser_session,
            llm=llm.get_browser_use_llm(),
            max_steps=5,
            flash_mode=True,
        )

        if result_text and len(result_text.strip()) > 50:
            return result_text.strip()
        return None
    except Exception as e:
        logger.debug("browser_extract_failed", url=url, error=str(e))
        return None


async def web_extract(
    url: str,
    query: str | None = None,
    browser_session: BrowserSession | None = None,
    llm: LLMProvider | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Extract web page content to clean markdown.

    Strategy:
      1. Try fast HTTP extraction (httpx + readability + markdownify)
      2. If content is too thin, fall back to browser extraction
      3. If query provided and content > max_chars, LLM-summarize

    Returns dict with keys: content, stats, truncated, summarized.
    """
    result: dict[str, Any] = {
        "content": "",
        "stats": {},
        "truncated": False,
        "summarized": False,
    }

    # ── Step 1: Try HTTP extraction ───────────────────────────
    try:
        markdown, stats = await http_extract(url)
        result["stats"] = stats

        if len(markdown.strip()) > 100:
            result["content"] = markdown
        else:
            logger.info("http_extract_thin", url=url, chars=len(markdown.strip()))
    except Exception as e:
        logger.info("http_extract_failed", url=url, error=str(e))

    # ── Step 2: Browser fallback if HTTP was too thin ─────────
    if not result["content"] and browser_session and llm:
        logger.info("trying_browser_fallback", url=url)
        browser_content = await browser_extract(url, browser_session, llm)
        if browser_content:
            result["content"] = browser_content
            result["stats"]["method"] = "browser"

    if not result["content"]:
        result["content"] = (
            f"Could not extract content from {url}. "
            f"The page may require JavaScript rendering, authentication, or be unavailable."
        )
        result["stats"]["method"] = "failed"
        return result

    # ── Step 3: Truncation / LLM summarization ────────────────
    content = result["content"]
    if len(content) > max_chars:
        if query and llm:
            summarized = await _summarize_with_llm(content, query, llm, max_chars)
            if summarized:
                result["content"] = summarized
                result["summarized"] = True
                result["stats"]["summarized"] = True
                result["stats"]["original_chars"] = len(content)
            else:
                result["content"] = content[:max_chars] + "\n\n... (truncated)"
                result["truncated"] = True
                result["stats"]["truncated"] = True
        else:
            result["content"] = content[:max_chars] + "\n\n... (truncated)"
            result["truncated"] = True
            result["stats"]["truncated"] = True

    return result


async def _summarize_with_llm(
    content: str,
    query: str,
    llm: LLMProvider,
    max_chars: int,
) -> str | None:
    """Use LLM to summarize large page content focused on a query."""
    try:
        from sediman.llm.provider import LLMResponse

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a web content extractor. Given a web page's markdown content "
                    "and a user query, extract and summarize the information relevant to the query. "
                    "Be concise but complete. Output raw information only — no preamble or commentary."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Query: {query}\n\n"
                    f"Web page content:\n{content[:30000]}\n\n"
                    f"Extract information relevant to the query above. "
                    f"Keep it under {max_chars} characters."
                ),
            },
        ]

        response: LLMResponse = await llm.chat(messages=messages, tools=[])

        if response.text and len(response.text.strip()) > 50:
            return response.text.strip()
        return None
    except Exception as e:
        logger.debug("llm_summarize_failed", error=str(e))
        return None
