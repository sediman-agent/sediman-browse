from __future__ import annotations

import time
from typing import Any

import structlog

from sediman.memory.tiers import WorkingMemory, SessionMemory, MemoryTier, Channel
from sediman.memory.importance import score_importance, classify_channel

logger = structlog.get_logger()


class AutoMemory:
    def __init__(
        self,
        working: WorkingMemory | None = None,
        session: SessionMemory | None = None,
        long_term_store: Any = None,
    ):
        self._working = working or WorkingMemory()
        self._session = session or SessionMemory()
        self._long_term = long_term_store

    @property
    def working(self) -> WorkingMemory:
        return self._working

    @property
    def session(self) -> SessionMemory:
        return self._session

    def observe_action(self, action: str, result: str, success: bool) -> None:
        now = time.time()
        importance = score_importance(action + " " + result)
        if not success:
            importance = min(1.0, importance + 0.2)
        channel_str = classify_channel(action + " " + result)
        channel = Channel.PROCEDURAL if channel_str == "procedural" else Channel.DECLARATIVE

        self._working.add(
            content=f"{'SUCCESS' if success else 'FAILED'}: {action[:100]} → {result[:200]}",
            channel=channel,
            importance=importance,
            timestamp=now,
        )

    def extract_lesson(self, task: str, outcome: str, success: bool) -> str | None:
        if success:
            if any(kw in outcome.lower() for kw in ("navigated", "clicked", "typed", "completed")):
                return None
            return f"When doing '{task[:80]}': {outcome[:200]}"
        else:
            return f"FAILED '{task[:80]}': {outcome[:200]} — try alternative approach"

    def record_lesson(self, lesson: str) -> None:
        if not lesson:
            return
        now = time.time()
        importance = score_importance(lesson)
        channel_str = classify_channel(lesson)
        channel = Channel.PROCEDURAL if channel_str == "procedural" else Channel.DECLARATIVE

        self._session.add(
            content=lesson,
            channel=channel,
            importance=importance,
            timestamp=now,
        )

    def consolidate_to_long_term(self) -> int:
        if not self._long_term:
            return 0

        promoted = self._session.promote_to_long_term(min_importance=0.7)
        count = 0
        for entry in promoted:
            try:
                target = "memory"
                self._long_term.add_or_consolidate(target, entry.content)
                count += 1
            except Exception as e:
                logger.debug("auto_memory_consolidate_failed", error=str(e))

        if count > 0:
            logger.info("auto_memory_consolidated", entries=count)
        return count

    def get_context_for_task(self, task: str, max_chars: int = 2000) -> str:
        parts = []

        session_results = self._session.search(task, limit=5)
        for entry in session_results:
            parts.append(entry.content)

        working_entries = self._working.get()
        for entry in working_entries[-5:]:
            parts.append(entry.content)

        combined = "\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars]

        return combined

    def end_session(self) -> int:
        self._working.clear()
        return self.consolidate_to_long_term()
