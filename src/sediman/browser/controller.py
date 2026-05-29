from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable

import structlog

try:
    import playwright.async_api as _pw_api
except ImportError:
    import types
    _pw_api = types.ModuleType("playwright.async_api")

from sediman.config import DATA_DIR

logger = structlog.get_logger()


@dataclass
class ElementInfo:
    ref_id: int
    tag: str
    text: str = ""
    role: str = ""
    placeholder: str = ""
    href: str = ""
    src: str = ""
    alt: str = ""
    type: str = ""
    value: str = ""
    aria_label: str = ""
    title: str = ""
    is_visible: bool = True
    bounding_box: dict[str, float] | None = None
    children: list[ElementInfo] = field(default_factory=list)


@dataclass
class PageSnapshot:
    url: str
    title: str
    elements: list[ElementInfo]
    text_preview: str = ""
    scroll_position: dict[str, int] | None = None


class BrowserController:
    """Thin Playwright-based browser controller.

    Exposes discrete browser actions as tools instead of a monolithic agent.
    Can use its own Playwright instance or operate on an externally-provided page.
    """

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str | None = None,
        on_step: Callable[[str, str], None] | None = None,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir or str(DATA_DIR / "browser-profile")
        self._playwright: Any = None
        self._own_browser: Any = None
        self._context: Any = None
        self._own_page: Any = None
        self._started = False
        self._start_lock = asyncio.Lock()
        self._on_step = on_step
        self._element_counter = 0
        self._page_provider: Callable[[], Any] | None = None

    def set_page_provider(self, provider: Callable[[], Any]) -> None:
        self._page_provider = provider

    @property
    def _page(self) -> Any:
        if self._page_provider:
            try:
                return self._page_provider()
            except Exception:
                pass
        return self._own_page

    @_page.setter
    def _page(self, value: Any) -> None:
        self._own_page = value

    @property
    def is_started(self) -> bool:
        if self._page_provider:
            try:
                return self._page_provider() is not None
            except Exception:
                return False
        return self._started and self._own_page is not None

    async def start(self) -> None:
        if self._page_provider:
            return
        async with self._start_lock:
            if self._started:
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._own_browser = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
                viewport={"width": 1280, "height": 720},
            )
            pages = self._own_browser.pages
            self._own_page = pages[0] if pages else await self._own_browser.new_page()
            self._started = True
            logger.info(
                "browser_controller_started",
                headless=self.headless,
                page_count=len(pages),
            )

    async def stop(self) -> None:
        if self._own_browser:
            try:
                await self._own_browser.close()
            except Exception as e:
                logger.debug("browser_close_failed", error=str(e))
            self._own_browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("playwright_stop_failed", error=str(e))
            self._playwright = None
        self._own_page = None
        self._started = False
        logger.info("browser_controller_stopped")

    # ── Core Actions ───────────────────────────────────────

    async def navigate(self, url: str) -> str:
        if not self._page:
            return "Browser not started."
        try:
            response = await self._page.goto(url, wait_until="networkidle", timeout=30000)
            final_url = self._page.url
            status = response.status if response else "unknown"
            self._emit_step("navigate", f"{final_url} (status: {status})")
            return f"Navigated to {final_url} (HTTP {status})"
        except Exception as e:
            logger.warning("navigate_failed", url=url, error=str(e))
            return f"Failed to navigate to {url}: {e}"

    async def click(self, ref_id: int) -> str:
        if not self._page:
            return "Browser not started."
        try:
            selector = f'[data-sediman-ref-id="{ref_id}"]'
            element = await self._page.query_selector(selector)
            if not element:
                return f"Element [ref_id={ref_id}] not found on page. Try browser_snapshot() to see available elements."
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            text = await element.evaluate("el => el.textContent?.slice(0,50) || ''")
            await element.click()
            self._emit_step("click", f"[ref_id={ref_id}] {tag} '{text}'")
            return f"Clicked element [ref_id={ref_id}] ({tag}: '{text}')"
        except Exception as e:
            logger.warning("click_failed", ref_id=ref_id, error=str(e))
            return f"Click failed for [ref_id={ref_id}]: {e}"

    async def type_text(self, ref_id: int, text: str, submit: bool = False) -> str:
        if not self._page:
            return "Browser not started."
        try:
            selector = f'[data-sediman-ref-id="{ref_id}"]'
            element = await self._page.query_selector(selector)
            if not element:
                return f"Element [ref_id={ref_id}] not found on page. Try browser_snapshot() to see available elements."
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            await element.fill(text)
            if submit:
                await element.press("Enter")
            self._emit_step("type", f"[ref_id={ref_id}] '{text[:50]}'")
            return f"Typed '{text[:50]}' into [ref_id={ref_id}] ({tag})"
        except Exception as e:
            logger.warning("type_failed", ref_id=ref_id, error=str(e))
            return f"Type failed for [ref_id={ref_id}]: {e}"

    async def scroll(self, direction: str = "down", amount: int = 300) -> str:
        if not self._page:
            return "Browser not started."
        try:
            if direction == "down":
                await self._page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self._page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "bottom":
                await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "top":
                await self._page.evaluate("window.scrollTo(0, 0)")
            else:
                return f"Unknown scroll direction: {direction}. Use: down, up, bottom, top."
            self._emit_step("scroll", direction)
            return f"Scrolled {direction}"
        except Exception as e:
            logger.warning("scroll_failed", error=str(e))
            return f"Scroll failed: {e}"

    async def press_key(self, key: str) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.keyboard.press(key)
            self._emit_step("press_key", key)
            return f"Pressed key: {key}"
        except Exception as e:
            logger.warning("press_key_failed", key=key, error=str(e))
            return f"Key press failed: {e}"

    async def go_back(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.go_back(wait_until="networkidle")
            self._emit_step("go_back", self._page.url)
            return f"Went back to {self._page.url}"
        except Exception as e:
            return f"Go back failed: {e}"

    async def go_forward(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.go_forward(wait_until="networkidle")
            self._emit_step("go_forward", self._page.url)
            return f"Went forward to {self._page.url}"
        except Exception as e:
            return f"Go forward failed: {e}"

    async def refresh(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.reload(wait_until="networkidle")
            self._emit_step("refresh", self._page.url)
            return f"Refreshed {self._page.url}"
        except Exception as e:
            return f"Refresh failed: {e}"

    async def screenshot(self) -> str | None:
        if not self._page:
            return None
        try:
            screenshot_bytes = await self._page.screenshot(type="jpeg", quality=80, full_page=False)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            self._emit_step("screenshot", f"{len(b64)} chars")
            return b64
        except Exception as e:
            logger.warning("screenshot_failed", error=str(e))
            return None

    async def get_url(self) -> str:
        if not self._page:
            return ""
        return self._page.url

    async def get_title(self) -> str:
        if not self._page:
            return ""
        return await self._page.title()

    # ── Snapshot / Extraction ──────────────────────────────

    async def snapshot(self) -> PageSnapshot:
        """Return a structured accessibility-like snapshot of the page."""
        if not self._page:
            return PageSnapshot(url="", title="", elements=[])

        url = self._page.url
        title = await self._page.title()

        # Inject ref IDs and extract element info via JS
        elements_js = await self._page.evaluate(_SNAPSHOT_JS)
        elements = []
        for idx, raw in enumerate(elements_js):
            info = ElementInfo(
                ref_id=raw["ref_id"],
                tag=raw["tag"],
                text=raw.get("text", ""),
                role=raw.get("role", ""),
                placeholder=raw.get("placeholder", ""),
                href=raw.get("href", ""),
                src=raw.get("src", ""),
                alt=raw.get("alt", ""),
                type=raw.get("type", ""),
                value=raw.get("value", ""),
                aria_label=raw.get("ariaLabel", ""),
                title=raw.get("title", ""),
                is_visible=raw.get("isVisible", True),
            )
            elements.append(info)

        # Extract text preview (first 2000 chars)
        text_preview = await self._page.evaluate("() => document.body.innerText.slice(0,2000)")

        scroll_position = await self._page.evaluate(
            "() => ({x: window.scrollX, y: window.scrollY})"
        )

        return PageSnapshot(
            url=url,
            title=title,
            elements=elements,
            text_preview=text_preview,
            scroll_position=scroll_position,
        )

    async def extract_text(self) -> str:
        """Extract all visible text from the page."""
        if not self._page:
            return ""
        try:
            return await self._page.evaluate("() => document.body.innerText")
        except Exception as e:
            logger.warning("extract_text_failed", error=str(e))
            return ""

    async def extract_by_selector(self, selector: str) -> str:
        """Extract text matching a CSS selector."""
        if not self._page:
            return ""
        try:
            elements = await self._page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.evaluate("el => el.innerText || el.textContent || ''")
                if text.strip():
                    texts.append(text.strip())
            return "\n".join(texts)
        except Exception as e:
            logger.warning("extract_selector_failed", selector=selector, error=str(e))
            return f"Extraction failed: {e}"

    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return f"Element '{selector}' appeared."
        except Exception as e:
            return f"Wait timed out for '{selector}': {e}"

    # ── State Persistence ────────────────────────────────────

    async def save_state(self, name: str) -> None:
        from sediman.browser.session import SESSION_DIR

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            state = await self._context.storage_state()
            path = SESSION_DIR / f"{name}.json"
            path.write_text(json.dumps(state, indent=2))
            logger.info("browser_state_saved", name=name)
        except Exception as e:
            logger.warning("save_state_failed", error=str(e))

    async def load_state(self, name: str) -> bool:
        from sediman.browser.session import SESSION_DIR

        path = SESSION_DIR / f"{name}.json"
        if not path.exists():
            return False
        try:
            state = json.loads(path.read_text())
            cookies = state.get("cookies", [])
            if cookies and self._context:
                await self._context.add_cookies(cookies)
            logger.info("browser_state_loaded", name=name, cookies=len(cookies))
            return True
        except Exception as e:
            logger.warning("load_state_failed", name=name, error=str(e))
            return False

    # ── Internals ──────────────────────────────────────────

    def _emit_step(self, action: str, detail: str) -> None:
        if self._on_step:
            try:
                self._on_step(action, detail)
            except Exception:
                pass


# ── JavaScript for snapshotting ─────────────────────────

_SNAPSHOT_JS = """
(() => {
    // Remove old ref IDs
    document.querySelectorAll('[data-sediman-ref-id]').forEach(el => {
        el.removeAttribute('data-sediman-ref-id');
    });
    let counter = 0;
    const results = [];
    const interactiveTags = new Set([
        'a', 'button', 'input', 'textarea', 'select', 'option', 'label',
        'form', 'details', 'summary', 'nav', 'menu', 'menuitem'
    ]);
    const walk = (node) => {
        if (node.nodeType !== 1) return; // not element
        const tag = node.tagName.toLowerCase();
        const style = window.getComputedStyle(node);
        const isVisible = style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        const rect = node.getBoundingClientRect();
        const inViewport = rect.top < window.innerHeight && rect.bottom > 0 && rect.width > 0 && rect.height > 0;
        const isInteractive = interactiveTags.has(tag) ||
            node.onclick || node.getAttribute('onclick') ||
            node.getAttribute('role') ||
            node.tagName === 'A' || node.tagName === 'BUTTON' ||
            (node.tagName === 'INPUT' && node.type !== 'hidden');
        if ((isInteractive || tag === 'img' || tag === 'h1' || tag === 'h2' || tag === 'h3') && isVisible && inViewport) {
            counter++;
            node.setAttribute('data-sediman-ref-id', String(counter));
            const text = (node.innerText || node.textContent || '').trim().slice(0, 200);
            const placeholder = node.getAttribute('placeholder') || '';
            const ariaLabel = node.getAttribute('aria-label') || '';
            const title = node.getAttribute('title') || '';
            const role = node.getAttribute('role') || '';
            results.push({
                ref_id: counter,
                tag: tag,
                text: text,
                role: role,
                placeholder: placeholder,
                href: node.getAttribute('href') || '',
                src: node.getAttribute('src') || '',
                alt: node.getAttribute('alt') || '',
                type: node.getAttribute('type') || '',
                value: node.value || '',
                ariaLabel: ariaLabel,
                title: title,
                isVisible: true,
            });
        }
        for (const child of node.children) {
            walk(child);
        }
    };
    walk(document.body);
    return results;
})()
"""


def format_snapshot(snapshot: PageSnapshot, max_elements: int = 50) -> str:
    """Format a PageSnapshot into a text representation for LLM consumption."""
    lines = []
    lines.append(f"URL: {snapshot.url}")
    lines.append(f"Title: {snapshot.title}")
    if snapshot.scroll_position:
        lines.append(f"Scroll: x={snapshot.scroll_position['x']}, y={snapshot.scroll_position['y']}")
    lines.append("")

    elements = snapshot.elements[:max_elements]
    if not elements:
        lines.append("No interactive elements found on the page.")
    else:
        lines.append(f"Interactive elements ({len(elements)} shown):")
        for el in elements:
            parts = [f"[{el.ref_id}] {el.tag}"]
            if el.role:
                parts.append(f"role={el.role}")
            if el.text:
                parts.append(f'"{el.text[:80]}"')
            if el.placeholder:
                parts.append(f"placeholder=\"{el.placeholder[:40]}\"")
            if el.aria_label:
                parts.append(f"aria-label=\"{el.aria_label[:40]}\"")
            if el.href:
                parts.append(f"href={el.href[:60]}")
            if el.src:
                parts.append(f"src={el.src[:60]}")
            if el.alt:
                parts.append(f"alt=\"{el.alt[:40]}\"")
            if el.type:
                parts.append(f"type={el.type}")
            if el.value:
                parts.append(f"value=\"{el.value[:40]}\"")
            lines.append("  " + " ".join(parts[1:]) if len(parts) > 1 else "  " + parts[0])

    if snapshot.text_preview:
        lines.append("")
        lines.append("Page text preview:")
        lines.append(snapshot.text_preview[:500])

    return "\n".join(lines)
