from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog

from sediman.skills.format import SkillData
from sediman.skills.validator import validate_skill

logger = structlog.get_logger()

DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/sediman/skills-hub/main"

_HUB_CACHE: list[dict[str, Any]] | None = None
_CACHE_KEY: str = ""
_CACHE_TS: float = 0.0
_CACHE_TTL: float = 300.0

_LOCK_FILE: Path = Path.home() / ".sediman" / "skills-lock.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_skill_dir(skill_dir: Path) -> str:
    h = hashlib.sha1()
    if skill_dir.exists():
        for f in sorted(skill_dir.iterdir()):
            if f.is_file():
                h.update(f.read_bytes())
    return h.hexdigest()


@dataclass
class LockEntry:
    source: str
    source_type: str = "unknown"
    source_url: str = ""
    skill_path: str = "SKILL.md"
    skill_folder_hash: str = ""
    installed_at: str = ""
    updated_at: str = ""

    def to_json(self) -> dict[str, str]:
        d: dict[str, str] = {
            "source": self.source,
            "sourceType": self.source_type,
            "sourceUrl": self.source_url,
            "skillPath": self.skill_path,
        }
        if self.skill_folder_hash:
            d["skillFolderHash"] = self.skill_folder_hash
        if self.installed_at:
            d["installedAt"] = self.installed_at
        if self.updated_at:
            d["updatedAt"] = self.updated_at
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> LockEntry:
        return cls(
            source=data.get("source", ""),
            source_type=data.get("sourceType", data.get("source_type", "unknown")),
            source_url=data.get("sourceUrl", data.get("source_url", "")),
            skill_path=data.get("skillPath", data.get("skill_path", "SKILL.md")),
            skill_folder_hash=data.get(
                "skillFolderHash", data.get("skill_folder_hash", "")
            ),
            installed_at=data.get("installedAt", data.get("installed_at", "")),
            updated_at=data.get("updatedAt", data.get("updated_at", "")),
        )

    def to_dict(self) -> dict[str, str]:
        return self.to_json()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LockEntry:
        return cls.from_json(d)


@dataclass
class HubSkillSummary:
    name: str
    description: str
    category: str
    author: str | None = None
    version: int = 1
    installs: int = 0
    trust: str = "community"
    variables: list[str] | None = None
    schedule: str | None = None
    source: str = "hub"


class SkillLockFile:
    def __init__(self, path: Path | None = None):
        self.path = path or _LOCK_FILE

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "skills": {}}
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict) and "skills" in data:
                return data
            return {"version": 1, "skills": {}}
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "skills": {}}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))

    def set(self, name: str, entry: LockEntry) -> None:
        data = self._read()
        data["skills"][name] = entry.to_json()
        self._write(data)

    def add(self, entry: LockEntry) -> None:
        name = (
            entry.source.split("@")[-1]
            if "@" in entry.source
            else entry.source.split(":")[-1]
        )
        data = self._read()
        data["skills"][name] = entry.to_json()
        self._write(data)

    def remove(self, name: str) -> None:
        data = self._read()
        data.get("skills", {}).pop(name, None)
        self._write(data)

    def get(self, name: str) -> LockEntry | None:
        data = self._read()
        d = data.get("skills", {}).get(name)
        return LockEntry.from_json(d) if d else None

    def list_all(self) -> dict[str, LockEntry]:
        data = self._read()
        return {
            k: LockEntry.from_json(v)
            for k, v in data.get("skills", {}).items()
            if isinstance(v, dict)
        }


class GitHubInstaller:
    _GITHUB_RAW = "https://raw.githubusercontent.com"

    def parse_ref(self, ref: str) -> tuple[str, str, str, str]:
        if "@" in ref:
            repo_part, skill_name = ref.rsplit("@", 1)
        else:
            repo_part = ref
            skill_name = ref.rsplit("/", 1)[-1]
        parts = repo_part.split("/")
        if len(parts) < 2:
            raise ValueError(
                f"Invalid GitHub reference: {ref!r}. Expected owner/repo[@skill]"
            )
        owner = parts[0]
        repo = parts[1]
        branch = "main"
        return owner, repo, skill_name, branch

    def _parse_ref(self, ref: str) -> tuple[str, str, str, str]:
        return self.parse_ref(ref)

    def _github_url(self, owner: str, repo: str, branch: str, path: str) -> str:
        return f"{self._GITHUB_RAW}/{owner}/{repo}/{branch}/{path}"

    def _fetch_skill_json(
        self, owner: str, repo: str, branch: str, skill_name: str
    ) -> str | None:
        paths = [
            f"skills/{skill_name}/skill.json",
            f"{skill_name}/skill.json",
            "skill.json",
        ]
        for path in paths:
            url = self._github_url(owner, repo, branch, path)
            try:
                resp = httpx.get(url, timeout=15, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
            except httpx.HTTPError:
                continue
        return None

    def _fetch_skill_md(
        self, owner: str, repo: str, branch: str, skill_name: str
    ) -> str | None:
        paths = [
            f"skills/{skill_name}/SKILL.md",
            f"{skill_name}/SKILL.md",
            "SKILL.md",
        ]
        for path in paths:
            url = self._github_url(owner, repo, branch, path)
            try:
                resp = httpx.get(url, timeout=15, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text
            except httpx.HTTPError:
                continue
        return None

    def get_skill(self, ref: str) -> tuple[SkillData | None, str]:
        try:
            owner, repo, skill_name, branch = self.parse_ref(ref)
        except ValueError as e:
            return None, str(e)

        skill_json_text = self._fetch_skill_json(owner, repo, branch, skill_name)
        if skill_json_text:
            from sediman.skills.format import parse_skill_json

            parsed = parse_skill_json(skill_json_text)
            if parsed:
                parsed.source = f"github:{owner}/{repo}"
                return parsed, f"github:{owner}/{repo}"

        skill_md_text = self._fetch_skill_md(owner, repo, branch, skill_name)
        if skill_md_text:
            from sediman.skills.format import parse_skill_md

            parsed = parse_skill_md(skill_md_text)
            if parsed:
                parsed.source = f"github:{owner}/{repo}"
                return parsed, f"github:{owner}/{repo}"

        return None, "Skill not found"

    def install(self, ref: str, engine: Any, force: bool = False) -> tuple[bool, str]:
        from sediman.skills.engine import SkillEngine

        if not isinstance(engine, SkillEngine):
            return False, "Invalid engine"

        try:
            owner, repo, skill_name, branch = self.parse_ref(ref)
        except ValueError as e:
            return False, str(e)

        existing = engine.read(skill_name)
        if existing and not force:
            return (
                False,
                f"Skill '{skill_name}' already exists. Use --force to overwrite.",
            )

        skill, _ = self.get_skill(ref)
        if skill is None:
            return False, f"Skill not found in {owner}/{repo} (branch: {branch})"

        result = validate_skill(skill)
        if not result.valid:
            return False, f"Validation failed: {'; '.join(result.errors)}"

        if existing and force:
            engine.delete(skill_name)

        engine.install(skill)

        lock = SkillLockFile()
        skill_dir = engine._skill_path(skill_name)
        installed_at = _now_iso()
        lock.set(
            skill_name,
            LockEntry(
                source=f"{owner}/{repo}",
                source_type="github",
                source_url=f"https://github.com/{owner}/{repo}",
                skill_folder_hash=_hash_skill_dir(skill_dir)
                if skill_dir.exists()
                else "",
                installed_at=installed_at,
                updated_at=installed_at,
            ),
        )

        logger.info("skill_installed_from_github", name=skill_name)
        return True, f"Installed {skill_name} from {owner}/{repo} (v{skill.version})"

    def check_update(self, name: str, engine: Any) -> tuple[bool, str]:
        lock = SkillLockFile()
        entry = lock.get(name)
        if not entry or entry.source_type != "github":
            return False, "No GitHub source"

        if not engine.read(name):
            return False, "not installed"

        try:
            owner, repo, skill_name, branch = self.parse_ref(entry.source)
        except ValueError:
            return False, "Invalid source ref"

        skill_json_text = self._fetch_skill_json(owner, repo, branch, skill_name)
        if skill_json_text:
            from sediman.skills.format import parse_skill_json

            remote = parse_skill_json(skill_json_text)
            if remote:
                installed_version = (engine.read(name) or {}).get("version", 1)
                if remote.version > installed_version:
                    return True, f"v{remote.version} available"
                skill_dir = engine._skill_path(name)
                if skill_dir.exists() and entry.skill_folder_hash:
                    current_hash = _hash_skill_dir(skill_dir)
                    if current_hash != entry.skill_folder_hash:
                        return True, "content changed"
        return False, "Up to date"

    def update_skill(self, name: str, engine: Any) -> tuple[bool, str]:
        lock = SkillLockFile()
        entry = lock.get(name)
        if not entry or entry.source_type != "github":
            return False, f"Skill '{name}' is not tracked from GitHub"

        existing = engine.read(name)
        if not existing:
            return False, f"Skill '{name}' not installed"

        old_installed_at = entry.installed_at
        ok, install_msg = self.install(entry.source, engine, force=True)
        if ok:
            updated_lock = SkillLockFile()
            current = updated_lock.get(name)
            if current:
                current.installed_at = old_installed_at
                current.updated_at = _now_iso()
                updated_lock.set(name, current)
            return True, f"Updated {name}"
        return False, f"{name}: update failed — {install_msg}"


class HubClient:
    def __init__(self, registry_url: str | None = None):
        url = (registry_url or DEFAULT_REGISTRY_URL).rstrip("/")
        self.registry_url = url
        self._http = httpx.Client(timeout=10, follow_redirects=True)

    def _fetch_json(self, path: str) -> Any:
        url = f"{self.registry_url}/{path}"
        try:
            resp = self._http.get(url)
            if resp.status_code == 200:
                return resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.warning("hub_fetch_failed", url=url, error=str(e))
        return None

    def _fetch_text(self, path: str) -> str | None:
        url = f"{self.registry_url}/{path}"
        try:
            resp = self._http.get(url)
            if resp.status_code == 200:
                return resp.text
        except httpx.HTTPError as e:
            logger.warning("hub_fetch_failed", url=url, error=str(e))
        return None

    def _get_index(self) -> list[dict[str, Any]]:
        global _HUB_CACHE, _CACHE_TS

        if _HUB_CACHE is not None and (time.monotonic() - _CACHE_TS) < _CACHE_TTL:
            return _HUB_CACHE

        data = self._fetch_json("index.json")
        if isinstance(data, list):
            _HUB_CACHE = data
            _CACHE_TS = time.monotonic()
            return data
        return []

    def browse(self, category: str | None = None) -> list[HubSkillSummary]:
        index = self._get_index()
        results = []
        for entry in index:
            if category and entry.get("category") != category:
                continue
            results.append(
                HubSkillSummary(
                    name=entry.get("name", ""),
                    description=entry.get("description", ""),
                    category=entry.get("category", "general"),
                    author=entry.get("author"),
                    version=entry.get("version", 1),
                    installs=entry.get("installs", 0),
                    trust=entry.get("trust", "community"),
                    variables=entry.get("variables"),
                    schedule=entry.get("schedule"),
                    source="hub",
                )
            )
        return results

    def search(self, query: str) -> list[HubSkillSummary]:
        query_lower = query.lower()
        index = self._get_index()
        results = []
        for entry in index:
            searchable = (
                f"{entry.get('name', '')} {entry.get('description', '')} "
                f"{entry.get('category', '')}"
            ).lower()
            if query_lower in searchable:
                results.append(
                    HubSkillSummary(
                        name=entry.get("name", ""),
                        description=entry.get("description", ""),
                        category=entry.get("category", "general"),
                        author=entry.get("author"),
                        version=entry.get("version", 1),
                        installs=entry.get("installs", 0),
                        trust=entry.get("trust", "community"),
                        variables=entry.get("variables"),
                        schedule=entry.get("schedule"),
                        source="hub",
                    )
                )
        return results

    def get_skill(self, name: str) -> SkillData | None:
        skill_json_text = self._fetch_text(f"skills/{name}/skill.json")
        if not skill_json_text:
            skill_md_text = self._fetch_text(f"skills/{name}/SKILL.md")
            if skill_md_text:
                from sediman.skills.format import parse_skill_md

                parsed = parse_skill_md(skill_md_text)
                if parsed:
                    parsed.source = "hub"
                return parsed
            return None

        from sediman.skills.format import parse_skill_json

        parsed = parse_skill_json(skill_json_text)
        if parsed:
            parsed.source = "hub"
            return parsed

        skill_md_text = self._fetch_text(f"skills/{name}/SKILL.md")
        if skill_md_text:
            from sediman.skills.format import parse_skill_md

            parsed = parse_skill_md(skill_md_text)
            if parsed:
                parsed.source = "hub"
                return parsed

        return None

    def install(self, name: str, engine: Any, force: bool = False) -> tuple[bool, str]:
        from sediman.skills.engine import SkillEngine

        if not isinstance(engine, SkillEngine):
            return False, "Invalid engine"

        existing = engine.read(name)
        if existing and not force:
            return False, f"Skill '{name}' already exists. Use --force to overwrite."

        skill = self.get_skill(name)
        if not skill:
            return False, f"Skill '{name}' not found in hub."

        result = validate_skill(skill)
        if not result.valid:
            return False, f"Skill validation failed: {'; '.join(result.errors)}"

        if existing and force:
            engine.delete(name)

        skill.source = "hub"
        engine.install(skill)

        lock = SkillLockFile()
        skill_dir = engine._skill_path(name)
        installed_at = _now_iso()
        lock.set(
            name,
            LockEntry(
                source=f"hub:{name}",
                source_type="hub",
                source_url=self.registry_url,
                skill_folder_hash=_hash_skill_dir(skill_dir)
                if skill_dir.exists()
                else "",
                installed_at=installed_at,
                updated_at=installed_at,
            ),
        )

        logger.info("skill_installed_from_hub", name=name)
        return True, f"Installed {name} (v{skill.version}, {result.trust_level})"

    def info(self, name: str) -> dict[str, Any] | None:
        skill = self.get_skill(name)
        if not skill:
            return None
        result = validate_skill(skill)
        return {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "version": skill.version,
            "author": skill.author,
            "variables": skill.variables,
            "schedule": skill.schedule,
            "steps": skill.steps,
            "license": skill.license,
            "trust": result.trust_level,
            "warnings": result.warnings,
        }

    def publish(self, skill_data: SkillData) -> tuple[bool, str]:
        result = validate_skill(skill_data)
        if not result.valid:
            return False, f"Validation failed: {'; '.join(result.errors)}"

        logger.info("skill_publish", name=skill_data.name, trust=result.trust_level)
        return True, (
            f"Skill '{skill_data.name}' validated ({result.trust_level}). "
            "Publish to hub by opening a PR at https://github.com/sediman/skills-hub"
        )
