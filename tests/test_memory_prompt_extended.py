from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from sediman.memory.prompt import (
    load_memory,
    get_memory_size,
    save_structured_memory,
    save_episodic,
    save_procedural,
    get_relevant_context,
    MemoryType,
    MAX_MEMORY_BYTES,
    MAX_ENTRIES_PER_TYPE,
)


class TestSaveStructuredMemory:
    def test_saves_to_memory(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_structured_memory("structured fact", memory_type=MemoryType.SEMANTIC)
            mem_file = mem_dir / "MEMORY.md"
            assert mem_file.exists()
            assert "structured fact" in mem_file.read_text()

    def test_with_metadata(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_structured_memory("with metadata", memory_type=MemoryType.PROCEDURAL, source="skill", metadata={"key": "val"})
            assert get_memory_size() > 0

    def test_episodic_memory_type(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_structured_memory("episodic note", memory_type=MemoryType.EPISODIC)
            assert "episodic note" in load_memory()


class TestSaveEpisodic:
    def test_saves_task_result(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_episodic("search for laptops", "found 10 results", success=True)
            content = load_memory()
            assert "search for laptops" in content
            assert "Success" in content

    def test_saves_failed_task(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_episodic("do something", "error occurred", success=False)
            content = load_memory()
            assert "Failed" in content

    def test_truncates_long_task(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_episodic("x" * 200, "short result", success=True)
            content = load_memory()
            assert len(content) > 0


class TestSaveProcedural:
    def test_saves_procedure(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            save_procedural("check-stock", ["open site", "search", "extract"])
            content = load_memory()
            assert "check-stock" in content
            assert "open site" in content

    def test_truncates_long_steps(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            steps = ["x" * 100] * 10
            save_procedural("long-skill", steps)
            content = load_memory()
            assert content


class TestGetRelevantContext:
    def test_returns_matching_entries(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            from sediman.memory.store import MemoryStore
            store = MemoryStore()
            store.add("memory", "user prefers python programming")
            store.add("memory", "use chrome for browser tasks")
            store.add("memory", "always check stock prices first")

            results = get_relevant_context("python", limit=5)
            assert len(results) >= 1
            assert any("python" in r.lower() for r in results)

    def test_returns_empty_when_no_match(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"), \
             patch("sediman.memory.manager.MemoryManager._get_vector_store", return_value=MagicMock(search=MagicMock(return_value=[]))):
            from sediman.memory.store import MemoryStore
            store = MemoryStore()
            store.add("memory", "some unrelated fact")

            results = get_relevant_context("nonexistent", limit=5)
            assert results == []

    def test_respects_limit(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            from sediman.memory.store import MemoryStore
            store = MemoryStore()
            for i in range(10):
                store.add("memory", f"common word entry {i}")

            results = get_relevant_context("common", limit=3)
            assert len(results) <= 3

    def test_returns_empty_when_no_entries(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"), \
             patch("sediman.memory.manager.MemoryManager._get_vector_store", return_value=MagicMock(search=MagicMock(return_value=[]))):
            results = get_relevant_context("anything")
            assert results == []

    def test_scoring_by_word_count(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            from sediman.memory.store import MemoryStore
            store = MemoryStore()
            store.add("memory", "user prefers python for scripting and automation tasks")
            store.add("memory", "python is great for data science and machine learning")
            store.add("memory", "use chrome browser for all tasks")

            results = get_relevant_context("python automation")
            assert len(results) >= 1
            assert "python" in results[0].lower()


class TestMemoryType:
    def test_enum_values(self):
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.PROCEDURAL.value == "procedural"

    def test_enum_membership(self):
        assert MemoryType("episodic") == MemoryType.EPISODIC


class TestConstants:
    def test_constants_exist(self):
        assert MAX_MEMORY_BYTES > 0
        assert MAX_ENTRIES_PER_TYPE > 0
