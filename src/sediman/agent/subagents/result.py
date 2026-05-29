from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Artifact:
    """An artifact produced by a subagent (file, skill, etc.)."""

    kind: str
    name: str
    content: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentResult:
    """The structured result returned by a subagent session."""

    success: bool
    summary: str
    detail: str | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    iterations: int = 0
    strategy_used: str = "direct"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "detail": self.detail,
            "actions_taken": self.actions_taken,
            "artifacts": [
                {
                    "kind": a.kind,
                    "name": a.name,
                    "path": a.path,
                    "metadata": a.metadata,
                }
                for a in self.artifacts
            ],
            "iterations": self.iterations,
            "strategy_used": self.strategy_used,
            "errors": self.errors,
        }
