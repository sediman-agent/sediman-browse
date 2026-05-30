"""SedimanTUI — slim orchestration shell. Run loops, lifecycle, and callbacks."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from typing import Any

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from sediman.agent.interrupt import InterruptedError, InterruptSignal
from sediman.tui.commands import _SLASH_NAMES, handle_slash, handle_task
from sediman.tui.display import cprint, print_banner
from sediman.tui.logging import (
    install_global_log_filter,
    remove_global_log_filter,
    suppress_logging,
)
from sediman.tui.scheduler import SchedulerManager

_PERMISSION_MODES = ["ask", "acceptEdits", "plan", "auto"]


class _ProgressRenderable:
    """Reads step_log and renders as a live-updating Panel."""

    def __init__(self, tui: SedimanTUI):
        self.tui = tui

    def __rich_console__(self, console, options):
        lines = list(self.tui._step_log)
        if not lines:
            lines.append("  Waiting for agent...")
        content = Text("\n".join(lines[-50:]))
        elapsed = time.monotonic() - self.tui._tool_start_time
        elapsed_str = f"{elapsed:.0f}s"
        if elapsed >= 60:
            elapsed_str = f"{elapsed // 60:.0f}m {elapsed % 60:.0f}s"
        panel = Panel(
            content,
            title=f"  ⏳ {elapsed_str}  {self.tui._spinner_text or 'Working...'}",
            border_style="blue",
            padding=(0, 1),
        )
        yield panel


class SedimanTUI:
    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        base_url: str | None = None,
        headless: bool = False,
        browser_backend: str = "browser-use",
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.headless = headless
        self.browser_backend = browser_backend
        self._llm: Any = None
        self._browser: Any = None
        self._agent: Any = None
        self._running = True
        self._task_count = 0
        self._agent_running = False
        self._spinner_text: str = ""
        self._tool_start_time: float = 0.0
        self._should_exit = False
        self._scheduler = SchedulerManager()
        self._prompt_active = False
        self._session_name: str = ""
        self._session_color: str = ""
        self._session_start_time: float = 0.0
        self._permission_mode: str = "ask"
        self._plan_mode: bool = False
        self._step_log: list[str] = []
        self._live: Live | None = None

    # ── lazy init ──────────────────────────────────────────────────

    def _get_llm(self) -> Any:
        if self._llm is None:
            from sediman.llm.provider import create_provider

            self._llm = create_provider(self.provider, self.model, self.base_url)
        return self._llm

    async def _get_browser(self) -> Any:
        if self._browser is None:
            if self.browser_backend == "openbrowser":
                from sediman.openbrowser.session import OpenBrowserSession

                self._browser = OpenBrowserSession(headless=self.headless)
            else:
                from sediman.browser.session import BrowserSession

                self._browser = BrowserSession(
                    headless=self.headless, stealth=True
                )
            await self._browser.start()
        return self._browser

    async def _get_agent(self) -> Any:
        if self._agent is None:
            from sediman.agent.loop import AgentLoop
            from sediman.agent.tools import set_terminal_approval_callback

            llm = self._get_llm()
            browser = await self._get_browser()
            self._agent = AgentLoop(
                llm_provider=llm,
                browser_session=browser,
                on_step=self._on_browser_step,
                on_streaming_text=self._on_streaming_text,
            )
            set_terminal_approval_callback(self._on_terminal_approval)
        return self._agent

    # ── callbacks ──────────────────────────────────────────────────

    async def _on_terminal_approval(self, command: str, cwd: str) -> bool:
        cprint(f"\n  \033[33m? Terminal:\033[0m {command}")
        if cwd and cwd != ".":
            cprint(f"  \033[2m[cwd: {cwd}]\033[0m")

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: input("  Allow? [y/n/a(llow session)] ").strip().lower(),
            )
        except (EOFError, KeyboardInterrupt):
            cprint("  \033[31mX Denied.\033[0m")
            return False

        if response in ("a", "allow", "always"):
            from sediman.agent.tools import set_terminal_allowed

            set_terminal_allowed(True)
            cprint("  \033[32m+ Terminal approved for this session.\033[0m")
            return True

        if response in ("y", "yes"):
            return True

        cprint("  \033[31mX Denied.\033[0m")
        return False

    def _on_browser_step(self, event: Any) -> None:
        from sediman.agent.loop import StepEvent

        if not isinstance(event, StepEvent):
            return

        if InterruptSignal.get().is_set():
            InterruptSignal.get().clear()
            raise InterruptedError("Interrupted by user")

        phase = event.phase or ""

        phase_styles = {
            "planning": "\033[33m",
            "executing": "\033[34m",
            "observing": "\033[36m",
            "reflecting": "\033[35m",
            "delegating": "\033[32m",
            "done": "\033[32m",
            "failed": "\033[31m",
        }

        phase_symbols = {
            "planning": "◈",
            "executing": "▶",
            "observing": "◎",
            "reflecting": "◆",
            "delegating": "◇",
            "done": "✓",
            "failed": "✗",
        }

        action = event.action
        for prefix in (
            "[planning] ",
            "[executing] ",
            "[observing] ",
            "[reflecting] ",
            "[delegating] ",
            "[done] ",
            "[failed] ",
        ):
            action = action.replace(prefix, "")

        style = phase_styles.get(phase, "\033[0m")
        symbol = phase_symbols.get(phase, "·")
        rst = "\033[0m"
        dim = "\033[2m"

        # Append to step log for Live rendering
        self._step_log.append(f"  {style}{symbol}{rst} {action}")
        self._spinner_text = action[:60]
        self._tool_start_time = time.monotonic()

        detail = getattr(event, "detail", "")
        if detail:
            lines = detail.split("\n")
            for i, line in enumerate(lines):
                prefix = "    └ " if i == len(lines) - 1 else "    │ "
                self._step_log.append(f"{prefix}{dim}{line[:120]}{rst}")

        if len(self._step_log) > 200:
            self._step_log = self._step_log[-200:]

    def _on_streaming_text(self, token: str, phase: str = "responding") -> None:
        if self._live:
            style = "\033[36m" if phase == "responding" else "\033[33m"
            rst = "\033[0m"
            if not self._step_log or not self._step_log[-1].startswith("  ▶ streaming"):
                self._step_log.append(f"  {style}▶ streaming:{rst} {token}")
            else:
                self._step_log[-1] += token

    # ── entry point ────────────────────────────────────────────────

    def run(self) -> None:
        """Sync entry point."""
        asyncio.run(self._run_main())

    async def _run_main(self) -> None:
        """Async entry point — single event loop for the entire session."""
        from sediman.logging import suppress_noisy_loggers

        self._session_start_time = time.monotonic()

        suppress_noisy_loggers()
        install_global_log_filter()

        with suppress_logging():
            from sediman.logging import ensure_db

            await ensure_db()

        self._scheduler.start()

        try:
            await self._run_async()
        except ImportError:
            self._run_fallback()

        self._scheduler.stop()

        if self._browser:
            with suppress_logging():
                try:
                    await self._browser.stop()
                except Exception:
                    pass

        self._kill_orphan_browsers()
        remove_global_log_filter()
        self._print_exit_summary()

    def _print_exit_summary(self) -> None:
        elapsed = time.monotonic() - self._session_start_time
        elapsed_str = f"{elapsed:.0f}s"
        if elapsed >= 60:
            elapsed_str = f"{elapsed // 60:.0f}m {elapsed % 60:.0f}s"
        cprint(
            f"  \033[36m⏹ Session ended\033[0m · "
            f"{self._task_count} tasks · "
            f"{elapsed_str}"
        )
        cprint("  \033[2mResume with: sediman chat\033[0m")

    @staticmethod
    def _kill_orphan_browsers() -> None:
        try:
            import subprocess

            result = subprocess.run(
                ["pgrep", "-f", "chromium.*--remote-debugging"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    os.kill(int(pid_str.strip()), signal.SIGKILL)
                except (ValueError, OSError):
                    pass
        except Exception:
            pass

    # ── context usage ──────────────────────────────────────────────

    def _context_bar(self) -> str:
        if not self._agent:
            return ""
        conv = self._agent.get_conversation()
        total_chars = sum(len(str(m)) for m in conv)
        est_tokens = total_chars // 4
        ctx_pct = min(est_tokens / 128_000, 1.0)
        bar_len = 10
        filled = int(bar_len * ctx_pct)
        bar = "▓" * filled + "░" * (bar_len - filled)
        return f"[{bar}] {est_tokens // 1000}K"

    # ── bottom toolbar ─────────────────────────────────────────────

    def _get_bottom_toolbar(self):
        from prompt_toolkit.formatted_text import HTML

        parts = []

        if self._agent_running:
            elapsed = time.monotonic() - self._tool_start_time
            elapsed_str = f"{elapsed:.0f}s"
            if elapsed >= 60:
                elapsed_str = f"{elapsed // 60:.0f}m {elapsed % 60:.0f}s"

            spinner_text = self._spinner_text or "Working..."
            parts.append(f'<b><style fg="ansigreen">⏳ {elapsed_str}</style></b>')
            parts.append(f"  <i>{spinner_text}</i>  ")
        else:
            parts.append('<style fg="gray">● idle</style>  ')

        provider_str = f"{self.provider}/{self.model or 'default'}"
        parts.append(f'<style fg="gray">{provider_str}</style>')

        mode_hint = "plan" if self._plan_mode else self._permission_mode
        mode_colors = {
            "ask": "ansiwhite",
            "acceptEdits": "ansigreen",
            "plan": "ansimagenta",
            "auto": "ansired",
        }
        mc = mode_colors.get(mode_hint, "ansiwhite")
        parts.append(f'  <style fg="{mc}">· {mode_hint}</style>')

        if self._session_name:
            color = self._session_color or "cyan"
            parts.append(f'  <style fg="{color}"> · {self._session_name}</style>')

        parts.append(f'  <style fg="gray"> · {self._task_count} tasks</style>')

        # Context bar
        ctx = self._context_bar()
        if ctx:
            parts.append(f'  <style fg="gray"> · {ctx}</style>')

        hints = ["? help", "Esc int", "^C exit", "⇧Tab mode", "! shell"]
        parts.append(f'  <style fg="gray"> · {" · ".join(hints)}</style>')

        return HTML("".join(parts))

    # ── main async loop ────────────────────────────────────────────

    async def _run_async(self) -> None:
        from sediman.config import HISTORY_FILE as hist_path

        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings

        hist_path.parent.mkdir(parents=True, exist_ok=True)

        kb = KeyBindings()

        @kb.add("escape")
        def _(event):
            if self._agent_running:
                InterruptSignal.get().trigger("Esc pressed by user")
            else:
                event.app.current_buffer.reset()

        @kb.add("s-tab")
        def _(event):
            self._cycle_permission_mode()

        @kb.add("c-o")
        def _(event):
            event.app.current_buffer.insert_text("\n")

        @kb.add("enter")
        def _(event):
            event.app.current_buffer.validate_and_handle()

        completer = WordCompleter(_SLASH_NAMES, sentence=True)
        history = FileHistory(str(hist_path))

        session = PromptSession(
            completer=completer,
            history=history,
            key_bindings=kb,
            bottom_toolbar=self._get_bottom_toolbar,
            multiline=True,
        )

        os.system("cls" if os.name == "nt" else "clear")

        print_banner(self.headless)

        while not self._should_exit:
            self._scheduler.flush_messages()
            try:
                user_input = await session.prompt_async(
                    f" [{self._task_count + 1}] > ",
                )
                user_input = user_input.strip()
            except KeyboardInterrupt:
                print("")
                continue
            except EOFError:
                break

            if not user_input:
                continue

            self._task_count += 1

            if user_input.startswith("!"):
                await self._run_shell_command(user_input[1:])
                continue

            self._agent_running = True
            InterruptSignal.get().clear()
            self._spinner_text = "Starting..."
            self._tool_start_time = time.monotonic()
            self._step_log = []

            if user_input.startswith("/"):
                try:
                    await self._maybe_with_live(handle_slash(self, user_input))
                except asyncio.CancelledError:
                    cprint("\n  \033[33m-- Interrupted --\033[0m\n")
                except InterruptedError:
                    cprint("\n  \033[33m-- Interrupted --\033[0m\n")
            else:
                if self._plan_mode:
                    self._step_log.append(
                        "  \033[35mℹ Plan mode: researching without making changes.\033[0m"
                    )
                live = Live(
                    _ProgressRenderable(self),
                    refresh_per_second=10,
                    transient=True,
                )
                self._live = live
                live.start()
                try:
                    await handle_task(self, user_input)
                except asyncio.CancelledError:
                    cprint("\n  \033[33m-- Interrupted --\033[0m\n")
                except InterruptedError:
                    cprint("\n  \033[33m-- Interrupted --\033[0m\n")
                except Exception as e:
                    cprint(f"\n  \033[31mX Task failed: {e}\033[0m\n")
                finally:
                    self._live = None
                    live.stop()

            self._agent_running = False
            InterruptSignal.get().clear()
            self._spinner_text = ""
            self._tool_start_time = 0.0
            self._scheduler.refresh()
            self._scheduler.flush_messages()

        if self._browser:
            try:
                await self._browser.stop()
            except Exception:
                pass

    async def _maybe_with_live(self, coro):
        """Run a slash command — show Live if it takes more than ~1s."""
        live = Live(
            _ProgressRenderable(self),
            refresh_per_second=10,
            transient=True,
        )
        self._live = live
        live.start()
        try:
            return await coro
        finally:
            self._live = None
            live.stop()

    # ── shell command ──────────────────────────────────────────────

    async def _run_shell_command(self, cmd: str) -> None:
        """Run a ! shell command and display output."""
        cprint(f"  \033[32m$\033[0m {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode() if stdout else ""
            for line in output.split("\n")[:20]:
                if line:
                    cprint(f"  {line}")
            if proc.returncode != 0:
                cprint(f"  \033[31m✗ exit code {proc.returncode}\033[0m")
            else:
                cprint("  \033[32m✓ done\033[0m")
        except FileNotFoundError:
            cprint("  \033[31m✗ Command not found\033[0m")

    # ── permission modes ──────────────────────────────────────────

    def _cycle_permission_mode(self) -> None:
        self._plan_mode = False
        idx = _PERMISSION_MODES.index(self._permission_mode)
        self._permission_mode = _PERMISSION_MODES[(idx + 1) % len(_PERMISSION_MODES)]
        self._apply_permission_mode()

    def _apply_permission_mode(self) -> None:
        if self._permission_mode == "ask":
            from sediman.agent.tools import set_terminal_allowed

            set_terminal_allowed(False)
        elif self._permission_mode == "acceptEdits":
            from sediman.agent.tools import set_terminal_allowed

            set_terminal_allowed(True)
        elif self._permission_mode == "plan":
            pass
        elif self._permission_mode == "auto":
            from sediman.agent.tools import set_terminal_allowed

            set_terminal_allowed(True)

    # ── fallback (no prompt_toolkit) ───────────────────────────────

    def _run_fallback(self) -> None:
        print_banner(self.headless)

        while self._running:
            try:
                prompt_text = f" [{self._task_count + 1}] > "
                user_input = input(prompt_text).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n  Bye!")
                break

            if not user_input:
                continue

            self._task_count += 1

            if user_input.startswith("!"):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._run_shell_command(user_input[1:]))
                finally:
                    loop.close()
                continue

            if user_input.startswith("/"):
                self._handle_slash_sync(user_input)
            else:
                self._run_task_sync(user_input)

        if self._browser:
            with suppress_logging():
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._browser.stop())
                    loop.close()
                except Exception:
                    pass

    def _run_task_sync(self, task: str) -> None:
        if self._plan_mode:
            cprint("  \033[35mℹ Plan mode: researching without making changes.\033[0m")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(handle_task(self, task))
        except Exception as e:
            cprint(f"\n  \033[31mX Task failed: {e}\033[0m\n")
        finally:
            loop.close()

    def _handle_slash_sync(self, cmd: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(handle_slash(self, cmd))
        except Exception as e:
            cprint(f"  \033[31mX Command failed: {e}\033[0m")
        finally:
            loop.close()
