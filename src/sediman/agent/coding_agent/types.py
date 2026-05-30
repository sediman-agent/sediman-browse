from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodingResult:
    text: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    iterations: int = 0
    tool_calls: list[str] = field(default_factory=list)
    files_edited: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)
    verifications_passed: int = 0
    verifications_failed: int = 0


@dataclass
class ProjectInfo:
    project_type: str = ""
    root_dir: str = ""
    config_files: list[str] = field(default_factory=list)
    lint_commands: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    format_commands: list[str] = field(default_factory=list)
    build_commands: list[str] = field(default_factory=list)
    package_manager: str = ""
    language: str = ""
    frameworks: list[str] = field(default_factory=list)
    project_instructions: str = ""
    conventions: dict[str, str] = field(default_factory=dict)


@dataclass
class VerifyResult:
    command: str
    success: bool
    output: str
    exit_code: int
    tool: str = ""


@dataclass
class PlanStep:
    description: str
    files_to_read: list[str] = field(default_factory=list)
    files_to_edit: list[str] = field(default_factory=list)
    commands_to_run: list[str] = field(default_factory=list)
    verification: str = ""


@dataclass
class HookContext:
    tool_name: str
    tool_input: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    agent_name: str = "coding_agent"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorEvent:
    line: str
    stream: str
    timestamp: float = 0.0


@dataclass
class MonitorResult:
    exit_code: int | None = None
    output: str = ""
    events: list[MonitorEvent] = field(default_factory=list)
    timed_out: bool = False
    stopped_by_pattern: bool = False
    matched_pattern: str = ""
    elapsed: float = 0.0
