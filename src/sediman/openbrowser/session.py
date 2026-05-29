from __future__ import annotations

import json
from typing import Any
from collections.abc import Callable

import structlog

from sediman.browser.controller import BrowserController
from sediman.config import DATA_DIR
from sediman.openbrowser.client import OpenBrowserClient
from sediman.openbrowser.controller import OpenBrowserController
from sediman.openbrowser.process import OpenBrowserProcess

logger = structlog.get_logger()

_SESSIONS_DIR = DATA_DIR / "sessions"


class OpenBrowserSession:
    """Drop-in replacement for BrowserSession that uses open-browser instead of BrowserUse.

    Manages the open-browser server lifecycle and provides the same interface
    as BrowserSession so the rest of Sediman can use either backend transparently.
    """

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str | None = None,
        on_screenshot: Callable[[str], None] | None = None,
        host: str = "127.0.0.1",
        port: int = 7788,
        js: bool = True,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir or str(DATA_DIR / "browser-profile-open")
        self.on_screenshot = on_screenshot
        self.host = host
        self.port = port
        self.js = js
        self._process = OpenBrowserProcess(host=host, port=port, js=js)
        self._client: OpenBrowserClient | None = None
        self._controller: OpenBrowserController | None = None
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started and self._client is not None

    @property
    def browser(self) -> Any:
        return self._client

    def get_controller(self) -> BrowserController | None:
        return self._controller

    async def start(self) -> None:
        if self._started:
            return

        try:
            await self._process.start()
        except FileNotFoundError:
            logger.warning(
                "openbrowser_binary_not_found",
                hint="Falling back to connecting to an already-running server",
            )
            pass

        self._client = OpenBrowserClient(
            base_url=f"http://{self.host}:{self.port}",
        )

        healthy = await self._client.health()
        if not healthy:
            raise RuntimeError(
                f"open-browser server not reachable at {self.host}:{self.port}. "
                "Start it manually: open-browser serve --port 7788"
            )

        self._controller = OpenBrowserController(client=self._client)
        await self._controller.start()
        self._started = True
        logger.info("openbrowser_session_started", url=f"http://{self.host}:{self.port}")

    async def stop(self) -> None:
        if self._controller:
            try:
                await self._controller.stop()
            except Exception as e:
                logger.debug("controller_stop_failed", error=str(e))
            self._controller = None
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.debug("client_close_failed", error=str(e))
            self._client = None
        try:
            await self._process.stop()
        except Exception as e:
            logger.debug("process_stop_failed", error=str(e))
        self._started = False
        logger.info("openbrowser_session_stopped")

    async def take_screenshot(self) -> str | None:
        return None

    async def save_state(self, name: str) -> None:
        if not self._client:
            return
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            cookies_result = await self._client.get_cookies()
            cookies = cookies_result.get("cookies", [])
            state = {"cookies": cookies}
            state_path = _SESSIONS_DIR / f"{name}.json"
            state_path.write_text(json.dumps(state, indent=2))
            logger.info("openbrowser_state_saved", name=name, cookies=len(cookies))
        except Exception as e:
            logger.warning("openbrowser_save_state_failed", error=str(e))

    async def load_state(self, name: str) -> bool:
        if not self._client:
            return False
        state_path = _SESSIONS_DIR / f"{name}.json"
        if not state_path.exists():
            return False
        try:
            state = json.loads(state_path.read_text())
            for cookie in state.get("cookies", []):
                await self._client.set_cookie(
                    name=cookie.get("name", ""),
                    value=cookie.get("value", ""),
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/"),
                )
            logger.info("openbrowser_state_loaded", name=name)
            return True
        except Exception as e:
            logger.warning("openbrowser_load_state_failed", name=name, error=str(e))
            return False
