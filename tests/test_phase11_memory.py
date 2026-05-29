from __future__ import annotations

import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from sediman.memory.tiers import (
    TieredEntry,
    MemoryTier,
    Channel,
    WorkingMemory,
    SessionMemory,
)
from sediman.memory.importance import score_importance, classify_channel, score_with_llm
from sediman.memory.auto_memory import AutoMemory
from sediman.memory.consolidator import MemoryConsolidator


class TestTieredEntry:
    def test_recency_score_fresh(self):
        entry = TieredEntry(content="test", tier=MemoryTier.WORKING, timestamp=time.time())
        assert entry.recency_score(time.time()) == 1.0

    def test_recency_score_old(self):
        entry = TieredEntry(content="test", tier=MemoryTier.WORKING, timestamp=time.time() - 7200 * 3600)
        assert entry.recency_score(time.time()) == 0.3

    def test_combined_score_weights(self):
        now = time.time()
        entry = TieredEntry(
            content="important preference",
            tier=MemoryTier.LONG_TERM,
            importance=0.9,
            access_count=10,
            timestamp=now,
        )
        score = entry.combined_score(now)
        assert score > 0.5

    def test_combined_score_low_importance(self):
        now = time.time()
        entry = TieredEntry(
            content="test",
            tier=MemoryTier.WORKING,
            importance=0.1,
            access_count=0,
            timestamp=now - 10000,
        )
        score = entry.combined_score(now)
        assert score < 0.5


class TestWorkingMemory:
    def test_add_and_get(self):
        wm = WorkingMemory()
        entry = wm.add("test entry", channel=Channel.DECLARATIVE, importance=0.7)
        assert entry.content == "test entry"
        assert len(wm.get()) == 1

    def test_channel_filter(self):
        wm = WorkingMemory()
        wm.add("declarative", channel=Channel.DECLARATIVE)
        wm.add("procedural", channel=Channel.PROCEDURAL)
        decl = wm.get(channel=Channel.DECLARATIVE)
        proc = wm.get(channel=Channel.PROCEDURAL)
        assert len(decl) == 1
        assert len(proc) == 1

    def test_eviction(self):
        wm = WorkingMemory(max_entries=3, max_chars=10000)
        for i in range(5):
            wm.add(f"entry {i}", importance=0.1 + i * 0.2)
        assert wm.count <= 3

    def test_clear(self):
        wm = WorkingMemory()
        wm.add("test")
        wm.clear()
        assert wm.count == 0

    def test_total_chars(self):
        wm = WorkingMemory()
        wm.add("hello")
        wm.add("world")
        assert wm.total_chars == 10


class TestSessionMemory:
    def test_add_and_get(self):
        sm = SessionMemory()
        sm.add("session note", importance=0.6)
        assert len(sm.get()) == 1

    def test_search(self):
        sm = SessionMemory()
        sm.add("user prefers dark mode on the website")
        sm.add("search for python tutorials")
        sm.add("browser chrome is used")
        results = sm.search("dark mode preference")
        assert len(results) >= 1
        assert "dark mode" in results[0].content

    def test_min_importance_filter(self):
        sm = SessionMemory()
        sm.add("low importance", importance=0.2)
        sm.add("high importance", importance=0.9)
        results = sm.get(min_importance=0.7)
        assert len(results) == 1
        assert "high" in results[0].content

    def test_promote_to_long_term(self):
        sm = SessionMemory()
        sm.add("trivial", importance=0.3)
        sm.add("important", importance=0.8)
        sm.add("critical", importance=0.95)
        promoted = sm.promote_to_long_term(min_importance=0.7)
        assert len(promoted) == 2
        assert sm.count == 1


class TestImportanceScoring:
    def test_high_importance_keywords(self):
        score = score_importance("This is a critical preference that must always be followed")
        assert score > 0.6

    def test_low_importance_keywords(self):
        score = score_importance("ok maybe test this tmp thing")
        assert score < 0.5

    def test_neutral_content(self):
        score = score_importance("The website uses a standard layout with navigation")
        assert 0.3 <= score <= 0.8

    def test_empty_content(self):
        assert score_importance("") == 0.0

    def test_short_content_lower(self):
        score = score_importance("hi")
        assert score < 0.5

    def test_long_content_higher(self):
        long_text = "This is a detailed description of a complex workflow. " * 10
        score = score_importance(long_text)
        assert score > 0.4


class TestClassifyChannel:
    def test_procedural(self):
        assert classify_channel("First navigate to the page, then click the button") == "procedural"

    def test_declarative(self):
        assert classify_channel("The user prefers dark mode") == "declarative"

    def test_procedural_with_steps(self):
        assert classify_channel("Step 1: open browser. Step 2: search for item.") == "procedural"


class TestLLMImportanceScoring:
    @pytest.mark.asyncio
    async def test_score_with_llm(self):
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(text="4")
        score = await score_with_llm("User always prefers Chrome browser", llm)
        assert score == 0.8

    @pytest.mark.asyncio
    async def test_score_with_llm_error(self):
        llm = AsyncMock()
        llm.chat.side_effect = Exception("fail")
        score = await score_with_llm("test content", llm)
        assert score == 0.5


class TestAutoMemory:
    def test_observe_action_success(self):
        am = AutoMemory()
        am.observe_action("click #btn", "button clicked", success=True)
        assert am.working.count == 1

    def test_observe_action_failure(self):
        am = AutoMemory()
        am.observe_action("click #missing", "element not found", success=False)
        entries = am.working.get()
        assert any("FAILED" in e.content for e in entries)

    def test_extract_lesson_success(self):
        am = AutoMemory()
        lesson = am.extract_lesson("search shoes", "found 10 results", success=True)
        assert lesson is not None
        assert "search shoes" in lesson

    def test_extract_lesson_failure(self):
        am = AutoMemory()
        lesson = am.extract_lesson("buy item", "cart empty", success=False)
        assert lesson is not None
        assert "FAILED" in lesson

    def test_extract_lesson_trivial(self):
        am = AutoMemory()
        lesson = am.extract_lesson("click", "navigated to page", success=True)
        assert lesson is None

    def test_record_lesson(self):
        am = AutoMemory()
        am.record_lesson("When searching: always use lowercase query")
        assert am.session.count == 1

    def test_get_context_for_task(self):
        am = AutoMemory()
        am.record_lesson("User prefers dark mode on all websites")
        am.record_lesson("Chrome browser is preferred")
        am.observe_action("search dark mode", "results found", success=True)
        ctx = am.get_context_for_task("configure dark mode")
        assert len(ctx) > 0

    def test_consolidate_to_long_term_no_store(self):
        am = AutoMemory()
        am.record_lesson("important lesson about preferences")
        count = am.consolidate_to_long_term()
        assert count == 0

    def test_consolidate_to_long_term_with_store(self):
        store = MagicMock()
        store.add_or_consolidate = MagicMock(return_value=MagicMock(success=True))
        am = AutoMemory(long_term_store=store)
        am.session.add("critical preference", importance=0.9)
        am.session.add("trivial note", importance=0.2)
        count = am.consolidate_to_long_term()
        assert count == 1

    def test_end_session(self):
        store = MagicMock()
        am = AutoMemory(long_term_store=store)
        am.observe_action("test", "done", success=True)
        am.record_lesson("lesson learned")
        am.end_session()
        assert am.working.count == 0


class TestConsolidatorLLM:
    @pytest.mark.asyncio
    async def test_consolidate_with_llm(self):
        from sediman.memory.store import MemoryStore, ENTRY_SEPARATOR

        store = MemoryStore()
        target_file = store._get_file("memory")

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)

            entries = []
            for i in range(10):
                entries.append(f"Memory entry number {i} about topic {i % 3}. This is a longer entry to fill space.")
            store._atomic_write(target_file, ENTRY_SEPARATOR.join(entries))
            store._invalidate_cache("memory")

            llm = AsyncMock()
            llm.chat.return_value = MagicMock(
                text="Consolidated: entries about topics 0-2 covering various memory items."
            )

            consolidator = MemoryConsolidator(llm=llm)
            result = await consolidator.consolidate_with_llm(
                store, "memory", "new important entry that needs space"
            )
        finally:
            if target_file.exists():
                target_file.unlink()

    @pytest.mark.asyncio
    async def test_consolidate_fallback_no_llm(self):
        consolidator = MemoryConsolidator()
        result = await consolidator.consolidate_with_llm(
            MagicMock(
                get_usage=MagicMock(return_value=MagicMock(entries=[], chars=0, limit=100)),
            ),
            "memory",
            "test",
            llm=None,
        )
        assert result is None


class TestConsolidatorImportanceBased:
    def test_removes_low_importance_first(self):
        consolidator = MemoryConsolidator()
        entries = [
            "This is a critical preference that must always be kept",
            "ok test tmp thing whatever fine",
            "Another important rule about the system",
            "maybe try this sure fine",
            "essential policy for the browser agent always follow",
        ]
        result = consolidator._try_remove_least_relevant(entries, "memory", 50)
        if result is not None:
            important_found = any(
                "critical preference" in e or "important rule" in e or "essential policy" in e
                for e in result
            )
            assert important_found


class TestVectorStoreMeta:
    def test_upsert_meta(self):
        from sediman.memory.vector import VectorStore
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            vs = VectorStore(lazy=False)
            vs._db_path = Path(tmp) / "test_vec.db"
            vs._ensure_db_schema()

            vs.upsert_meta(
                text="test entry",
                tier="session",
                channel="procedural",
                importance=0.8,
            )

            conn = vs._get_conn()
            try:
                row = conn.execute(
                    "SELECT tier, channel, importance FROM vector_meta WHERE text = ?",
                    ("test entry",),
                ).fetchone()
                assert row is not None
                assert row[0] == "session"
                assert row[1] == "procedural"
                assert row[2] == 0.8
            finally:
                conn.close()

    def test_sqlite_vec_check(self):
        from sediman.memory.vector import _check_sqlite_vec
        result = _check_sqlite_vec()
        assert isinstance(result, bool)


class TestTieredMemoryIntegration:
    def test_full_lifecycle(self):
        wm = WorkingMemory()
        sm = SessionMemory()

        wm.observe_action = None
        wm.add("current task: search for shoes", importance=0.5, timestamp=time.time())
        sm.add("user prefers dark mode on shopping sites", importance=0.8, timestamp=time.time())
        sm.add("search for shoes: found 15 results", importance=0.3, timestamp=time.time())

        assert wm.count == 1
        assert sm.count == 2

        promoted = sm.promote_to_long_term(min_importance=0.7)
        assert len(promoted) == 1
        assert "dark mode" in promoted[0].content
        assert sm.count == 1

        wm.clear()
        assert wm.count == 0
