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
    level: str = ""
    checked: str = ""
    disabled: str = ""
    selected: str = ""
    required: str = ""


@dataclass
class PageSnapshot:
    url: str
    title: str
    elements: list[ElementInfo]
    text_preview: str = ""
    scroll_position: dict[str, int] | None = None


@dataclass
class BrowserState:
    url: str
    scroll_x: int
    scroll_y: int
    title: str = ""


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
        self._saved_states: list[BrowserState] = []

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
            self._context = self._own_browser
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

    # ── Overlay Dismissal ─────────────────────────────────────

    async def dismiss_overlays(self) -> str:
        """Detect and dismiss common popup/cookie/banner overlays."""
        if not self._page:
            return ""
        try:
            dismissed = await self._page.evaluate(_DISMISS_OVERLAYS_JS)
            if dismissed:
                self._emit_step("dismiss_overlay", f"Removed {dismissed} overlay(s)")
                return f"Dismissed {dismissed} overlay(s)"
            return ""
        except Exception as e:
            logger.debug("dismiss_overlays_failed", error=str(e))
            return ""

    # ── Core Actions ───────────────────────────────────────

    async def navigate(self, url: str) -> str:
        if not self._page:
            return "Browser not started."
        try:
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
            element = await self._resolve_element(ref_id)
            if not element:
                return f"Element [ref_id={ref_id}] not found on page. Try browser_snapshot() to see available elements."
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            text = await element.evaluate("el => el.textContent?.slice(0,50) || ''")
            url_before = self._page.url
            await element.click()
            try:
                if tag in ("a", "button") and text.lower().strip() not in ("cancel", "close", "dismiss"):
                    await self._page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass
            self._emit_step("click", f"[ref_id={ref_id}] {tag} '{text}'")
            return f"Clicked element [ref_id={ref_id}] ({tag}: '{text}')"
        except Exception as e:
            logger.warning("click_failed", ref_id=ref_id, error=str(e))
            return f"Click failed for [ref_id={ref_id}]: {e}"

    async def type_text(self, ref_id: int, text: str, submit: bool = False) -> str:
        if not self._page:
            return "Browser not started."
        try:
            element = await self._resolve_element(ref_id)
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

    async def hover(self, ref_id: int) -> str:
        if not self._page:
            return "Browser not started."
        try:
            element = await self._resolve_element(ref_id)
            if not element:
                return f"Element [ref_id={ref_id}] not found on page. Try browser_snapshot() to see available elements."
            await element.scroll_into_view_if_needed()
            await element.hover()
            self._emit_step("hover", f"[ref_id={ref_id}]")
            return f"Hovered over element [ref_id={ref_id}]"
        except Exception as e:
            logger.warning("hover_failed", ref_id=ref_id, error=str(e))
            return f"Hover failed for [ref_id={ref_id}]: {e}"

    async def select_option(self, ref_id: int, value: str) -> str:
        if not self._page:
            return "Browser not started."
        try:
            element = await self._resolve_element(ref_id)
            if not element:
                return f"Element [ref_id={ref_id}] not found on page. Try browser_snapshot() to see available elements."
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag != "select":
                return f"Element [ref_id={ref_id}] is not a <select> (got <{tag}>). Use browser_click instead."
            await element.select_option(value=value)
            self._emit_step("select_option", f"[ref_id={ref_id}] value='{value}'")
            return f"Selected '{value}' in [ref_id={ref_id}]"
        except Exception as e:
            logger.warning("select_option_failed", ref_id=ref_id, error=str(e))
            return f"Select option failed for [ref_id={ref_id}]: {e}"

    async def switch_tab(self, index: int = -1) -> str:
        if not self._page:
            return "Browser not started."
        try:
            context = self._page.context
            pages = context.pages
            if not pages:
                return "No tabs available."
            if index < 0:
                index = len(pages) + index
            if index < 0 or index >= len(pages):
                return f"Tab index {index} out of range (0-{len(pages)-1})."
            target_page = pages[index]
            await target_page.bring_to_front()
            self._own_page = target_page
            self._emit_step("switch_tab", f"tab {index}: {target_page.url}")
            return f"Switched to tab {index}: {target_page.url}"
        except Exception as e:
            logger.warning("switch_tab_failed", error=str(e))
            return f"Switch tab failed: {e}"

    async def list_tabs(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            context = self._page.context
            pages = context.pages
            if not pages:
                return "No tabs open."
            lines = []
            for i, p in enumerate(pages):
                marker = " (active)" if p == self._page else ""
                lines.append(f"  [{i}] {p.url}{marker}")
            return f"Open tabs ({len(pages)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"List tabs failed: {e}"

    async def _resolve_element(self, ref_id: int):
        """Cascading element resolution: ref_id -> aria -> text -> role."""
        if not self._page:
            return None

        selector = f'[data-sediman-ref-id="{ref_id}"]'
        element = await self._page.query_selector(selector)
        if element:
            return element

        snapshot = await self.snapshot()
        target = None
        for el in snapshot.elements:
            if el.ref_id == ref_id:
                target = el
                break

        if not target:
            return None

        if target.aria_label:
            el = await self._page.query_selector(f'[aria-label="{target.aria_label}"]')
            if el:
                return el

        if target.href and target.tag == 'a':
            el = await self._page.query_selector(f'a[href="{target.href}"]')
            if el:
                return el

        if target.text and len(target.text) > 3:
            escaped = target.text[:60].replace('"', '\\"')
            for tag_match in [target.tag, 'button', 'a', 'span', 'div']:
                el = await self._page.query_selector(
                    f'{tag_match}:text-is("{escaped}")'
                )
                if el:
                    return el
            el = await self._page.query_selector(f':text("{escaped}")')
            if el:
                return el

        if target.role and target.tag in ('button', 'a', 'input'):
            el = await self._page.query_selector(f'[role="{target.role}"]')
            if el:
                count = await self._page.evaluate(
                    f'document.querySelectorAll(\'[role="{target.role}"]\').length'
                )
                if count == 1:
                    return el

        if target.placeholder:
            el = await self._page.query_selector(f'[placeholder="{target.placeholder}"]')
            if el:
                return el

        return None

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
            await self._page.go_back(wait_until="domcontentloaded")
            try:
                await self._page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            self._emit_step("go_back", self._page.url)
            return f"Went back to {self._page.url}"
        except Exception as e:
            return f"Go back failed: {e}"

    async def go_forward(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.go_forward(wait_until="domcontentloaded")
            try:
                await self._page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            self._emit_step("go_forward", self._page.url)
            return f"Went forward to {self._page.url}"
        except Exception as e:
            return f"Go forward failed: {e}"

    async def refresh(self) -> str:
        if not self._page:
            return "Browser not started."
        try:
            await self._page.reload(wait_until="domcontentloaded")
            try:
                await self._page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
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

        await self.dismiss_overlays()

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
                level=raw.get("level", ""),
                checked=raw.get("checked", ""),
                disabled=raw.get("disabled", ""),
                selected=raw.get("selected", ""),
                required=raw.get("required", ""),
            )
            elements.append(info)

        # Extract text preview (first 2000 chars)
        text_preview = await self._page.evaluate("() => document.body.innerText.slice(0,4000)")

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

    async def save_checkpoint(self) -> int:
        if not self._page:
            return -1
        try:
            url = self._page.url
            scroll = await self._page.evaluate("() => ({x: window.scrollX, y: window.scrollY})")
            title = await self._page.title()
            state = BrowserState(
                url=url,
                scroll_x=scroll.get("x", 0),
                scroll_y=scroll.get("y", 0),
                title=title,
            )
            self._saved_states.append(state)
            return len(self._saved_states) - 1
        except Exception as e:
            logger.warning("save_checkpoint_failed", error=str(e))
            return -1

    async def restore_checkpoint(self, index: int = -1) -> bool:
        if not self._saved_states or not self._page:
            return False
        try:
            state = self._saved_states[index]
            await self._page.goto(state.url, wait_until="domcontentloaded", timeout=15000)
            await self._page.evaluate(
                f"() => window.scrollTo({state.scroll_x}, {state.scroll_y})"
            )
            return True
        except Exception as e:
            logger.warning("restore_checkpoint_failed", error=str(e))
            return False

    def clear_checkpoints(self) -> None:
        self._saved_states.clear()

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

_DISMISS_OVERLAYS_JS = """
(() => {
    let count = 0;
    const overlaySelectors = [
        '[id*="cookie" i]', '[class*="cookie" i]', '[id*="consent" i]',
        '[class*="consent" i]', '[class*="gdpr" i]', '[class*="banner" i]',
        '[id*="banner" i]', '[class*="popup" i]', '[class*="modal-overlay" i]',
        '[class*="lightbox" i]', '[class*="newsletter" i]', '[class*="subscribe" i]',
        '[id*="onetrust" i]', '[class*="onetrust" i]', '[id*="didomi" i]',
        '[class*="didomi" i]', '[id*="accept" i].overlay', '[class*="cc-banner" i]',
        '[class*="toast" i]', '[class*="notification-bar" i]',
        '[aria-modal="true"][role="dialog"]',
    ];

    const acceptButtons = [
        'button[id*="accept" i]', 'button[class*="accept" i]',
        'button[id*="agree" i]', 'button[class*="agree" i]',
        'button[id*="allow" i]', 'button[class*="allow" i]',
        'button[id*="consent" i]', 'button[class*="consent" i]',
        'button[id*="got-it" i]', 'button[class*="got-it" i]',
        'button[id*="close" i]', 'button[class*="close" i]',
        'a[id*="accept" i]', 'a[class*="accept" i]',
        '[class*="dismiss" i]', '[aria-label*="close" i]',
        '[aria-label*="accept" i]', '[aria-label*="dismiss" i]',
    ];

    for (const sel of acceptButtons) {
        try {
            const btns = document.querySelectorAll(sel);
            for (const btn of btns) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    const text = (btn.textContent || '').trim().toLowerCase();
                    if (text.length < 50 && (
                        text.includes('accept') || text.includes('agree') ||
                        text.includes('allow') || text.includes('got it') ||
                        text.includes('ok') || text.includes('close') ||
                        text.includes('dismiss') || text.includes('continue')
                    )) {
                        btn.click();
                        count++;
                        break;
                    }
                }
            }
            if (count > 0) break;
        } catch(e) {}
    }

    for (const sel of overlaySelectors) {
        try {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const style = window.getComputedStyle(el);
                if (style.position === 'fixed' || style.position === 'absolute') {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > window.innerWidth * 0.3 || rect.height > window.innerHeight * 0.3) {
                        el.style.display = 'none';
                        el.style.pointerEvents = 'none';
                        count++;
                    }
                }
            }
        } catch(e) {}
    }

    return count;
})()
"""

_SNAPSHOT_JS = """
(() => {
    document.querySelectorAll('[data-sediman-ref-id]').forEach(el => {
        el.removeAttribute('data-sediman-ref-id');
    });

    const MAX_ELEMENTS = 120;
    let counter = 0;

    const INTERACTIVE_TAGS = new Set([
        'a', 'button', 'input', 'textarea', 'select', 'option', 'label',
        'form', 'details', 'summary', 'nav', 'menu', 'menuitem'
    ]);
    const HEADING_TAGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']);
    const CONTENT_TAGS = new Set([
        'p', 'span', 'div', 'li', 'td', 'th', 'tr', 'table', 'thead', 'tbody',
        'ol', 'ul', 'dl', 'dt', 'dd', 'section', 'article', 'main', 'aside',
        'header', 'footer', 'figure', 'figcaption', 'blockquote', 'pre', 'code',
        'strong', 'em', 'b', 'i', 'mark', 'small', 'sub', 'sup', 'time',
        'address', 'cite', 'caption', 'summary', 'details'
    ]);
    const SKIP_TAGS = new Set([
        'script', 'style', 'noscript', 'svg', 'path', 'meta', 'link', 'head',
        'br', 'hr', 'wbr', 'template', 'slot', 'iframe'
    ]);

    const results = [];

    function isVisuallyInViewport(node) {
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return false;
        const buffer = 200;
        return rect.bottom > -buffer && rect.top < window.innerHeight + buffer &&
               rect.right > -buffer && rect.left < window.innerWidth + buffer;
    }

    function isHidden(node) {
        const style = window.getComputedStyle(node);
        return style.display === 'none' || style.visibility === 'hidden' ||
               style.opacity === '0' || style.clip === 'rect(0px, 0px, 0px, 0px)';
    }

    function getDirectText(node) {
        let text = '';
        for (const child of node.childNodes) {
            if (child.nodeType === 3) {
                text += child.textContent;
            }
        }
        return text.trim().slice(0, 300);
    }

    function getRole(node, tag) {
        const explicit = node.getAttribute('role');
        if (explicit) return explicit;
        const roleMap = {
            'a': node.hasAttribute('href') ? 'link' : '',
            'button': 'button',
            'input': 'textbox',
            'textarea': 'textbox',
            'select': 'combobox',
            'option': 'option',
            'li': 'listitem',
            'ul': 'list',
            'ol': 'list',
            'table': 'table',
            'tr': 'row',
            'td': 'cell',
            'th': 'columnheader',
            'thead': 'rowgroup',
            'tbody': 'rowgroup',
            'nav': 'navigation',
            'main': 'main',
            'header': 'banner',
            'footer': 'contentinfo',
            'form': 'form',
            'img': 'img',
            'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
            'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
            'details': 'group',
            'summary': 'button',
            'dialog': 'dialog',
            'section': 'region',
            'article': 'article',
            'aside': 'complementary',
            'figure': 'figure',
            'figcaption': 'caption',
        };
        return roleMap[tag] || '';
    }

    function shouldInclude(node, tag) {
        if (SKIP_TAGS.has(tag)) return false;
        if (isHidden(node)) return false;

        if (INTERACTIVE_TAGS.has(tag)) return true;
        if (HEADING_TAGS.has(tag)) return true;
        if (tag === 'img') return true;

        if (node.getAttribute('role')) return true;
        if (node.getAttribute('aria-label')) return true;
        if (node.getAttribute('onclick') || node.onclick) return true;
        if (node.getAttribute('tabindex') && node.getAttribute('tabindex') !== '-1') return true;
        if (tag === 'input' && node.type !== 'hidden') return true;

        if (CONTENT_TAGS.has(tag)) {
            const directText = getDirectText(node);
            const hasChildElements = node.children.length > 0;
            if (directText.length > 0 || hasChildElements) return true;
        }

        return false;
    }

    function walk(node, depth) {
        if (counter >= MAX_ELEMENTS) return;
        if (depth > 15) return;

        const tag = node.tagName.toLowerCase();
        if (SKIP_TAGS.has(tag)) return;
        if (isHidden(node)) return;

        if (shouldInclude(node, tag)) {
            const inViewport = isVisuallyInViewport(node);

            counter++;
            node.setAttribute('data-sediman-ref-id', String(counter));

            const ownText = getDirectText(node);
            const fullText = (node.innerText || node.textContent || '').trim().slice(0, 200);
            const displayText = ownText.length > 0 ? ownText : (fullText !== ownText ? fullText.slice(0, 150) : '');

            const role = getRole(node, tag);
            const ariaLabel = node.getAttribute('aria-label') || '';
            const placeholder = node.getAttribute('placeholder') || '';
            const href = node.getAttribute('href') || '';
            const src = node.getAttribute('src') || '';
            const alt = node.getAttribute('alt') || '';
            const inputType = node.getAttribute('type') || '';
            const value = (node.value !== undefined && node.value !== null) ? String(node.value) : '';
            const titleAttr = node.getAttribute('title') || '';
            const checked = node.checked != null ? String(!!node.checked) : '';
            const disabled = node.disabled ? 'true' : '';
            const selected = node.selected != null ? String(!!node.selected) : '';
            const level = HEADING_TAGS.has(tag) ? tag.replace('h', '') : (node.getAttribute('aria-level') || '');
            const required = node.required ? 'true' : '';

            const entry = {
                ref_id: counter,
                tag: tag,
                text: displayText,
                role: role,
                placeholder: placeholder,
                href: href.startsWith('javascript:') ? '' : href,
                src: src,
                alt: alt,
                type: inputType,
                value: value.slice(0, 80),
                ariaLabel: ariaLabel,
                title: titleAttr,
                isVisible: inViewport,
            };
            if (level) entry.level = level;
            if (checked) entry.checked = checked;
            if (disabled) entry.disabled = disabled;
            if (selected) entry.selected = selected;
            if (required) entry.required = required;

            results.push(entry);
        }

        for (const child of node.children) {
            walk(child, depth + 1);
        }
    }

    walk(document.body, 0);
    return results;
})()
"""


def format_snapshot(snapshot: PageSnapshot, max_elements: int = 80) -> str:
    """Format a PageSnapshot into a text representation for LLM consumption."""
    lines = []
    lines.append(f"URL: {snapshot.url}")
    lines.append(f"Title: {snapshot.title}")
    if snapshot.scroll_position:
        lines.append(f"Scroll: x={snapshot.scroll_position['x']}, y={snapshot.scroll_position['y']}")
    lines.append("")

    elements = snapshot.elements[:max_elements]
    if not elements:
        lines.append("No elements found on the page.")
    else:
        lines.append(f"Page elements ({len(elements)} shown):")
        for el in elements:
            parts = [f"[{el.ref_id}]"]
            tag_label = el.tag.upper() if el.tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') else el.tag
            if el.level and el.role == 'heading':
                tag_label = f"h{el.level}"
            parts.append(tag_label)

            if el.role and el.role != el.tag:
                parts.append(f"role={el.role}")
            if el.text:
                display = el.text[:120].replace('\n', ' ')
                parts.append(f'"{display}"')
            if el.placeholder:
                parts.append(f"placeholder=\"{el.placeholder[:40]}\"")
            if el.aria_label:
                parts.append(f"aria=\"{el.aria_label[:40]}\"")
            if el.href:
                parts.append(f"href={el.href[:80]}")
            if el.src:
                parts.append(f"src={el.src[:60]}")
            if el.alt:
                parts.append(f"alt=\"{el.alt[:40]}\"")
            if el.type and el.tag in ('input', 'button'):
                parts.append(f"type={el.type}")
            if el.value and el.tag in ('input', 'textarea', 'select'):
                display_val = el.value[:40]
                parts.append(f"val=\"{display_val}\"")
            if el.checked:
                parts.append(f"checked={el.checked}")
            if el.disabled:
                parts.append("disabled")
            if el.selected:
                parts.append(f"selected={el.selected}")
            if el.required:
                parts.append("required")
            if not el.is_visible:
                parts.append("offscreen")

            lines.append("  " + " ".join(parts))

    if snapshot.text_preview:
        lines.append("")
        lines.append("Page text:")
        lines.append(snapshot.text_preview[:800])

    return "\n".join(lines)
