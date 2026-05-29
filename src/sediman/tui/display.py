"""Print helpers, Rich adapter, banner — extracted from tui.py."""

from __future__ import annotations

import shutil
from io import StringIO

from rich.console import Console

from sediman import __version__

_SPINNER_FRAMES = ("-", "\\", "|", "/")


def cprint(text: str) -> None:
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


def relative_time(timestamp: str, now) -> str:
    from sediman.utils import relative_time as _rt

    return _rt(timestamp, now)


def _get_skills_list() -> list:
    try:
        from sediman.skills.engine import SkillEngine

        return SkillEngine().list_skills()
    except Exception:
        return []


def print_banner(headless: bool) -> None:
    skills = _get_skills_list()
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
    $$$$$$/   $$$$$$$/  $$$$$$$/ $$/ $$/  |$$/  $$/  $$$$$$$/ $$/   $$/"""
    )
    lines.append(f"  v{__version__}")
    lines.append("  ----------------------------------------------------")
    lines.append("")

    mode = "headless" if headless else "headed + vision"
    lines.append(f"  \033[32m*\033[0m Browser: {mode}")

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
        cprint(line)
