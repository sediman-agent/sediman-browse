from __future__ import annotations

import asyncio
import sys

import click
import structlog

from sediman import __version__

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

PROVIDER_CHOICES = click.Choice(["openai", "ollama"])


def _validate_startup(provider: str, model: str | None, base_url: str | None) -> None:
    import os

    from sediman.display import print_error

    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            print_error(
                "OPENAI_API_KEY is not set.",
                "Run: export OPENAI_API_KEY=sk-...",
            )
            sys.exit(1)


@click.group()
@click.version_option(__version__)
def main() -> None:
    """Sediman — a self-improving browser agent.

    \b
    sediman run "search for laptops on Amazon"
    sediman chat
    sediman skill list
    sediman serve --port 8080
    """
    pass


@main.command()
@click.argument("task")
@click.option("--model", default=None, help="LLM model to use")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider (openai, ollama)")
@click.option("--base-url", default=None, help="Override the default LLM API endpoint (e.g. for local/proxy)")
@click.option("--headless/--no-headless", default=False, help="Run browser headless (no visible window)")
@click.option("--timeout", default=None, type=int, help="Max seconds to run before cancelling")
@click.option("--verbose", is_flag=True, help="Show detailed logs")
def run(task: str, model: str | None, provider: str, base_url: str | None, headless: bool, timeout: int | None, verbose: bool) -> None:
    """Run a one-shot browser task."""
    if verbose:
        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(10))

    _validate_startup(provider, model, base_url)

    from sediman.logging import suppress_noisy_loggers
    suppress_noisy_loggers()

    try:
        asyncio.run(_run_task(task, model, provider, base_url, headless, timeout))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        from sediman.display import friendly_error
        friendly_error(exc)
        sys.exit(1)


@main.command()
@click.option("--model", default=None, help="LLM model to use")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider (openai, ollama)")
@click.option("--base-url", default=None, help="Override the default LLM API endpoint")
@click.option("--headless/--no-headless", default=False, help="Run browser headless")
def chat(model: str | None, provider: str, base_url: str | None, headless: bool) -> None:
    """Interactive agent session with slash commands."""
    _validate_startup(provider, model, base_url)

    from sediman.tui import SedimanTUI

    tui = SedimanTUI(provider=provider, model=model, base_url=base_url, headless=headless)
    try:
        tui.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        from sediman.display import friendly_error
        friendly_error(exc)
        sys.exit(1)


@main.group()
def skill() -> None:
    """Manage skills (list, run, create, delete, browse hub)."""
    pass


@skill.command("list")
def skill_list() -> None:
    """List all skills."""
    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skills = engine.list_skills()

    if not skills:
        from sediman.display import console
        console.print("  No skills found. Skills are created automatically after complex tasks.")
        return

    from rich.table import Table
    from sediman.display import console

    table = Table(title="Skills", show_header=True, header_style="cyan", box=None, padding=(0, 2))
    table.add_column("Name", style="green")
    table.add_column("Category", style="dim")
    table.add_column("Description")

    for s in skills:
        table.add_row(s["name"], s.get("category", ""), s["description"])

    console.print(table)


@skill.command("run")
@click.argument("name")
@click.option("--model", default=None, help="LLM model to use")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--base-url", default=None, help="Override the default LLM API endpoint")
@click.option("--headless/--no-headless", default=False, help="Run browser headless")
def skill_run(name: str, model: str | None, provider: str, base_url: str | None, headless: bool) -> None:
    """Run a saved skill."""
    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skill_data = engine.read(name)

    if not skill_data:
        from sediman.display import print_error
        print_error(f"Skill '{name}' not found.", "Use 'sediman skill list' to see available skills.")
        sys.exit(1)

    _validate_startup(provider, model, base_url)

    from sediman.logging import suppress_noisy_loggers
    suppress_noisy_loggers()

    from sediman.display import print_startup_banner
    print_startup_banner(provider, model, headless, mode=f"skill: {name}")

    try:
        asyncio.run(_run_skill(skill_data, model, provider, base_url, headless))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        from sediman.display import friendly_error
        friendly_error(exc)
        sys.exit(1)


@skill.command("show")
@click.argument("name")
def skill_show(name: str) -> None:
    """Show skill details."""
    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skill_data = engine.read(name)

    if not skill_data:
        from sediman.display import print_error
        print_error(f"Skill '{name}' not found.")
        sys.exit(1)

    from sediman.display import console, render_skill_detail

    console.print(render_skill_detail(skill_data, title=name))


@skill.command("delete")
@click.argument("name")
@click.confirmation_option(prompt=f"Delete this skill?")
def skill_delete(name: str) -> None:
    """Delete a skill."""
    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    if engine.delete(name):
        from sediman.display import print_success
        print_success("Deleted", f"Skill '{name}' removed.")
    else:
        from sediman.display import print_error
        print_error(f"Skill '{name}' not found.")
        sys.exit(1)


@skill.command("add")
@click.argument("name", required=False)
@click.option("--desc", default=None, help="Skill description")
@click.option("--steps", multiple=True, help="Skill steps (repeatable)")
@click.option("--category", default=None, help="Skill category")
@click.option("--from", "from_file", default=None, help="Import from JSON/YAML file")
def skill_add(name: str | None, desc: str | None, steps: tuple[str, ...], category: str | None, from_file: str | None) -> None:
    """Create a new skill. Prompts for missing fields.

    \b
    sediman skill add my-skill --desc "..." --steps "step 1" --steps "step 2"
    sediman skill add --from ./skill.json
    sediman skill add              # fully interactive
    """
    import json
    from pathlib import Path

    if from_file:
        p = Path(from_file)
        if not p.exists():
            from sediman.display import print_error
            print_error(f"File not found: {from_file}")
            sys.exit(1)

        raw = p.read_text()
        if p.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(raw)
            except ImportError:
                from sediman.display import print_error
                print_error("PyYAML not installed.", "Use JSON or: pip install pyyaml")
                sys.exit(1)
            except Exception as exc:
                from sediman.display import print_error
                print_error(f"Invalid YAML file: {exc}")
                sys.exit(1)
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                from sediman.display import print_error
                print_error(f"Invalid JSON file: {exc}")
                sys.exit(1)

        if not name:
            name = data.get("name")
        if not desc:
            desc = data.get("description")
        if not steps:
            steps = tuple(data.get("steps", []))
        if not category:
            category = data.get("category")

    if not name:
        name = click.prompt("Skill name")
    if not desc:
        desc = click.prompt("Description")
    if not steps:
        from sediman.display import console
        console.print("  Add steps (enter empty line to finish):")
        step_list: list[str] = []
        i = 1
        while True:
            step = click.prompt(f"  Step {i}", default="", show_default=False)
            if not step:
                break
            step_list.append(step)
            i += 1
        steps = tuple(step_list)
    if not category:
        category = click.prompt("Category", default="general")

    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    try:
        engine.create(name=name, description=desc, steps=list(steps), category=category)
    except ValueError as e:
        from sediman.display import print_error
        print_error(str(e))
        sys.exit(1)

    from sediman.display import print_success
    print_success("Created", f"Skill '{name}' with {len(steps)} step(s).")


@skill.command("record")
@click.argument("name")
@click.option("--desc", default=None, help="Skill description")
@click.option("--model", default=None, help="LLM model to use")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--base-url", default=None, help="Override the default LLM API endpoint")
@click.option("--fps", default=3, type=int, help="Frames per second for recording (default: 3)")
@click.option("--max-duration", default=300, type=int, help="Max recording duration in seconds (default: 300)")
def skill_record(name: str, desc: str | None, model: str | None, provider: str, base_url: str | None, fps: int, max_duration: int) -> None:
    """Record your browser actions as a reusable skill.

    Opens a browser. Perform your task. Press Ctrl+C when done.
    The agent will analyze your recording and create a skill.

    \b
    sediman skill record post-medium-article
    sediman skill record send-gmail --desc "Send an email via Gmail"
    """
    _validate_startup(provider, model, base_url)

    from sediman.logging import suppress_noisy_loggers
    suppress_noisy_loggers()

    try:
        asyncio.run(_record_skill(name, desc, model, provider, base_url, fps, max_duration))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        from sediman.display import friendly_error
        friendly_error(exc)
        sys.exit(1)


@skill.command("install-bundled")
def skill_install_bundled() -> None:
    """Install bundled skill templates."""
    import json
    from pathlib import Path

    from sediman.skills.engine import SkillEngine

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    bundled_dir = project_root / "skills"

    if not bundled_dir.exists():
        bundled_dir = Path.cwd() / "skills"

    if not bundled_dir.exists():
        from sediman.display import print_error
        print_error("No bundled skills found.", "Run from the project root directory.")
        sys.exit(1)

    engine = SkillEngine()
    installed = 0
    for skill_dir in sorted(bundled_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "skill.json"
        if not skill_file.exists():
            continue

        data = json.loads(skill_file.read_text())
        existing = engine.read(data["name"])
        if existing:
            from sediman.display import console
            console.print(f"  Skipping {data['name']} (already exists)")
            continue

        engine.create(
            name=data["name"],
            description=data["description"],
            steps=data.get("steps", []),
            category=data.get("category", "bundled"),
        )
        from sediman.display import console
        console.print(f"  Installed {data['name']}: {data['description']}")
        installed += 1

    from sediman.display import print_success
    print_success("Done", f"{installed} skill(s) installed.")


@skill.group("hub")
def skill_hub() -> None:
    """Browse and install skills from the Skills Hub."""
    pass


@skill_hub.command("browse")
@click.option("--category", default=None, help="Filter by category")
def hub_browse(category: str | None) -> None:
    """Browse available skills in the hub."""
    from sediman.skills.hub import HubClient
    from sediman.display import console

    console.print("  [dim]Loading hub...[/dim]")
    client = HubClient()
    skills = client.browse(category=category)
    if not skills:
        console.print("  No skills found in hub.")
        return

    from rich.table import Table

    table = Table(title=f"Skills Hub ({len(skills)} skills)", show_header=True, header_style="cyan", box=None, padding=(0, 2))
    table.add_column("Name", style="cyan")
    table.add_column("Trust", style="green")
    table.add_column("Category", style="dim")
    table.add_column("Description")

    for s in skills:
        table.add_row(s.name, s.trust, s.category, s.description[:80])

    console.print(table)
    console.print("\n  Install with: [cyan]sediman skill hub install <name>[/cyan]")


@skill_hub.command("search")
@click.argument("query")
def hub_search(query: str) -> None:
    """Search the Skills Hub."""
    from sediman.skills.hub import HubClient

    client = HubClient()
    skills = client.search(query)
    if not skills:
        from sediman.display import console
        console.print(f"  No skills matching '{query}'.")
        return

    from rich.table import Table
    from sediman.display import console
    table = Table(title=f"Results for '{query}'", show_header=True, header_style="cyan", box=None, padding=(0, 2))
    table.add_column("Name", style="cyan")
    table.add_column("Description")

    for s in skills:
        table.add_row(s.name, s.description[:80])

    console.print(table)


@skill_hub.command("install")
@click.argument("name")
@click.option("--force", is_flag=True, help="Overwrite existing skill")
def hub_install(name: str, force: bool) -> None:
    """Install a skill from the hub."""
    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import HubClient

    client = HubClient()
    engine = SkillEngine()
    ok, msg = client.install(name, engine, force=force)
    if ok:
        from sediman.display import print_success
        print_success("Installed", msg)
    else:
        from sediman.display import print_error
        print_error(msg)


@skill_hub.command("info")
@click.argument("name")
def hub_info(name: str) -> None:
    """Show details about a hub skill."""
    from sediman.skills.hub import HubClient

    client = HubClient()
    info = client.info(name)
    if not info:
        from sediman.display import print_error
        print_error(f"Skill '{name}' not found in hub.")
        return

    from sediman.display import console, render_skill_detail

    console.print(render_skill_detail(info, title=info["name"]))


@skill_hub.command("publish")
@click.argument("name")
def hub_publish(name: str) -> None:
    """Validate and prepare a skill for hub publishing."""
    from sediman.skills.engine import SkillEngine
    from sediman.skills.format import SkillData
    from sediman.skills.hub import HubClient

    engine = SkillEngine()
    data = engine.read(name)
    if not data:
        from sediman.display import print_error
        print_error(f"Skill '{name}' not found locally.")
        return

    skill = SkillData(
        name=data["name"],
        description=data["description"],
        steps=data.get("steps", []),
        category=data.get("category", "general"),
        version=data.get("version", 1),
    )

    client = HubClient()
    ok, msg = client.publish(skill)
    if ok:
        from sediman.display import print_success
        print_success("Validated", msg)
    else:
        from sediman.display import print_error
        print_error(msg)


@main.group()
def schedule() -> None:
    """Manage scheduled tasks (cron jobs)."""
    pass


@schedule.command("list")
def schedule_list() -> None:
    """List all scheduled tasks."""
    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    jobs = cron.list_jobs()

    if not jobs:
        from sediman.display import console
        console.print("  No scheduled tasks.")
        return

    from rich.table import Table
    from sediman.display import console
    table = Table(title="Scheduled Tasks", show_header=True, header_style="cyan", box=None, padding=(0, 2))
    table.add_column("Status", width=1)
    table.add_column("ID", style="dim")
    table.add_column("Cron")
    table.add_column("Task")

    for j in jobs:
        status = "●" if j.get("enabled", True) else "○"
        table.add_row(status, j["id"][:8], j["cron"], j["task"])

    console.print(table)
    console.print("\n  Remove with: [cyan]sediman schedule remove <job_id>[/cyan]")


@schedule.command("add")
@click.argument("cron_expr")
@click.argument("task", required=False, default=None)
@click.option("--skill", default=None, help="Run a specific skill instead of a task")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--model", default=None, help="LLM model")
@click.option("--base-url", default=None, help="Custom API base URL")
def schedule_add(cron_expr: str, task: str | None, skill: str | None, provider: str, model: str | None, base_url: str | None) -> None:
    """Add a scheduled task.

    \b
    sediman schedule add "0 9 * * *" "Check Hacker News"
    sediman schedule add "*/30 * * * *" --skill stock-tracker
    """
    if not task and not skill:
        from sediman.display import print_error
        print_error("Provide a task description or --skill.")
        sys.exit(1)

    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    try:
        job_id = cron.add_job(
            cron_expr=cron_expr,
            task=task or f"Run skill: {skill}",
            skill_name=skill,
            provider=provider,
            model=model,
            base_url=base_url,
        )
    except ValueError as e:
        from sediman.display import print_error
        print_error(str(e))
        sys.exit(1)
    from sediman.display import print_success
    print_success("Scheduled", f"Job [{job_id[:8]}] {cron_expr} → {task or skill}")


@schedule.command("remove")
@click.argument("job_id")
@click.confirmation_option(prompt=f"Remove this scheduled task?")
def schedule_remove(job_id: str) -> None:
    """Remove a scheduled task. Accepts full or partial job ID."""
    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    removed = cron.remove_job(job_id.strip())
    if removed:
        from sediman.display import print_success
        print_success("Removed", f"Scheduled job {job_id.strip()[:8]}")
    else:
        from sediman.display import print_error
        print_error(f"Job '{job_id.strip()[:8]}' not found.", "Use 'sediman schedule list' to see job IDs.")
        sys.exit(1)


@schedule.command("start")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--model", default=None, help="LLM model")
@click.option("--base-url", default=None, help="Custom API base URL")
def schedule_start(provider: str, model: str | None, base_url: str | None) -> None:
    """Start the cron daemon. Runs scheduled tasks in headless mode.

    This is the standalone scheduler for 24/7 operation without the API server.
    Use 'sediman serve' instead if you want API + scheduler together.
    """
    from sediman.logging import suppress_noisy_loggers
    suppress_noisy_loggers()

    from sediman.display import print_startup_banner
    print_startup_banner(provider, model, headless=True, mode="cron daemon")

    from sediman.scheduler.cron import CronManager
    from sediman.display import console

    cron = CronManager()
    jobs = cron.list_jobs()
    if not jobs:
        console.print("  [yellow]No scheduled tasks. Add one with: [cyan]sediman schedule add[/cyan][/yellow]")
        return

    for j in jobs:
        status = "[green]●[/green]" if j.get("enabled", True) else "[red]○[/red]"
        console.print(f"  {status} {j['cron']:20s} {j['task'][:50]}")

    console.print()
    console.print("  Press Ctrl+C to stop.")
    console.print()

    from sediman.scheduler.cron import start_scheduler
    start_scheduler()


@schedule.command("register-skill")
@click.argument("skill_name")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--model", default=None, help="LLM model")
@click.option("--base-url", default=None, help="Custom API base URL")
def schedule_register_skill(skill_name: str, provider: str, model: str | None, base_url: str | None) -> None:
    """Register a skill's built-in schedule as a cron job."""
    from sediman.skills.engine import SkillEngine
    from sediman.scheduler.cron import CronManager

    engine = SkillEngine()
    data = engine.read(skill_name)
    if not data:
        from sediman.display import print_error
        print_error(f"Skill '{skill_name}' not found.")
        sys.exit(1)

    schedule_expr = data.get("schedule")
    if not schedule_expr:
        from sediman.display import print_error
        print_error(f"Skill '{skill_name}' has no schedule defined.", "Only skills with a schedule field can be registered.")
        sys.exit(1)

    cron = CronManager()
    job_id = cron.add_job(
        cron_expr=schedule_expr,
        task=f"Run skill: {skill_name}",
        skill_name=skill_name,
        provider=provider,
        model=model,
        base_url=base_url,
    )
    from sediman.display import print_success
    print_success("Registered", f"'{skill_name}' as cron job [{job_id[:8]}], schedule: {schedule_expr}")


@main.command()
def memory() -> None:
    """Show current agent memory."""
    from sediman.memory.store import MemoryStore
    from sediman.display import console

    store = MemoryStore()
    all_entries = store.get_all_entries()

    if not any(all_entries.values()):
        console.print("  No memory stored yet. Memory is built automatically as you use the agent.")
        return

    mem_usage = store.get_usage("memory")
    user_usage = store.get_usage("user")

    console.print(f"  [cyan bold]MEMORY [{mem_usage.formatted}][/cyan bold]")
    for i, entry in enumerate(mem_usage.entries, 1):
        console.print(f"    {i}. {entry[:120]}")
    console.print()

    if user_usage.entries:
        console.print(f"  [green bold]USER PROFILE [{user_usage.formatted}][/green bold]")
        for i, entry in enumerate(user_usage.entries, 1):
            console.print(f"    {i}. {entry[:120]}")
        console.print()


@main.command()
def sessions() -> None:
    """Show recent sessions."""
    try:
        asyncio.run(_show_sessions())
    except Exception as exc:
        from sediman.display import friendly_error
        friendly_error(exc)
        sys.exit(1)


@main.command()
@click.option("--host", default="0.0.0.0", help="API server host (default: 0.0.0.0 — all interfaces)")
@click.option("--port", default=8080, help="API server port")
@click.option("--provider", default="openai", type=PROVIDER_CHOICES, help="LLM provider")
@click.option("--model", default=None, help="LLM model to use")
@click.option("--base-url", default=None, help="Custom API base URL")
def serve(host: str, port: int, provider: str, model: str | None, base_url: str | None) -> None:
    """Start the agent server: API + scheduler + headed browser.

    This is the main entry point for 24/7 operation.
    Opens a visible browser window and starts the API server
    so the UI (or any client) can connect.
    """
    import uvicorn
    from sediman.api.app import app, init_state
    from sediman.logging import ensure_db

    asyncio.run(ensure_db())
    init_state(provider=provider, model=model, base_url=base_url)

    from sediman.display import print_startup_banner, console
    print_startup_banner(provider, model, headless=False, mode="API server")
    console.print(f"  API:    http://{host}:{port}")
    console.print(f"  Docs:   http://{host}:{port}/docs")
    console.print()
    console.print("  Press Ctrl+C to stop.")
    console.print()

    uvicorn.run(app, host=host, port=port, log_level="warning")


async def _record_skill(
    name: str, desc: str | None, model: str | None, provider: str, base_url: str | None, fps: int, max_duration: int,
) -> None:
    import time

    from sediman.agent.recording_manager import RecordingManager
    from sediman.agent.trace_to_skill import TraceToSkill
    from sediman.browser.session import BrowserSession
    from sediman.display import print_startup_banner, print_success, print_error, console
    from sediman.llm.provider import create_provider
    from sediman.skills.engine import SkillEngine

    from sediman.logging import ensure_db

    await ensure_db()

    print_startup_banner(provider, model, headless=False, mode=f"recording: {name}")

    llm = create_provider(provider, model, base_url)
    browser = BrowserSession(headless=False)

    try:
        console.print(f"  Starting browser for recording [cyan]{name}[/cyan]...")
        await browser.start()

        manager = RecordingManager()
        session = await manager.start_recording(
            name=name,
            browser=browser,
            description=desc,
            fps=fps,
            max_duration=max_duration,
        )

        console.print("")
        console.print(f"  [green]● Recording started[/green] — session [dim]{session.id}[/dim]")
        console.print(f"  [dim]FPS: {fps} | Max duration: {max_duration}s[/dim]")
        console.print("")
        console.print("  Perform your task in the browser window.")
        console.print("  Press [bold]Ctrl+C[/bold] when done to stop recording and create the skill.")
        console.print("")

        frame_count = 0
        try:
            while True:
                await asyncio.sleep(0.5)
                current = manager.get_session(session.id)
                if current and current.frame_count != frame_count:
                    frame_count = current.frame_count
                    elapsed = current.duration_seconds
                    console.print(
                        f"  [dim]Recording... {frame_count} frames, {elapsed:.0f}s elapsed[/dim]",
                        end="\r",
                    )
        except KeyboardInterrupt:
            console.print("")
            console.print("  [yellow]Stopping recording...[/yellow]")

        recording = await manager.stop_recording(name)

        console.print("")
        console.print(
            f"  Recording complete: [green]{recording.frame_count}[/green] frames, "
            f"[green]{recording.duration_seconds:.1f}s[/green], "
            f"[green]{len(recording.actions)}[/green] actions"
        )
        console.print("  [dim]Analyzing recording with AI...[/dim]")

        converter = TraceToSkill(llm)
        skill_data = await converter.convert(recording)

        if not skill_data:
            print_error(
                "Could not extract a skill from this recording.",
                "The recording may be too short or the task too simple. Try recording a longer workflow.",
            )
            return

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
            console.print(f"  [yellow]Updated existing skill: {skill_data['skill_name']}[/yellow]")
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

        print_success(
            "Skill created",
            f"'{skill_data['skill_name']}' with {len(skill_data['steps'])} steps.\n"
            f"  Run it with: [cyan]sediman skill run {skill_data['skill_name']}[/cyan]",
        )

    except Exception:
        raise
    finally:
        await browser.stop()


async def _run_task(task: str, model: str | None, provider: str, base_url: str | None, headless: bool, timeout: int | None = None) -> None:
    import time

    from sediman.agent.loop import AgentLoop
    from sediman.browser.session import BrowserSession
    from sediman.display import TaskProgress, print_result_panel, print_badges
    from sediman.llm.provider import create_provider
    from sediman.logging import ensure_db

    await ensure_db()

    from sediman.display import print_startup_banner
    print_startup_banner(provider, model, headless)

    llm = create_provider(provider, model, base_url)
    browser = BrowserSession(headless=headless)

    progress = TaskProgress()

    def on_step(event) -> None:
        from sediman.agent.loop import StepEvent
        if isinstance(event, StepEvent):
            progress.update(phase=event.phase or "executing", action=event.action, url=event.observation)

    try:
        progress.start(task)
        progress.update(phase="starting", action="Starting browser...")
        await browser.start()

        agent = AgentLoop(llm_provider=llm, browser_session=browser, on_step=on_step)
        progress.update(phase="planning", action="Planning task...")

        start = time.monotonic()
        task_coro = agent.run(task)

        if timeout:
            result = await asyncio.wait_for(task_coro, timeout=timeout)
        else:
            result = await task_coro

        elapsed = time.monotonic() - start

        progress.stop()

        success = result.result and "Task could not be completed" not in result.result
        print_result_panel(result.result or "No result returned.", elapsed=elapsed, success=success)
        print_badges(skill_created=result.skill_created, scheduled_job_id=result.scheduled_job_id, schedule_cron=result.schedule_cron)

    except asyncio.TimeoutError:
        progress.stop()
        from sediman.display import print_error
        print_error(f"Task timed out after {timeout}s.", "Try a simpler task or increase --timeout.")
    except Exception:
        progress.stop()
        raise
    finally:
        await browser.stop()


async def _run_skill(
    skill_data: dict, model: str | None, provider: str, base_url: str | None, headless: bool
) -> None:
    import time

    from sediman.browser.session import BrowserSession
    from sediman.display import TaskProgress, print_result_panel
    from sediman.llm.provider import create_provider
    from sediman.skills.executor import execute_skill
    from sediman.logging import ensure_db

    await ensure_db()

    llm = create_provider(provider, model, base_url)
    browser = BrowserSession(headless=headless)

    progress = TaskProgress()

    try:
        progress.start(skill_data["name"])
        progress.update(phase="starting", action="Starting browser...")
        await browser.start()

        progress.update(phase="executing", action=f"Executing skill: {skill_data['name']}...")
        start = time.monotonic()
        result = await execute_skill(skill_data, browser, llm)
        elapsed = time.monotonic() - start

        progress.stop()

        success = bool(result and not result.startswith("Skill") and "failed" not in result.lower())
        print_result_panel(result or "Skill completed with no output.", elapsed=elapsed, success=success)

    except Exception:
        progress.stop()
        raise
    finally:
        await browser.stop()


async def _show_sessions() -> None:
    from sediman.memory.sessions import get_recent_sessions
    from sediman.logging import ensure_db

    await ensure_db()
    recent = await get_recent_sessions()

    if not recent:
        from sediman.display import console
        console.print("  No sessions yet.")
        return

    from rich.table import Table
    from sediman.display import console
    table = Table(title="Recent Sessions", show_header=True, header_style="cyan", box=None, padding=(0, 2))
    table.add_column("ID", style="dim")
    table.add_column("Task")
    table.add_column("Time", style="dim")

    for s in recent[:15]:
        task_text = s["task"][:60]
        if len(s["task"]) > 60:
            task_text += "..."
        table.add_row(str(s["id"])[:8], task_text, s.get("created_at", ""))

    console.print(table)


if __name__ == "__main__":
    main()
