"""Sandbox runner — wraps sediman-sandbox CLI for isolated command execution.

Replaces direct subprocess calls with sandboxed execution via the Go wrapper.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog

logger = structlog.get_logger()

_DANGEROUS_PATTERNS: list[str] = [
    "rm -rf /", "mkfs", "dd if=", "> /dev/sd", "chmod -R 777 /",
    "curl .* | sh", "wget .* | sh", "eval(", "exec(",
]


class SandboxRunner:
    """Runs shell commands inside sediman-sandbox for filesystem isolation."""

    def __init__(self, cli: str | None = None) -> None:
        self.cli = cli or self._find_cli()
        self.available = Path(self.cli).exists()

    def _find_cli(self) -> str:
        for name in ("sediman-sandbox",):
            if p := shutil_which(name):
                return p
        for p in (
            Path.home() / ".local" / "bin" / "sediman-sandbox",
            Path.home() / ".sediman" / "sandbox" / "sediman-sandbox",
            Path("/usr/local/bin/sediman-sandbox"),
        ):
            if p.exists():
                return str(p)
        return "sediman-sandbox"

    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 30,
        allow_dirs: list[str] | None = None,
        allow_net: bool = False,
    ) -> tuple[bool, str, int]:
        """Run command in sandbox. Returns (success, output, exit_code)."""
        if not self.available:
            return False, "sediman-sandbox not available", 1

        args = [
            self.cli,
            "run",
            f"--timeout={timeout}s",
        ]
        if allow_net:
            args.append("--allow-net")
        for d in allow_dirs or []:
            args.append(f"--allow-dir={d}")
        if cwd:
            args.append(f"--work-dir={cwd}")

        args.extend(["--", "bash", "-c", command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
            output = ""
            if stdout:
                output += stdout.decode(errors="replace")
            if stderr:
                output += stderr.decode(errors="replace")
            return proc.returncode == 0, output, proc.returncode
        except asyncio.TimeoutError:
            return False, f"Sandbox timed out after {timeout}s", 124
        except Exception as e:
            logger.debug("sandbox_run_failed", error=str(e))
            return False, f"Sandbox error: {e}", 1


def is_dangerous(command: str) -> bool:
    """Quick heuristic for commands that need sandboxing."""
    lowered = command.lower().strip()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in lowered:
            return True
    return False


def get_sandbox_dirs(cwd: str | None) -> list[str]:
    """Determine which directories to allow based on cwd."""
    dirs: list[str] = []
    if cwd and cwd != ".":
        dirs.append(os.path.abspath(cwd))
    # Always allow the project directory
    proj = os.getcwd()
    if proj not in dirs:
        dirs.append(proj)
    # Always allow tmp
    if "/tmp" not in dirs:
        dirs.append("/tmp")
    return dirs


def shutil_which(cmd: str) -> str | None:
    try:
        import shutil
        return shutil.which(cmd)
    except Exception:
        return None
