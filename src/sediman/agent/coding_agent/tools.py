from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sediman.agent.tool_dispatch import ToolRegistry, ToolResult, ToolDefinition


async def _handle_glob(
    pattern: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not pattern:
        return ToolResult(success=False, output="pattern is required.")
    try:
        base = Path(path or ".").expanduser().resolve()
        if not base.exists():
            return ToolResult(success=False, output=f"Directory not found: {base}")
        matches = sorted(base.glob(pattern))[:200]
        if not matches:
            return ToolResult(
                success=True,
                output=f"No files matching '{pattern}' in {base}",
                data={"files": [], "count": 0},
            )
        lines = []
        for m in matches:
            rel = m.relative_to(base) if m.is_relative_to(base) else m
            suffix = "/" if m.is_dir() else ""
            lines.append(str(rel) + suffix)
        output = "\n".join(lines)
        if len(output) > 15000:
            output = output[:15000] + "\n... (truncated)"
        return ToolResult(
            success=True,
            output=output,
            data={"files": [str(m) for m in matches], "count": len(matches)},
        )
    except Exception as e:
        return ToolResult(success=False, output=f"Glob failed: {e}")


async def _handle_git_status(
    path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        cwd = str(Path(path).expanduser().resolve()) if path else None
        result = subprocess.run(
            ["git", "status", "--porcelain", "--branch"],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        output = result.stdout.strip() or "(clean working tree)"
        if result.returncode != 0:
            if "not a git repository" in result.stderr.lower():
                return ToolResult(
                    success=True,
                    output="Not a git repository (or any parent directory).",
                    data={"is_repo": False},
                )
            return ToolResult(
                success=False,
                output=f"git status failed: {result.stderr[:500]}",
            )

        branch_line = output.splitlines()[0] if output else ""
        status_lines = output.splitlines()[1:] if output else []

        staged = [l for l in status_lines if l[0] != " " and l[1] != "?"]
        unstaged = [l for l in status_lines if l[1] != " "]
        untracked = [l for l in status_lines if l.startswith("??")]

        summary_parts = [branch_line]
        if staged:
            summary_parts.append(f"Staged: {len(staged)} file(s)")
        if unstaged:
            summary_parts.append(f"Modified: {len(unstaged)} file(s)")
        if untracked:
            summary_parts.append(f"Untracked: {len(untracked)} file(s)")

        return ToolResult(
            success=True,
            output="\n".join(summary_parts + [""] + output.splitlines()),
            data={
                "is_repo": True,
                "branch": branch_line,
                "staged_count": len(staged),
                "modified_count": len(unstaged),
                "untracked_count": len(untracked),
            },
        )
    except FileNotFoundError:
        return ToolResult(
            success=False, output="git is not installed or not in PATH."
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="git status timed out.")
    except Exception as e:
        return ToolResult(success=False, output=f"git status failed: {e}")


async def _handle_git_diff(
    staged: bool = False,
    path: str | None = None,
    file_path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        cwd = str(Path(path).expanduser().resolve()) if path else None
        cmd = ["git", "diff", "--unified=5"]
        if staged:
            cmd.append("--staged")
        if file_path:
            cmd.extend(["--", file_path])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output=f"git diff failed: {result.stderr[:500]}",
            )
        output = result.stdout.strip()
        if not output:
            return ToolResult(
                success=True,
                output="No changes (working tree clean).",
                data={"has_changes": False},
            )
        if len(output) > 15000:
            output = output[:15000] + "\n... (diff truncated)"
        return ToolResult(
            success=True,
            output=output,
            data={"has_changes": True},
        )
    except FileNotFoundError:
        return ToolResult(
            success=False, output="git is not installed or not in PATH."
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="git diff timed out.")
    except Exception as e:
        return ToolResult(success=False, output=f"git diff failed: {e}")


async def _handle_git_log(
    count: int = 10,
    path: str | None = None,
    file_path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        cwd = str(Path(path).expanduser().resolve()) if path else None
        count = max(1, min(count, 50))
        cmd = [
            "git", "log",
            f"-{count}",
            "--oneline",
            "--decorate",
            "--no-merges",
        ]
        if file_path:
            cmd.extend(["--", file_path])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output=f"git log failed: {result.stderr[:500]}",
            )
        output = result.stdout.strip()
        if not output:
            output = "(no commits)"
        return ToolResult(
            success=True,
            output=output,
            data={"commits": output.count("\n") + 1 if output != "(no commits)" else 0},
        )
    except FileNotFoundError:
        return ToolResult(
            success=False, output="git is not installed or not in PATH."
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="git log timed out.")
    except Exception as e:
        return ToolResult(success=False, output=f"git log failed: {e}")


async def _handle_git_commit(
    message: str | None = None,
    files: list[str] | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    if not message or not message.strip():
        return ToolResult(success=False, output="message is required.")
    try:
        cwd = str(Path(path).expanduser().resolve()) if path else None

        if files:
            add_cmd = ["git", "add"] + files
            add_result = subprocess.run(
                add_cmd, capture_output=True, text=True, timeout=10, cwd=cwd,
            )
            if add_result.returncode != 0:
                return ToolResult(
                    success=False,
                    output=f"git add failed: {add_result.stderr[:500]}",
                )

        commit_cmd = ["git", "commit", "-m", message.strip()]
        if not files:
            commit_cmd.insert(1, "-a")

        result = subprocess.run(
            commit_cmd, capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output=f"git commit failed: {result.stderr[:500]}",
            )
        output = result.stdout.strip() or result.stderr.strip()
        return ToolResult(
            success=True,
            output=output,
            data={"message": message.strip(), "files": files},
        )
    except FileNotFoundError:
        return ToolResult(
            success=False, output="git is not installed or not in PATH."
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="git commit timed out.")
    except Exception as e:
        return ToolResult(success=False, output=f"git commit failed: {e}")


async def _handle_git_branch(
    action: str = "list",
    name: str | None = None,
    path: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    try:
        cwd = str(Path(path).expanduser().resolve()) if path else None

        if action == "list":
            cmd = ["git", "branch", "-a"]
        elif action == "create":
            if not name:
                return ToolResult(success=False, output="name is required for action='create'.")
            cmd = ["git", "checkout", "-b", name]
        elif action == "switch":
            if not name:
                return ToolResult(success=False, output="name is required for action='switch'.")
            cmd = ["git", "checkout", name]
        elif action == "current":
            cmd = ["git", "branch", "--show-current"]
        else:
            return ToolResult(
                success=False,
                output=f"Unknown action: {action}. Use 'list', 'create', 'switch', or 'current'.",
            )

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        if result.returncode != 0:
            return ToolResult(
                success=False,
                output=f"git branch failed: {result.stderr[:500]}",
            )
        output = result.stdout.strip()
        return ToolResult(
            success=True,
            output=output,
            data={"action": action, "name": name},
        )
    except FileNotFoundError:
        return ToolResult(
            success=False, output="git is not installed or not in PATH."
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="git branch timed out.")
    except Exception as e:
        return ToolResult(success=False, output=f"git branch failed: {e}")


def create_coding_tool_registry() -> ToolRegistry:
    from sediman.agent.tools import create_agent_tool_registry

    full = create_agent_tool_registry()
    coding = ToolRegistry()

    allowed = {
        "terminal", "read_file", "write_file", "patch",
        "list_files", "search_files", "web_search",
        "web_extract", "skill_search", "skill_manage",
        "delegate_task", "clarify", "todo",
    }

    for name in full.list_tools():
        if name in allowed:
            coding.register(full.get_definition(name), full._handlers[name])

    _register_coding_tools(coding)
    _register_web_fetch_alias(coding)

    return coding


def _register_coding_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="glob",
            description=(
                "Find files matching a glob pattern. Supports ** for recursive "
                "directory matching. Use to discover project structure, find files "
                "by type, or locate specific files. Returns sorted file paths. "
                "Faster than list_files when you know the pattern.\n\n"
                "DO: '**/*.py' for all Python files, 'src/**/*.test.ts' for test files\n"
                "DO: '**/*.{js,ts}' for multiple extensions\n"
                "DON'T: Use for content search — prefer search_files"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Glob pattern. Supports ** for recursive matching. "
                            "Examples: '**/*.py', 'src/**/*.ts', '**/*.test.*'"
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory (default: current directory, supports ~)",
                    },
                },
                "required": ["pattern"],
            },
        ),
        _handle_glob,
    )

    registry.register(
        ToolDefinition(
            name="git_status",
            description=(
                "Show the working tree status including current branch, staged "
                "changes, unstaged changes, and untracked files. Use before "
                "starting work to understand the current state, and after making "
                "changes to see what was modified.\n\n"
                "DO: Check status at the start of every coding task\n"
                "DON'T: Proceed if there are unexpected changes without asking"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the git repository (default: current directory)",
                    },
                },
            },
        ),
        _handle_git_status,
    )

    registry.register(
        ToolDefinition(
            name="git_diff",
            description=(
                "Show detailed unified diff between the working tree and the index "
                "(unstaged and staged changes). Use to review your own changes "
                "before considering work complete. Shows 5 lines of context.\n\n"
                "DO: Always review diffs before finishing a task\n"
                "DO: Use staged=true to see what would be committed\n"
                "DO: Use file_path to focus on a specific file\n"
                "DON'T: Skip reviewing diffs — it catches unintended changes"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show only staged changes (default: false)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to the git repository (default: current directory)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Show diff for a specific file only",
                    },
                },
            },
        ),
        _handle_git_diff,
    )

    registry.register(
        ToolDefinition(
            name="git_log",
            description=(
                "Show recent commit history (oneline format, no merges). "
                "Use to understand the project's change history, find when a feature "
                "was added, or see the commit message style.\n\n"
                "DO: Check recent commits to understand project momentum\n"
                "DO: Use file_path to see history of a specific file\n"
                "DON'T: Use for anything other than reading history"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of recent commits to show (default: 10, max: 50)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to the git repository (default: current directory)",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Show history for a specific file only",
                    },
                },
            },
        ),
        _handle_git_log,
    )

    registry.register(
        ToolDefinition(
            name="git_commit",
            description=(
                "Stage and commit changes with a descriptive message. "
                "By default commits all modified tracked files (equivalent to git commit -a). "
                "Use 'files' parameter to commit specific files only.\n\n"
                "DO: Write descriptive messages explaining WHY, not just WHAT\n"
                "DO: Review with git_diff before committing\n"
                "DO: Match the project's commit message convention (check git_log)\n"
                "DON'T: Commit without user approval\n"
                "DON'T: Commit generated files, build artifacts, or node_modules\n\n"
                "Example: git_commit(message='Fix race condition in auth token refresh')\n"
                "Example: git_commit(message='Update API types', files=['src/types.ts', 'src/api.ts'])"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Commit message (required). Be descriptive — explain WHY.",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Specific files to commit. If omitted, commits all modified "
                            "tracked files (git commit -a)."
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to git repository (default: current directory)",
                    },
                },
                "required": ["message"],
            },
        ),
        _handle_git_commit,
    )

    registry.register(
        ToolDefinition(
            name="git_branch",
            description=(
                "Manage git branches. Actions: 'list' (show all branches), "
                "'create' (create and switch to new branch), 'switch' (switch to "
                "existing branch), 'current' (show current branch name).\n\n"
                "DO: Create feature branches for significant changes\n"
                "DO: Check current branch with action='current'\n"
                "DON'T: Switch branches with uncommitted changes\n\n"
                "Example: git_branch(action='create', name='feature/add-auth')\n"
                "Example: git_branch(action='switch', name='main')\n"
                "Example: git_branch(action='current')"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "create", "switch", "current"],
                        "description": "Action: 'list' (show branches), 'create' (new branch), 'switch' (change branch), 'current' (show name)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Branch name (required for 'create' and 'switch')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to git repository (default: current directory)",
                    },
                },
                "required": ["action"],
            },
        ),
        _handle_git_branch,
    )


def _register_web_fetch_alias(registry: ToolRegistry) -> None:
    if registry.has_tool("web_extract") and not registry.has_tool("web_fetch"):
        web_extract_def = registry.get_definition("web_extract")
        handler = registry._handlers["web_extract"]
        registry.register(
            ToolDefinition(
                name="web_fetch",
                description=(
                    "Fetch and extract web page content as clean markdown. "
                    "Use to read documentation, blog posts, API references, or "
                    "any web content without browser overhead. Returns readable "
                    "text with navigation and ads stripped out.\n\n"
                    "DO: Use for reading online documentation during coding\n"
                    "DO: Use for checking API docs, package readmes, tech blogs\n"
                    "DON'T: Use for pages requiring login, JS rendering, or interaction\n"
                    "DON'T: Use for web automation tasks — those need browser tools"
                ),
                parameters=web_extract_def.parameters,
            ),
            handler,
        )
