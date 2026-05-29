from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Callable

import structlog

from sediman.browser.controller import (
    BrowserController,
    ElementInfo,
    PageSnapshot,
)
from sediman.openbrowser.client import OpenBrowserClient

logger = structlog.get_logger()


class OpenBrowserController(BrowserController):
    """BrowserController that delegates to the open-browser REST API.

    Inherits the interface from BrowserController but overrides every method
    to call the open-browser server instead of using Playwright directly.
    """

    def __init__(
        self,
        client: OpenBrowserClient,
        on_step: Callable[[str, str], None] | None = None,
    ):
        self._client = client
        self._on_step = on_step
        self._current_url: str = ""
        self._current_title: str = ""
        self._started = False
        self._page_provider: Callable[[], Any] | None = None

    def set_page_provider(self, provider: Callable[[], Any]) -> None:
        self._page_provider = provider

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def _page(self) -> Any:
        return None

    @_page.setter
    def _page(self, value: Any) -> None:
        pass

    async def start(self) -> None:
        if self._started:
            return
        healthy = await self._client.health()
        if not healthy:
            raise RuntimeError("open-browser server is not healthy")
        self._started = True
        logger.info("openbrowser_controller_started")

    async def stop(self) -> None:
        await self._client.close()
        self._started = False
        logger.info("openbrowser_controller_stopped")

    async def navigate(self, url: str) -> str:
        result = await self._client.navigate(url)
        if result.get("ok") is False:
            return f"Failed to navigate to {url}: {result.get('error', 'unknown')}"
        page = await self._client.current_page()
        self._current_url = page.get("url", url)
        self._current_title = page.get("title", "")
        self._emit_step("navigate", self._current_url)
        return f"Navigated to {self._current_url} (title: {self._current_title})"

    async def click(self, ref_id: int) -> str:
        result = await self._client.click(element_id=ref_id)
        if result.get("ok") is False:
            return f"Click failed for element [{ref_id}]: {result.get('error', 'unknown')}"
        page = await self._client.current_page()
        self._current_url = page.get("url", self._current_url)
        self._emit_step("click", f"element [{ref_id}] → {self._current_url}")
        return f"Clicked element [{ref_id}]"

    async def type_text(self, ref_id: int, text: str, submit: bool = False) -> str:
        result = await self._client.type_text(value=text, element_id=ref_id)
        if result.get("ok") is False:
            return f"Type failed for element [{ref_id}]: {result.get('error', 'unknown')}"
        self._emit_step("type", f"[{ref_id}] '{text[:50]}'")
        if submit:
            await asyncio.sleep(0.3)
            page = await self._client.current_page()
            self._current_url = page.get("url", self._current_url)
        return f"Typed '{text[:50]}' into element [{ref_id}]"

    async def scroll(self, direction: str = "down", amount: int = 300) -> str:
        result = await self._client.scroll(direction)
        if result.get("ok") is False:
            return f"Scroll failed: {result.get('error', 'unknown')}"
        self._emit_step("scroll", direction)
        return f"Scrolled {direction}"

    async def press_key(self, key: str) -> str:
        return f"Key press not supported by open-browser (key: {key})"

    async def go_back(self) -> str:
        return "Back navigation not yet supported by open-browser"

    async def go_forward(self) -> str:
        return "Forward navigation not yet supported by open-browser"

    async def refresh(self) -> str:
        result = await self._client.reload()
        if result.get("ok") is False:
            return f"Refresh failed: {result.get('error', 'unknown')}"
        page = await self._client.current_page()
        self._current_url = page.get("url", self._current_url)
        self._emit_step("refresh", self._current_url)
        return f"Refreshed {self._current_url}"

    async def screenshot(self) -> str | None:
        return None

    async def get_url(self) -> str:
        page = await self._client.current_page()
        return page.get("url", self._current_url)

    async def get_title(self) -> str:
        page = await self._client.current_page()
        return page.get("title", self._current_title)

    async def snapshot(self) -> PageSnapshot:
        tree = await self._client.semantic_tree()
        elements = self._parse_semantic_elements(tree)

        page = await self._client.current_page()
        url = page.get("url", self._current_url)
        title = page.get("title", self._current_title)

        text_preview = ""
        try:
            html_result = await self._client.html()
            text_preview = html_result.get("html", "")[:2000]
        except Exception:
            pass

        return PageSnapshot(
            url=url,
            title=title,
            elements=elements,
            text_preview=text_preview,
        )

    async def extract_text(self) -> str:
        html_result = await self._client.html()
        return html_result.get("html", "")

    async def extract_by_selector(self, selector: str) -> str:
        elements_result = await self._client.interactive_elements()
        elements = elements_result.get("elements", [])
        matches = [
            e for e in elements
            if selector in e.get("selector", "") or selector in e.get("tag", "")
        ]
        if not matches:
            return ""
        return "\n".join(
            e.get("text", "") or e.get("label", "") or str(e)
            for e in matches
        )

    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> str:
        import asyncio

        deadline = asyncio.get_event_loop().time() + timeout / 1000.0
        while asyncio.get_event_loop().time() < deadline:
            elements_result = await self._client.interactive_elements()
            elements = elements_result.get("elements", [])
            for e in elements:
                e_selector = e.get("selector", "")
                if selector in e_selector:
                    return f"Element '{selector}' found."
            await asyncio.sleep(0.5)
        return f"Wait timed out for '{selector}'"

    def _parse_semantic_elements(self, tree_data: dict[str, Any]) -> list[ElementInfo]:
        elements: list[ElementInfo] = []
        self._walk_tree(tree_data, elements)
        return elements

    def _walk_tree(self, node: dict[str, Any], elements: list[ElementInfo]) -> None:
        role = node.get("role", "")
        tag = node.get("tag", node.get("tag_name", ""))
        text = node.get("text", "") or node.get("label", "")
        element_id = node.get("element_id") or node.get("id")
        action = node.get("action", "")
        href = node.get("href", "")

        is_interactive = action in (
            "navigate", "click", "fill", "toggle", "select", "submit",
        ) or role in (
            "link", "button", "textbox", "combobox", "checkbox", "radio",
            "search", "form",
        )

        if is_interactive and element_id is not None:
            info = ElementInfo(
                ref_id=int(element_id),
                tag=tag,
                text=text[:200],
                role=role,
                href=href,
                aria_label=node.get("aria_label", ""),
                placeholder=node.get("placeholder", ""),
            )
            elements.append(info)

        for child in node.get("children", []):
            self._walk_tree(child, elements)

    def _emit_step(self, action: str, detail: str) -> None:
        if self._on_step:
            try:
                self._on_step(action, detail)
            except Exception:
                pass
