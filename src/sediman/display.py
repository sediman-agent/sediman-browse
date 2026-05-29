from __future__ import annotations

import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

console = Console()

COLORS = {
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "info": "cyan",
    "muted": "dim",
    "accent": "bright_blue",
    "badge": "magenta",
}

SYMBOLS = {
    "success": "✓",
    "error": "✗",
    "progress": "◌",
    "info": "◈",
    "scheduled": "⏰",
    "skill": "◈",
}


@dataclass
class TaskProgress:
    task: str = ""
    phase: str = "idle"
    step: int = 0
    total_steps: int = 0
    action: str = ""
    url: str = ""
    elapsed: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    _live: Live | None = field(default=None, repr=False)

    def start(self, task: str) -> None:
        self.task = task
        self.phase = "starting"
        self.start_time = time.monotonic()
        self.step = 0
        self.total_steps = 0
        spinner = Spinner("dots", self._render_text())
        self._live = Live(spinner, console=console, transient=True, refresh_per_second=4)
        self._live.start()

    def update(
        self,
        phase: str | None = None,
        step: int | None = None,
        action: str | None = None,
        url: str | None = None,
    ) -> None:
        if phase is not None:
            self.phase = phase
        if step is not None:
            self.step = step
        if action is not None:
            self.action = action
        if url is not None:
            self.url = url
        self.elapsed = time.monotonic() - self.start_time
        if self._live:
            self._live.update(Spinner("dots", self._render_text()))

    def _render_text(self) -> Text:
        parts: list[tuple[str, str]] = []

        phase_labels = {
            "starting": "Starting",
            "planning": "Planning",
            "executing": "Executing",
            "observing": "Observing",
            "reflecting": "Reflecting",
            "delegating": "Delegating",
            "healing": "Self-healing",
        }
        label = phase_labels.get(self.phase, self.phase.title())
        parts.append((f"  {label}", COLORS["info"]))

        if self.action:
            action_display = self.action[:80]
            if action_display != self.action:
                action_display += "..."
            parts.append((" — ", "dim"))
            parts.append((action_display, "white"))

        elapsed_str = f"{self.elapsed:.0f}s"
        parts.append((f"  [{elapsed_str}]", "dim"))

        text = Text()
        for content, style in parts:
            text.append(content, style=style)
        return text

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None


def print_error(message: str, suggestion: str | None = None) -> None:
    body = Text()
    body.append(f"  {SYMBOLS['error']} ", style=COLORS["error"])
    body.append(message)
    if suggestion:
        body.append(f"\n  → {suggestion}", style="dim")
    console.print(Panel(body, border_style=COLORS["error"], padding=(0, 1)))


def print_success(title: str, body_text: str, elapsed: float | None = None) -> None:
    lines = body_text.split("\n")
    content = Text()
    for i, line in enumerate(lines):
        content.append(f"  {line}")
        if i < len(lines) - 1:
            content.append("\n")

    header = f"{SYMBOLS['success']} {title}"
    if elapsed is not None:
        header += f"  ({elapsed:.1f}s)"

    console.print()
    console.print(Panel(
        content,
        title=Text(header, style=COLORS["success"]),
        border_style=COLORS["success"],
        padding=(0, 1),
    ))


def print_result_panel(result: str, elapsed: float | None = None, success: bool = True) -> None:
    if success:
        header = f"{SYMBOLS['success']} Sediman"
        if elapsed is not None:
            header += f"  ({elapsed:.1f}s)"
        border_color = COLORS["success"]
    else:
        header = f"{SYMBOLS['error']} Task Failed"
        if elapsed is not None:
            header += f"  ({elapsed:.1f}s)"
        border_color = COLORS["error"]

    console.print()

    try:
        from rich.markdown import Markdown
        console.print(Panel(
            Markdown(result),
            title=Text(header, style=border_color),
            border_style=border_color,
            padding=(0, 1),
        ))
    except Exception:
        content = Text()
        for line in result.split("\n"):
            content.append(f"  {line}\n")
        console.print(Panel(
            content,
            title=Text(header, style=border_color),
            border_style=border_color,
            padding=(0, 1),
        ))


def print_badges(skill_created: str | None = None, scheduled_job_id: str | None = None, schedule_cron: str | None = None) -> None:
    if skill_created:
        console.print(f"  {SYMBOLS['skill']} Skill auto-created: [magenta]{skill_created}[/magenta]")
    if scheduled_job_id:
        console.print(f"  {SYMBOLS['scheduled']} Scheduled: [cyan]{schedule_cron}[/cyan] → job {scheduled_job_id[:8]}")


def print_startup_banner(provider: str, model: str | None, headless: bool, mode: str = "task") -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style=COLORS["success"], width=1)
    table.add_column(style="white")

    model_str = model or "default"
    mode_str = "headless" if headless else "headed + vision"

    table.add_row("⏺", f"{provider}/{model_str}")
    table.add_row("⏺", f"browser: {mode_str}")

    console.print()
    console.print(Panel(table, title=Text(f"Sediman — {mode}", style=COLORS["accent"]), border_style=COLORS["accent"], padding=(0, 1)))
    console.print()


def format_error_message(exc: Exception) -> tuple[str, str | None]:
    from sediman.errors import classify_error
    info = classify_error(exc)
    return info.message, info.suggestion


def friendly_error(exc: Exception) -> None:
    message, suggestion = format_error_message(exc)
    print_error(message, suggestion)


def render_skill_detail(skill_data: dict, title: str | None = None) -> Panel:
    content = Text()
    name = title or skill_data.get("name", "Skill")
    content.append(f"  Description:  {skill_data.get('description', '')}\n")
    content.append(f"  Version:      {skill_data.get('version', 1)}\n")
    content.append(f"  Category:     {skill_data.get('category', 'general')}\n")
    if skill_data.get("created_at"):
        content.append(f"  Created:      {skill_data['created_at']}\n")
    if skill_data.get("trust"):
        content.append(f"  Trust:        {skill_data['trust']}\n")
    if skill_data.get("author"):
        content.append(f"  Author:       {skill_data['author']}\n")
    if skill_data.get("variables"):
        content.append(f"  Variables:    {', '.join(skill_data['variables'])}\n")
    if skill_data.get("warnings"):
        content.append("\n  Warnings:\n", style="yellow")
        for w in skill_data["warnings"]:
            content.append(f"    - {w}\n", style="yellow")
    content.append("\n  Steps:\n")
    for i, step in enumerate(skill_data.get("steps", []), 1):
        content.append(f"    {i}. {step}\n")
    return Panel(content, title=Text(f"  {name}", style="cyan"), border_style="cyan", padding=(0, 1))
