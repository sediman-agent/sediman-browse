from __future__ import annotations

import re
from typing import Awaitable, Callable

import structlog

from sediman.agent.tool_dispatch import ToolRegistry, ToolDefinition

logger = structlog.get_logger()

TerminalApprovalCallback = Callable[[str, str], Awaitable[bool]]

_terminal_approval_callback: TerminalApprovalCallback | None = None
_terminal_session_allowed: bool = False
_memory_manager = None

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


def set_memory_manager(manager) -> None:
    global _memory_manager
    _memory_manager = manager


def get_memory_manager():
    return _memory_manager


def _is_dangerous(command: str) -> bool:
    return any(p.search(command) for p in _DANGEROUS_PATTERNS)


def create_agent_tool_registry() -> ToolRegistry:
    from .misc import (
        _handle_clarify,
        _handle_cronjob,
        _handle_delegate_task,
        _handle_get_schedule_results,
        _handle_list_schedules,
        _handle_memory,
        _handle_session_search,
        _handle_todo,
        _handle_web_extract,
        _handle_web_search,
    )
    from .terminal import _handle_terminal
    from .fileops import (
        _handle_list_files,
        _handle_patch,
        _handle_read_file,
        _handle_search_files,
        _handle_write_file,
    )

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

    registry.register(
        ToolDefinition(
            name="web_extract",
            description="Extract and clean web page content. Returns markdown text from any URL. Use when you need to read a web page's content without interacting with it (faster than browser navigation).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to extract content from",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search query to focus extraction on relevant content",
                    },
                },
                "required": ["url"],
            },
        ),
        _handle_web_extract,
    )

    registry.register(
        ToolDefinition(
            name="session_search",
            description="Search and browse past sessions. Use when the user asks about previous tasks or wants to recall something from a past session.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to find in past sessions",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Specific session ID to view details",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 5)",
                    },
                },
            },
        ),
        _handle_session_search,
    )

    registry.register(
        ToolDefinition(
            name="memory",
            description="Manage agent memory. Use action='add' to store information, 'replace' to update, 'remove' to delete.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace", "remove"],
                        "description": "The action to perform",
                    },
                    "target": {
                        "type": "string",
                        "description": "Target memory area: 'memory' or 'user'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to add or replace",
                    },
                    "old_entry": {
                        "type": "string",
                        "description": "Entry to replace or remove",
                    },
                },
                "required": ["action"],
            },
        ),
        _handle_memory,
    )

    registry.register(
        ToolDefinition(
            name="cronjob",
            description="Manage scheduled cron jobs. Use action='create' to schedule a task, 'list' to see all jobs, 'view' to inspect one, 'update' to modify, 'remove' to delete.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "view", "update", "remove"],
                        "description": "The action to perform",
                    },
                    "cron": {
                        "type": "string",
                        "description": "Cron expression (e.g. '0 9 * * *')",
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description or instruction",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Optional skill to run instead of a task",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "Job ID for view/update/remove actions",
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "Whether the job is enabled (for update action)",
                    },
                },
                "required": ["action"],
            },
        ),
        _handle_cronjob,
    )

    return registry


# Re-exports for backward compatibility
from .skills import _TodoStore, _handle_skill_manage  # noqa: E402, F401
