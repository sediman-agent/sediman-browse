from __future__ import annotations

from typing import Any

import structlog

from sediman.agent.sandbox_runner import SandboxRunner, get_sandbox_dirs
from sediman.agent.tool_dispatch import ToolResult

logger = structlog.get_logger()

_runner: SandboxRunner | None = None


def _get_runner() -> SandboxRunner:
    global _runner
    if _runner is None:
        _runner = SandboxRunner()
    return _runner


async def _handle_terminal(
    command: str | None = None,
    cwd: str | None = None,
    timeout: int = 30,
    allow_net: bool = False,
    **kwargs: Any,
) -> ToolResult:
    if not command or not command.strip():
        return ToolResult(success=False, output="command is required.")

    command = command.strip()
    timeout = max(1, min(timeout, 180))

    from ..tools import _terminal_session_allowed, _terminal_approval_callback
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

    runner = _get_runner()
    allow_dirs = get_sandbox_dirs(cwd)

    result = await runner.run(
        command=command,
        cwd=cwd,
        timeout=timeout,
        allow_dirs=allow_dirs,
        allow_net=allow_net,
    )

    if not result.sandboxed:
        logger.warning(
            "terminal_ran_without_sandbox",
            command=command[:80],
        )

    output = result.output or ""
    if len(output) > 10000:
        output = output[:10000] + "\n... (output truncated)"

    if not result.success and not result.timed_out:
        output = _format_error_output(command, result.exit_code, output)

    return ToolResult(
        success=result.success,
        output=output,
        data={
            "command": command,
            "exit_code": result.exit_code,
            "sandboxed": result.sandboxed,
            "timed_out": result.timed_out,
        },
    )


def _format_error_output(command: str, exit_code: int, output: str) -> str:
    header = (
        f"[Command failed with exit code {exit_code}]\n"
        f"Command: {command[:200]}\n"
    )

    output_lines = output.strip().splitlines() if output.strip() else []
    errors = [l for l in output_lines if _is_error_line(l)]
    warnings = [l for l in output_lines if _is_warning_line(l)]

    parts = [header]
    if output.strip():
        parts.append(f"--- Full output ({len(output_lines)} lines) ---")
        parts.append(output)

    if errors:
        parts.append(
            f"\n--- {len(errors)} error(s) detected ---\n"
            + "\n".join(errors[:20])
        )
    if warnings and not errors:
        parts.append(
            f"\n--- {len(warnings)} warning(s) ---\n"
            + "\n".join(warnings[:10])
        )

    parts.append(
        f"\n--- Action required ---\n"
        f"Read the error output above. Diagnose the root cause, then fix the issue "
        f"and re-run the command. If the same error persists, try a different approach "
        f"or use web_search to research the error message."
    )

    return "\n".join(parts)


def _is_error_line(line: str) -> bool:
    line_lower = line.lower()
    error_indicators = [
        "error:", "error ", "traceback", "exception:", "exception ",
        "fatal:", "fatal ", "panic:", "panic ", "failed:", "failed ",
        "cannot find", "not found", "permission denied", "command not found",
        "no such file", "syntax error", "typeerror:", "valueerror:",
        "modulenotfounderror:", "importerror:", "segmentation fault",
        "aborted", "killed", "out of memory",
    ]
    return any(ind in line_lower for ind in error_indicators)


def _is_warning_line(line: str) -> bool:
    line_lower = line.lower()
    warning_indicators = [
        "warning:", "warning ", "deprecated", "deprecation",
        "warn ", "warn:", "notice:", "note:",
    ]
    return any(ind in line_lower for ind in warning_indicators)
