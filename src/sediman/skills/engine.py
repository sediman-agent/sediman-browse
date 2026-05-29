from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import re

import structlog

from sediman.skills.format import SkillData, load_skill

logger = structlog.get_logger()

_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

SKILLS_DIR = Path.home() / ".sediman" / "skills"


def _validate_safe_name(name: str) -> None:
    if not name or not _SAFE_NAME_RE.match(name) or len(name) > 64:
        raise ValueError(f"Invalid skill name: {name!r}")


class SkillEngine:
    def __init__(self, skills_dir: Path | None = None, use_cache: bool = False):
        self.skills_dir = skills_dir or SKILLS_DIR
        self.use_cache = use_cache
        self._list_cache: list[dict[str, str]] | None = None
        self._read_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Write to a temp file then rename — avoids partial writes."""
        fd, tmp = tempfile.mkstemp(
            dir=str(path.parent), prefix=".tmp-", suffix=path.suffix
        )
        try:
            with open(fd, "w") as f:
                f.write(content)
            Path(tmp).rename(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _skill_path(self, name: str) -> Path:
        _validate_safe_name(name)
        resolved = (self.skills_dir / name).resolve()
        base = self.skills_dir.resolve()
        try:
            os.path.commonpath([resolved, base])
        except ValueError:
            raise ValueError(f"Path traversal detected in skill name: {name!r}")
        if resolved == base or not str(resolved).startswith(str(base) + os.sep):
            raise ValueError(f"Path traversal detected in skill name: {name!r}")
        return resolved

    def create(
        self,
        name: str,
        description: str,
        steps: list[str],
        category: str = "general",
        when_to_use: str | None = None,
        pitfalls: list[str] | None = None,
        verification: str | None = None,
        structured_steps: list[dict[str, Any]] | None = None,
        variables: list[str] | None = None,
    ) -> dict[str, Any]:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self._skill_path(name)
        skill_dir.mkdir(exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()

        skill = SkillData(
            name=name,
            description=description,
            steps=steps,
            category=category,
            created_at=now,
            updated_at=now,
            when_to_use=when_to_use,
            pitfalls=pitfalls or [],
            verification=verification,
            structured_steps=structured_steps or [],
            variables=variables or [],
        )

        self._atomic_write(
            skill_dir / "skill.json", json.dumps(skill.to_json(), indent=2)
        )
        self._atomic_write(skill_dir / "SKILL.md", skill.to_skill_md())

        if self.use_cache:
            self._list_cache = None
            self._read_cache.pop(name, None)

        logger.info("skill_created", name=name)
        return skill.to_json()

    def read(self, name: str) -> dict[str, Any] | None:
        if self.use_cache and name in self._read_cache:
            return self._read_cache[name]
        skill_dir = self._skill_path(name)
        if not skill_dir.is_dir():
            return None
        skill = load_skill(skill_dir)
        if skill:
            result = skill.to_json()
            if self.use_cache:
                self._read_cache[name] = result
            return result
        return None

    def list_skills(self) -> list[dict[str, str]]:
        if self.use_cache and self._list_cache is not None:
            return self._list_cache

        if not self.skills_dir.exists():
            return []

        skills = []
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill = load_skill(skill_dir)
            if skill:
                result = {
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category,
                    "version": skill.version,
                    "use_count": skill.use_count,
                    "last_used_at": skill.last_used_at,
                    "updated_at": skill.updated_at,
                }
                skills.append(result)
                if self.use_cache:
                    self._read_cache[skill.name] = skill.to_json()

        if self.use_cache:
            self._list_cache = skills
        return skills

    def _snapshot_history(self, skill_dir: Path, version: int) -> None:
        history_dir = skill_dir / "history"
        history_dir.mkdir(exist_ok=True)
        version_tag = f"v{version}"

        for fname in ("skill.json", "SKILL.md"):
            src = skill_dir / fname
            if src.exists():
                self._atomic_write(
                    history_dir / f"{fname}.{version_tag}", src.read_text()
                )

    def patch(self, name: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        skill_dir = self._skill_path(name)
        skill = load_skill(skill_dir)
        if not skill:
            return None

        self._snapshot_history(skill_dir, skill.version)

        for key in (
            "description",
            "steps",
            "category",
            "when_to_use",
            "pitfalls",
            "verification",
        ):
            if key in updates:
                setattr(skill, key, updates[key])

        skill.version += 1
        skill.updated_at = datetime.now(timezone.utc).isoformat()

        self._atomic_write(
            skill_dir / "skill.json", json.dumps(skill.to_json(), indent=2)
        )
        self._atomic_write(skill_dir / "SKILL.md", skill.to_skill_md())

        if self.use_cache:
            self._list_cache = None
            self._read_cache.pop(name, None)

        logger.info("skill_patched", name=name, version=skill.version)
        return skill.to_json()

    def rollback(
        self, name: str, target_version: int | None = None
    ) -> dict[str, Any] | None:
        skill_dir = self._skill_path(name)
        skill = load_skill(skill_dir)
        if not skill:
            return None

        if target_version is None:
            target_version = skill.version - 1

        if target_version < 1 or target_version >= skill.version:
            return None

        version_tag = f"v{target_version}"
        history_json = skill_dir / "history" / f"skill.json.{version_tag}"

        if not history_json.exists():
            return None

        self._snapshot_history(skill_dir, skill.version)

        restored_data = json.loads(history_json.read_text())
        restored_data["version"] = skill.version + 1
        restored_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        restored_skill = SkillData(
            name=restored_data["name"],
            description=restored_data["description"],
            steps=restored_data.get("steps", []),
            category=restored_data.get("category", "general"),
            version=restored_data["version"],
            variables=restored_data.get("variables", []),
            schedule=restored_data.get("schedule"),
            author=restored_data.get("author"),
            source=restored_data.get("source", "local"),
            created_at=restored_data.get("created_at"),
            updated_at=restored_data["updated_at"],
            when_to_use=restored_data.get("when_to_use"),
            pitfalls=restored_data.get("pitfalls", []),
            use_count=restored_data.get("use_count", 0),
            last_used_at=restored_data.get("last_used_at"),
            verification=restored_data.get("verification"),
        )

        self._atomic_write(
            skill_dir / "skill.json", json.dumps(restored_skill.to_json(), indent=2)
        )
        self._atomic_write(skill_dir / "SKILL.md", restored_skill.to_skill_md())

        logger.info(
            "skill_rolled_back",
            name=name,
            from_version=skill.version,
            to_version=target_version,
            new_version=restored_skill.version,
        )
        return restored_skill.to_json()

    def list_history(self, name: str) -> list[dict[str, Any]]:
        skill_dir = self._skill_path(name)
        history_dir = skill_dir / "history"
        if not history_dir.exists():
            return []

        versions = []
        for f in sorted(history_dir.iterdir()):
            if f.name.startswith("skill.json.v"):
                version_num = int(f.name.split(".v")[1])
                try:
                    data = json.loads(f.read_text())
                    versions.append(
                        {
                            "version": version_num,
                            "updated_at": data.get("updated_at"),
                            "description": data.get("description", "")[:80],
                            "steps_count": len(data.get("steps", [])),
                        }
                    )
                except (json.JSONDecodeError, ValueError):
                    pass
        return versions

    def delete(self, name: str) -> bool:
        skill_dir = self._skill_path(name)
        if not skill_dir.exists():
            return False

        for f in skill_dir.iterdir():
            f.unlink()
        skill_dir.rmdir()

        if self.use_cache:
            self._list_cache = None
            self._read_cache.pop(name, None)

        try:
            from sediman.skills.hub import SkillLockFile

            SkillLockFile().remove(name)
        except Exception:
            pass

        logger.info("skill_deleted", name=name)
        return True

    def install(self, skill: SkillData) -> dict[str, Any]:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self._skill_path(skill.name)
        skill_dir.mkdir(exist_ok=True)

        self._atomic_write(
            skill_dir / "skill.json", json.dumps(skill.to_json(), indent=2)
        )
        self._atomic_write(skill_dir / "SKILL.md", skill.to_skill_md())

        logger.info("skill_installed", name=skill.name, source=skill.source)
        return skill.to_json()

    def get_skill_summaries(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [f"- {s['name']}: {s['description']}" for s in skills]
        return "\n".join(lines)

    def list_skills_full(self) -> list[dict[str, Any]]:
        if not self.skills_dir.exists():
            return []
        skills = []
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill = load_skill(skill_dir)
            if skill:
                skills.append(skill.to_json())
        return skills

    def record_usage(self, name: str) -> dict[str, Any] | None:
        skill_dir = self._skill_path(name)
        skill = load_skill(skill_dir)
        if not skill:
            return None

        skill.use_count += 1
        skill.last_used_at = datetime.now(timezone.utc).isoformat()

        self._atomic_write(
            skill_dir / "skill.json", json.dumps(skill.to_json(), indent=2)
        )
        self._atomic_write(skill_dir / "SKILL.md", skill.to_skill_md())

        logger.debug("skill_usage_recorded", name=name, use_count=skill.use_count)
        return skill.to_json()

    def find_similar(
        self, name: str, description: str, threshold: float = 0.7
    ) -> dict[str, Any] | None:
        skills = self.list_skills()
        if not skills:
            return None

        if name in [s["name"] for s in skills]:
            return self.read(name)

        try:
            from sediman.memory.vector import VectorStore

            vs = VectorStore()
            results = vs.search(f"{name}: {description}", top_k=1)
            if results and results[0].get("score", 0) >= threshold:
                match_name = results[0].get("metadata", {}).get("name")
                if match_name:
                    return self.read(match_name)
        except Exception:
            pass

        desc_words = set(description.lower().split()) - {
            "a",
            "an",
            "the",
            "and",
            "or",
            "of",
            "in",
            "on",
            "to",
            "for",
            "is",
            "it",
            "from",
            "with",
            "by",
            "this",
            "that",
        }

        best_match = None
        best_overlap = 0

        for s in skills:
            existing_words = set(s["description"].lower().split()) - {
                "a",
                "an",
                "the",
                "and",
                "or",
                "of",
                "in",
                "on",
                "to",
                "for",
                "is",
                "it",
                "from",
                "with",
                "by",
                "this",
                "that",
            }
            overlap = len(desc_words & existing_words)
            if overlap > best_overlap and overlap >= 2:
                best_overlap = overlap
                best_match = s

        if best_match:
            return self.read(best_match["name"])

        return None

    def verify_and_rollback(
        self,
        name: str,
        verify_prompt: str,
        screenshot_path: str | None = None,
        dom_snapshot: str | None = None,
    ) -> dict[str, Any] | None:
        skill = self.read(name)
        if not skill:
            return None

        from sediman.skills.healer import verify_skill

        result = verify_skill(
            name,
            skill,
            verify_prompt,
            screenshot_path=screenshot_path,
            dom_snapshot=dom_snapshot,
        )

        if result.get("passed", False):
            return skill

        if skill.get("version", 1) <= 1:
            return None

        rollback_result = self.rollback(name, skill.get("version", 1) - 1)
        if rollback_result:
            rollback_result["_verify_fail_reason"] = result.get("fail_reason", "")
        return rollback_result
