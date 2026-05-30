"""Core MemoryStore — dual-file bounded storage with frozen snapshots.

Hermes-style architecture: MEMORY.md (agent notes) + USER.md (user profile).
Entries separated by §. Snapshot frozen at session start to protect prefix cache.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from sediman.memory.security import scan_content

logger = structlog.get_logger()

MEMORY_DIR = Path.home() / ".sediman" / "memories"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
USER_FILE = MEMORY_DIR / "USER.md"

OLD_MEMORY_FILE = Path.home() / ".sediman" / "MEMORY.md"
OLD_USER_FILE = Path.home() / ".sediman" / "USER.md"
OLD_MEMORY_DB = Path.home() / ".sediman" / "memory.json"

MEMORY_LIMIT = 2200
USER_LIMIT = 1375
ENTRY_SEPARATOR = "\n§\n"

MEMORY_GUIDANCE = """\
MEMORY GUIDANCE:
- Save: user preferences, environment facts, tool quirks, stable conventions
- Save: things that reduce future user corrections
- Don't save: task progress, session results, completed-work logs, temp TODOs
- Use session_search for historical info, not memory
- If memory is full, replace outdated entries or remove unimportant ones"""


@dataclass
class MemoryUsage:
    target: str
    chars: int
    limit: int
    entries: list[str]

    @property
    def pct(self) -> int:
        return int(self.chars / self.limit * 100) if self.limit else 0

    @property
    def formatted(self) -> str:
        return f"{self.pct}% — {self.chars:,}/{self.limit:,} chars"


@dataclass
class StoreResult:
    success: bool
    message: str
    entries: list[str] = field(default_factory=list)
    usage: MemoryUsage | None = None


class MemoryStore:
    def __init__(self) -> None:
        self._snapshot: str | None = None
        self._snapshot_loaded = False

    # ── Frozen snapshot ──────────────────────────────────────────

    def load_snapshot(self) -> str:
        if self._snapshot_loaded:
            return self._snapshot or ""

        self._maybe_migrate()
        self._snapshot = self._format_snapshot()
        self._snapshot_loaded = True

        mem_usage = self.get_usage("memory")
        user_usage = self.get_usage("user")
        logger.info(
            "memory_snapshot_loaded",
            memory_entries=len(mem_usage.entries),
            memory_usage=mem_usage.formatted,
            user_entries=len(user_usage.entries),
        )
        return self._snapshot

    @property
    def snapshot(self) -> str | None:
        return self._snapshot

    def _format_snapshot(self) -> str:
        parts: list[str] = []

        mem_usage = self.get_usage("memory")
        if mem_usage.entries:
            parts.append(f"MEMORY (your personal notes) [{mem_usage.formatted}]")
            for entry in mem_usage.entries:
                parts.append(entry)
        else:
            parts.append(
                f"MEMORY (your personal notes) [0/{MEMORY_LIMIT:,} chars — empty]"
            )

        user_usage = self.get_usage("user")
        if user_usage.entries:
            parts.append(f"USER PROFILE [{user_usage.formatted}]")
            for entry in user_usage.entries:
                parts.append(entry)

        parts.append(MEMORY_GUIDANCE)

        return "\n".join(parts)

    def format_for_system_prompt(self) -> str:
        if not self._snapshot_loaded:
            self.load_snapshot()
        if not self._snapshot:
            return ""
        return f"<memory-context>\n{self._snapshot}\n</memory-context>"

    # ── Entry operations ─────────────────────────────────────────

    def add(self, target: str, content: str) -> StoreResult:
        threats = scan_content(content)
        if threats:
            return StoreResult(
                success=False,
                message=f"Content rejected: {', '.join(threats)}",
            )

        content = content.strip()
        if not content:
            return StoreResult(success=False, message="Empty content.")

        entries = self._parse_entries(target)

        for existing in entries:
            if existing.strip() == content:
                return StoreResult(
                    success=False,
                    message="Duplicate entry — already exists.",
                    entries=entries,
                    usage=self.get_usage(target),
                )

        new_entries = entries + [content]
        new_text = ENTRY_SEPARATOR.join(new_entries)

        limit = self._get_limit(target)
        if len(new_text) > limit:
            usage = self.get_usage(target)
            return StoreResult(
                success=False,
                message=(
                    f"{target} at {usage.formatted}. "
                    f"Adding this entry ({len(content)} chars) would exceed the limit. "
                    f"Replace or remove existing entries first."
                ),
                entries=entries,
                usage=usage,
            )

        self._atomic_write(self._get_file(target), new_text)
        logger.info("memory_entry_added", target=target, chars=len(content))

        usage = self.get_usage(target)
        return StoreResult(
            success=True,
            message=f"Added to {target}.",
            entries=new_entries,
            usage=usage,
        )

    def replace(self, target: str, old_entry: str, new_entry: str) -> StoreResult:
        threats = scan_content(new_entry)
        if threats:
            return StoreResult(
                success=False,
                message=f"Content rejected: {', '.join(threats)}",
            )

        new_entry = new_entry.strip()
        if not new_entry:
            return StoreResult(success=False, message="Empty content.")

        entries = self._parse_entries(target)
        old_clean = old_entry.strip()

        found = False
        updated = []
        for e in entries:
            if e.strip() == old_clean:
                updated.append(new_entry)
                found = True
            else:
                updated.append(e)

        if not found:
            return StoreResult(
                success=False,
                message=f"Entry not found in {target}. Use exact text to match.",
                entries=entries,
                usage=self.get_usage(target),
            )

        new_text = ENTRY_SEPARATOR.join(updated)
        limit = self._get_limit(target)
        if len(new_text) > limit:
            usage = self.get_usage(target)
            return StoreResult(
                success=False,
                message=f"Replacement would exceed {target} limit ({usage.formatted}). Remove entries first.",
                entries=entries,
                usage=usage,
            )

        self._atomic_write(self._get_file(target), new_text)
        logger.info("memory_entry_replaced", target=target)

        usage = self.get_usage(target)
        return StoreResult(
            success=True,
            message=f"Replaced in {target}.",
            entries=updated,
            usage=usage,
        )

    def remove(self, target: str, entry: str) -> StoreResult:
        entries = self._parse_entries(target)
        entry_clean = entry.strip()

        updated = [e for e in entries if e.strip() != entry_clean]
        if len(updated) == len(entries):
            return StoreResult(
                success=False,
                message=f"Entry not found in {target}. Use exact text to match.",
                entries=entries,
                usage=self.get_usage(target),
            )

        new_text = ENTRY_SEPARATOR.join(updated)
        if new_text.strip():
            self._atomic_write(self._get_file(target), new_text)
        else:
            path = self._get_file(target)
            if path.exists():
                path.unlink()

        logger.info("memory_entry_removed", target=target)

        usage = self.get_usage(target)
        return StoreResult(
            success=True,
            message=f"Removed from {target}.",
            entries=updated,
            usage=usage,
        )

    # ── Read helpers ─────────────────────────────────────────────

    def get_usage(self, target: str) -> MemoryUsage:
        entries = self._parse_entries(target)
        text = ENTRY_SEPARATOR.join(entries) if entries else ""
        return MemoryUsage(
            target=target,
            chars=len(text),
            limit=self._get_limit(target),
            entries=entries,
        )

    def get_all_entries(self) -> dict[str, list[str]]:
        return {
            "memory": self._parse_entries("memory"),
            "user": self._parse_entries("user"),
        }

    def read_raw(self, target: str) -> str:
        path = self._get_file(target)
        if not path.exists():
            return ""
        return path.read_text()

    # ── Internal ─────────────────────────────────────────────────

    def _parse_entries(self, target: str) -> list[str]:
        path = self._get_file(target)
        if not path.exists():
            return []
        text = path.read_text().strip()
        if not text:
            return []
        entries = [e.strip() for e in text.split(ENTRY_SEPARATOR)]
        return [e for e in entries if e]

    def _get_file(self, target: str) -> Path:
        if target == "user":
            return USER_FILE
        return MEMORY_FILE

    def _get_limit(self, target: str) -> int:
        if target == "user":
            return USER_LIMIT
        return MEMORY_LIMIT

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=".tmp-", suffix=path.suffix
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    # ── Migration from old format ────────────────────────────────

    def _maybe_migrate(self) -> None:
        if MEMORY_DIR.exists():
            return

        has_old = (
            OLD_MEMORY_FILE.exists() or OLD_USER_FILE.exists() or OLD_MEMORY_DB.exists()
        )
        if not has_old:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            return

        logger.info("memory_migration_start")
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        entries: list[str] = []

        if OLD_MEMORY_FILE.exists():
            old_text = OLD_MEMORY_FILE.read_text().strip()
            if old_text:
                entries.extend(self._split_old_entries(old_text))

        if OLD_MEMORY_DB.exists():
            try:
                data = json.loads(OLD_MEMORY_DB.read_text())
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("content"):
                            entries.append(item["content"].strip())
            except (json.JSONDecodeError, OSError):
                pass

        if entries:
            self._atomic_write(MEMORY_FILE, ENTRY_SEPARATOR.join(entries))

        if OLD_USER_FILE.exists():
            old_user = OLD_USER_FILE.read_text().strip()
            if old_user:
                self._atomic_write(USER_FILE, old_user)

        logger.info("memory_migration_done", memory_entries=len(entries))

    @staticmethod
    def _split_old_entries(text: str) -> list[str]:
        parts = re.split(r"\n{2,}", text)
        return [p.strip() for p in parts if p.strip()]
