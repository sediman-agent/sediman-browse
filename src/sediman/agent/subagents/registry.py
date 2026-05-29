from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import re

from sediman.agent.subagents.template import AgentTemplate, parse_agent_file, render_agent_file
from sediman.config import AGENTS_DIR as USER_DIR

logger = structlog.get_logger()

BUILTIN_DIR = Path(__file__).parent / "builtin"
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _validate_safe_name(name: str) -> None:
    if not name or not _SAFE_NAME_RE.match(name) or len(name) > 64:
        raise ValueError(f"Invalid agent name: {name!r}")


class SubagentRegistry:
    """Registry for agent templates loaded from built-in and user directories."""

    def __init__(
        self,
        builtin_dir: Path | None = None,
        user_dir: Path | None = None,
    ):
        self._builtin_dir = builtin_dir or BUILTIN_DIR
        self._user_dir = user_dir or USER_DIR
        self._templates: dict[str, AgentTemplate] = {}
        self._load_builtin()
        self._load_user()

    def _load_builtin(self) -> None:
        if not self._builtin_dir.exists():
            logger.debug("builtin_agent_dir_missing", path=str(self._builtin_dir))
            return
        for path in sorted(self._builtin_dir.glob("*.md")):
            template = parse_agent_file(path)
            if template:
                self._templates[template.name] = template
                logger.debug("builtin_agent_loaded", name=template.name)

    def _load_user(self) -> None:
        if not self._user_dir.exists():
            return
        for path in sorted(self._user_dir.glob("*.md")):
            template = parse_agent_file(path)
            if template:
                # User agents override built-ins by name
                self._templates[template.name] = template
                logger.debug("user_agent_loaded", name=template.name, path=str(path))

    def get(self, name: str) -> AgentTemplate | None:
        return self._templates.get(name)

    def list(self) -> list[AgentTemplate]:
        return list(self._templates.values())

    def names(self) -> list[str]:
        return sorted(self._templates.keys())

    def exists(self, name: str) -> bool:
        return name in self._templates

    def save(self, template: AgentTemplate) -> Path:
        """Save a new or updated agent template to the user directory."""
        _validate_safe_name(template.name)
        self._user_dir.mkdir(parents=True, exist_ok=True)
        path = self._user_dir / f"{template.name}.md"
        path.write_text(render_agent_file(template), encoding="utf-8")
        self._templates[template.name] = template
        logger.info("agent_saved", name=template.name, path=str(path))
        return path

    def delete(self, name: str) -> bool:
        """Remove a user-defined agent. Built-ins cannot be deleted."""
        template = self._templates.get(name)
        if not template:
            return False
        if template.source_path and template.source_path.parent == self._builtin_dir:
            logger.warning("cannot_delete_builtin_agent", name=name)
            return False
        user_path = self._user_dir / f"{name}.md"
        if user_path.exists():
            user_path.unlink()
        self._templates.pop(name, None)
        logger.info("agent_deleted", name=name)
        return True

    def reload(self) -> None:
        """Reload all templates from disk."""
        self._templates.clear()
        self._load_builtin()
        self._load_user()
        logger.info("registry_reloaded", count=len(self._templates))

    def get_summaries(self) -> str:
        """Return a formatted list of available agents for injection into prompts."""
        lines = ["Available subagents:"]
        for template in sorted(self.list(), key=lambda t: t.name):
            lines.append(f"- {template.name}: {template.description}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {t.name: t.to_dict() for t in self.list()}
