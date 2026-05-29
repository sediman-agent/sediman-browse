from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable

import structlog

from sediman.agent.tool_dispatch import ToolRegistry, ToolResult
from sediman.llm.provider import ToolDefinition

logger = structlog.get_logger()

TerminalApprovalCallback = Callable[[str, str], Awaitable[bool]]

_terminal_approval_callback: TerminalApprovalCallback | None = None
_terminal_session_allowed: bool = False

_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+(-\w*f\w*\s+)?/"),
    re.compile(r"mkfs\b"),
    re.compile(r":\(\)\s*\{"),
    re.compile(r">\s*/dev/sd"),
    re.compile(r"chmod\s+-R\s+777\s+/"),
    re.compile(r"curl\s.*\|\s*(ba)?sh\s*$"),
    re.compile(r"wget\s.*\|\s*(ba)?sh\s*$"),
]


def set_terminal_approval_callback(cb: TerminalApprovalCallback | None) -> None:
    global _terminal_approval_callback
    _terminal_approval_callback = cb


def set_terminal_allowed(allowed: bool) -> None:
    global _terminal_session_allowed
    _terminal_session_allowed = allowed


def is_terminal_allowed() -> bool:
    return _terminal_session_allowed


def reset_terminal_state() -> None:
    global _terminal_approval_callback, _terminal_session_allowed
    _terminal_approval_callback = None
    _terminal_session_allowed = False


def _is_dangerous(command: str) -> bool:
    return any(p.search(command) for p in _DANGEROUS_PATTERNS)


def _scan_skill_content(name: str, description: str, steps: list[str]) -> list[str]:
    all_text = f"{name} {description} {' '.join(steps)}"
    try:
        from sediman.memory.security import scan_content
        return scan_content(all_text)
    except Exception:
        return []


async def _handle_skill_manage(
    action: str = "create",
    name: str | None = None,
    description: str | None = None,
    steps: list[str] | None = None,
    verification: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        from sediman.skills.engine import SkillEngine
        engine = SkillEngine()

        if action == "list":
            skills = engine.list_skills()
            if not skills:
                return ToolResult(success=True, output="No skills found.", data={"skills": []})
            lines = [f"- {s['name']}: {s['description']}" for s in skills]
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"skills": skills},
            )

        if action == "view":
            if not name:
                return ToolResult(success=False, output="name is required for view action.")
            skill = engine.read(name)
            if not skill:
                return ToolResult(success=False, output=f"Skill '{name}' not found.")
            return ToolResult(
                success=True,
                output=f"Skill: {skill['name']}\nDescription: {skill['description']}\nSteps: {skill.get('steps', [])}\nVerification: {skill.get('verification', 'N/A')}\nUsed: {skill.get('use_count', 0)}x, last: {skill.get('last_used_at', 'never')}",
                data=skill,
            )

        if action == "create":
            if not name or not description or not steps:
                return ToolResult(
                    success=False,
                    output="name, description, and steps are required for create action.",
                )

            threats = _scan_skill_content(name, description, steps)
            if threats:
                return ToolResult(
                    success=False,
                    output=f"Skill rejected — security threats detected: {', '.join(threats)}",
                )

            existing = engine.read(name)
            if existing:
                return ToolResult(
                    success=False,
                    output=f"Skill '{name}' already exists. Use action='patch' to update it.",
                )

            engine.create(
                name=name,
                description=description,
                steps=steps,
                category="auto-created",
                verification=verification,
            )
            logger.info("tool_created_skill", name=name)
            return ToolResult(
                success=True,
                output=f"Skill '{name}' created with {len(steps)} steps.",
                data={"name": name, "steps": len(steps)},
            )

        if action == "patch":
            if not name:
                return ToolResult(success=False, output="name is required for patch action.")

            updates: dict[str, Any] = {}
            if description:
                updates["description"] = description
            if steps:
                updates["steps"] = steps
            if verification:
                updates["verification"] = verification

            if not updates:
                return ToolResult(
                    success=False,
                    output="Nothing to patch — provide description and/or steps.",
                )

            all_text = f"{name} {description or ''} {' '.join(steps or [])}"
            try:
                from sediman.memory.security import scan_content
                threats = scan_content(all_text)
                if threats:
                    return ToolResult(
                        success=False,
                        output=f"Skill rejected — security threats: {', '.join(threats)}",
                    )
            except Exception:
                pass

            patched = engine.patch(name, updates)
            if not patched:
                return ToolResult(
                    success=False,
                    output=f"Skill '{name}' not found. Use action='create' first.",
                )
            logger.info("tool_patched_skill", name=name, version=patched.get("version"))
            return ToolResult(
                success=True,
                output=f"Skill '{name}' patched to version {patched.get('version')}.",
                data=patched,
            )

        if action == "delete":
            if not name:
                return ToolResult(success=False, output="name is required for delete action.")
            deleted = engine.delete(name)
            if not deleted:
                return ToolResult(success=False, output=f"Skill '{name}' not found.")
            logger.info("tool_deleted_skill", name=name)
            return ToolResult(
                success=True,
                output=f"Skill '{name}' deleted.",
                data={"name": name, "deleted": True},
            )

        return ToolResult(
            success=False,
            output=f"Unknown action '{action}'. Use: create, patch, list, view, delete.",
        )

    except Exception as e:
        return ToolResult(success=False, output=f"Skill operation failed: {e}")


class _TodoStore:
    _instance: _TodoStore | None = None

    def __init__(self) -> None:
        self._items: list[dict[str, str]] = []

    @classmethod
    def get(cls) -> _TodoStore:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def list_items(self) -> list[dict[str, str]]:
        return list(self._items)

    def set_items(self, items: list[dict[str, str]]) -> None:
        self._items = items

    def merge_items(self, items: list[dict[str, str]]) -> None:
        existing_by_content = {it["content"]: it for it in self._items}
        for item in items:
            existing_by_content[item["content"]] = item
        self._items = list(existing_by_content.values())

    def format_items(self) -> str:
        if not self._items:
            return "No tasks."
        icons = {"pending": "○", "in_progress": "◐", "completed": "●"}
        lines = []
        for i, item in enumerate(self._items, 1):
            icon = icons.get(item.get("status", "pending"), "○")
            lines.append(f"  {i}. {icon} {item['content']}")
        done = sum(1 for it in self._items if it.get("status") == "completed")
        total = len(self._items)
        lines.append(f"  ({done}/{total} completed)")
        return "\n".join(lines)


async def _handle_clarify(
    question: str | None = None,
    choices: list[str] | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not question or not question.strip():
        return ToolResult(success=False, output="question is required.")
    if choices:
        if len(choices) > 4:
            return ToolResult(success=False, output="Maximum 4 choices allowed.")
        lines = [f"  {i}. {c}" for i, c in enumerate(choices, 1)]
        lines.append(f"  {len(choices) + 1}. Other (type your own answer)")
        choices_text = "\n".join(lines)
        output = f"{question}\n\n{choices_text}\n\nWaiting for user response."
    else:
        output = f"{question}\n\nWaiting for user response."
    return ToolResult(
        success=True,
        output=output,
        data={"question": question, "choices": choices or []},
    )


async def _handle_todo(
    todos: list[dict[str, str]] | None = None,
    merge: bool = False,
    **kwargs: Any,
) -> ToolResult:
    store = _TodoStore.get()

    if todos is None:
        return ToolResult(
            success=True,
            output=store.format_items(),
            data={"todos": store.list_items()},
        )

    for item in todos:
        if "content" not in item or not item["content"].strip():
            return ToolResult(
                success=False,
                output="Each todo item must have a 'content' field.",
            )
        status = item.get("status", "pending")
        if status not in ("pending", "in_progress", "completed"):
            return ToolResult(
                success=False,
                output=f"Invalid status '{status}'. Use: pending, in_progress, or completed.",
            )

    cleaned = [
        {"content": it["content"].strip(), "status": it.get("status", "pending")}
        for it in todos
    ]

    if merge:
        store.merge_items(cleaned)
    else:
        store.set_items(cleaned)

    return ToolResult(
        success=True,
        output=f"Todo list updated.\n{store.format_items()}",
        data={"todos": store.list_items()},
    )


async def _handle_terminal(
    command: str | None = None,
    cwd: str | None = None,
    timeout: int = 30,
    **kwargs: Any,
) -> ToolResult:
    if not command or not command.strip():
        return ToolResult(success=False, output="command is required.")

    command = command.strip()
    timeout = max(1, min(timeout, 180))

    if _is_dangerous(command):
        return ToolResult(
            success=False,
            output=f"Command blocked (dangerous pattern): {command[:100]}",
            data={"command": command, "blocked": True},
        )

    if not _terminal_session_allowed:
        if _terminal_approval_callback is not None:
            approved = await _terminal_approval_callback(command, cwd or ".")
            if not approved:
                return ToolResult(
                    success=False,
                    output=f"Command not approved: {command[:100]}",
                    data={"command": command, "denied": True},
                )
        else:
            return ToolResult(
                success=False,
                output="Terminal access not available. No approval mechanism configured.",
                data={"command": command, "denied": True},
            )

    proc = None
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        parts: list[str] = []
        if stdout:
            parts.append(stdout.decode(errors="replace"))
        if stderr:
            parts.append(stderr.decode(errors="replace"))
        output = "\n".join(parts) if parts else "(no output)"
        if proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"
        if len(output) > 10000:
            output = output[:10000] + "\n... (output truncated)"
        return ToolResult(
            success=proc.returncode == 0,
            output=output,
            data={"command": command, "exit_code": proc.returncode},
        )
    except asyncio.TimeoutError:
        if proc is not None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return ToolResult(
            success=False,
            output=f"Command timed out after {timeout}s: {command[:100]}",
            data={"command": command, "timed_out": True},
        )
    except Exception as e:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return ToolResult(success=False, output=f"Command failed: {e}")


async def _handle_web_search(query: str, **kwargs: Any) -> ToolResult:
    return ToolResult(
        success=True,
        output=f"Web search delegated to browser subagent for: {query}",
        data={"query": query, "delegated": True},
    )


async def _handle_delegate_task(task: str, **kwargs: Any) -> ToolResult:
    return ToolResult(
        success=True,
        output=f"Task delegation queued: {task[:100]}",
        data={"task": task, "delegated": True},
    )


async def _handle_get_schedule_results(
    job_id: str | None = None,
    task_filter: str | None = None,
    limit: int = 5,
    **kwargs: Any,
) -> ToolResult:
    try:
        from sediman.scheduler.cron import CronManager
        cron = CronManager()
        results = cron.get_results(job_id=job_id, task_filter=task_filter, limit=limit)
        if not results:
            return ToolResult(
                success=True,
                output="No scheduled task results found.",
                data={"results": []},
            )
        lines = []
        for r in results:
            lines.append(
                f"[{r['timestamp']}] Job {r['job_id']}: {r.get('task', 'N/A')}\n{r['result'][:500]}"
            )
        output = "\n\n---\n\n".join(lines)
        return ToolResult(
            success=True,
            output=output,
            data={"results": results, "count": len(results)},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to query schedule results: {e}")


async def _handle_list_schedules(**kwargs: Any) -> ToolResult:
    try:
        from sediman.scheduler.cron import CronManager
        cron = CronManager()
        jobs = cron.list_jobs()
        if not jobs:
            return ToolResult(success=True, output="No scheduled tasks.", data={"jobs": []})
        lines = []
        for j in jobs:
            status = "enabled" if j.get("enabled", True) else "disabled"
            lines.append(
                f"[{j['id'][:8]}] ({status}) {j['cron']} -> {j['task'][:80]}\n"
                f"  last_run: {j.get('last_run', 'never')} | last_result: {(j.get('last_result') or 'N/A')[:200]}"
            )
        return ToolResult(
            success=True,
            output="\n\n".join(lines),
            data={"jobs": jobs},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to list schedules: {e}")


async def _handle_read_file(
    path: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not path:
        return ToolResult(success=False, output="path is required.")
    try:
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return ToolResult(success=False, output=f"File not found: {p}")
        if not p.is_file():
            return ToolResult(success=False, output=f"Not a file: {p}")
        if p.stat().st_size > 500_000:
            return ToolResult(success=False, output=f"File too large ({p.stat().st_size} bytes). Use terminal with head/tail.")
        raw = p.read_text(errors="replace")
        lines = raw.splitlines()
        total_lines = len(lines)
        start = max(1, (offset or 1))
        end = start + (limit or total_lines)
        start = min(start, total_lines + 1)
        sliced = lines[start - 1 : end - 1]
        numbered = [f"{i}: {line}" for i, line in zip(range(start, start + len(sliced)), sliced)]
        content = "\n".join(numbered)
        if len(content) > 50000:
            content = content[:50000] + "\n... (truncated)"
        header = f"File: {p} ({total_lines} lines)"
        if offset or limit:
            header += f" [showing lines {start}-{start + len(sliced) - 1}]"
        return ToolResult(
            success=True,
            output=f"{header}\n{content}",
            data={"path": str(p), "size": p.stat().st_size, "total_lines": total_lines},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to read file: {e}")


async def _handle_list_files(
    path: str | None = None,
    pattern: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        from pathlib import Path
        import glob as globmod
        base = Path(path or ".").expanduser().resolve()
        if not base.exists():
            return ToolResult(success=False, output=f"Directory not found: {base}")
        if not base.is_dir():
            return ToolResult(success=False, output=f"Not a directory: {base}")
        pat = pattern or "*"
        matches = sorted(base.glob(pat))[:100]
        if not matches:
            return ToolResult(
                success=True,
                output=f"No files matching '{pat}' in {base}",
                data={"files": []},
            )
        lines = []
        for m in matches:
            if m.is_dir():
                lines.append(f"  {m.name}/")
            else:
                size = m.stat().st_size
                lines.append(f"  {m.name}  ({size:,} bytes)")
        return ToolResult(
            success=True,
            output=f"Files in {base} matching '{pat}':\n" + "\n".join(lines),
            data={"files": [str(m) for m in matches]},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to list files: {e}")


def _fuzzy_match_hunk(lines: list[str], old_lines: list[str], start: int) -> int | None:
    best_pos: int | None = None
    best_score = -1
    old_len = len(old_lines)
    search_end = min(len(lines), start + old_len + 20)
    for i in range(max(0, start - 5), search_end):
        if i + old_len > len(lines):
            break
        score = 0
        for j in range(old_len):
            a = lines[i + j].strip()
            b = old_lines[j].strip()
            if a == b:
                score += 3
            elif a in b or b in a:
                score += 2
            elif _token_overlap(a, b) > 0.5:
                score += 1
        if score > best_score:
            best_score = score
            best_pos = i
    if best_pos is not None and best_score >= old_len:
        return best_pos
    return None


def _token_overlap(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


async def _handle_write_file(
    path: str | None = None,
    content: str | None = None,
    create_dirs: bool = True,
    **kwargs: Any,
) -> ToolResult:
    if not path:
        return ToolResult(success=False, output="path is required.")
    if content is None:
        return ToolResult(success=False, output="content is required.")
    try:
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        existed = p.exists()
        if create_dirs:
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        size = p.stat().st_size
        action = "Updated" if existed else "Created"
        logger.info("tool_wrote_file", path=str(p), size=size, new=not existed)
        return ToolResult(
            success=True,
            output=f"{action} {p} ({size:,} bytes)",
            data={"path": str(p), "size": size, "existed": existed},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to write file: {e}")


async def _handle_patch(
    path: str | None = None,
    old: str | None = None,
    new: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not path:
        return ToolResult(success=False, output="path is required.")
    if old is None or new is None:
        return ToolResult(success=False, output="old and new are both required.")
    try:
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return ToolResult(success=False, output=f"File not found: {p}")
        if not p.is_file():
            return ToolResult(success=False, output=f"Not a file: {p}")
        content = p.read_text(encoding="utf-8", errors="replace")
        if old in content:
            count = content.count(old)
            if count > 1:
                return ToolResult(
                    success=False,
                    output=f"Found {count} matches for old text. Provide more context to make it unique.",
                    data={"matches": count},
                )
            patched = content.replace(old, new, 1)
            p.write_text(patched, encoding="utf-8")
            old_start = content[: content.index(old)].count("\n") + 1
            logger.info("tool_patched_file", path=str(p), line=old_start, mode="exact")
            return ToolResult(
                success=True,
                output=f"Patched {p} (line {old_start}, exact match)",
                data={"path": str(p), "line": old_start},
            )

        lines = content.splitlines()
        old_lines = old.splitlines()
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip() == old_lines[0].strip():
                content_start = i
                break
        pos = _fuzzy_match_hunk(lines, old_lines, content_start)
        if pos is None:
            return ToolResult(
                success=False,
                output="Could not find a matching location for the old text. Check indentation, whitespace, or provide more surrounding context.",
            )
        new_lines = new.splitlines()
        lines[pos : pos + len(old_lines)] = new_lines
        patched = "\n".join(lines)
        p.write_text(patched, encoding="utf-8")
        logger.info("tool_patched_file", path=str(p), line=pos + 1, mode="fuzzy")
        return ToolResult(
            success=True,
            output=f"Patched {p} (line {pos + 1}, fuzzy match)",
            data={"path": str(p), "line": pos + 1},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to patch file: {e}")


async def _handle_search_files(
    query: str | None = None,
    path: str | None = None,
    file_pattern: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not query:
        return ToolResult(success=False, output="query is required.")
    import subprocess
    from pathlib import Path
    base = Path(path or ".").expanduser().resolve()
    if not base.exists():
        return ToolResult(success=False, output=f"Directory not found: {base}")
    cmd = ["rg", "--no-heading", "-n", "--max-count", "50"]
    if file_pattern:
        cmd.extend(["--glob", file_pattern])
    cmd.append(query)
    cmd.append(str(base))
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return ToolResult(success=False, output="Search timed out after 15 seconds.")
        if proc.returncode == 2:
            return ToolResult(success=False, output=f"Search error: {stderr[:500]}")
        if proc.returncode == 1 or not stdout.strip():
            return ToolResult(
                success=True,
                output=f"No matches found for '{query}' in {base}",
                data={"matches": [], "count": 0},
            )
        output = stdout.strip()
        if len(output) > 10000:
            output = output[:10000] + "\n... (truncated)"
        match_count = output.count("\n") + 1
        return ToolResult(
            success=True,
            output=output,
            data={"matches": match_count, "query": query, "path": str(base)},
        )
    except FileNotFoundError:
        return ToolResult(
            success=False,
            output="ripgrep (rg) is not installed. Install it or use terminal with grep.",
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Failed to search files: {e}")
    finally:
        if proc is not None:
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass


def create_agent_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="skill_manage",
            description="Manage reusable skills. Use action='create' after completing a complex multi-step task (5+ steps, error recovery, non-obvious workflow). Use action='patch' when you find an existing skill is outdated or broken. Use action='delete' to remove a skill that is no longer useful. Use action='list' to see all skills, 'view' to inspect one.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "patch", "list", "view", "delete"],
                        "description": "The action to perform. 'create' saves a new skill, 'patch' updates an existing one, 'delete' removes a skill, 'list' shows all skills, 'view' reads one skill.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Short kebab-case name for the skill (required for create, patch, view)",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this skill does in one sentence (for create and patch)",
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of step descriptions that capture the workflow (for create and patch)",
                    },
                    "verification": {
                        "type": "string",
                        "description": "How to verify the skill succeeded — what should be true after execution (for create and patch)",
                    },
                },
                "required": ["action"],
            },
        ),
        _handle_skill_manage,
    )

    registry.register(
        ToolDefinition(
            name="web_search",
            description="Search the web for information. Use when you need to find current data, verify facts, or look up URLs before browsing.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
        ),
        _handle_web_search,
    )

    registry.register(
        ToolDefinition(
            name="delegate_task",
            description="Delegate a subtask to an isolated subagent. Use for parallelizable independent tasks like researching multiple items simultaneously.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The task to delegate to the subagent",
                    },
                },
                "required": ["task"],
            },
        ),
        _handle_delegate_task,
    )

    registry.register(
        ToolDefinition(
            name="get_schedule_results",
            description="Retrieve past execution results from scheduled tasks. Use when the user asks about data from a previous scheduled run (e.g., 'what was the last PDD price you found?').",
            parameters={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Optional specific job ID to look up",
                    },
                    "task_filter": {
                        "type": "string",
                        "description": "Optional keyword to filter by task description or result content (e.g., 'PDD', 'stock', 'weather')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results to return (default 5)",
                    },
                },
            },
        ),
        _handle_get_schedule_results,
    )

    registry.register(
        ToolDefinition(
            name="terminal",
            description="Execute shell commands on the local system. Each command requires user approval before execution unless the user has approved all commands for the session. Use for file operations, running scripts, installing packages, and system tasks. Do NOT use for reading files — prefer the read_file tool. Do NOT use for searching — prefer the search_files tool. Set timeout for long-running commands.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command (default: current directory)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30, max: 180)",
                    },
                },
                "required": ["command"],
            },
        ),
        _handle_terminal,
    )

    registry.register(
        ToolDefinition(
            name="clarify",
            description="Ask the user a question when you need clarification, feedback, or a decision before proceeding. Supports multiple-choice with an implicit 'Other' free-text option. Use this when the task is ambiguous, you need to confirm an approach, or there are multiple valid paths forward.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user",
                    },
                    "choices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of up to 4 choices for the user to pick from. An implicit 'Other' option is always added. Omit for free-text questions.",
                    },
                },
                "required": ["question"],
            },
        ),
        _handle_clarify,
    )

    registry.register(
        ToolDefinition(
            name="todo",
            description="Manage a session task list for complex multi-step tasks. Call with no parameters to read the current list. Provide a 'todos' array to create or update items. Each item has 'content' (string) and 'status' (pending, in_progress, or completed). Set merge=true to update existing items by content match instead of replacing the whole list.",
            parameters={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "Description of the task item",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "Status of the item (default: pending)",
                                },
                            },
                            "required": ["content"],
                        },
                        "description": "List of todo items to set or merge",
                    },
                    "merge": {
                        "type": "boolean",
                        "description": "If true, merge with existing items by content match. If false (default), replace the entire list.",
                    },
                },
            },
        ),
        _handle_todo,
    )

    registry.register(
        ToolDefinition(
            name="list_schedules",
            description="List all scheduled tasks with their status, cron expressions, last run time, and last result. Use when the user asks about their scheduled tasks or cron jobs.",
            parameters={
                "type": "object",
                "properties": {},
            },
        ),
        _handle_list_schedules,
    )

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read the contents of a local file with line numbers. Use for CSV files, logs, configs, source code, or any file the user asks to see. Do NOT use terminal cat — prefer this tool. Supports ~ expansion, pagination with offset/limit.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file (supports ~ for home directory)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-based line number to start reading from (default: 1)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (default: all lines)",
                    },
                },
                "required": ["path"],
            },
        ),
        _handle_read_file,
    )

    registry.register(
        ToolDefinition(
            name="list_files",
            description="List files in a directory. Use when the user asks what files exist in a location or to find a specific file by pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: current directory, supports ~)",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (default: '*')",
                    },
                },
            },
        ),
        _handle_list_files,
    )

    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write content to a local file. Creates the file if it doesn't exist, overwrites if it does. Automatically creates parent directories. Use for creating new files, saving output, or replacing entire file contents. Do NOT use for small edits — prefer the patch tool.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file (supports ~ for home directory)",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                    "create_dirs": {
                        "type": "boolean",
                        "description": "Create parent directories if they don't exist (default: true)",
                    },
                },
                "required": ["path", "content"],
            },
        ),
        _handle_write_file,
    )

    registry.register(
        ToolDefinition(
            name="patch",
            description="Apply a targeted find-and-replace edit to a file. Provide the exact text to find (old) and what to replace it with (new). The tool uses fuzzy matching to survive minor whitespace differences. For multiple non-adjacent edits, call this tool once per edit. Do NOT use for rewriting entire files — prefer write_file for that.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit (supports ~ for home directory)",
                    },
                    "old": {
                        "type": "string",
                        "description": "The exact text to find in the file. Include enough surrounding context to make the match unique.",
                    },
                    "new": {
                        "type": "string",
                        "description": "The text to replace the old text with",
                    },
                },
                "required": ["path", "old", "new"],
            },
        ),
        _handle_patch,
    )

    registry.register(
        ToolDefinition(
            name="search_files",
            description="Search file contents using ripgrep. Use for finding where a function is defined, where a variable is used, or any text pattern across files. Supports regex. Faster and more accurate than using terminal grep. Do NOT use for listing files — prefer list_files.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search pattern (supports regex, e.g. 'def my_function' or 'import.*os')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory, supports ~)",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files (e.g. '*.py', '*.{js,ts}', '*.md')",
                    },
                },
                "required": ["query"],
            },
        ),
        _handle_search_files,
    )

    return registry
