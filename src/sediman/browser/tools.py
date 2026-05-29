from __future__ import annotations

from typing import Any

import structlog

from sediman.agent.tool_dispatch import ToolRegistry, ToolResult
from sediman.browser.controller import BrowserController, format_snapshot
from sediman.llm.provider import ToolDefinition

logger = structlog.get_logger()

_DEFAULT_CONTROLLER: BrowserController | None = None


def get_default_browser_controller() -> BrowserController | None:
    return _DEFAULT_CONTROLLER


def set_default_browser_controller(controller: BrowserController | None) -> None:
    global _DEFAULT_CONTROLLER
    _DEFAULT_CONTROLLER = controller


async def _handle_browser_navigate(url: str, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        await ctrl.start()
    result = await ctrl.navigate(url)
    return ToolResult(success="Failed" not in result, output=result)


async def _handle_browser_click(ref_id: int, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started. Call browser_navigate first.")
    result = await ctrl.click(ref_id)
    return ToolResult(success="not found" not in result.lower(), output=result)


async def _handle_browser_type(ref_id: int, text: str, submit: bool = False, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started. Call browser_navigate first.")
    result = await ctrl.type_text(ref_id, text, submit=submit)
    return ToolResult(success="not found" not in result.lower(), output=result)


async def _handle_browser_scroll(direction: str = "down", amount: int = 300, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.scroll(direction, amount)
    return ToolResult(success="Failed" not in result, output=result)


async def _handle_browser_press_key(key: str, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.press_key(key)
    return ToolResult(success="failed" not in result.lower(), output=result)


async def _handle_browser_go_back(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.go_back()
    return ToolResult(success="failed" not in result.lower(), output=result)


async def _handle_browser_go_forward(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.go_forward()
    return ToolResult(success="failed" not in result.lower(), output=result)


async def _handle_browser_screenshot(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    b64 = await ctrl.screenshot()
    if b64:
        return ToolResult(
            success=True,
            output=f"Screenshot captured ({len(b64)} chars base64).",
            data={"screenshot_base64": b64},
        )
    return ToolResult(success=False, output="Screenshot failed.")


async def _handle_browser_snapshot(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started. Call browser_navigate first.")
    snapshot = await ctrl.snapshot()
    formatted = format_snapshot(snapshot)
    return ToolResult(
        success=True,
        output=formatted,
        data={"url": snapshot.url, "title": snapshot.title, "element_count": len(snapshot.elements)},
    )


async def _handle_browser_extract(selector: str | None = None, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    if selector:
        text = await ctrl.extract_by_selector(selector)
    else:
        text = await ctrl.extract_text()
    return ToolResult(
        success=True,
        output=text[:5000] if text else "(no text found)",
        data={"length": len(text) if text else 0},
    )


async def _handle_browser_get_url(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    url = await ctrl.get_url()
    return ToolResult(success=True, output=url)


async def _handle_browser_refresh(**kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.refresh()
    return ToolResult(success="failed" not in result.lower(), output=result)


async def _handle_browser_wait_for_selector(selector: str, timeout: int = 5000, **kwargs: Any) -> ToolResult:
    ctrl = get_default_browser_controller()
    if not ctrl:
        return ToolResult(success=False, output="Browser controller not initialized.")
    if not ctrl.is_started:
        return ToolResult(success=False, output="Browser not started.")
    result = await ctrl.wait_for_selector(selector, timeout=timeout)
    return ToolResult(success="timed out" not in result.lower(), output=result)


def register_browser_tools(registry: ToolRegistry) -> None:
    """Register all browser tools into the given ToolRegistry."""

    registry.register(
        ToolDefinition(
            name="browser_navigate",
            description="Navigate the browser to a URL. Always call this first before interacting with a page.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to (e.g. https://example.com)"},
                },
                "required": ["url"],
            },
        ),
        _handle_browser_navigate,
    )

    registry.register(
        ToolDefinition(
            name="browser_snapshot",
            description="Get a structured snapshot of the current page showing all interactive elements with ref IDs. Use this to understand what's on the page before clicking or typing.",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_snapshot,
    )

    registry.register(
        ToolDefinition(
            name="browser_click",
            description="Click an element by its ref_id (from browser_snapshot).",
            parameters={
                "type": "object",
                "properties": {
                    "ref_id": {"type": "integer", "description": "The ref_id of the element to click"},
                },
                "required": ["ref_id"],
            },
        ),
        _handle_browser_click,
    )

    registry.register(
        ToolDefinition(
            name="browser_type",
            description="Type text into an input/textarea element by its ref_id.",
            parameters={
                "type": "object",
                "properties": {
                    "ref_id": {"type": "integer", "description": "The ref_id of the input element"},
                    "text": {"type": "string", "description": "The text to type"},
                    "submit": {"type": "boolean", "description": "If true, press Enter after typing", "default": False},
                },
                "required": ["ref_id", "text"],
            },
        ),
        _handle_browser_type,
    )

    registry.register(
        ToolDefinition(
            name="browser_scroll",
            description="Scroll the page.",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down", "up", "bottom", "top"], "default": "down"},
                    "amount": {"type": "integer", "description": "Pixels to scroll (for down/up)", "default": 300},
                },
            },
        ),
        _handle_browser_scroll,
    )

    registry.register(
        ToolDefinition(
            name="browser_press_key",
            description="Press a keyboard key (e.g. Enter, Escape, Tab, ArrowDown).",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "The key to press"},
                },
                "required": ["key"],
            },
        ),
        _handle_browser_press_key,
    )

    registry.register(
        ToolDefinition(
            name="browser_go_back",
            description="Go back to the previous page in browser history.",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_go_back,
    )

    registry.register(
        ToolDefinition(
            name="browser_go_forward",
            description="Go forward in browser history.",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_go_forward,
    )

    registry.register(
        ToolDefinition(
            name="browser_screenshot",
            description="Take a screenshot of the current page. Returns base64 JPEG. Use sparingly — only when visual context is needed (e.g. to understand layout, read charts, or verify rendering).",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_screenshot,
    )

    registry.register(
        ToolDefinition(
            name="browser_extract",
            description="Extract text from the current page. Optionally pass a CSS selector to extract only matching elements.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Optional CSS selector (e.g. 'article', '.price', 'h1')"},
                },
            },
        ),
        _handle_browser_extract,
    )

    registry.register(
        ToolDefinition(
            name="browser_get_url",
            description="Get the current page URL.",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_get_url,
    )

    registry.register(
        ToolDefinition(
            name="browser_refresh",
            description="Refresh the current page.",
            parameters={"type": "object", "properties": {}},
        ),
        _handle_browser_refresh,
    )

    registry.register(
        ToolDefinition(
            name="browser_wait_for_selector",
            description="Wait for an element matching a CSS selector to appear on the page.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for"},
                    "timeout": {"type": "integer", "description": "Timeout in ms (default 5000)", "default": 5000},
                },
                "required": ["selector"],
            },
        ),
        _handle_browser_wait_for_selector,
    )

    logger.info("browser_tools_registered", count=14)
