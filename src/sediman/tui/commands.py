"""Slash command handlers extracted from tui.py."""

from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING

from sediman.agent.interrupt import InterruptedError
from sediman.tui.display import _rich, cprint, relative_time

if TYPE_CHECKING:
    from sediman.tui.app import SedimanTUI

_SLASH_COMMANDS = {
    "/help": "Show available commands",
    "/skills": "List all skills",
    "/skill <name>": "Show skill details",
    "/run-skill <name>": "Execute a skill",
    "/install <ref> [--force]": "Install skill from GitHub or hub",
    "/search <query>": "Search the hub for skills",
    "/update [name|--all]": "Update installed skills",
    "/outdated": "Check for skill updates",
    "/skill-info <name>": "Show skill provenance and source info",
    "/hub browse [--category X]": "Browse the Skills Hub (legacy)",
    "/hub search <query>": "Search the Skills Hub (legacy)",
    "/hub install <name> [--force]": "Install from hub (legacy)",
    "/hub info <name>": "Show hub skill details (legacy)",
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
    "/resume": "Resume a recent session",
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
    "/checkpoint": "List filesystem checkpoints",
    "/checkpoint-create <dir>": "Create a checkpoint of a directory",
    "/checkpoint-revert <dir> <id>": "Revert directory to a checkpoint",
    "/rewind <id>": "Revert current directory to checkpoint",
    "/branch <name>": "Save current state as a named branch checkpoint",
    "/branches": "List saved branch checkpoints",
    "/plan": "Toggle plan (read-only research) mode",
    "/color <color>": "Set prompt bar color",
    "/rename <name>": "Name this session",
    "/usage": "Show session usage stats",
    "/btw <question>": "Ask an ephemeral side question",
    "/doctor": "Diagnose installation and settings",
    "/export": "Export conversation to file",
    "/exit": "Exit Sediman",
}

_HELP_CATEGORIES = [
    ("General", ["/help", "/exit", "/status", "/clear", "/reset"]),
    ("Agent", ["/model", "/models", "/plan", "/compress", "/soul"]),
    (
        "Skills",
        [
            "/skills",
            "/skill",
            "/run-skill",
            "/install",
            "/search",
            "/update",
            "/outdated",
            "/skill-info",
            "/record",
            "/stop",
        ],
    ),
    (
        "Hub (legacy)",
        [
            "/hub browse",
            "/hub search",
            "/hub install",
            "/hub info",
            "/hub publish",
        ],
    ),
    ("Browser", ["/browser", "/screenshot"]),
    (
        "Sessions & Memory",
        [
            "/sessions",
            "/memory",
            "/remember",
            "/resume",
        ],
    ),
    ("Schedule", ["/schedule", "/schedule-add", "/schedule-remove"]),
    (
        "Terminal & Permissions",
        [
            "/terminal",
            "/color",
            "/rename",
            "/checkpoint",
            "/checkpoint-create",
            "/checkpoint-revert",
            "/rewind",
            "/branch",
            "/branches",
        ],
    ),
    ("Task Management", ["/delegate", "/parallel", "/usage"]),
    ("Utilities", ["/btw", "/doctor", "/export"]),
]

_SLASH_NAMES = sorted(
    [c.split()[0] for c in _SLASH_COMMANDS],
    key=lambda x: x,
)


async def handle_task(tui: SedimanTUI, task: str) -> None:
    from sediman.tui.logging import suppress_logging

    with suppress_logging():
        try:
            agent = await tui._get_agent()
        except Exception as e:
            cprint(f"\n  \033[31mX Failed to start agent: {e}\033[0m")
            return

        tui._spinner_text = "Working..."
        tui._tool_start_time = time.monotonic()

        start = time.monotonic()
        try:
            result = await agent.run(task)
        except InterruptedError:
            cprint("\n  \033[33m-- Interrupted --\033[0m\n")
            return
        except Exception as e:
            cprint(f"\n  \033[31mX Task failed: {e}\033[0m\n")
            return

        elapsed = time.monotonic() - start
        tui._spinner_text = ""
        tui._tool_start_time = 0.0

        result_text = result.result or "No result returned."
        success = "Task could not be completed" not in result_text

        border_color = "green" if success else "red"
        icon = "+" if success else "X"
        header = (
            f"{icon} Sediman  ({elapsed:.1f}s)"
            if success
            else f"{icon} Task Failed  ({elapsed:.1f}s)"
        )

        try:
            from rich.markdown import Markdown
            from rich.text import Text

            content = Markdown(result_text)
        except Exception:
            content = Text()
            for line in result_text.split("\n"):
                content.append(f"  {line}\n")

        from rich.text import Text
        from rich.panel import Panel

        _rich.print(
            Panel(
                content,
                title=Text(f"  {header}", style=border_color),
                border_style=border_color,
                padding=(0, 1),
            )
        )

        if result.skill_created:
            cprint(f"  \033[35m* Skill auto-created: {result.skill_created}\033[0m")
        if result.scheduled_job_id:
            cprint(
                f"  \033[36m[Sched] Scheduled: {result.schedule_cron} -> job {result.scheduled_job_id[:8]}\033[0m"
            )
        cprint("")


def _find_closest_command(cmd: str) -> str | None:
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


async def handle_slash(tui: SedimanTUI, cmd: str) -> None:
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Handler map keyed by base command name
    handler = {
        "/help": cmd_help,
        "/skills": cmd_skills,
        "/skill": cmd_skill_detail,
        "/run-skill": cmd_run_skill,
        "/install": cmd_install,
        "/search": cmd_search,
        "/update": cmd_update,
        "/outdated": cmd_outdated,
        "/skill-info": cmd_skill_info,
        "/hub": cmd_hub,
        "/memory": cmd_memory,
        "/remember": cmd_remember,
        "/model": cmd_model,
        "/models": cmd_models,
        "/schedule": cmd_schedule,
        "/schedule-add": cmd_schedule_add,
        "/schedule-remove": cmd_schedule_remove,
        "/sessions": cmd_sessions,
        "/resume": cmd_resume,
        "/screenshot": cmd_screenshot,
        "/browser": cmd_browser,
        "/status": cmd_status,
        "/soul": cmd_soul,
        "/record": cmd_record,
        "/stop": cmd_stop,
        "/delegate": cmd_delegate,
        "/parallel": cmd_parallel,
        "/compress": cmd_compress,
        "/clear": cmd_clear,
        "/reset": cmd_reset,
        "/terminal": cmd_terminal,
        "/checkpoint": cmd_checkpoint_list,
        "/checkpoint-create": cmd_checkpoint_create,
        "/checkpoint-revert": cmd_checkpoint_revert,
        "/rewind": cmd_rewind,
        "/branch": cmd_branch,
        "/branches": cmd_branches,
        "/plan": cmd_plan,
        "/color": cmd_color,
        "/rename": cmd_rename,
        "/usage": cmd_usage,
        "/btw": cmd_btw,
        "/doctor": cmd_doctor,
        "/export": cmd_export,
        "/exit": cmd_exit,
    }.get(command)

    if handler:
        try:
            await handler(tui, args)
        except Exception as e:
            cprint(f"  \033[31mX Command failed: {e}\033[0m")
    else:
        closest = _find_closest_command(command)
        msg = f"  \033[31mUnknown command: {command}\033[0m"
        if closest:
            msg += f"\n  \033[2mDid you mean \033[36m{closest}\033[0m?\033[0m"
        msg += "\n  \033[2mType \033[36m/help\033[0m for a list of commands.\033[0m"
        cprint(msg)


async def cmd_help(tui: SedimanTUI, _args: str) -> None:
    from rich.style import Style
    from rich.table import Table

    table = Table(title="Commands", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="yellow")
    table.add_column()
    for cat_name, cmds in _HELP_CATEGORIES:
        table.add_row(f"\n[{cat_name}]", "", style=Style(dim=True))
        for cmd in cmds:
            desc = _SLASH_COMMANDS.get(cmd, "")
            table.add_row(cmd, desc)
    _rich.print(table)
    cprint("\n  Or just type a task and press Enter to run it.\n")


async def cmd_skills(tui: SedimanTUI, _args: str) -> None:
    from rich.table import Table

    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skills = engine.list_skills()
    if not skills:
        cprint("  No skills yet. Skills are auto-created after complex tasks.")
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
    cprint("")


async def cmd_skill_detail(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/skill <name>\033[0m")
        return
    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skill = engine.read(args.strip())
    if not skill:
        cprint(f"  \033[31mSkill '{args.strip()}' not found.\033[0m")
        return
    from sediman.display import render_skill_detail

    _rich.print(render_skill_detail(skill, title=skill.get("name")))


async def cmd_run_skill(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/run-skill <name>\033[0m")
        return
    from sediman.skills.engine import SkillEngine
    from sediman.skills.executor import execute_skill

    engine = SkillEngine()
    skill = engine.read(args.strip())
    if not skill:
        cprint(f"  \033[31mSkill '{args.strip()}' not found.\033[0m")
        return

    cprint(f"  \033[33m... Running skill: {skill['name']}...\033[0m")
    browser = await tui._get_browser()
    llm = tui._get_llm()

    try:
        start = time.monotonic()
        tui._spinner_text = f"Executing {skill['name']}..."
        tui._tool_start_time = start
        result = await execute_skill(skill, browser, llm)
        elapsed = time.monotonic() - start
        tui._spinner_text = ""
        success = bool(result and "failed" not in result.lower())
        border = "32" if success else "31"
        header = f"\033[{border}m+ {skill['name']}  ({elapsed:.1f}s)\033[0m"
        cprint(f"\n  {header}")
        cprint(f"  {result or 'Skill completed with no output.'}")
    except Exception as e:
        tui._spinner_text = ""
        cprint(f"  \033[31mX Skill execution failed: {e}\033[0m")


async def cmd_install(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint(
            "  Usage: \033[36m/install <owner/repo@skill>[/install] or \033[36m/install <name> --from hub[/install]"
        )
        cprint("  Examples:")
        cprint("    \033[36m/install anthropics/skills@frontend-design\033[0m")
        cprint("    \033[36m/install my-skill\033[0m  (from hub)")
        return

    parts = args.split()
    ref = parts[0]
    force = "--force" in parts
    from_hub = "--from" in parts and "hub" in parts

    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()

    if from_hub or "/" not in ref:
        from sediman.skills.hub import HubClient

        client = HubClient()
        ok, msg = client.install(ref, engine, force=force)
    else:
        from sediman.skills.hub import GitHubInstaller

        installer = GitHubInstaller()
        ok, msg = installer.install(ref, engine, force=force)

    if ok:
        cprint(f"  \033[32m+ {msg}\033[0m")
    else:
        cprint(f"  \033[31mX {msg}\033[0m")


async def cmd_search(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/search <query>\033[0m")
        return

    from sediman.skills.hub import HubClient

    client = HubClient()
    skills = client.search(args.strip())
    if not skills:
        cprint(f"  No skills matching '{args.strip()}'.")
        cprint(
            "  Try installing from GitHub: \033[36m/install owner/repo@skill-name\033[0m"
        )
        return

    from rich.table import Table

    table = Table(
        title=f"Results for '{args.strip()}' ({len(skills)})",
        show_header=True,
        header_style="cyan",
        box=None,
        padding=(0, 2),
    )
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Description")
    for s in skills:
        table.add_row(s.name, s.category, s.description[:70])
    _rich.print(table)
    cprint("")


async def cmd_update(tui: SedimanTUI, args: str) -> None:
    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import GitHubInstaller, SkillLockFile

    engine = SkillEngine()
    lock = SkillLockFile()
    installer = GitHubInstaller()

    if "--all" in args:
        entries = lock.list_all()
        if not entries:
            cprint("  No tracked skills to update.")
            return

        updated = 0
        for skill_name, entry in entries.items():
            if entry.source_type != "github":
                continue
            ok, msg = installer.update_skill(skill_name, engine)
            if ok:
                updated += 1
                cprint(f"  \033[32m+ {msg}\033[0m")
            else:
                cprint(f"  {msg}")

        if updated:
            cprint(f"\n  \033[32m+ {updated} skill(s) updated.\033[0m")
        else:
            cprint("  All skills are up to date.")
        return

    name = args.strip()
    if not name:
        cprint("  Usage: \033[36m/update <name>\033[0m or \033[36m/update --all\033[0m")
        return

    ok, msg = installer.update_skill(name, engine)
    if ok:
        cprint(f"  \033[32m+ {msg}\033[0m")
    else:
        cprint(f"  \033[31mX {msg}\033[0m")


async def cmd_outdated(tui: SedimanTUI, _args: str) -> None:
    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import GitHubInstaller, SkillLockFile

    engine = SkillEngine()
    lock = SkillLockFile()
    installer = GitHubInstaller()
    entries = lock.list_all()

    if not entries:
        cprint("  No tracked skills installed from external sources.")
        return

    from rich.table import Table

    outdated_list = []
    for skill_name, entry in entries.items():
        if entry.source_type != "github":
            continue
        has_update, msg = installer.check_update(skill_name, engine)
        if has_update:
            outdated_list.append((skill_name, entry.source, msg))

    if not outdated_list:
        cprint("  All skills are up to date.")
        return

    table = Table(
        title="Outdated Skills",
        show_header=True,
        header_style="yellow",
        box=None,
        padding=(0, 2),
    )
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Status")
    for skill_name, source, msg in outdated_list:
        table.add_row(skill_name, source, msg)
    _rich.print(table)
    cprint("  Update with: \033[36m/update --all\033[0m\n")


async def cmd_skill_info(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/skill-info <name>\033[0m")
        return

    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import SkillLockFile

    engine = SkillEngine()
    data = engine.read(args.strip())
    if not data:
        cprint(f"  \033[31mSkill '{args.strip()}' not found.\033[0m")
        return

    lock = SkillLockFile()
    entry = lock.get(args.strip())

    from rich.table import Table

    table = Table(
        title=f"Skill: {data['name']}", show_header=False, box=None, padding=(0, 2)
    )
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Name:", data.get("name", ""))
    table.add_row("Description:", data.get("description", "")[:120])
    table.add_row("Category:", data.get("category", ""))
    table.add_row("Version:", f"v{data.get('version', 1)}")
    if entry:
        table.add_row("", "")
        table.add_row("[bold]Source[/bold]", "")
        table.add_row("Source:", entry.source)
        table.add_row("Type:", entry.source_type)
        table.add_row("URL:", entry.source_url)
        table.add_row(
            "Installed:", entry.installed_at[:19] if entry.installed_at else "unknown"
        )
    else:
        table.add_row("Source:", "local")
    _rich.print(table)
    cprint("")


async def cmd_hub(tui: SedimanTUI, args: str) -> None:
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
            cprint("  No skills found in hub.")
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
        cprint("")
    elif subcmd == "search":
        if not sub_args:
            cprint("  Usage: \033[36m/hub search <query>\033[0m")
            return
        client = HubClient()
        skills = client.search(sub_args)
        if not skills:
            cprint(f"  No skills matching '{sub_args}'.")
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
        cprint("")
    elif subcmd == "install":
        if not sub_args:
            cprint("  Usage: \033[36m/hub install <name> [--force]\033[0m")
            return
        name = sub_args.replace("--force", "").strip()
        force = "--force" in sub_args
        client = HubClient()
        engine = SkillEngine()
        ok, msg = client.install(name, engine, force=force)
        if ok:
            cprint(f"  \033[32m+ {msg}\033[0m")
        else:
            cprint(f"  \033[31mX {msg}\033[0m")
    elif subcmd == "info":
        if not sub_args:
            cprint("  Usage: \033[36m/hub info <name>\033[0m")
            return
        client = HubClient()
        info = client.info(sub_args.strip())
        if not info:
            cprint(f"  \033[31mSkill '{sub_args.strip()}' not found in hub.\033[0m")
            return
        from sediman.display import render_skill_detail

        _rich.print(render_skill_detail(info, title=info["name"]))
    elif subcmd == "publish":
        if not sub_args:
            cprint("  Usage: \033[36m/hub publish <name>\033[0m")
            return
        engine = SkillEngine()
        data = engine.read(sub_args.strip())
        if not data:
            cprint(f"  \033[31mSkill '{sub_args.strip()}' not found.\033[0m")
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
            cprint(f"  \033[32m+ {msg}\033[0m")
        else:
            cprint(f"  \033[31mX {msg}\033[0m")
    else:
        cprint("  Usage: \033[36m/hub [browse|search|install|info|publish]\033[0m")


async def cmd_memory(tui: SedimanTUI, _args: str) -> None:
    from rich.panel import Panel
    from rich.text import Text

    from sediman.memory.store import MemoryStore

    store = MemoryStore()
    all_entries = store.get_all_entries()
    mem_usage = store.get_usage("memory")
    user_usage = store.get_usage("user")

    if not any(all_entries.values()):
        cprint("  No memory stored. Use \033[36m/remember <text>\033[0m to add.")
        return

    _rich.print(
        Panel(
            Text("\n\n".join(mem_usage.entries) if mem_usage.entries else "(empty)"),
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


async def cmd_remember(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/remember <text to save>\033[0m")
        return
    from sediman.memory.store import MemoryStore

    store = MemoryStore()
    result = store.add("memory", args)
    if result.success:
        cprint("  \033[32m+ Saved to memory.\033[0m")
    else:
        cprint(f"  \033[31mX {result.message}\033[0m")


async def cmd_model(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint(
            f"  Current: \033[32m{tui.provider}\033[0m / \033[32m{tui.model or 'default'}\033[0m"
        )
        if tui.base_url:
            cprint(f"  Base URL: {tui.base_url}")
        return

    old_provider = tui.provider
    old_model = tui.model
    old_llm = tui._llm

    if ":" in args:
        provider, model = args.split(":", 1)
    else:
        provider = tui.provider
        model = args

    tui.provider = provider
    tui.model = model
    tui._llm = None
    conv = tui._agent.get_conversation() if tui._agent else []
    tui._agent = None

    try:
        agent = await tui._get_agent()
        if conv:
            agent.set_conversation(conv)
        cprint(f"  \033[32m+ Switched to {provider}:{model}\033[0m")
    except Exception as e:
        tui.provider = old_provider
        tui.model = old_model
        tui._llm = old_llm
        tui._agent = None
        cprint(f"  \033[31mX Failed to switch to {provider}:{model}: {e}\033[0m")


async def cmd_models(tui: SedimanTUI, _args: str) -> None:
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
        table.add_row(name, config["model"], config.get("base_url", "default"))
    _rich.print(table)
    cprint("\n  Switch with: \033[36m/model <provider:model>\033[0m")


async def cmd_schedule(tui: SedimanTUI, _args: str) -> None:
    from rich.table import Table

    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    jobs = cron.list_jobs()
    if not jobs:
        cprint("  No scheduled tasks. Use \033[36m/schedule-add <cron> <task>\033[0m")
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
        status = "\033[32mo\033[0m" if j.get("enabled", True) else "\033[31mx\033[0m"
        table.add_row(f"{status} {j['id'][:8]}", j["cron"], j["task"])
        if j.get("last_run"):
            table.add_row("", f"Last: {j['last_run'][:19]}", "")
    _rich.print(table)
    cprint("")


async def cmd_schedule_add(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/schedule-add <cron> <task>\033[0m")
        cprint("  Example: /schedule-add '0 * * * *' 'check stock price'")
        return
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        cprint("  Need both cron expression and task description.")
        return
    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    job_id = cron.add_job(
        cron_expr=parts[0],
        task=parts[1],
        provider=tui.provider,
        model=tui.model,
        base_url=tui.base_url,
    )
    cprint(f"  \033[32m+ Scheduled: [{job_id[:8]}] {parts[0]} -> {parts[1]}\033[0m")


async def cmd_schedule_remove(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/schedule-remove <job_id>\033[0m")
        cprint("  Tip: Use the 8-char ID shown in \033[36m/schedule\033[0m")
        return
    from sediman.scheduler.cron import CronManager

    cron = CronManager()
    if cron.remove_job(args.strip()):
        cprint(f"  \033[32m+ Removed: {args.strip()[:8]}\033[0m")
    else:
        cprint(f"  \033[31mJob '{args.strip()[:8]}' not found.\033[0m")
        cprint(
            "  \033[2mUse \033[36m/schedule\033[0m to list jobs with their IDs.\033[0m"
        )


async def cmd_sessions(tui: SedimanTUI, _args: str) -> None:
    from rich.table import Table

    from sediman.memory.sessions import get_recent_sessions

    sessions = await get_recent_sessions()
    if not sessions:
        cprint("  No sessions yet.")
        return
    now = datetime.datetime.now(datetime.UTC)
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
        rel = relative_time(created, now)
        table.add_row(str(s["id"])[:8], task_text, rel)
    _rich.print(table)
    cprint("")


async def cmd_screenshot(tui: SedimanTUI, _args: str) -> None:
    import base64

    from sediman.config import SCREENSHOT_FILE as _shot_path

    browser = await tui._get_browser()
    b64 = await browser.take_screenshot()
    if b64:
        _shot_path.write_bytes(base64.b64decode(b64))
        cprint(f"  \033[32m+ Screenshot saved to {_shot_path}\033[0m")
    else:
        cprint("  \033[31mNo browser page available.\033[0m")


async def cmd_browser(tui: SedimanTUI, args: str) -> None:
    from sediman.tui.logging import suppress_logging

    if not args.strip():
        mode = "headless" if tui.headless else "headed + vision"
        cprint(
            f"  Browser: \033[32m{mode}\033[0m\n"
            f"  Switch with: \033[36m/browser headless\033[0m or \033[36m/browser headed\033[0m"
        )
        return

    new_mode = args.strip().lower()
    if new_mode not in ("headless", "headed"):
        cprint(
            "  \033[31mUnknown mode. Use \033[36mheadless\033[0m\033[31m or \033[36mheaded\033[0m"
        )
        return

    new_headless = new_mode == "headless"
    if new_headless == tui.headless:
        cprint(f"  Already in {new_mode} mode.")
        return

    if tui._browser:
        with suppress_logging():
            try:
                await tui._browser.stop()
            except Exception:
                pass
        tui._browser = None
        tui._agent = None

    tui.headless = new_headless
    mode = "headless" if tui.headless else "headed + vision"
    cprint(f"  \033[32m+ Switched to {mode}\033[0m")


async def cmd_status(tui: SedimanTUI, _args: str) -> None:
    from rich.table import Table

    table = Table(title="Status", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()

    browser_mode = "headless" if tui.headless else "headed + vision"
    browser_status = (
        "running" if tui._browser and tui._browser.is_started else "not started"
    )
    table.add_row("Browser:", f"{browser_status} ({browser_mode})")
    table.add_row("Provider:", tui.provider)
    table.add_row("Model:", tui.model or "default")
    if tui.base_url:
        table.add_row("Base URL:", tui.base_url)
    table.add_row("Tasks run:", str(tui._task_count))

    if tui._agent:
        conv_len = len(tui._agent.get_conversation())
        table.add_row(
            "Conversation:",
            f"{conv_len // 2} turns ({conv_len} messages)",
        )

    _rich.print(table)
    cprint("")


async def cmd_soul(tui: SedimanTUI, args: str) -> None:
    from rich.panel import Panel
    from rich.text import Text

    from sediman.agent.soul import load_soul, save_soul, reset_soul

    if not args:
        soul = load_soul()
        _rich.print(
            Panel(
                Text(soul),
                title=Text("  Personality (SOUL.md)", style="cyan"),
                border_style="cyan",
                padding=(0, 1),
            )
        )
        cprint(
            "  Change with: \033[36m/soul <text>\033[0m   Reset with: \033[36m/soul reset\033[0m"
        )
    elif args.strip().lower() == "reset":
        reset_soul()
        cprint("  \033[32m+ Personality reset to default.\033[0m")
    else:
        save_soul(args)
        cprint("  \033[32m+ Personality updated. Takes effect on next task.\033[0m")


async def cmd_record(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/record <name> [--desc description]\033[0m")
        cprint(
            '  Example: /record post-medium-article --desc "Post an article on Medium"'
        )
        return

    parts = args.split()
    name = parts[0]

    desc = None
    if "--desc" in parts:
        idx = parts.index("--desc")
        if idx + 1 < len(parts):
            desc = " ".join(parts[idx + 1 :])

    from sediman.agent.recording_manager import RecordingManager

    manager = RecordingManager.get_instance()
    if manager.is_recording(name):
        cprint(
            f"  \033[31mAlready recording '{name}'. Use \033[36m/stop\033[0m\033[31m first.\033[0m"
        )
        return

    if manager.is_recording():
        cprint(
            "  \033[31mAnother recording is active. Use \033[36m/stop\033[0m\033[31m first.\033[0m"
        )
        return

    browser = await tui._get_browser()

    try:
        session = await manager.start_recording(
            name=name,
            browser=browser,
            description=desc,
            fps=3,
            max_duration=300,
        )
        cprint(f"  \033[32m● Recording started: {name}\033[0m (session {session.id})")
        cprint(
            "  \033[2mPerform your task in the browser. Use \033[36m/stop\033[0m\033[2m when done.\033[0m"
        )
    except Exception as e:
        cprint(f"  \033[31mX Failed to start recording: {e}\033[0m")


async def cmd_stop(tui: SedimanTUI, _args: str) -> None:
    from sediman.agent.recording_manager import RecordingManager

    manager = RecordingManager.get_instance()
    active = manager.get_active_sessions()

    if not active:
        cprint(
            "  \033[33mNo active recording. Use \033[36m/record <name>\033[0m\033[33m to start one.\033[0m"
        )
        return

    session = active[0]
    name = session.name

    cprint(f"  \033[33mStopping recording '{name}'...\033[0m")

    try:
        recording = await manager.stop_recording(name)
    except Exception as e:
        cprint(f"  \033[31mX Failed to stop recording: {e}\033[0m")
        return

    cprint(
        f"  \033[32m+ Recording stopped:\033[0m "
        f"{recording.frame_count} frames, "
        f"{recording.duration_seconds:.1f}s, "
        f"{len(recording.actions)} actions"
    )

    cprint("  \033[33mAnalyzing recording with AI...\033[0m")

    try:
        from sediman.agent.trace_to_skill import TraceToSkill

        llm = tui._get_llm()
        converter = TraceToSkill(llm)
        skill_data = await converter.convert(recording)

        if not skill_data:
            cprint(
                "  \033[33mCould not extract a skill.\033[0m "
                "The recording may be too short or the task too simple."
            )
            return

        from sediman.skills.engine import SkillEngine

        engine = SkillEngine()
        existing = engine.read(skill_data["skill_name"])
        if existing:
            engine.patch(
                skill_data["skill_name"],
                {
                    "description": skill_data["description"],
                    "steps": skill_data["steps"],
                    "when_to_use": skill_data.get("when_to_use"),
                    "pitfalls": skill_data.get("pitfalls", []),
                    "verification": skill_data.get("verification"),
                },
            )
            cprint(
                f"  \033[33mUpdated existing skill: {skill_data['skill_name']}\033[0m"
            )
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
        cprint(
            f"\n  \033[32m+ Skill created: {skill_data['skill_name']}\033[0m\n"
            f"  {skill_data['description']}\n"
            f"{steps_preview}\n"
            f"\n  \033[2mRun with: \033[36m/run-skill {skill_data['skill_name']}\033[0m"
        )
        cprint("")

    except Exception as e:
        cprint(f"  \033[31mX Failed to analyze recording: {e}\033[0m")
    finally:
        manager.cleanup(name)


async def cmd_delegate(tui: SedimanTUI, args: str) -> None:
    if not args:
        cprint("  Usage: \033[36m/delegate <task>\033[0m")
        cprint("  Runs a task as an isolated subagent.")
        return

    from sediman.agent.delegate import delegate_task

    cprint("  \033[33m... Delegating to subagent...\033[0m")
    browser = await tui._get_browser()
    llm = tui._get_llm().get_browser_use_llm()
    try:
        start = time.monotonic()
        tui._spinner_text = "Subagent working..."
        tui._tool_start_time = start
        result = await delegate_task(args, browser, llm)
        elapsed = time.monotonic() - start
        tui._spinner_text = ""
        border = "32" if "failed" not in result.lower() else "31"
        cprint(f"\n  \033[{border}m+ Subagent  ({elapsed:.1f}s)\033[0m")
        cprint(f"  {result or 'Subagent completed with no output.'}")
        cprint("")
    except Exception as e:
        tui._spinner_text = ""
        cprint(f"  \033[31mX Subagent failed: {e}\033[0m")


async def cmd_parallel(tui: SedimanTUI, args: str) -> None:
    if not args or "|" not in args:
        cprint("  Usage: \033[36m/parallel <task1> | <task2> | <task3>\033[0m")
        cprint("  Runs up to 5 tasks in parallel.")
        return

    from sediman.agent.delegate import delegate_parallel

    tasks = [t.strip() for t in args.split("|") if t.strip()]
    if len(tasks) > 5:
        cprint(f"  \033[33mWarning: Truncating to 5 tasks (got {len(tasks)}).\033[0m")
        tasks = tasks[:5]
    cprint(f"  \033[33m... Running {len(tasks)} tasks in parallel...\033[0m")
    browser = await tui._get_browser()
    llm = tui._get_llm()
    try:
        start = time.monotonic()
        tui._spinner_text = f"Running {len(tasks)} tasks..."
        tui._tool_start_time = start
        results = await delegate_parallel(tasks, browser, llm)
        elapsed = time.monotonic() - start
        tui._spinner_text = ""

        for i, (task_text, result) in enumerate(zip(tasks, results)):
            cprint(f"  \033[1;36mTask {i + 1}:\033[0m {task_text}")
            display = result if len(result) <= 300 else result[:297] + "..."
            cprint(f"    \033[32m-> {display}\033[0m")
        cprint(f"\n  \033[2mAll {len(tasks)} tasks completed in {elapsed:.1f}s\033[0m")
        cprint("")
    except Exception as e:
        tui._spinner_text = ""
        cprint(f"  \033[31mX Parallel execution failed: {e}\033[0m")


async def cmd_compress(tui: SedimanTUI, _args: str) -> None:
    if tui._agent is None:
        cprint("  Nothing to compress — no agent session yet.")
        return

    conv = tui._agent.get_conversation()
    if len(conv) <= 4:
        cprint("  Nothing to compress — conversation is short.")
        return

    try:
        tui._spinner_text = "Compressing context..."
        removed = await tui._agent.compress_context()
        tui._spinner_text = ""
        if removed > 0:
            cprint(
                f"  \033[32m+ Compressed: removed {removed} messages. {len(tui._agent.get_conversation())} remaining.\033[0m"
            )
        else:
            cprint(
                "  \033[33mCould not compress further. Try /clear to start fresh.\033[0m"
            )
    except Exception as e:
        tui._spinner_text = ""
        cprint(f"  \033[31mX Compression failed: {e}\033[0m")


async def cmd_clear(tui: SedimanTUI, _args: str) -> None:
    if tui._agent is None:
        cprint("  \033[32m+ Already clear — no active session.\033[0m")
        return
    tui._agent.clear_conversation()
    cprint("  \033[32m+ Conversation cleared. Browser and skills kept.\033[0m")


async def cmd_terminal(tui: SedimanTUI, args: str) -> None:
    from sediman.agent.tools import is_terminal_allowed, set_terminal_allowed

    sub = args.strip().lower()
    if sub == "on":
        set_terminal_allowed(True)
        cprint("  \033[32m+ Terminal access: approved for this session.\033[0m")
        cprint("  \033[2mAll commands will execute without asking.\033[0m")
    elif sub == "off":
        set_terminal_allowed(False)
        cprint("  \033[33m* Terminal access: each command requires approval.\033[0m")
    else:
        if is_terminal_allowed():
            cprint("  Terminal access: \033[32mapproved\033[0m (all commands allowed)")
        else:
            cprint(
                "  Terminal access: \033[33mapproval required\033[0m (each command asks)"
            )
        cprint(
            "  \033[2mUse \033[36m/terminal on\033[0m\033[2m or \033[36m/terminal off\033[0m\033[2m to change.\033[0m"
        )


async def cmd_reset(tui: SedimanTUI, _args: str) -> None:
    from sediman.agent.tools import reset_terminal_state

    tui._agent = None
    tui._llm = None
    tui._task_count = 0
    reset_terminal_state()
    cprint("  \033[32m+ Full reset. Starting fresh session.\033[0m")


async def cmd_export(tui: SedimanTUI, _args: str) -> None:
    if tui._agent is None:
        cprint("  No conversation to export.")
        return
    import json
    from pathlib import Path
    from datetime import datetime

    conv = tui._agent.get_conversation()
    if not conv:
        cprint("  No conversation to export.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(f"sediman-export-{ts}.json")
    out.write_text(json.dumps(conv, indent=2, ensure_ascii=False))
    cprint(f"  \033[32m+ Exported {len(conv)} messages to {out}\033[0m")


async def cmd_exit(tui: SedimanTUI, _args: str) -> None:
    cprint("  \033[36mBye!\033[0m")
    tui._running = False
    tui._should_exit = True


async def cmd_resume(tui: SedimanTUI, args: str) -> None:
    from rich.table import Table

    from sediman.memory.sessions import get_recent_sessions

    sessions = await get_recent_sessions()
    if not sessions:
        cprint("  No sessions to resume.")
        return
    now = datetime.datetime.now(datetime.UTC)
    table = Table(
        title="Recent Sessions",
        show_header=True,
        header_style="cyan",
        box=None,
        padding=(0, 2),
    )
    table.add_column("#", style="dim")
    table.add_column("ID", style="dim")
    table.add_column("Task")
    table.add_column("When", style="dim")
    for i, s in enumerate(sessions[:10], 1):
        task_text = s["task"][:55]
        if len(s["task"]) > 55:
            task_text += "..."
        rel = relative_time(s.get("created_at", ""), now)
        table.add_row(str(i), str(s["id"])[:8], task_text, rel)
    _rich.print(table)
    cprint("  \033[2mUse \033[36m/sessions\033[0m\033[2m to see session IDs.\033[0m")


async def cmd_plan(tui: SedimanTUI, args: str) -> None:
    if tui._permission_mode == "plan":
        tui._plan_mode = not tui._plan_mode
        status = "on" if tui._plan_mode else "off"
        cprint(f"  \033[35mℹ Plan mode {status}\033[0m")
        if tui._plan_mode:
            cprint("  \033[2mResearch only — no changes will be made.\033[0m")
        return
    tui._plan_mode = True
    tui._permission_mode = "plan"
    cprint("  \033[35mℹ Plan mode: researching without making changes.\033[0m")
    cprint(
        "  \033[2mType a task to research. Use \033[36m/plan\033[0m"
        "\033[2m again to toggle off.\033[0m"
    )


async def cmd_usage(tui: SedimanTUI, _args: str) -> None:
    conv = tui._agent.get_conversation() if tui._agent else []
    turn_count = len(conv) // 2
    msg_count = len(conv)
    total_chars = sum(len(str(m)) for m in conv)
    est_tokens = total_chars // 4
    cprint("  \033[36mSession Usage\033[0m")
    cprint(f"  Turns:      {turn_count}")
    cprint(f"  Messages:   {msg_count}")
    cprint(f"  Est. tokens: ~{est_tokens:,}")
    cprint(f"  Tasks run:  {tui._task_count}")
    cprint(f"  Model:      {tui.provider}/{tui.model or 'default'}")


async def cmd_color(tui: SedimanTUI, args: str) -> None:
    colors = [
        "red",
        "blue",
        "green",
        "yellow",
        "purple",
        "orange",
        "pink",
        "cyan",
    ]
    if not args.strip():
        current = tui._session_color or "default"
        if current != "default":
            idx = colors.index(current)
            cprint(f"  Current color: \033[{31 + idx}m● {current}\033[0m")
        else:
            cprint("  Current color: default")
        cprint("  Usage: \033[36m/color " + " | ".join(colors) + " | random\033[0m")
        return
    color = args.strip().lower()
    if color == "random":
        import random

        color = random.choice(colors)
    if color not in colors:
        cprint(
            "  \033[31mUnknown color. Use: " + ", ".join(colors) + ", or random\033[0m"
        )
        return
    tui._session_color = color
    idx = colors.index(color)
    cprint(f"  \033[32m+ Session color set to \033[{31 + idx}m● {color}\033[0m")


async def cmd_rename(tui: SedimanTUI, args: str) -> None:
    if not args.strip():
        current = tui._session_name or "(unnamed)"
        cprint(f"  Current name: \033[36m{current}\033[0m")
        cprint("  Usage: \033[36m/rename <name>\033[0m")
        return
    tui._session_name = args.strip()[:30]
    cprint(f"  \033[32m+ Session renamed to: {tui._session_name}\033[0m")


async def cmd_btw(tui: SedimanTUI, args: str) -> None:
    """Ephemeral side question — no conversation context added."""
    if not args:
        cprint("  Usage: \033[36m/btw <question>\033[0m")
        return
    from sediman.llm.provider import create_provider

    llm = create_provider(tui.provider, tui.model, tui.base_url)
    cprint("  \033[33m...\033[0m")
    try:
        response = await llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Answer concisely.",
                },
                {"role": "user", "content": args},
            ]
        )
        cprint(f"  {response}")
    except Exception as e:
        cprint(f"  \033[31mX {e}\033[0m")


async def cmd_doctor(tui: SedimanTUI, _args: str) -> None:
    """Diagnose installation and settings."""
    import shutil

    cprint("  \033[36mSediman Doctor\033[0m")
    cprint("  ──────────────────────────")
    try:
        tui._get_llm()
        cprint(f"  ✓ Provider: {tui.provider}/{tui.model or 'default'}")
    except Exception as e:
        cprint(f"  ✗ Provider: {e}")
    if tui._browser and tui._browser.is_started:
        cprint("  ✓ Browser: running")
    else:
        cprint("  ○ Browser: not started")
    for binary in ["google-chrome", "chromium", "python3"]:
        path = shutil.which(binary)
        if path:
            cprint(f"  ✓ {binary}: {path}")
        else:
            cprint(f"  ○ {binary}: not found")
    cprint("  ──────────────────────────")
    cprint("  \033[2mUse /usage for session stats.\033[0m")


async def cmd_checkpoint_list(tui: SedimanTUI, _args: str) -> None:
    """List all filesystem checkpoints."""
    import subprocess
    from pathlib import Path
    from rich.table import Table

    data_dir = Path.home() / ".sediman" / "sandbox" / "checkpoints"
    if not data_dir.exists():
        cprint("  No checkpoints yet.")
        return

    # Try using the Go CLI for a consistent view
    try:
        result = subprocess.run(
            ["sediman-sandbox", "checkpoint", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            cprint("  \033[36mCheckpoints\033[0m")
            for line in result.stdout.strip().split("\n"):
                cprint(f"  {line}")
            return
    except Exception:
        pass

    # Fallback: scan directory
    entries = sorted(data_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not entries:
        cprint("  No checkpoints yet.")
        return
    table = Table(
        title="Checkpoints",
        show_header=True,
        header_style="cyan",
        box=None,
        padding=(0, 2),
    )
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("When", style="dim")
    for entry in entries:
        if not entry.is_dir():
            continue
        meta = entry / "checkpoint.json"
        name = ""
        if meta.exists():
            import json

            try:
                info = json.loads(meta.read_text())
                name = info.get("name", "")
            except Exception:
                pass
        rel = relative_time(
            datetime.datetime.fromtimestamp(
                entry.stat().st_mtime, datetime.UTC
            ).isoformat(),
            datetime.datetime.now(datetime.UTC),
        )
        table.add_row(entry.name, name, rel)
    _rich.print(table)


async def cmd_checkpoint_create(tui: SedimanTUI, args: str) -> None:
    """Create a checkpoint of a directory."""
    import subprocess
    from pathlib import Path

    if not args:
        cprint("  Usage: \033[36m/checkpoint-create <dir> [--name=<name>]\033[0m")
        return
    parts = args.split()
    target_dir = Path(parts[0]).expanduser().resolve()
    if not target_dir.exists():
        cprint(f"  \033[31mX Directory not found: {target_dir}\033[0m")
        return
    name = ""
    for p in parts[1:]:
        if p.startswith("--name="):
            name = p[7:]
    cmd = ["sediman-sandbox", "checkpoint", "create", str(target_dir)]
    if name:
        cmd.append(f"--name={name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            cprint(f"  \033[32m+ {result.stdout.strip()}\033[0m")
        else:
            cprint(f"  \033[31mX {result.stderr.strip()}\033[0m")
    except FileNotFoundError:
        cprint("  \033[31mX sediman-sandbox not found in PATH.\033[0m")
    except Exception as e:
        cprint(f"  \033[31mX {e}\033[0m")


async def cmd_checkpoint_revert(tui: SedimanTUI, args: str) -> None:
    """Revert a directory to a checkpoint."""
    import subprocess
    from pathlib import Path

    if not args:
        cprint("  Usage: \033[36m/checkpoint-revert <dir> <id>\033[0m")
        return
    parts = args.split()
    if len(parts) < 2:
        cprint("  Usage: \033[36m/checkpoint-revert <dir> <id>\033[0m")
        return
    target_dir = Path(parts[0]).expanduser().resolve()
    cp_id = parts[1]
    if not target_dir.exists():
        cprint(f"  \033[31mX Directory not found: {target_dir}\033[0m")
        return
    try:
        result = subprocess.run(
            [
                "sediman-sandbox",
                "checkpoint",
                "revert",
                str(target_dir),
                f"--id={cp_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            cprint(f"  \033[32m+ {result.stdout.strip()}\033[0m")
        else:
            cprint(f"  \033[31mX {result.stderr.strip()}\033[0m")
    except FileNotFoundError:
        cprint("  \033[31mX sediman-sandbox not found in PATH.\033[0m")
    except Exception as e:
        cprint(f"  \033[31mX {e}\033[0m")


async def cmd_rewind(tui: SedimanTUI, args: str) -> None:
    """Revert current directory to a checkpoint."""
    import subprocess
    from pathlib import Path

    if not args:
        cprint("  Usage: \033[36m/rewind <checkpoint-id>\033[0m")
        cprint("  \033[2mUse /checkpoint to list IDs.\033[0m")
        return
    cp_id = args.strip()
    target_dir = Path.cwd()
    try:
        result = subprocess.run(
            [
                "sediman-sandbox",
                "checkpoint",
                "revert",
                str(target_dir),
                f"--id={cp_id}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            cprint(f"  \033[32m+ {result.stdout.strip()}\033[0m")
        else:
            cprint(f"  \033[31mX {result.stderr.strip()}\033[0m")
    except FileNotFoundError:
        cprint("  \033[31mX sediman-sandbox not found in PATH.\033[0m")
    except Exception as e:
        cprint(f"  \033[31mX {e}\033[0m")


async def cmd_branch(tui: SedimanTUI, args: str) -> None:
    """Save current directory state as a named branch checkpoint."""
    import subprocess
    from pathlib import Path

    if not args:
        cprint("  Usage: \033[36m/branch <name> [dir]\033[0m")
        return
    parts = args.split()
    name = parts[0]
    target_dir = Path(parts[1]).expanduser().resolve() if len(parts) > 1 else Path.cwd()
    if not target_dir.exists():
        cprint(f"  \033[31mX Directory not found: {target_dir}\033[0m")
        return
    try:
        result = subprocess.run(
            [
                "sediman-sandbox",
                "checkpoint",
                "create",
                str(target_dir),
                f"--name={name}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            cprint(f"  \033[32m+ Branch saved: {result.stdout.strip()}\033[0m")
        else:
            cprint(f"  \033[31mX {result.stderr.strip()}\033[0m")
    except FileNotFoundError:
        cprint("  \033[31mX sediman-sandbox not found in PATH.\033[0m")
    except Exception as e:
        cprint(f"  \033[31mX {e}\033[0m")


async def cmd_branches(tui: SedimanTUI, _args: str) -> None:
    """List named branch checkpoints."""
    await cmd_checkpoint_list(tui, "")
