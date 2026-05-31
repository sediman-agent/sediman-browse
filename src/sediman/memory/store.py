"""Core MemoryStore — dual-file bounded storage with frozen snapshots.

Hermes-style architecture: MEMORY.md (agent notes) + USER.md (user profile).
Entries separated by §. Snapshot frozen at session start to protect prefix cache.
Metadata sidecar tracks timestamps, access counts, and entry types.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from sediman.config import DATA_DIR, MEMORY_LIMIT, USER_LIMIT
from sediman.memory.security import scan_content

logger = structlog.get_logger()

MEMORY_DIR = DATA_DIR / "memories"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
USER_FILE = MEMORY_DIR / "USER.md"

OLD_MEMORY_FILE = DATA_DIR / "MEMORY.md"
OLD_USER_FILE = DATA_DIR / "USER.md"
OLD_MEMORY_DB = DATA_DIR / "memory.json"
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
        self._entries_cache: dict[str, list[str]] = {}

    def _invalidate_cache(self, target: str | None = None) -> None:
        if target:
            self._entries_cache.pop(target, None)
        else:
            self._entries_cache.clear()
        self._snapshot_loaded = False

    # ── Frozen snapshot ──────────────────────────────────────────

    def load_snapshot(self) -> str:
        if self._snapshot_loaded:
            return self._snapshot or ""

        self._maybe_migrate()
        snapshot_text, mem_usage, user_usage = self._format_snapshot_with_usage()
        self._snapshot = snapshot_text
        self._snapshot_loaded = True

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
        text, _, _ = self._format_snapshot_with_usage()
        return text

    def _format_snapshot_with_usage(self) -> tuple[str, MemoryUsage, MemoryUsage]:
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

        return "\n".join(parts), mem_usage, user_usage

    def format_for_system_prompt(self) -> str:
        if not self._snapshot_loaded:
            self.load_snapshot()
        if not self._snapshot:
            return ""
        return f"<memory-context>\n{self._snapshot}\n</memory-context>"

    def format_for_system_prompt_filtered(self, query: str, max_chars: int = 1500) -> str:
        if not self._snapshot_loaded:
            self.load_snapshot()

        all_entries = self.get_all_entries()
        scored_entries = self._rank_entries_for_query(all_entries, query)

        if not scored_entries:
            return self.format_for_system_prompt()

        parts: list[str] = []
        total = 0

        for target, entry, _score in scored_entries:
            entry_len = len(entry) + 1
            if total + entry_len > max_chars:
                break
            parts.append(entry)
            total += entry_len

        if not parts:
            return self.format_for_system_prompt()

        guidance = MEMORY_GUIDANCE
        content = "\n".join(parts)
        return f"<memory-context>\n{content}\n\n{guidance}\n</memory-context>"

    def _rank_entries_for_query(
        self,
        all_entries: dict[str, list[str]],
        query: str,
    ) -> list[tuple[str, str, float]]:
        from sediman.memory.entry import get_meta_map_for_target, MemoryEntryMeta

        query_lower = query.lower()
        query_words = set(query_lower.split())
        results: list[tuple[str, str, float]] = []

        for target in ("memory", "user"):
            entries = all_entries.get(target, [])
            meta_map = get_meta_map_for_target(target)

            for entry in entries:
                meta = meta_map.get(entry)
                text_score = self._text_relevance(entry, query_words)

                recency_score = 0.5
                access_score = 0.5
                type_bonus = 0.0
                if meta:
                    age_hours = meta.age_hours
                    if age_hours < 1:
                        recency_score = 1.0
                    elif age_hours < 24:
                        recency_score = 0.9
                    elif age_hours < 168:
                        recency_score = 0.7
                    elif age_hours < 720:
                        recency_score = 0.5
                    else:
                        recency_score = 0.3

                    access_count = meta.access_count
                    if access_count > 10:
                        access_score = 1.0
                    elif access_count > 5:
                        access_score = 0.8
                    elif access_count > 2:
                        access_score = 0.6
                    else:
                        access_score = 0.4

                    if meta.type == "preference":
                        type_bonus = 0.15
                    elif meta.type == "fact":
                        type_bonus = 0.1

                combined = (
                    text_score * 0.5
                    + recency_score * 0.25
                    + access_score * 0.15
                    + type_bonus
                )

                if text_score > 0 or recency_score > 0.6 or access_score > 0.7:
                    results.append((target, entry, combined))

        results.sort(key=lambda x: -x[2])
        return results

    @staticmethod
    def _text_relevance(entry: str, query_words: set[str]) -> float:
        entry_lower = entry.lower()
        entry_words = set(entry_lower.split())
        if not query_words or not entry_words:
            return 0.0
        overlap = len(query_words & entry_words)
        return overlap / max(len(query_words), 1)

    def refresh_snapshot(self) -> str:
        self._snapshot = self._format_snapshot()
        self._snapshot_loaded = True
        return self._snapshot or ""

    def add_or_consolidate(self, target: str, content: str) -> StoreResult:
        result = self.add(target, content)
        if result.success:
            return result

        if "would exceed the limit" in result.message:
            consolidated = self._try_consolidate(target, content)
            if consolidated is not None:
                return consolidated

        return result

    def _try_consolidate(self, target: str, new_content: str) -> StoreResult | None:
        try:
            from sediman.memory.consolidator import MemoryConsolidator
            consolidator = MemoryConsolidator()
            return consolidator.consolidate_and_add(self, target, new_content)
        except Exception as e:
            logger.debug("memory_consolidation_failed", error=str(e))
            return None

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
        self._invalidate_cache(target)

        try:
            from sediman.memory.entry import ensure_meta_for_entry, classify_entry_type
            from sediman.memory.changelog import append_change, MemoryChange
            entry_type = classify_entry_type(content)
            meta = ensure_meta_for_entry(content, target, type=entry_type, source="agent")
            append_change(MemoryChange(
                action="add",
                target=target,
                content=content,
                entry_id=meta.id,
                source="agent",
            ))
        except Exception as e:
            logger.debug("memory_meta_track_failed", error=str(e))

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
        self._invalidate_cache(target)

        try:
            from sediman.memory.entry import (
                ensure_meta_for_entry, delete_entry_meta, MemoryEntryMeta,
                _remove_from_target_index,
            )
            from sediman.memory.changelog import append_change, MemoryChange
            old_id = MemoryEntryMeta.make_id(old_entry)
            delete_entry_meta(old_id)
            _remove_from_target_index(target, old_id)
            entry_type_meta = "fact"
            try:
                from sediman.memory.entry import classify_entry_type
                entry_type_meta = classify_entry_type(new_entry)
            except Exception:
                pass
            meta = ensure_meta_for_entry(new_entry, target, type=entry_type_meta, source="agent")
            append_change(MemoryChange(
                action="replace",
                target=target,
                content=new_entry,
                old_content=old_entry,
                entry_id=meta.id,
                source="agent",
            ))
        except Exception as e:
            logger.debug("memory_meta_track_replace_failed", error=str(e))

        logger.info("memory_entry_replaced", target=target)

        usage = self.get_usage(target)
        return StoreResult(
            success=True,
            message=f"Replaced in {target}.",
            entries=updated,
            usage=usage,
        )

    def remove(self, target: str, entry: str, reason: str = "") -> StoreResult:
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
        self._invalidate_cache(target)

        try:
            from sediman.memory.entry import (
                delete_entry_meta, MemoryEntryMeta, _remove_from_target_index,
            )
            from sediman.memory.changelog import append_change, MemoryChange
            entry_id = MemoryEntryMeta.make_id(entry)
            delete_entry_meta(entry_id)
            _remove_from_target_index(target, entry_id)
            append_change(MemoryChange(
                action="remove",
                target=target,
                content=entry,
                entry_id=entry_id,
                reason=reason or "manual",
                source="agent",
            ))
        except Exception as e:
            logger.debug("memory_meta_track_remove_failed", error=str(e))

        logger.info("memory_entry_removed", target=target)

        usage = self.get_usage(target)
        return StoreResult(
            success=True,
            message=f"Removed from {target}.",
            entries=updated,
            usage=usage,
        )

    def record_access(self, content: str) -> None:
        try:
            from sediman.memory.entry import record_access_by_content
            record_access_by_content(content)
        except Exception as e:
            logger.debug("memory_record_access_failed", error=str(e))

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
        cached = self._entries_cache.get(target)
        if cached is not None:
            return cached
        path = self._get_file(target)
        if not path.exists():
            self._entries_cache[target] = []
            return []
        text = path.read_text().strip()
        if not text:
            self._entries_cache[target] = []
            return []
        entries = [e.strip() for e in text.split(ENTRY_SEPARATOR)]
        result = [e for e in entries if e]
        self._entries_cache[target] = result
        return result

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
