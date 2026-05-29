from __future__ import annotations

import asyncio
from typing import Any

import structlog

from sediman.agent.tool_dispatch import ToolResult

logger = structlog.get_logger()


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

    from ..tools import _is_dangerous
    if _is_dangerous(command):
        return ToolResult(
            success=False,
            output=f"Command blocked (dangerous pattern): {command[:100]}",
            data={"command": command, "blocked": True, "dangerous_pattern": True},
        )

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
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return ToolResult(
            success=False,
            output=f"Command timed out after {timeout}s: {command[:100]}",
            data={"command": command, "timed_out": True},
        )
    except (OSError, asyncio.CancelledError) as e:
        logger.error("terminal_execution_error", command=command[:100], error=str(e))
        return ToolResult(success=False, output=f"Command failed: {e}")
