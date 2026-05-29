from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import structlog

from sediman.agent.tool_dispatch import ToolRegistry, ToolLoop, ToolResult
from sediman.llm.provider import LLMProvider, ToolDefinition
from sediman.openbrowser.client import OpenBrowserClient

logger = structlog.get_logger()

_SYSTEM_PROMPT = """You are Sediman's browser agent using OpenBrowser — a headless semantic browser.
You interact with web pages through structured semantic trees and numbered element IDs.

## How it works

1. Navigate to a URL with `open_navigate`
2. Get the page state with `open_snapshot` — this returns a semantic tree with numbered interactive elements like [#1], [#2], etc.
3. Interact with elements using their IDs: `open_click`, `open_type`, `open_submit`
4. Scroll with `open_scroll`, then snapshot again to see more content
5. When done, respond with your final answer

## Rules
- Always snapshot after navigating or clicking to see what changed
- Use element IDs from the snapshot (e.g. click element [#3])
- Be concise — snapshots can be large, so extract only what you need
- If a page requires JavaScript rendering and looks empty, note that OpenBrowser may not render it fully
- Never guess element IDs — always get a fresh snapshot first
"""


@dataclass
class BrowserResult:
    text: str
    actions: list[dict[str, Any]]


class OpenBrowserSubagent:
    """Browser subagent that uses OpenBrowser's REST API with LLM tool calling.

    Instead of BrowserUse's Agent (which wraps Playwright/Chromium), this uses
    Sediman's own ToolLoop to drive the browser via the open-browser REST API.
    """

    def __init__(
        self,
        client: OpenBrowserClient,
        llm_provider: LLMProvider,
        max_steps: int = 20,
        on_browser_step: Callable[[str, str], None] | None = None,
        conversation: list[dict[str, str]] | None = None,
        memory_context: str | None = None,
    ):
        self.client = client
        self.llm = llm_provider
        self.max_steps = max_steps
        self._on_step = on_browser_step
        self._conversation = conversation or []
        self._memory_context = memory_context

    async def run(
        self,
        task: str,
        skill_summaries: str | None = None,
    ) -> BrowserResult:
        registry = self._build_tool_registry()
        tool_loop = ToolLoop(
            llm=self.llm,
            registry=registry,
            max_rounds=self.max_steps,
            original_task=task,
        )

        system = _SYSTEM_PROMPT
        if self._memory_context:
            system += f"\n\n<user_context>\n{self._memory_context}\n</user_context>"
        if skill_summaries:
            system += f"\n\n<available_skills>\n{skill_summaries}\n</available_skills>"
        if self._conversation:
            from sediman.utils import format_conversation_context

            ctx = format_conversation_context(self._conversation, limit=6)
            system += (
                f"\n\n<conversation_context>\n{ctx}\n</conversation_context>"
            )

        messages = [{"role": "user", "content": task}]
        result = await tool_loop.run(messages, system=system)

        actions = []
        for _name, _args in tool_loop._history if hasattr(tool_loop, "_history") else []:
            actions.append({"action": _name, "arguments": _args})

        text = (result.text or "").strip()
        if not text:
            text = "Task completed but no explicit result was returned."

        return BrowserResult(text=text, actions=actions)

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        client = self.client
        on_step = self._on_step

        def _emit(action: str, detail: str) -> None:
            if on_step:
                on_step(action, detail)

        async def _navigate(url: str, **kwargs: Any) -> ToolResult:
            _emit("navigate", url)
            result = await client.navigate(url)
            if result.get("ok") is False:
                return ToolResult(success=False, output=f"Navigation failed: {result.get('error')}")
            page = await client.current_page()
            url_out = page.get("url", url)
            title = page.get("title", "")
            return ToolResult(
                success=True,
                output=f"Navigated to {url_out}\nTitle: {title}",
            )

        async def _snapshot(**kwargs: Any) -> ToolResult:
            tree = await client.semantic_tree()
            elements = await client.interactive_elements()
            page = await client.current_page()
            url = page.get("url", "")
            title = page.get("title", "")

            md_tree = _format_tree(tree)
            elem_list = _format_elements(elements)

            output = f"URL: {url}\nTitle: {title}\n\n"
            if md_tree:
                output += f"Semantic Tree:\n{md_tree}\n\n"
            if elem_list:
                output += f"Interactive Elements:\n{elem_list}"
            else:
                output += "No interactive elements found."

            _emit("snapshot", url)
            return ToolResult(success=True, output=output)

        async def _click(element_id: int, **kwargs: Any) -> ToolResult:
            _emit("click", f"element [{element_id}]")
            result = await client.click(element_id=element_id)
            if result.get("ok") is False:
                return ToolResult(success=False, output=f"Click failed: {result.get('error')}")
            page = await client.current_page()
            new_url = page.get("url", "")
            return ToolResult(success=True, output=f"Clicked element [{element_id}]. Current URL: {new_url}")

        async def _type(element_id: int, text: str, submit: bool = False, **kwargs: Any) -> ToolResult:
            _emit("type", f"[{element_id}] '{text[:50]}'")
            result = await client.type_text(value=text, element_id=element_id)
            if result.get("ok") is False:
                return ToolResult(success=False, output=f"Type failed: {result.get('error')}")
            if submit:
                await _click(element_id)
            return ToolResult(success=True, output=f"Typed '{text[:80]}' into element [{element_id}]")

        async def _submit(form_selector: str, fields: dict[str, str] | None = None, **kwargs: Any) -> ToolResult:
            _emit("submit", form_selector)
            result = await client.submit(form_selector, fields=fields)
            if result.get("ok") is False:
                return ToolResult(success=False, output=f"Submit failed: {result.get('error')}")
            page = await client.current_page()
            return ToolResult(success=True, output=f"Submitted form '{form_selector}'. URL: {page.get('url', '')}")

        async def _scroll(direction: str = "down", **kwargs: Any) -> ToolResult:
            _emit("scroll", direction)
            result = await client.scroll(direction)
            if result.get("ok") is False:
                return ToolResult(success=False, output=f"Scroll failed: {result.get('error')}")
            return ToolResult(success=True, output=f"Scrolled {direction}")

        async def _extract_text(selector: str | None = None, **kwargs: Any) -> ToolResult:
            _emit("extract", selector or "full")
            html_result = await client.html()
            html = html_result.get("html", "")
            if selector:
                elements_result = await client.interactive_elements()
                elements = elements_result.get("elements", [])
                matches = [e for e in elements if selector in e.get("selector", "")]
                text = "\n".join(e.get("text", "") for e in matches if e.get("text"))
                return ToolResult(success=True, output=text or f"No matches for '{selector}'")
            return ToolResult(success=True, output=html[:10000] if html else "(empty page)")

        async def _get_url(**kwargs: Any) -> ToolResult:
            page = await client.current_page()
            return ToolResult(success=True, output=page.get("url", ""))

        async def _get_cookies(**kwargs: Any) -> ToolResult:
            result = await client.get_cookies()
            cookies = result.get("cookies", [])
            lines = [f"  {c.get('name', '')}={c.get('value', '')[:50]} ({c.get('domain', '')})" for c in cookies]
            return ToolResult(success=True, output="\n".join(lines) or "No cookies")

        async def _set_cookie(name: str, value: str, domain: str, path: str = "/", **kwargs: Any) -> ToolResult:
            await client.set_cookie(name=name, value=value, domain=domain, path=path)
            return ToolResult(success=True, output=f"Cookie '{name}' set for {domain}")

        registry.register(
            ToolDefinition(
                name="open_navigate",
                description="Navigate to a URL. Always call this first.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to navigate to"},
                    },
                    "required": ["url"],
                },
            ),
            _navigate,
        )

        registry.register(
            ToolDefinition(
                name="open_snapshot",
                description="Get the current page's semantic tree and interactive elements with numbered IDs. Call after every navigation or click to see what's on the page.",
                parameters={"type": "object", "properties": {}},
            ),
            _snapshot,
        )

        registry.register(
            ToolDefinition(
                name="open_click",
                description="Click an interactive element by its element ID (from open_snapshot).",
                parameters={
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "integer", "description": "Element ID to click (e.g. 1 for [#1]"},
                    },
                    "required": ["element_id"],
                },
            ),
            _click,
        )

        registry.register(
            ToolDefinition(
                name="open_type",
                description="Type text into an input element by its element ID.",
                parameters={
                    "type": "object",
                    "properties": {
                        "element_id": {"type": "integer", "description": "Element ID to type into"},
                        "text": {"type": "string", "description": "Text to type"},
                        "submit": {"type": "boolean", "description": "If true, click the element after typing (e.g. for search)", "default": False},
                    },
                    "required": ["element_id", "text"],
                },
            ),
            _type,
        )

        registry.register(
            ToolDefinition(
                name="open_submit",
                description="Submit a form by its CSS selector with field values.",
                parameters={
                    "type": "object",
                    "properties": {
                        "form_selector": {"type": "string", "description": "CSS selector for the form"},
                        "fields": {
                            "type": "object",
                            "description": "Field name-value pairs",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                    "required": ["form_selector"],
                },
            ),
            _submit,
        )

        registry.register(
            ToolDefinition(
                name="open_scroll",
                description="Scroll the page.",
                parameters={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["down", "up"],
                            "default": "down",
                            "description": "Scroll direction",
                        },
                    },
                },
            ),
            _scroll,
        )

        registry.register(
            ToolDefinition(
                name="open_extract_text",
                description="Extract text from the current page. Optionally filter by CSS selector.",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "Optional CSS selector to filter elements"},
                    },
                },
            ),
            _extract_text,
        )

        registry.register(
            ToolDefinition(
                name="open_get_url",
                description="Get the current page URL.",
                parameters={"type": "object", "properties": {}},
            ),
            _get_url,
        )

        registry.register(
            ToolDefinition(
                name="open_get_cookies",
                description="Get all cookies for the current session.",
                parameters={"type": "object", "properties": {}},
            ),
            _get_cookies,
        )

        registry.register(
            ToolDefinition(
                name="open_set_cookie",
                description="Set a cookie.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "domain": {"type": "string"},
                        "path": {"type": "string", "default": "/"},
                    },
                    "required": ["name", "value", "domain"],
                },
            ),
            _set_cookie,
        )

        return registry


def _format_tree(tree_data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    _walk_tree(tree_data, lines, indent)
    return "\n".join(lines)


def _walk_tree(node: dict[str, Any], lines: list[str], indent: int) -> None:
    role = node.get("role", "")
    text = node.get("text", "") or node.get("label", "")
    tag = node.get("tag", node.get("tag_name", ""))
    element_id = node.get("element_id") or node.get("id")
    action = node.get("action", "")
    href = node.get("href", "")

    prefix = "  " * indent
    parts: list[str] = []

    if role:
        parts.append(role)
    elif tag:
        parts.append(tag)

    if element_id is not None:
        parts.append(f"[#{element_id}]")

    if text:
        parts.append(f'"{text[:80]}"')

    if action:
        parts.append(f"({action})")

    if href:
        parts.append(f"→ {href[:80]}")

    if parts:
        lines.append(f"{prefix}{' '.join(parts)}")

    for child in node.get("children", []):
        _walk_tree(child, lines, indent + 1)


def _format_elements(elements_data: dict[str, Any]) -> str:
    elements = elements_data.get("elements", [])
    if not elements:
        return ""
    lines: list[str] = []
    for e in elements:
        eid = e.get("element_id") or e.get("id", "?")
        tag = e.get("tag", "")
        text = e.get("text", "") or e.get("label", "")
        action = e.get("action", "")
        selector = e.get("selector", "")
        parts = [f"[#{eid}] {tag}"]
        if text:
            parts.append(f'"{text[:60]}"')
        if action:
            parts.append(f"({action})")
        if selector:
            parts.append(f"selector={selector[:40]}")
        lines.append("  " + " ".join(parts))
    return "\n".join(lines)
