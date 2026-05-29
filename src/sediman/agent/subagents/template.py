from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class AgentTemplate:
    """A subagent template loaded from a .md file with YAML frontmatter."""

    name: str
    description: str = ""
    mode: str = "subagent"
    model: str | None = None
    permissions: dict[str, str] = field(default_factory=dict)
    system_prompt: str = ""
    max_iterations: int = 5
    source_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "model": self.model,
            "permissions": dict(self.permissions),
            "max_iterations": self.max_iterations,
        }


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _clean_yaml_value(value: str) -> str:
    """Strip quotes and whitespace from a simple YAML scalar."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return value


def _parse_yaml_block(block: str) -> dict[str, Any]:
    """Parse a small subset of YAML sufficient for agent frontmatter."""
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_nested: dict[str, str] | None = None

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue

        # Detect nested map start (e.g. "permissions:")
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Top-level key with inline value
        if indent == 0 and ":" in stripped:
            parts = stripped.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            current_key = key

            if val == "":
                # Could be a list or nested dict on following lines
                current_nested = {}
                data[key] = current_nested
                continue
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1]
                data[key] = [_clean_yaml_value(v) for v in inner.split(",") if v.strip()]
                continue
            data[key] = _clean_yaml_value(val)
            continue

        # Nested key under current top-level key
        if indent >= 2 and current_key is not None and ":" in stripped:
            parts = stripped.split(":", 1)
            nkey = parts[0].strip()
            nval = parts[1].strip()
            if isinstance(data.get(current_key), dict):
                data[current_key][nkey] = _clean_yaml_value(nval)
            continue

        # List item under current top-level key
        if stripped.startswith("- ") and current_key is not None:
            item = stripped[2:].strip()
            if current_key not in data or not isinstance(data[current_key], list):
                data[current_key] = []
            data[current_key].append(_clean_yaml_value(item))
            continue

    return data


def parse_agent_file(path: Path) -> AgentTemplate | None:
    """Parse an agent markdown file with YAML frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("agent_file_read_failed", path=str(path), error=str(e))
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        logger.warning("agent_file_no_frontmatter", path=str(path))
        return None

    frontmatter = match.group(1)
    body = match.group(2).strip()

    data = _parse_yaml_block(frontmatter)

    name = data.get("name")
    if not name:
        logger.warning("agent_file_missing_name", path=str(path))
        return None

    template = AgentTemplate(
        name=name,
        description=data.get("description", ""),
        mode=data.get("mode", "subagent"),
        model=data.get("model") or None,
        permissions=data.get("permissions", {}),
        system_prompt=body,
        max_iterations=int(data.get("max_iterations", 5)),
        source_path=path,
    )
    return template


def render_agent_file(template: AgentTemplate) -> str:
    """Serialize an AgentTemplate back to markdown with YAML frontmatter."""
    lines = ["---"]
    lines.append(f'name: "{template.name}"')
    if template.description:
        lines.append(f'description: "{template.description}"')
    lines.append(f'mode: "{template.mode}"')
    if template.model:
        lines.append(f'model: "{template.model}"')
    if template.permissions:
        lines.append("permissions:")
        for k, v in template.permissions.items():
            lines.append(f"  {k}: {v}")
    lines.append(f"max_iterations: {template.max_iterations}")
    lines.append("---")
    lines.append("")
    lines.append(template.system_prompt)
    return "\n".join(lines)
