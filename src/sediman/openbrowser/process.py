from __future__ import annotations

import asyncio
import shutil
import signal

import structlog

logger = structlog.get_logger()


class OpenBrowserProcess:
    """Manages an `open-browser serve` child process."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7788,
        js: bool = True,
        binary: str | None = None,
    ):
        self.host = host
        self.port = port
        self.js = js
        self._binary = binary or self._find_binary()
        self._process: asyncio.subprocess.Process | None = None
        self._started = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._started and self._process is not None and self._process.returncode is None

    @staticmethod
    def _find_binary() -> str:
        for name in ("open-browser", "open-browser-bin"):
            path = shutil.which(name)
            if path:
                return path
        return "open-browser"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("open-browser") is not None or shutil.which("open-browser-bin") is not None

    async def start(self) -> None:
        if self._started:
            return

        if not self._binary or not shutil.which(self._binary):
            raise FileNotFoundError(
                "open-browser binary not found. Install it with: "
                "cargo install --path crates/open-cli --features js "
                "(from the Openbrowser repo)"
            )

        cmd = [self._binary, "serve", "--host", self.host, "--port", str(self.port)]
        if self.js:
            cmd.append("--js")

        logger.info("openbrowser_starting", cmd=cmd)

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        ready = await self._wait_ready(max_wait=15.0)
        if not ready:
            await self.stop()
            raise RuntimeError("open-browser server failed to start within 15s")

        self._started = True
        logger.info("openbrowser_started", url=self.base_url)

    async def stop(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None
        self._started = False
        logger.info("openbrowser_stopped")

    async def _wait_ready(self, max_wait: float = 15.0) -> bool:
        import httpx

        deadline = asyncio.get_event_loop().time() + max_wait
        while asyncio.get_event_loop().time() < deadline:
            if self._process and self._process.returncode is not None:
                stderr = ""
                try:
                    stderr = (await self._process.stderr.read()).decode(errors="replace")[:500]
                except Exception:
                    pass
                logger.error("openbrowser_exited", code=self._process.returncode, stderr=stderr)
                return False

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://{self.host}:{self.port}/api/health",
                        timeout=2.0,
                    )
                    if resp.status_code == 200:
                        return True
            except Exception:
                pass

            await asyncio.sleep(0.5)

        return False
