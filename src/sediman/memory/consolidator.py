"""Memory consolidation — merge or summarize entries to free space.

When memory is full and a new entry needs to be added, the consolidator
attempts to free space by merging similar entries or summarizing old ones.
Uses LLM summarization when available, falls back to heuristic truncation.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger()


class MemoryConsolidator:
    def __init__(self, llm: Any = None):
        self._llm = llm

    def consolidate_and_add(
        self,
        store: Any,
        target: str,
        new_content: str,
    ) -> Any:
        from sediman.memory.store import StoreResult

        usage = store.get_usage(target)
        entries = usage.entries
        if not entries:
            return None

        limit = usage.limit
        current_chars = usage.chars
        new_chars = len(new_content) + len(store.ENTRY_SEPARATOR)

        space_needed = (current_chars + new_chars) - limit
        if space_needed <= 0:
            return store.add(target, new_content)

        merged = self._try_merge_small_entries(entries, target, space_needed)
        if merged is not None:
            rewritten = store.ENTRY_SEPARATOR.join(merged)
            store._atomic_write(store._get_file(target), rewritten)
            logger.info("memory_consolidated", target=target, method="merge_small", before=len(entries), after=len(merged))
            return store.add(target, new_content)

        summarized = self._try_summarize_old_entries(entries, target, space_needed)
        if summarized is not None:
            rewritten = store.ENTRY_SEPARATOR.join(summarized)
            store._atomic_write(store._get_file(target), rewritten)
            logger.info("memory_consolidated", target=target, method="summarize_old", before=len(entries), after=len(summarized))
            return store.add(target, new_content)

        removed = self._try_remove_least_relevant(entries, target, space_needed)
        if removed is not None:
            rewritten = store.ENTRY_SEPARATOR.join(removed)
            store._atomic_write(store._get_file(target), rewritten)
            logger.info("memory_consolidated", target=target, method="remove_least_relevant", before=len(entries), after=len(removed))
            return store.add(target, new_content)

        logger.debug("memory_consolidation_unable", target=target, needed=space_needed)
        return None

    async def consolidate_with_llm(
        self,
        store: Any,
        target: str,
        new_content: str,
        llm: Any = None,
    ) -> Any:
        from sediman.memory.store import ENTRY_SEPARATOR

        llm = llm or self._llm
        if not llm:
            return self.consolidate_and_add(store, target, new_content)

        usage = store.get_usage(target)
        entries = usage.entries
        if not entries:
            return None

        limit = usage.limit
        current_chars = usage.chars
        new_chars = len(new_content) + len(ENTRY_SEPARATOR)
        space_needed = (current_chars + new_chars) - limit

        if space_needed <= 0:
            return store.add(target, new_content)

        oldest = entries[:max(1, len(entries) // 3)]
        total_oldest_chars = sum(len(e) for e in oldest)
        if total_oldest_chars < space_needed * 0.5:
            return self.consolidate_and_add(store, target, new_content)

        summarized = await self._llm_summarize(oldest, llm)
        if summarized and len(summarized) < total_oldest_chars * 0.7:
            result = [summarized] + entries[len(oldest):]
            rewritten = ENTRY_SEPARATOR.join(result)
            store._atomic_write(store._get_file(target), rewritten)
            logger.info("memory_consolidated_llm", target=target, before=len(entries), after=len(result))
            return store.add(target, new_content)

        return self.consolidate_and_add(store, target, new_content)

    async def _llm_summarize(self, entries: list[str], llm: Any) -> str | None:
        combined = "\n".join(f"- {e}" for e in entries)
        if len(combined) < 50:
            return None

        prompt = (
            "Summarize these memory entries into a single concise entry.\n"
            "Preserve all important facts, preferences, and rules.\n"
            "Remove redundant information.\n"
            "The summary should be significantly shorter than the originals.\n\n"
            f"Entries:\n{combined}\n\n"
            "Provide ONLY the summarized text, no explanations."
        )

        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
            )
            text = (response.text or "").strip()
            if text and len(text) < len(combined) * 0.9:
                return text
        except Exception as e:
            logger.debug("llm_summarize_failed", error=str(e))

        return None

    def _try_merge_small_entries(
        self,
        entries: list[str],
        target: str,
        space_needed: int,
    ) -> list[str] | None:
        short = [(i, e) for i, e in enumerate(entries) if len(e) < 60]
        if len(short) < 2:
            return None

        result = list(entries)
        first_idx, first_entry = short[0]
        merged_parts = [first_entry]
        freed = 0
        merged_indices = {first_idx}

        for idx, entry in short[1:]:
            if freed >= space_needed:
                break
            merged_parts.append(entry)
            freed += len(entry) + len("§\n")
            merged_indices.add(idx)

        if freed < space_needed * 0.5:
            return None

        merged_text = "; ".join(merged_parts)
        indices_sorted = sorted(merged_indices, reverse=True)
        for idx in indices_sorted:
            result.pop(idx)

        insert_pos = min(first_idx, len(result))
        result.insert(insert_pos, merged_text)

        return result

    def _try_summarize_old_entries(
        self,
        entries: list[str],
        target: str,
        space_needed: int,
    ) -> list[str] | None:
        if len(entries) < 3:
            return None

        oldest = entries[:max(1, len(entries) // 3)]
        total_oldest_chars = sum(len(e) for e in oldest)
        if total_oldest_chars < space_needed:
            return None

        summarized = self._summarize_texts(oldest)
        if summarized is None:
            return None

        result = [summarized] + entries[len(oldest):]
        return result

    def _try_remove_least_relevant(
        self,
        entries: list[str],
        target: str,
        space_needed: int,
    ) -> list[str] | None:
        from sediman.memory.importance import score_importance

        scored: list[tuple[int, str, float]] = []
        for i, entry in enumerate(entries):
            score = score_importance(entry)
            scored.append((i, entry, score))

        scored.sort(key=lambda x: x[2])

        to_remove: set[int] = set()
        freed = 0
        for i, entry, _score in scored:
            if freed >= space_needed:
                break
            to_remove.add(i)
            freed += len(entry) + len("§\n")

        if freed < space_needed:
            return None

        return [e for i, e in enumerate(entries) if i not in to_remove]

    def _summarize_texts(self, texts: list[str]) -> str | None:
        if not texts:
            return None

        combined = " ".join(texts)
        sentences = re.split(r'(?<=[.!?])\s+', combined)

        if len(sentences) <= 1:
            return None

        if len(combined) <= 80:
            return combined

        keep = max(1, len(sentences) // 2)
        summary = " ".join(sentences[:keep])
        if len(summary) >= len(combined) * 0.9:
            return None

        return summary
