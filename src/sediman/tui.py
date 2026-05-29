"""Sediman interactive TUI — prompt_toolkit prompt() for input, print() for output.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import shutil
import sys
import threading
import time
import queue
from contextlib import contextmanager
from io import StringIO
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from sediman import __version__

_SPINNER_FRAMES = ("-", "\\", "|", "/")

_SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/skills": "List all skills",
    "/skill <name>": "Show skill details",
    "/run-skill <name>": "Execute a skill",
    "/hub browse [--category X]": "Browse the Skills Hub",
    "/hub search <query>": "Search the Skills Hub",
    "/hub install <name> [--force]": "Install a skill from the hub",
    "/hub info <name>": "Show hub skill details",
    "/hub publish <name>": "Publish a local skill to the hub",
    "/memory": "Show current memory",
    "/remember <text>": "Save something to memory",
    "/model": "Show current model",
    "/model <provider:model>": "Switch model mid-session (e.g. ollama:qwen3)",
    "/models": "List available provider presets",
    "/schedule": "List scheduled tasks",
    "/schedule-add <cron> <task>": "Add a scheduled task",
    "/schedule-remove <id>": "Remove a scheduled task",
    "/sessions": "Show recent sessions",
    "/screenshot": "Take a screenshot of current browser",
    "/browser": "Show current browser mode",
    "/browser headless": "Switch to headless browser",
    "/browser headed": "Switch to headed browser (with GUI)",
    "/status": "Show agent status",
    "/soul": "Show current personality",
    "/soul <text>": "Set agent personality",
    "/soul reset": "Reset personality to default",
    "/record <name> [--desc ...]": "Record browser actions as a skill",
    "/stop": "Stop recording and save the skill",
    "/delegate <task>": "Run a task as an isolated subagent",
    "/parallel <t1> | <t2> | ...": "Run up to 5 tasks in parallel",
    "/compress": "Compress conversation history",
    "/clear": "Clear conversation history",
    "/reset": "Reset everything (new session)",
    "/terminal": "Show terminal access status",
    "/terminal on": "Allow all terminal commands this session",
    "/terminal off": "Require approval for each command",
    "/exit": "Exit Sediman",
}

_SLASH_NAMES = sorted(
    [c.split()[0] for c in _SLASH_COMMANDS],
    key=lambda x: x,
)


def _relative_time(timestamp: str, now) -> str:
    from sediman.utils import relative_time
    return relative_time(timestamp, now)


def _cprint(text: str) -> None:
    """Print text that scrolls above the prompt.

    With patch_stdout active, print() goes through prompt_toolkit's
    StdoutProxy which handles threading and scrolling automatically.
    Falls back to bare print() if prompt_toolkit is unavailable.
    """
    print(text)


class _RichAdapter:
    """Captures Rich output and routes it through print()."""

    def __init__(self):
        self._buffer = StringIO()
        self._console = Console(
            file=self._buffer,
            force_terminal=True,
            color_system="truecolor",
            highlight=False,
        )

    def print(self, *args, **kwargs):
        self._buffer.seek(0)
        self._buffer.truncate()
        self._console.width = shutil.get_terminal_size((80, 24)).columns
        self._console.print(*args, **kwargs)
        output = self._buffer.getvalue()
        print(output, end="")


_rich = _RichAdapter()


class _SuppressFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("sediman")


_root_filter = _SuppressFilter()


def _install_global_log_filter() -> None:
    logging.getLogger().addFilter(_root_filter)
    logging.getLogger().setLevel(logging.CRITICAL)


def _remove_global_log_filter() -> None:
    logging.getLogger().removeFilter(_root_filter)


@contextmanager
def _suppress_logging():
    import structlog

    devnull = open(os.devnull, "w")
    old_stderr = sys.stderr
    sys.stderr = devnull
    old_root_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.CRITICAL)
    structlog.configure(
        processors=[lambda _, __, ___: None],
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.WriteLoggerFactory(devnull),
    )
    try:
        yield
    finally:
        sys.stderr = old_stderr
        structlog.reset_defaults()
        logging.getLogger().setLevel(old_root_level)
        try:
            devnull.close()
        except Exception:
            pass


class SedimanTUI:
    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        base_url: str | None = None,
        headless: bool = False,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.headless = headless
        self._llm: Any = None
        self._browser: Any = None
        self._agent: Any = None
        self._running = True
        self._task_count = 0
        self._agent_running = False
        self._spinner_text: str = ""
        self._tool_start_time: float = 0.0
        self._should_exit = False
        self._scheduler: Any = None
        self._scheduler_lock = threading.Lock()
        self._cron_messages: queue.Queue[str] = queue.Queue()
        self._prompt_active = False
        self._cron_loops: list[Any] = []
        self._cron_loops_lock = threading.Lock()

    def _get_skills_list(self) -> list:
        try:
            from sediman.skills.engine import SkillEngine

            return SkillEngine().list_skills()
        except Exception:
            return []

    def _print_banner(self) -> None:
        skills = self._get_skills_list()
        lines = []
        lines.append("")
        lines.append(
            """    ______                   __  __
    /      \\                 /  |/  |
   /$$$$$$  |  ______    ____$$ |$$/  _____  ____    ______   _______
   $$ \\__$$/  /      \\  /    $$ |/  |/     \\/    \\  /      \\ /       \\
   $$      \\ /$$$$$$  |/$$$$$$$ |$$ |$$$$$$ $$$$  | $$$$$$  |$$$$$$$  |
    $$$$$$  |$$    $$ |$$ |  $$ |$$ |$$ | $$ | $$ | /    $$ |$$ |  $$ |
   /  \\__$$ |$$$$$$$$/ $$ \\__$$ |$$ |$$ | $$ | $$ |/$$$$$$$ |$$ |  $$ |
   $$    $$/ $$       |$$    $$ |$$ |$$ | $$ | $$ |$$    $$ |$$ |  $$ |
    $$$$$$/   $$$$$$$/  $$$$$$$/ $$/ $$/  $$/  $$/  $$$$$$$/ $$/   $$/"""
        )
        lines.append(f"  v{__version__}")
        lines.append("  ----------------------------------------------------")
        lines.append("")

        mode = "headless" if self.headless else "headed + vision"
        lines.append(
            f"  \033[32m*\033[0m Browser: {mode}"
        )

        if skills:
            lines.append(f"  \033[33m*\033[33m {len(skills)} skill(s) loaded")
            for s in skills:
                desc = s["description"]
                if len(desc) > 50:
                    desc = desc[:47] + "..."
                lines.append(f"      \033[36m-\033[0m {s['name']:25s} {desc}")

        lines.append("")
        lines.append(
            "  \033[36m/help\033[0m for commands   \033[36m/exit\033[0m to quit   just type to run a task"
        )
        lines.append("  ----------------------------------------------------")
        lines.append("")

        for line in lines:
            _cprint(line)

    def _get_llm(self) -> Any:
        if self._llm is None:
            from sediman.llm.provider import create_provider

            self._llm = create_provider(self.provider, self.model, self.base_url)
        return self._llm

    async def _get_browser(self) -> Any:
        if self._browser is None:
            from sediman.browser.session import BrowserSession

            self._browser = BrowserSession(headless=self.headless)
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
            )
            set_terminal_approval_callback(self._on_terminal_approval)
        return self._agent

    async def _on_terminal_approval(self, command: str, cwd: str) -> bool:
        _cprint(f"\n  \033[33m? Terminal:\033[0m {command}")
        if cwd and cwd != ".":
            _cprint(f"  \033[2m[cwd: {cwd}]\033[0m")

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: input("  Allow? [y/n/a(llow session)] ").strip().lower(),
            )
        except (EOFError, KeyboardInterrupt):
            _cprint("  \033[31mX Denied.\033[0m")
            return False

        if response in ("a", "allow", "always"):
            from sediman.agent.tools import set_terminal_allowed
            set_terminal_allowed(True)
            _cprint("  \033[32m+ Terminal approved for this session.\033[0m")
            return True

        if response in ("y", "yes"):
            return True

        _cprint("  \033[31mX Denied.\033[0m")
        return False

    def _on_browser_step(self, event: Any) -> None:
        from sediman.agent.loop import StepEvent

        if not isinstance(event, StepEvent):
            return

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

        phase_tags = {
            "planning": "~",
            "executing": ">",
            "observing": "?",
            "reflecting": "@",
            "delegating": "^",
            "done": "+",
            "failed": "!",
        }

        style = phase_styles.get(phase, "\033[0m")
        tag = phase_tags.get(phase, "-")
        rst = "\033[0m"
        dim = "\033[2m"

        _cprint(f"  {style}{tag}{rst} {action}")

        detail = getattr(event, "detail", "")
        if detail:
            _cprint(f"    {dim}{detail[:120]}{rst}")

        self._spinner_text = action[:60]
        self._tool_start_time = time.monotonic()

    def _start_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from sediman.scheduler.cron import CronManager

            with self._scheduler_lock:
                if self._scheduler is not None:
                    self._refresh_scheduler()
                    return
                self._scheduler = BackgroundScheduler(daemon=True)
                cron = CronManager()
                jobs = cron.list_jobs()
                for job in jobs:
                    if not job.get("enabled", True):
                        continue
                    parts = job["cron"].split()
                    if len(parts) != 5:
                        continue
                    trigger = CronTrigger(
                        minute=parts[0], hour=parts[1],
                        day=parts[2], month=parts[3], day_of_week=parts[4],
                    )
                    self._scheduler.add_job(
                        self._run_scheduled_job,
                        trigger=trigger,
                        id=job["id"],
                        args=[job],
                        replace_existing=True,
                    )
                self._scheduler.start()
                if jobs:
                    active = sum(1 for j in jobs if j.get("enabled", True))
                    print(f"  \033[36m[Scheduler]\033[0m {active} active job(s)")
        except ImportError:
            pass
        except Exception:
            pass

    def _refresh_scheduler(self) -> None:
        try:
            from apscheduler.triggers.cron import CronTrigger
            from sediman.scheduler.cron import CronManager

            with self._scheduler_lock:
                if self._scheduler is None:
                    return
                self._scheduler.remove_all_jobs()
                cron = CronManager()
                jobs = cron.list_jobs()
                for job in jobs:
                    if not job.get("enabled", True):
                        continue
                    parts = job["cron"].split()
                    if len(parts) != 5:
                        continue
                    trigger = CronTrigger(
                        minute=parts[0], hour=parts[1],
                        day=parts[2], month=parts[3], day_of_week=parts[4],
                    )
                    self._scheduler.add_job(
                        self._run_scheduled_job,
                        trigger=trigger,
                        id=job["id"],
                        args=[job],
                        replace_existing=True,
                    )
                if jobs:
                    active = sum(1 for j in jobs if j.get("enabled", True))
                    print(f"  \033[36m[Scheduler]\033[0m {active} active job(s)")
        except Exception:
            pass

    def _stop_scheduler(self) -> None:
        with self._scheduler_lock:
            if self._scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:
                    pass
                self._scheduler = None

        with self._cron_loops_lock:
            for loop in self._cron_loops:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except Exception:
                    pass
            self._cron_loops.clear()

    def _run_scheduled_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"][:8]
        task_desc = job.get("task", "")[:60]

        self._cron_messages.put(f"  [Cron] [{job_id}] {task_desc}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._cron_loops_lock:
            self._cron_loops.append(loop)
        with _suppress_logging():
            try:
                result = loop.run_until_complete(self._execute_scheduled_job(job))
                result_preview = (result or "No result")[:200]
                self._cron_messages.put(f"  [Done]  [{job_id}] {result_preview}")
            except Exception as e:
                self._cron_messages.put(f"  [Fail]  [{job_id}] {e}")
            finally:
                with self._cron_loops_lock:
                    if loop in self._cron_loops:
                        self._cron_loops.remove(loop)
                self._cleanup_loop(loop)

    def _flush_cron_messages(self) -> None:
        while True:
            try:
                msg = self._cron_messages.get_nowait()
                print(msg)
            except queue.Empty:
                break

    async def _execute_scheduled_job(self, job: dict[str, Any]) -> str:
        from sediman.scheduler.cron import execute_cron_job, CronManager
        result = await execute_cron_job(job)
        cron = CronManager()
        cron.update_job_result(job["id"], result)
        return result

    def run(self) -> None:
        from sediman.logging import suppress_noisy_loggers

        suppress_noisy_loggers()
        _install_global_log_filter()

        with _suppress_logging():
            from sediman.logging import ensure_db
            asyncio.get_event_loop().run_until_complete(ensure_db())

        self._start_scheduler()

        try:
            self._run_with_prompt_toolkit()
        except ImportError:
            self._run_fallback()

        self._stop_scheduler()

        if self._browser:
            with _suppress_logging():
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._browser.stop())
                    self._cleanup_loop(loop)
                except Exception:
                    pass

        self._kill_orphan_browsers()
        _remove_global_log_filter()

    @staticmethod
    def _kill_orphan_browsers() -> None:
        import signal
        try:
            import subprocess
            result = subprocess.run(
                ["pgrep", "-f", "chromium.*--remote-debugging"],
                capture_output=True, text=True, timeout=3,
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    os.kill(int(pid_str.strip()), signal.SIGKILL)
                except (ValueError, OSError):
                    pass
        except Exception:
            pass

    def _run_with_prompt_toolkit(self) -> None:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from pathlib import Path

        cli = self

        hist_path = Path.home() / ".sediman" / "history"
        hist_path.parent.mkdir(parents=True, exist_ok=True)

        completer = WordCompleter(_SLASH_NAMES, sentence=True)
        history = FileHistory(str(hist_path))

        os.system("cls" if os.name == "nt" else "clear")

        cli._print_banner()

        while not cli._should_exit:
            cli._flush_cron_messages()
            try:
                user_input = pt_prompt(
                    f" [{cli._task_count + 1}] > ",
                    completer=completer,
                    history=history,
                ).strip()
            except KeyboardInterrupt:
                print("")
                continue
            except EOFError:
                break

            if not user_input:
                continue

            cli._task_count += 1

            if user_input.startswith("/"):
                cli._handle_slash_sync(user_input)
            else:
                cli._agent_running = True
                cli._spinner_text = "Starting..."
                cli._tool_start_time = time.monotonic()
                try:
                    cli._run_task_sync(user_input)
                except KeyboardInterrupt:
                    print("\n  \033[33m-- Interrupted -- ready for next command.\033[0m")
                finally:
                    cli._agent_running = False
                    cli._spinner_text = ""
                    cli._tool_start_time = 0.0
                    cli._refresh_scheduler()
                    cli._flush_cron_messages()

        if cli._browser:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(cli._browser.stop())
                self._cleanup_loop(loop)
            except Exception:
                pass

    def _run_fallback(self) -> None:
        self._print_banner()

        while self._running:
            try:
                self._task_count += 1
                prompt_text = f" [{self._task_count}] > "
                user_input = input(prompt_text).strip()
            except (KeyboardInterrupt, EOFError):
                print("\n  Bye!")
                break

            if not user_input:
                self._task_count -= 1
                continue

            if user_input.startswith("/"):
                self._handle_slash_sync(user_input)
            else:
                self._run_task_sync(user_input)

        if self._browser:
            with _suppress_logging():
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._browser.stop())
                    self._cleanup_loop(loop)
                except Exception:
                    pass

    @staticmethod
    def _cleanup_loop(loop: asyncio.AbstractEventLoop) -> None:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def _run_task_sync(self, task: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._handle_task(task))
        except Exception as e:
            _cprint(f"\n  \033[31mX Task failed: {e}\033[0m\n")
        finally:
            self._cleanup_loop(loop)

    def _handle_slash_sync(self, cmd: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._handle_slash(cmd))
        except Exception as e:
            _cprint(f"  \033[31mX Command failed: {e}\033[0m")
        finally:
            self._cleanup_loop(loop)

    async def _handle_task(self, task: str) -> None:
        with _suppress_logging():
            try:
                agent = await self._get_agent()
            except Exception as e:
                _cprint(
                    f"\n  \033[31mX Failed to start agent: {e}\033[0m"
                )
                return

            self._spinner_text = "Working..."
            self._tool_start_time = time.monotonic()

            start = time.monotonic()
            try:
                result = await agent.run(task)
            except Exception as e:
                _cprint(f"\n  \033[31mX Task failed: {e}\033[0m\n")
                return

            elapsed = time.monotonic() - start
            self._spinner_text = ""
            self._tool_start_time = 0.0

            result_text = result.result or "No result returned."
            success = "Task could not be completed" not in result_text

            border_color = "green" if success else "red"
            icon = "+" if success else "X"
            header = f"{icon} Sediman  ({elapsed:.1f}s)" if success else f"{icon} Task Failed  ({elapsed:.1f}s)"

            try:
                from rich.markdown import Markdown
                content = Markdown(result_text)
            except Exception:
                content = Text()
                for line in result_text.split("\n"):
                    content.append(f"  {line}\n")

            _rich.print(
                Panel(
                    content,
                    title=Text(f"  {header}", style=border_color),
                    border_style=border_color,
                    padding=(0, 1),
                )
            )

            if result.skill_created:
                _cprint(f"  \033[35m* Skill auto-created: {result.skill_created}\033[0m")
            if result.scheduled_job_id:
                _cprint(
                    f"  \033[36m[Sched] Scheduled: {result.schedule_cron} -> job {result.scheduled_job_id[:8]}\033[0m"
                )
            _cprint("")

    async def _handle_slash(self, cmd: str) -> None:
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = {
            "/help": self._cmd_help,
            "/skills": self._cmd_skills,
            "/skill": self._cmd_skill_detail,
            "/run-skill": self._cmd_run_skill,
            "/hub": self._cmd_hub,
            "/memory": self._cmd_memory,
            "/remember": self._cmd_remember,
            "/model": self._cmd_model,
            "/models": self._cmd_models,
            "/schedule": self._cmd_schedule,
            "/schedule-add": self._cmd_schedule_add,
            "/schedule-remove": self._cmd_schedule_remove,
            "/sessions": self._cmd_sessions,
            "/screenshot": self._cmd_screenshot,
            "/browser": self._cmd_browser,
            "/status": self._cmd_status,
            "/soul": self._cmd_soul,
            "/record": self._cmd_record,
            "/stop": self._cmd_stop,
            "/delegate": self._cmd_delegate,
            "/parallel": self._cmd_parallel,
            "/compress": self._cmd_compress,
            "/clear": self._cmd_clear,
            "/reset": self._cmd_reset,
            "/terminal": self._cmd_terminal,
            "/exit": self._cmd_exit,
        }.get(command)

        if handler:
            try:
                await handler(args)
            except Exception as e:
                _cprint(f"  \033[31mX Command failed: {e}\033[0m")
        else:
            closest = self._find_closest_command(command)
            msg = f"  \033[31mUnknown command: {command}\033[0m"
            if closest:
                msg += f"\n  \033[2mDid you mean \033[36m{closest}\033[0m?\033[0m"
            msg += "\n  \033[2mType \033[36m/help\033[0m for a list of commands.\033[0m"
            _cprint(msg)

    def _find_closest_command(self, cmd: str) -> str | None:
        best = None
        best_score = float("inf")
        for name in _SLASH_NAMES:
            if not name:
                continue
            if cmd in name or name in cmd:
                return name
            score = sum(1 for a, b in zip(cmd, name) if a != b)
            if score < best_score and score <= 3:
                best_score = score
                best = name
        return best

    async def _cmd_help(self, _args: str) -> None:
        from rich.table import Table

        table = Table(
            title="Commands", show_header=False, box=None, padding=(0, 2)
        )
        table.add_column(style="yellow")
        table.add_column()
        for cmd, desc in _SLASH_COMMANDS.items():
            table.add_row(cmd, desc)
        _rich.print(table)
        _cprint("\n  Or just type a task and press Enter to run it.\n")

    async def _cmd_skills(self, _args: str) -> None:
        from rich.table import Table

        from sediman.skills.engine import SkillEngine

        engine = SkillEngine()
        skills = engine.list_skills()
        if not skills:
            _cprint(
                "  No skills yet. Skills are auto-created after complex tasks."
            )
            return
        table = Table(
            title="Skills",
            show_header=True,
            header_style="cyan",
            box=None,
            padding=(0, 2),
        )
        table.add_column("Name", style="green")
        table.add_column("Ver", style="dim")
        table.add_column("Category", style="dim")
        table.add_column("Description")
        for s in skills:
            table.add_row(
                s["name"],
                f"v{s.get('version', 1)}",
                s.get("category", ""),
                s["description"],
            )
        _rich.print(table)
        _cprint("")

    async def _cmd_skill_detail(self, args: str) -> None:
        if not args:
            _cprint("  Usage: \033[36m/skill <name>\033[0m")
            return
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine()
        skill = engine.read(args.strip())
        if not skill:
            _cprint(f"  \033[31mSkill '{args.strip()}' not found.\033[0m")
            return
        from sediman.display import render_skill_detail

        _rich.print(render_skill_detail(skill, title=skill.get("name")))

    async def _cmd_run_skill(self, args: str) -> None:
        if not args:
            _cprint("  Usage: \033[36m/run-skill <name>\033[0m")
            return
        from sediman.skills.engine import SkillEngine
        from sediman.skills.executor import execute_skill

        engine = SkillEngine()
        skill = engine.read(args.strip())
        if not skill:
            _cprint(f"  \033[31mSkill '{args.strip()}' not found.\033[0m")
            return

        _cprint(f"  \033[33m... Running skill: {skill['name']}...\033[0m")
        browser = await self._get_browser()
        llm = self._get_llm()
        import time

        try:
            start = time.monotonic()
            self._spinner_text = f"Executing {skill['name']}..."
            self._tool_start_time = start
            result = await execute_skill(skill, browser, llm)
            elapsed = time.monotonic() - start
            self._spinner_text = ""
            success = bool(result and "failed" not in result.lower())
            border = "32" if success else "31"
            header = f"\033[{border}m+ {skill['name']}  ({elapsed:.1f}s)\033[0m"
            _cprint(f"\n  {header}")
            _cprint(f"  {result or 'Skill completed with no output.'}")
        except Exception as e:
            self._spinner_text = ""
            _cprint(f"  \033[31mX Skill execution failed: {e}\033[0m")

    async def _cmd_hub(self, args: str) -> None:
        from rich.table import Table

        from sediman.skills.engine import SkillEngine
        from sediman.skills.hub import HubClient

        parts = args.split(maxsplit=1)
        subcmd = parts[0] if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if not subcmd or subcmd == "browse":
            client = HubClient()
            skills = client.browse(category=sub_args if subcmd else None)
            if not skills:
                _cprint("  No skills found in hub.")
                return
            table = Table(
                title=f"Skills Hub ({len(skills)} skills)",
                show_header=True,
                header_style="cyan",
                box=None,
                padding=(0, 2),
            )
            table.add_column("Name", style="cyan")
            table.add_column("Trust", style="green")
            table.add_column("Category", style="dim")
            table.add_column("Description")
            for s in skills:
                table.add_row(s.name, s.trust, s.category, s.description[:70])
            _rich.print(table)
            _cprint("")
        elif subcmd == "search":
            if not sub_args:
                _cprint("  Usage: \033[36m/hub search <query>\033[0m")
                return
            client = HubClient()
            skills = client.search(sub_args)
            if not skills:
                _cprint(f"  No skills matching '{sub_args}'.")
                return
            table = Table(
                title=f"Results for '{sub_args}'",
                show_header=True,
                header_style="cyan",
                box=None,
                padding=(0, 2),
            )
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            for s in skills:
                table.add_row(s.name, s.description[:70])
            _rich.print(table)
            _cprint("")
        elif subcmd == "install":
            if not sub_args:
                _cprint(
                    "  Usage: \033[36m/hub install <name> [--force]\033[0m"
                )
                return
            name = sub_args.replace("--force", "").strip()
            force = "--force" in sub_args
            client = HubClient()
            engine = SkillEngine()
            ok, msg = client.install(name, engine, force=force)
            if ok:
                _cprint(f"  \033[32m+ {msg}\033[0m")
            else:
                _cprint(f"  \033[31mX {msg}\033[0m")
        elif subcmd == "info":
            if not sub_args:
                _cprint("  Usage: \033[36m/hub info <name>\033[0m")
                return
            client = HubClient()
            info = client.info(sub_args.strip())
            if not info:
                _cprint(
                    f"  \033[31mSkill '{sub_args.strip()}' not found in hub.\033[0m"
                )
                return
            from sediman.display import render_skill_detail

            _rich.print(render_skill_detail(info, title=info["name"]))
        elif subcmd == "publish":
            if not sub_args:
                _cprint("  Usage: \033[36m/hub publish <name>\033[0m")
                return
            engine = SkillEngine()
            data = engine.read(sub_args.strip())
            if not data:
                _cprint(
                    f"  \033[31mSkill '{sub_args.strip()}' not found.\033[0m"
                )
                return
            from sediman.skills.format import SkillData

            skill_obj = SkillData(
                name=data["name"],
                description=data["description"],
                steps=data.get("steps", []),
                category=data.get("category", "general"),
            )
            client = HubClient()
            ok, msg = client.publish(skill_obj)
            if ok:
                _cprint(f"  \033[32m+ {msg}\033[0m")
            else:
                _cprint(f"  \033[31mX {msg}\033[0m")
        else:
            _cprint(
                "  Usage: \033[36m/hub [browse|search|install|info|publish]\033[0m"
            )

    async def _cmd_memory(self, _args: str) -> None:
        from sediman.memory.store import MemoryStore

        store = MemoryStore()
        all_entries = store.get_all_entries()
        mem_usage = store.get_usage("memory")
        user_usage = store.get_usage("user")

        if not any(all_entries.values()):
            _cprint(
                "  No memory stored. Use \033[36m/remember <text>\033[0m to add."
            )
            return

        _rich.print(
            Panel(
                Text(
                    "\n\n".join(mem_usage.entries)
                    if mem_usage.entries
                    else "(empty)"
                ),
                title=Text(
                    f"  MEMORY [{mem_usage.formatted}]",
                    style="cyan",
                ),
                border_style="cyan",
                padding=(0, 1),
            )
        )
        if user_usage.entries:
            _rich.print(
                Panel(
                    Text("\n\n".join(user_usage.entries)),
                    title=Text(
                        f"  USER PROFILE [{user_usage.formatted}]",
                        style="green",
                    ),
                    border_style="green",
                    padding=(0, 1),
                )
            )

    async def _cmd_remember(self, args: str) -> None:
        if not args:
            _cprint("  Usage: \033[36m/remember <text to save>\033[0m")
            return
        from sediman.memory.store import MemoryStore

        store = MemoryStore()
        result = store.add("memory", args)
        if result.success:
            _cprint("  \033[32m+ Saved to memory.\033[0m")
        else:
            _cprint(f"  \033[31mX {result.message}\033[0m")

    async def _cmd_model(self, args: str) -> None:
        if not args:
            _cprint(
                f"  Current: \033[32m{self.provider}\033[0m / \033[32m{self.model or 'default'}\033[0m"
            )
            if self.base_url:
                _cprint(f"  Base URL: {self.base_url}")
            return

        old_provider = self.provider
        old_model = self.model
        old_llm = self._llm

        if ":" in args:
            provider, model = args.split(":", 1)
        else:
            provider = self.provider
            model = args

        self.provider = provider
        self.model = model
        self._llm = None
        conv = self._agent.get_conversation() if self._agent else []
        self._agent = None

        try:
            agent = await self._get_agent()
            if conv:
                agent.set_conversation(conv)
            _cprint(
                f"  \033[32m+ Switched to {provider}:{model}\033[0m"
            )
        except Exception as e:
            self.provider = old_provider
            self.model = old_model
            self._llm = old_llm
            self._agent = None
            _cprint(
                f"  \033[31mX Failed to switch to {provider}:{model}: {e}\033[0m"
            )

    async def _cmd_models(self, _args: str) -> None:
        from rich.table import Table

        from sediman.llm.provider import PROVIDERS

        table = Table(
            title="Available Providers",
            show_header=True,
            header_style="cyan",
            box=None,
            padding=(0, 2),
        )
        table.add_column("Provider", style="green")
        table.add_column("Model")
        table.add_column("Base URL", style="dim")
        for name, config in PROVIDERS.items():
            table.add_row(
                name, config["model"], config.get("base_url", "default")
            )
        _rich.print(table)
        _cprint("\n  Switch with: \033[36m/model <provider:model>\033[0m")

    async def _cmd_schedule(self, _args: str) -> None:
        from rich.table import Table

        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        jobs = cron.list_jobs()
        if not jobs:
            _cprint(
                "  No scheduled tasks. Use \033[36m/schedule-add <cron> <task>\033[0m"
            )
            return
        table = Table(
            title="Scheduled Tasks",
            show_header=True,
            header_style="cyan",
            box=None,
            padding=(0, 2),
        )
        table.add_column("ID", style="dim")
        table.add_column("Cron")
        table.add_column("Task")
        for j in jobs:
            status = (
                "\033[32mo\033[0m"
                if j.get("enabled", True)
                else "\033[31mx\033[0m"
            )
            table.add_row(f"{status} {j['id'][:8]}", j["cron"], j["task"])
            if j.get("last_run"):
                table.add_row("", f"Last: {j['last_run'][:19]}", "")
        _rich.print(table)
        _cprint("")

    async def _cmd_schedule_add(self, args: str) -> None:
        if not args:
            _cprint(
                "  Usage: \033[36m/schedule-add <cron> <task>\033[0m"
            )
            _cprint(
                "  Example: /schedule-add '0 * * * *' 'check stock price'"
            )
            return
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            _cprint("  Need both cron expression and task description.")
            return
        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        try:
            job_id = cron.add_job(
                cron_expr=parts[0],
                task=parts[1],
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
            )
        except ValueError as e:
            _cprint(f"  \033[31m{e}\033[0m")
            return
        _cprint(
            f"  \033[32m+ Scheduled: [{job_id[:8]}] {parts[0]} -> {parts[1]}\033[0m"
        )

    async def _cmd_schedule_remove(self, args: str) -> None:
        if not args:
            _cprint(
                "  Usage: \033[36m/schedule-remove <job_id>\033[0m"
            )
            _cprint(
                "  Tip: Use the 8-char ID shown in \033[36m/schedule\033[0m"
            )
            return
        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        if cron.remove_job(args.strip()):
            _cprint(f"  \033[32m+ Removed: {args.strip()[:8]}\033[0m")
        else:
            _cprint(f"  \033[31mJob '{args.strip()[:8]}' not found.\033[0m")
            _cprint(
                "  \033[2mUse \033[36m/schedule\033[0m to list jobs with their IDs.\033[0m"
            )

    async def _cmd_sessions(self, _args: str) -> None:
        from rich.table import Table

        from sediman.memory.sessions import get_recent_sessions

        sessions = await get_recent_sessions()
        if not sessions:
            _cprint("  No sessions yet.")
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        table = Table(
            title="Recent Sessions",
            show_header=True,
            header_style="cyan",
            box=None,
            padding=(0, 2),
        )
        table.add_column("ID", style="dim")
        table.add_column("Task")
        table.add_column("When", style="dim")
        for s in sessions[:10]:
            task_text = s["task"][:55]
            if len(s["task"]) > 55:
                task_text += "..."
            created = s.get("created_at", "")
            rel = _relative_time(created, now)
            table.add_row(str(s["id"])[:8], task_text, rel)
        _rich.print(table)
        _cprint("")

    async def _cmd_screenshot(self, _args: str) -> None:
        import base64

        from pathlib import Path

        browser = await self._get_browser()
        b64 = await browser.take_screenshot()
        if b64:
            path = Path.home() / ".sediman" / "last_screenshot.png"
            path.write_bytes(base64.b64decode(b64))
            _cprint(f"  \033[32m+ Screenshot saved to {path}\033[0m")
        else:
            _cprint("  \033[31mNo browser page available.\033[0m")

    async def _cmd_browser(self, args: str) -> None:
        if not args.strip():
            mode = "headless" if self.headless else "headed + vision"
            _cprint(
                f"  Browser: \033[32m{mode}\033[0m\n"
                f"  Switch with: \033[36m/browser headless\033[0m or \033[36m/browser headed\033[0m"
            )
            return

        new_mode = args.strip().lower()
        if new_mode not in ("headless", "headed"):
            _cprint(
                "  \033[31mUnknown mode. Use \033[36mheadless\033[0m\033[31m or \033[36mheaded\033[0m"
            )
            return

        new_headless = new_mode == "headless"
        if new_headless == self.headless:
            _cprint(f"  Already in {new_mode} mode.")
            return

        if self._browser:
            with _suppress_logging():
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self._browser.stop())
                    self._cleanup_loop(loop)
                except Exception:
                    pass
            self._browser = None
            self._agent = None

        self.headless = new_headless
        mode = "headless" if self.headless else "headed + vision"
        _cprint(f"  \033[32m+ Switched to {mode}\033[0m")

    async def _cmd_status(self, _args: str) -> None:
        from rich.table import Table

        table = Table(
            title="Status", show_header=False, box=None, padding=(0, 2)
        )
        table.add_column(style="dim")
        table.add_column()

        browser_mode = "headless" if self.headless else "headed + vision"
        browser_status = (
            "running"
            if self._browser and self._browser.is_started
            else "not started"
        )
        table.add_row(
            "Browser:", f"{browser_status} ({browser_mode})"
        )
        table.add_row("Provider:", self.provider)
        table.add_row("Model:", self.model or "default")
        if self.base_url:
            table.add_row("Base URL:", self.base_url)
        table.add_row("Tasks run:", str(self._task_count))

        if self._agent:
            conv_len = len(self._agent.get_conversation())
            table.add_row(
                "Conversation:",
                f"{conv_len // 2} turns ({conv_len} messages)",
            )

        _rich.print(table)
        _cprint("")

    async def _cmd_soul(self, args: str) -> None:
        from sediman.agent.soul import load_soul, save_soul, reset_soul

        if not args:
            soul = load_soul()
            _rich.print(
                Panel(
                    Text(soul),
                    title=Text(
                        "  Personality (SOUL.md)", style="cyan"
                    ),
                    border_style="cyan",
                    padding=(0, 1),
                )
            )
            _cprint(
                "  Change with: \033[36m/soul <text>\033[0m   Reset with: \033[36m/soul reset\033[0m"
            )
        elif args.strip().lower() == "reset":
            reset_soul()
            _cprint("  \033[32m+ Personality reset to default.\033[0m")
        else:
            save_soul(args)
            _cprint(
                "  \033[32m+ Personality updated. Takes effect on next task.\033[0m"
            )

    async def _cmd_record(self, args: str) -> None:
        if not args:
            _cprint("  Usage: \033[36m/record <name> [--desc description]\033[0m")
            _cprint("  Example: /record post-medium-article --desc \"Post an article on Medium\"")
            return

        parts = args.split()
        name = parts[0]

        desc = None
        if "--desc" in parts:
            idx = parts.index("--desc")
            if idx + 1 < len(parts):
                desc = " ".join(parts[idx + 1:])

        from sediman.agent.recording_manager import RecordingManager

        manager = RecordingManager.get_instance()
        if manager.is_recording(name):
            _cprint(f"  \033[31mAlready recording '{name}'. Use \033[36m/stop\033[0m\033[31m first.\033[0m")
            return

        if manager.is_recording():
            _cprint(f"  \033[31mAnother recording is active. Use \033[36m/stop\033[0m\033[31m first.\033[0m")
            return

        browser = await self._get_browser()

        try:
            session = await manager.start_recording(
                name=name,
                browser=browser,
                description=desc,
                fps=3,
                max_duration=300,
            )
            _cprint(f"  \033[32m● Recording started: {name}\033[0m (session {session.id})")
            _cprint(f"  \033[2mPerform your task in the browser. Use \033[36m/stop\033[0m\033[2m when done.\033[0m")
        except Exception as e:
            _cprint(f"  \033[31mX Failed to start recording: {e}\033[0m")

    async def _cmd_stop(self, _args: str) -> None:
        from sediman.agent.recording_manager import RecordingManager

        manager = RecordingManager.get_instance()
        active = manager.get_active_sessions()

        if not active:
            _cprint("  \033[33mNo active recording. Use \033[36m/record <name>\033[0m\033[33m to start one.\033[0m")
            return

        session = active[0]
        name = session.name

        _cprint(f"  \033[33mStopping recording '{name}'...\033[0m")

        try:
            recording = await manager.stop_recording(name)
        except Exception as e:
            _cprint(f"  \033[31mX Failed to stop recording: {e}\033[0m")
            return

        _cprint(
            f"  \033[32m+ Recording stopped:\033[0m "
            f"{recording.frame_count} frames, "
            f"{recording.duration_seconds:.1f}s, "
            f"{len(recording.actions)} actions"
        )

        _cprint("  \033[33mAnalyzing recording with AI...\033[0m")

        try:
            from sediman.agent.trace_to_skill import TraceToSkill

            llm = self._get_llm()
            converter = TraceToSkill(llm)
            skill_data = await converter.convert(recording)

            if not skill_data:
                _cprint(
                    "  \033[33mCould not extract a skill.\033[0m "
                    "The recording may be too short or the task too simple."
                )
                return

            from sediman.skills.engine import SkillEngine

            engine = SkillEngine()
            existing = engine.read(skill_data["skill_name"])
            if existing:
                engine.patch(skill_data["skill_name"], {
                    "description": skill_data["description"],
                    "steps": skill_data["steps"],
                    "when_to_use": skill_data.get("when_to_use"),
                    "pitfalls": skill_data.get("pitfalls", []),
                    "verification": skill_data.get("verification"),
                })
                _cprint(f"  \033[33mUpdated existing skill: {skill_data['skill_name']}\033[0m")
            else:
                engine.create(
                    name=skill_data["skill_name"],
                    description=skill_data["description"],
                    steps=skill_data["steps"],
                    category=skill_data.get("category", "recorded"),
                    when_to_use=skill_data.get("when_to_use"),
                    pitfalls=skill_data.get("pitfalls", []),
                    verification=skill_data.get("verification"),
                )

            steps_preview = "\n".join(
                f"    {i}. {s}" for i, s in enumerate(skill_data["steps"][:5], 1)
            )
            _cprint(
                f"\n  \033[32m+ Skill created: {skill_data['skill_name']}\033[0m\n"
                f"  {skill_data['description']}\n"
                f"{steps_preview}\n"
                f"\n  \033[2mRun with: \033[36m/run-skill {skill_data['skill_name']}\033[0m"
            )
            _cprint("")

        except Exception as e:
            _cprint(f"  \033[31mX Failed to analyze recording: {e}\033[0m")
        finally:
            manager.cleanup(name)

    async def _cmd_delegate(self, args: str) -> None:
        if not args:
            _cprint("  Usage: \033[36m/delegate <task>\033[0m")
            _cprint("  Runs a task as an isolated subagent.")
            return
        import time

        from sediman.agent.delegate import delegate_task

        _cprint("  \033[33m... Delegating to subagent...\033[0m")
        browser = await self._get_browser()
        llm = self._get_llm().get_browser_use_llm()
        try:
            start = time.monotonic()
            self._spinner_text = "Subagent working..."
            self._tool_start_time = start
            result = await delegate_task(args, browser, llm)
            elapsed = time.monotonic() - start
            self._spinner_text = ""
            border = "32" if "failed" not in result.lower() else "31"
            _cprint(
                f"\n  \033[{border}m+ Subagent  ({elapsed:.1f}s)\033[0m"
            )
            _cprint(f"  {result or 'Subagent completed with no output.'}")
            _cprint("")
        except Exception as e:
            self._spinner_text = ""
            _cprint(f"  \033[31mX Subagent failed: {e}\033[0m")

    async def _cmd_parallel(self, args: str) -> None:
        if not args or "|" not in args:
            _cprint(
                "  Usage: \033[36m/parallel <task1> | <task2> | <task3>\033[0m"
            )
            _cprint("  Runs up to 5 tasks in parallel.")
            return
        import time

        from sediman.agent.delegate import delegate_parallel

        tasks = [t.strip() for t in args.split("|") if t.strip()]
        if len(tasks) > 5:
            _cprint(
                f"  \033[33mWarning: Truncating to 5 tasks (got {len(tasks)}).\033[0m"
            )
            tasks = tasks[:5]
        _cprint(
            f"  \033[33m... Running {len(tasks)} tasks in parallel...\033[0m"
        )
        browser = await self._get_browser()
        llm = self._get_llm()
        try:
            start = time.monotonic()
            self._spinner_text = f"Running {len(tasks)} tasks..."
            self._tool_start_time = start
            results = await delegate_parallel(tasks, browser, llm)
            elapsed = time.monotonic() - start
            self._spinner_text = ""

            for i, (task_text, result) in enumerate(zip(tasks, results)):
                _cprint(
                    f"  \033[1;36mTask {i + 1}:\033[0m {task_text}"
                )
                display = (
                    result
                    if len(result) <= 300
                    else result[:297] + "..."
                )
                _cprint(f"    \033[32m-> {display}\033[0m")
            _cprint(
                f"\n  \033[2mAll {len(tasks)} tasks completed in {elapsed:.1f}s\033[0m"
            )
            _cprint("")
        except Exception as e:
            self._spinner_text = ""
            _cprint(
                f"  \033[31mX Parallel execution failed: {e}\033[0m"
            )

    async def _cmd_compress(self, _args: str) -> None:
        if self._agent is None:
            _cprint(
                "  Nothing to compress — no agent session yet."
            )
            return

        conv = self._agent.get_conversation()
        if len(conv) <= 4:
            _cprint(
                "  Nothing to compress — conversation is short."
            )
            return

        try:
            self._spinner_text = "Compressing context..."
            removed = await self._agent.compress_context()
            self._spinner_text = ""
            if removed > 0:
                _cprint(
                    f"  \033[32m+ Compressed: removed {removed} messages. {len(self._agent.get_conversation())} remaining.\033[0m"
                )
            else:
                _cprint(
                    "  \033[33mCould not compress further. Try /clear to start fresh.\033[0m"
                )
        except Exception as e:
            self._spinner_text = ""
            _cprint(f"  \033[31mX Compression failed: {e}\033[0m")

    async def _cmd_clear(self, _args: str) -> None:
        if self._agent is None:
            _cprint(
                "  \033[32m+ Already clear — no active session.\033[0m"
            )
            return
        self._agent.clear_conversation()
        _cprint(
            "  \033[32m+ Conversation cleared. Browser and skills kept.\033[0m"
        )

    async def _cmd_terminal(self, args: str) -> None:
        from sediman.agent.tools import is_terminal_allowed, set_terminal_allowed

        sub = args.strip().lower()
        if sub == "on":
            set_terminal_allowed(True)
            _cprint("  \033[32m+ Terminal access: approved for this session.\033[0m")
            _cprint("  \033[2mAll commands will execute without asking.\033[0m")
        elif sub == "off":
            set_terminal_allowed(False)
            _cprint("  \033[33m* Terminal access: each command requires approval.\033[0m")
        else:
            if is_terminal_allowed():
                _cprint("  Terminal access: \033[32mapproved\033[0m (all commands allowed)")
            else:
                _cprint("  Terminal access: \033[33mapproval required\033[0m (each command asks)")
            _cprint("  \033[2mUse \033[36m/terminal on\033[0m\033[2m or \033[36m/terminal off\033[0m\033[2m to change.\033[0m")

    async def _cmd_reset(self, _args: str) -> None:
        from sediman.agent.tools import reset_terminal_state

        self._agent = None
        self._llm = None
        self._task_count = 0
        reset_terminal_state()
        _cprint("  \033[32m+ Full reset. Starting fresh session.\033[0m")

    async def _cmd_exit(self, _args: str) -> None:
        _cprint("  \033[36mBye!\033[0m")
        self._running = False
        self._should_exit = True
