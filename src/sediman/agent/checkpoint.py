"""Pre-edit checkpointing — auto-snapshots before dangerous tool calls.

Integrates with ToolRegistry to create filesystem checkpoints before
write_file, patch, or terminal operations. Users can /rewind if
something goes wrong.
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_DANGEROUS_TOOLS = {"write_file", "patch", "terminal"}


@dataclass
class CheckpointInfo:
    id: str
    name: str
    target_dir: str
    created_at: str


class CheckpointManager:
    """Manages pre-edit filesystem checkpoints via sediman-sandbox CLI."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._last_checkpoint: CheckpointInfo | None = None
        self._cli = self._find_cli()

    def _find_cli(self) -> str:
        """Locate sediman-sandbox binary in PATH or common locations."""
        for name in ("sediman-sandbox", "sediman_sandbox"):
            if found := shutil.which(name):
                return found
        # Common fallback paths
        for p in (
            Path.home() / ".local" / "bin" / "sediman-sandbox",
            Path.home() / ".sediman" / "sandbox" / "sediman-sandbox",
            Path("/usr/local/bin/sediman-sandbox"),
        ):
            if p.exists():
                return str(p)
        return "sediman-sandbox"

    async def maybe_checkpoint(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        cwd: str | None = None,
    ) -> CheckpointInfo | None:
        """Create a checkpoint before dangerous operations. Returns info or None."""
        if not self.enabled or tool_name not in _DANGEROUS_TOOLS:
            return None

        target_dir = self._resolve_target_dir(tool_name, arguments, cwd)
        if not target_dir or not Path(target_dir).exists():
            return None

        try:
            name = f"pre-{tool_name}"
            proc = await asyncio.create_subprocess_exec(
                self._cli, "checkpoint", "create", target_dir, f"--name={name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode != 0:
                logger.warning("checkpoint_create_failed", stderr=stderr.decode()[:200])
                return None

            lines = stdout.decode().strip().split("\n")
            cp_id = self._extract_id(lines[0])
            if cp_id:
                info = CheckpointInfo(
                    id=cp_id,
                    name=name,
                    target_dir=target_dir,
                    created_at=lines[0],
                )
                self._last_checkpoint = info
                logger.info("checkpoint_created", id=cp_id, tool=tool_name, dir=target_dir)
                return info
        except Exception as e:
            logger.debug("checkpoint_exception", error=str(e))
        return None

    def _resolve_target_dir(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        cwd: str | None,
    ) -> str | None:
        """Determine the directory to checkpoint from tool arguments."""
        if tool_name in ("write_file", "patch"):
            path = arguments.get("path")
            if path:
                p = Path(path).expanduser().resolve()
                return str(p.parent)
        if tool_name == "terminal":
            return cwd or "."
        return cwd or "."

    @staticmethod
    def _extract_id(line: str) -> str | None:
        """Extract checkpoint ID from 'Created checkpoint 12345 (name)' line."""
        parts = line.split()
        for i, p in enumerate(parts):
            if p == "checkpoint" and i + 1 < len(parts):
                return parts[i + 1].strip()
        return None

    async def revert(self, checkpoint_id: str, target_dir: str) -> bool:
        """Revert a directory to a checkpoint."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cli, "checkpoint", "revert", target_dir, f"--id={checkpoint_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            success = proc.returncode == 0
            if success:
                logger.info("checkpoint_reverted", id=checkpoint_id, dir=target_dir)
            else:
                logger.warning("checkpoint_revert_failed", stderr=stderr.decode()[:200])
            return success
        except Exception as e:
            logger.debug("checkpoint_revert_exception", error=str(e))
            return False

    def get_last(self) -> CheckpointInfo | None:
        return self._last_checkpoint


def shutil_which(cmd: str) -> str | None:
    """shutil.which polyfill that works in all environments."""
    try:
        import shutil
        return shutil.which(cmd)
    except Exception:
        return None
