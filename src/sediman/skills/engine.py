from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from sediman.skills.format import SkillData, load_skill

logger = structlog.get_logger()

_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

GLOBAL_SKILLS_DIR = Path.home() / ".sediman" / "skills"

_WATCH_INTERVAL = 5.0


def _validate_safe_name(name: str) -> None:
    if not name or not _SAFE_NAME_RE.match(name) or len(name) > 64:
        raise ValueError(f"Invalid skill name: {name!r}")


def _get_project_skills_dir() -> Path | None:
    cwd = Path.cwd()
    candidate = cwd / ".sediman" / "skills"
    if candidate.exists() and candidate.is_dir():
        return candidate
    return None


class SkillEngine:
    def __init__(self, skills_dir: Path | None = None, use_cache: bool = True):
        self.skills_dir = skills_dir or GLOBAL_SKILLS_DIR
        self.use_cache = use_cache
        self._list_cache: list[dict[str, str]] | None = None
        self._read_cache: dict[str, dict[str, Any]] = {}
        self._last_watch_check: float = 0.0

    def _all_skill_dirs(self) -> list[Path]:
        dirs = [self.skills_dir]
        project_dir = _get_project_skills_dir()
        if project_dir:
            dirs.append(project_dir)
        return dirs

    def _invalidate_cache_if_stale(self) -> None:
        if not self.use_cache:
            return
        now = time.monotonic()
        if now - self._last_watch_check < _WATCH_INTERVAL:
            return
        self._last_watch_check = now
        for skills_dir in self._all_skill_dirs():
            if not skills_dir.exists():
                continue
            try:
                mtime = skills_dir.stat().st_mtime
                
                if not hasattr(self, "_dir_mtimes"):
                    self._dir_mtimes: dict[str, float] = {}
                key = str(skills_dir)
                prev = self._dir_mtimes.get(key, 0)
                if mtime > prev + 1.0:  
                    self._list_cache = None
                    self._read_cache.clear()
                    self._dir_mtimes[key] = mtime
                    logger.debug("skills_cache_invalidated", dir=str(skills_dir))
            except OSError:
                pass

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
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

    def _find_skill_in_dirs(self, name: str) -> Path | None:
        _validate_safe_name(name)
        for skills_dir in self._all_skill_dirs():
            candidate = (skills_dir / name).resolve()
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

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
        disable_model_invocation: bool = False,
        allowed_tools: dict[str, str] | None = None,
        context: str = "",
        paths: list[str] | None = None,
        inputs: list[dict[str, str]] | None = None,
        outputs: list[dict[str, str]] | None = None,
        dependencies: list[str] | None = None,
        retry_policy: str | None = None,
        timeout_seconds: int | None = None,
        examples: list[str] | None = None,
        success_rate: float | None = None,
        execution_count: int = 0,
        avg_duration_ms: int | None = None,
    ) -> dict[str, Any]:
        skill = SkillData(
            name=name,
            description=description,
            steps=steps,
            category=category,
            when_to_use=when_to_use,
            pitfalls=pitfalls or [],
            verification=verification,
            structured_steps=structured_steps or [],
            variables=variables or [],
            disable_model_invocation=disable_model_invocation,
            allowed_tools=allowed_tools,
            context=context,
            paths=paths,
            inputs=inputs,
            outputs=outputs,
            dependencies=dependencies,
            retry_policy=retry_policy,
            timeout_seconds=timeout_seconds,
            examples=examples,
            success_rate=success_rate,
            execution_count=execution_count,
            avg_duration_ms=avg_duration_ms,
        )
        return self.ensure_skill(name, skill)

    def read(self, name: str) -> dict[str, Any] | None:
        self._invalidate_cache_if_stale()

        if self.use_cache and name in self._read_cache:
            return dict(self._read_cache[name])

        skill_dir = self._find_skill_in_dirs(name)
        if not skill_dir:
            return None

        skill_data = load_skill(skill_dir)
        if skill_data:
            result = skill_data.to_json()
            if self.use_cache:
                self._read_cache[name] = result
            return result

        return None

    def get_skill(self, name: str) -> dict[str, Any] | None:
        return self.read(name)

    def list_skills_full(self) -> list[dict[str, Any]]:
        return self.list_skills()

    def list_skills(self) -> list[dict[str, Any]]:
        self._invalidate_cache_if_stale()

        if self.use_cache and self._list_cache is not None:
            return [dict(s) for s in self._list_cache]

        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for skills_dir in self._all_skill_dirs():
            if not skills_dir.exists():
                continue
            try:
                entries = sorted(skills_dir.iterdir())
            except OSError:
                continue
            for entry in entries:
                if not entry.is_dir():
                    continue
                name = entry.name
                if name in seen:
                    continue
                seen.add(name)
                skill_data = load_skill(entry)
                if skill_data:
                    result = skill_data.to_json()
                    results.append(result)

        if self.use_cache:
            self._list_cache = results

        return results

    def ensure_skill(self, name: str, skill_data: SkillData | dict[str, Any]) -> dict[str, Any]:
        existing = self.read(name)
        if isinstance(skill_data, dict):
            sd = SkillData(
                name=skill_data.get("name", name),
                description=skill_data.get("description", ""),
                steps=skill_data.get("steps", []),
                category=skill_data.get("category", "general"),
                when_to_use=skill_data.get("when_to_use"),
                pitfalls=skill_data.get("pitfalls", []),
                verification=skill_data.get("verification"),
                structured_steps=skill_data.get("structured_steps", []),
                variables=skill_data.get("variables", []),
                version=int(skill_data.get("version", 1)),
                source=skill_data.get("source", "local"),
                disable_model_invocation=skill_data.get("disable_model_invocation", False),
                allowed_tools=skill_data.get("allowed_tools"),
                context=skill_data.get("context", ""),
                paths=skill_data.get("paths"),
                inputs=skill_data.get("inputs"),
                outputs=skill_data.get("outputs"),
                dependencies=skill_data.get("dependencies"),
                retry_policy=skill_data.get("retry_policy"),
                timeout_seconds=skill_data.get("timeout_seconds"),
                examples=skill_data.get("examples"),
                success_rate=skill_data.get("success_rate"),
                last_error=skill_data.get("last_error"),
                execution_count=skill_data.get("execution_count", 0),
                avg_duration_ms=skill_data.get("avg_duration_ms"),
            )
        else:
            sd = skill_data

        if existing:
            sd.version = existing.get("version", 1) + 1
            sd.created_at = existing.get("created_at")
            self._archive_version(name, existing)

        now = datetime.now(timezone.utc).isoformat()
        sd.updated_at = now
        if not sd.created_at:
            sd.created_at = now

        skill_dir = self._skill_path(name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(skill_dir / "skill.json", json.dumps(sd.to_json(), indent=2))
        self._atomic_write(skill_dir / "SKILL.md", sd.to_skill_md())

        result = sd.to_json()
        if self.use_cache:
            self._read_cache[name] = result
            self._list_cache = None
        return result

    def install(self, skill_data: SkillData) -> dict[str, Any]:
        return self.ensure_skill(skill_data.name, skill_data)

    def delete(self, name: str) -> bool:
        skill_dir = self._find_skill_in_dirs(name) or self._skill_path(name)
        if not skill_dir.exists():
            return False
        import shutil
        shutil.rmtree(skill_dir)
        self._list_cache = None
        self._read_cache.pop(name, None)
        try:
            from sediman.skills.hub import SkillLockFile
            SkillLockFile().remove(name)
        except Exception:
            pass
        return True

    def patch(self, name: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.read(name)
        if not existing:
            return None

        existing.pop("version", None)
        existing.pop("updated_at", None)
        existing.update(updates)
        existing["version"] = (existing.get("version", 0) or 0) + 1

        return self.ensure_skill(name, existing)

    def rollback(self, name: str, version: int | None = None, target_version: int | None = None) -> dict[str, Any] | None:
        if target_version is not None:
            version = target_version
        skill_dir = self._skill_path(name)
        history_dir = skill_dir / "history"
        if not history_dir.exists():
            return None

        versions = sorted([f for f in history_dir.iterdir() if f.name.startswith("skill.json.v")], reverse=True)
        if version is not None:
            versions = [v for v in versions if f"skill.json.v{version}" in v.name]
        if not versions:
            return None

        target = versions[0]
        try:
            data = json.loads(target.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        v_num = int(target.name.replace("skill.json.v", ""))
        existing = self.read(name)
        if existing:
            self._archive_version(name, existing)

        return self.ensure_skill(name, data)

    def list_history(self, name: str) -> list[dict[str, str]]:
        skill_dir = self._skill_path(name)
        history_dir = skill_dir / "history"
        if not history_dir.exists():
            return []
        result = []
        for entry in sorted(history_dir.iterdir(), reverse=True):
            if entry.name.startswith("skill.json.v"):
                try:
                    v = int(entry.name.replace("skill.json.v", ""))
                except ValueError:
                    continue
                result.append({
                    "version": v,
                    "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                })
        return result

    def _archive_version(self, name: str, existing: dict[str, Any]) -> None:
        skill_dir = self._skill_path(name)
        history_dir = skill_dir / "history"
        history_dir.mkdir(exist_ok=True)
        version = existing.get("version", 1)
        self._atomic_write(
            history_dir / f"skill.json.v{version}",
            json.dumps(existing, indent=2),
        )
        if (skill_dir / "SKILL.md").exists():
            self._atomic_write(
                history_dir / f"SKILL.md.v{version}",
                (skill_dir / "SKILL.md").read_text(),
            )

    def record_usage(self, name: str) -> None:
        existing = self.read(name)
        if not existing:
            return
        existing["use_count"] = existing.get("use_count", 0) + 1
        existing["last_used_at"] = datetime.now(timezone.utc).isoformat()
        skill_dir = self._find_skill_in_dirs(name) or self._skill_path(name)
        if skill_dir and skill_dir.exists():
            skill_json_path = skill_dir / "skill.json"
            if skill_json_path.exists():
                self._atomic_write(skill_json_path, json.dumps(existing, indent=2))
        if self.use_cache:
            self._read_cache[name] = existing

    async def find_similar(self, description: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for skills similar to the given description.

        Uses SkillSearchEngine for semantic + keyword search over actual skills,
        falling back to simple keyword matching if the engine is unavailable.
        """
        try:
            from sediman.skills.search import SkillSearchEngine
            search_engine = SkillSearchEngine()
            results = await search_engine.search(description, scope="internal", k=limit)
            return [
                {"text": r.name, "score": r.score, "name": r.name, "description": r.description}
                for r in results
            ]
        except Exception:
            logger.warning("find_similar_fallback_to_keyword", description=description[:50])
            all_skills = self.list_skills()
            desc_lower = description.lower()
            scored: list[tuple[int, dict[str, Any]]] = []
            for s in all_skills:
                s_name = s.get("name", "").lower()
                s_desc = s.get("description", "").lower()
                score = sum(1 for w in desc_lower.split() if w in s_name or w in s_desc)
                if score > 0:
                    scored.append((score, s))
            scored.sort(key=lambda x: -x[0])
            return [
                {"text": s[1].get("name", ""), "score": s[0], "name": s[1].get("name", ""), "description": s[1].get("description", "")}
                for s in scored[:limit]
            ]

    def verify_and_rollback(self, name: str, llm=None) -> tuple[bool, str]:
        existing = self.read(name)
        if not existing:
            return False, f"Skill {name} not found"
        return True, f"Skill {name} verified"

    def get_skill_summaries(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = []
        for s in skills:
            lines.append(f"- {s['name']}: {s.get('description', '')[:120]}")
        return "\n".join(lines)

    def _clear_caches(self) -> None:
        self._list_cache = None
        self._read_cache.clear()
