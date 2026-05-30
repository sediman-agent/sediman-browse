from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import structlog

logger = structlog.get_logger()

_PERMISSIONS_FILE = Path.home() / ".sediman" / "skill-permissions.json"

AllowDecision = Literal["allow_once", "always_allow_skill", "always_allow_source", "deny", "skip"]


@dataclass
class SkillPermission:
    decision: AllowDecision
    source: str = ""
    decided_at: str = ""


@dataclass
class PermissionsData:
    version: int = 1
    allow_once: dict[str, SkillPermission] = field(default_factory=dict)
    always_allow_skill: dict[str, SkillPermission] = field(default_factory=dict)
    always_allow_source: dict[str, SkillPermission] = field(default_factory=dict)
    deny: dict[str, SkillPermission] = field(default_factory=dict)
    skip: dict[str, SkillPermission] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        def _ser(d: dict[str, SkillPermission]) -> dict[str, dict[str, str]]:
            return {k: {"decision": v.decision, "source": v.source, "decided_at": v.decided_at} for k, v in d.items()}

        return {
            "version": self.version,
            "allow_once": _ser(self.allow_once),
            "always_allow_skill": _ser(self.always_allow_skill),
            "always_allow_source": _ser(self.always_allow_source),
            "deny": _ser(self.deny),
            "skip": _ser(self.skip),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> PermissionsData:
        def _deser(d: dict[str, Any]) -> dict[str, SkillPermission]:
            return {
                k: SkillPermission(
                    decision=v.get("decision", "deny"),
                    source=v.get("source", ""),
                    decided_at=v.get("decided_at", ""),
                )
                for k, v in d.items()
            }

        return cls(
            version=data.get("version", 1),
            allow_once=_deser(data.get("allow_once", {})),
            always_allow_skill=_deser(data.get("always_allow_skill", {})),
            always_allow_source=_deser(data.get("always_allow_source", {})),
            deny=_deser(data.get("deny", {})),
            skip=_deser(data.get("skip", {})),
        )


class SkillPermissions:
    def __init__(self, path: Path | None = None):
        self.path = path or _PERMISSIONS_FILE
        self._data: PermissionsData | None = None

    def _load(self) -> PermissionsData:
        if self._data is not None:
            return self._data
        if not self.path.exists():
            self._data = PermissionsData()
            return self._data
        try:
            raw = json.loads(self.path.read_text())
            self._data = PermissionsData.from_json(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("skill_permissions_load_failed", error=str(e))
            self._data = PermissionsData()
        return self._data

    def _save(self) -> None:
        data = self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data.to_json(), indent=2))

    def check(self, skill_name: str, source: str) -> AllowDecision | None:
        data = self._load()

        entry = data.deny.get(skill_name)
        if entry:
            return "deny"

        for src_name, entry in data.deny.items():
            if src_name == source:
                return "deny"

        entry = data.always_allow_source.get(source)
        if entry:
            return "always_allow_source"

        entry = data.always_allow_skill.get(skill_name)
        if entry:
            return "always_allow_skill"

        entry = data.allow_once.get(skill_name)
        if entry:
            return "allow_once"

        entry = data.skip.get(skill_name)
        if entry:
            return "skip"

        return None

    def set_decision(self, skill_name: str, source: str, decision: AllowDecision) -> None:
        data = self._load()

        now = datetime.now(timezone.utc).isoformat()
        perm = SkillPermission(decision=decision, source=source, decided_at=now)

        self._remove_from_all(data, skill_name)

        if decision == "allow_once":
            data.allow_once[skill_name] = perm
        elif decision == "always_allow_skill":
            data.always_allow_skill[skill_name] = perm
        elif decision == "always_allow_source":
            data.always_allow_source[source] = perm
        elif decision == "deny":
            data.deny[skill_name] = perm
        elif decision == "skip":
            data.skip[skill_name] = perm

        self._save()

    def clear_allow_once(self, skill_name: str) -> None:
        data = self._load()
        data.allow_once.pop(skill_name, None)
        self._save()

    def _remove_from_all(self, data: PermissionsData, skill_name: str) -> None:
        data.allow_once.pop(skill_name, None)
        data.always_allow_skill.pop(skill_name, None)
        data.deny.pop(skill_name, None)
        data.skip.pop(skill_name, None)

    def list_allowed_sources(self) -> list[str]:
        data = self._load()
        return list(data.always_allow_source.keys())

    def list_allowed_skills(self) -> list[str]:
        data = self._load()
        return list(data.always_allow_skill.keys())
