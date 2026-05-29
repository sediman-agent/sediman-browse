from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

import structlog

logger = structlog.get_logger()


class MemoryTier(Enum):
    WORKING = "working"
    SESSION = "session"
    LONG_TERM = "long_term"


class Channel(Enum):
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


@dataclass
class TieredEntry:
    content: str
    tier: MemoryTier
    channel: Channel = Channel.DECLARATIVE
    importance: float = 0.5
    timestamp: float = 0.0
    access_count: int = 0
    last_accessed: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str = ""

    def recency_score(self, now: float) -> float:
        if not self.timestamp:
            return 0.5
        age_hours = (now - self.timestamp) / 3600
        if age_hours < 1:
            return 1.0
        if age_hours < 24:
            return 0.9
        if age_hours < 168:
            return 0.7
        if age_hours < 720:
            return 0.5
        return 0.3

    def combined_score(self, now: float) -> float:
        recency = self.recency_score(now)
        access = min(1.0, self.access_count / 10.0)
        return self.importance * 0.5 + recency * 0.3 + access * 0.2


class WorkingMemory:
    def __init__(self, max_entries: int = 20, max_chars: int = 4000):
        self._entries: list[TieredEntry] = []
        self._max_entries = max_entries
        self._max_chars = max_chars

    def add(self, content: str, channel: Channel = Channel.DECLARATIVE, importance: float = 0.5, timestamp: float = 0.0) -> TieredEntry:
        entry = TieredEntry(
            content=content,
            tier=MemoryTier.WORKING,
            channel=channel,
            importance=importance,
            timestamp=timestamp,
        )
        self._entries.append(entry)
        self._evict_if_needed()
        return entry

    def get(self, channel: Channel | None = None) -> list[TieredEntry]:
        if channel is None:
            return list(self._entries)
        return [e for e in self._entries if e.channel == channel]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def total_chars(self) -> int:
        return sum(len(e.content) for e in self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self._max_entries or self.total_chars > self._max_chars:
            if not self._entries:
                break
            import time
            now = time.time()
            self._entries.sort(key=lambda e: e.combined_score(now))
            self._entries.pop(0)


class SessionMemory:
    def __init__(self, max_entries: int = 100, max_chars: int = 20000):
        self._entries: list[TieredEntry] = []
        self._max_entries = max_entries
        self._max_chars = max_chars

    def add(self, content: str, channel: Channel = Channel.DECLARATIVE, importance: float = 0.5, timestamp: float = 0.0) -> TieredEntry:
        entry = TieredEntry(
            content=content,
            tier=MemoryTier.SESSION,
            channel=channel,
            importance=importance,
            timestamp=timestamp,
        )
        self._entries.append(entry)
        self._evict_if_needed()
        return entry

    def get(self, channel: Channel | None = None, min_importance: float = 0.0) -> list[TieredEntry]:
        results = self._entries
        if channel is not None:
            results = [e for e in results if e.channel == channel]
        if min_importance > 0:
            results = [e for e in results if e.importance >= min_importance]
        return list(results)

    def search(self, query: str, limit: int = 10) -> list[TieredEntry]:
        query_words = set(query.lower().split())
        scored: list[tuple[float, TieredEntry]] = []
        for entry in self._entries:
            entry_words = set(entry.content.lower().split())
            overlap = len(query_words & entry_words)
            if overlap > 0:
                import time
                score = overlap / max(len(query_words), 1)
                score += entry.combined_score(time.time()) * 0.3
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def promote_to_long_term(self, min_importance: float = 0.7) -> list[TieredEntry]:
        promoted = [e for e in self._entries if e.importance >= min_importance]
        self._entries = [e for e in self._entries if e.importance < min_importance]
        return promoted

    def clear(self) -> None:
        self._entries.clear()

    @property
    def total_chars(self) -> int:
        return sum(len(e.content) for e in self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self._max_entries or self.total_chars > self._max_chars:
            if not self._entries:
                break
            import time
            now = time.time()
            self._entries.sort(key=lambda e: e.combined_score(now))
            self._entries.pop(0)
