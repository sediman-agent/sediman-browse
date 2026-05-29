from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sediman.memory.providers import BuiltinMemoryProvider, MemoryProvider, MEMORY_TOOL_SCHEMA
from sediman.memory.store import MemoryStore


class TestMemoryProviderABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            MemoryProvider()

    def test_subclass_must_implement_abstract(self):
        class Incomplete(MemoryProvider):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass(self):
        class Concrete(MemoryProvider):
            @staticmethod
            def name(): return "test"
            def is_available(self): return True
            async def initialize(self): pass
            def get_tool_schemas(self): return []

        c = Concrete()
        assert c.name() == "test"
        assert c.is_available() is True
        assert c.system_prompt_block() == ""
        assert c.get_tool_schemas() == []


class TestBuiltinMemoryProvider:
    @pytest.fixture
    def provider(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            store = MemoryStore()
            yield BuiltinMemoryProvider(store)

    def test_name(self, provider):
        assert provider.name() == "builtin"

    def test_is_available(self, provider):
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_initialize_loads_snapshot(self, provider):
        provider._store.add("memory", "pre-existing")
        await provider.initialize()
        snap = provider._store.snapshot
        assert snap is not None
        assert "pre-existing" in snap

    def test_get_tool_schemas_returns_memory_tool(self, provider):
        schemas = provider.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0].name == "memory"
        assert schemas[0].description is not None

    def test_memory_tool_schema_has_correct_structure(self):
        assert MEMORY_TOOL_SCHEMA.name == "memory"
        assert "action" in MEMORY_TOOL_SCHEMA.parameters["properties"]
        assert "target" in MEMORY_TOOL_SCHEMA.parameters["properties"]
        assert "content" in MEMORY_TOOL_SCHEMA.parameters["properties"]
        assert MEMORY_TOOL_SCHEMA.parameters["required"] == ["action", "target"]

    def test_system_prompt_block_returns_filled_string(self, provider):
        provider._store.add("memory", "note")
        block = provider.system_prompt_block()
        assert "<memory-context>" in block
        assert "note" in block

    def test_system_prompt_block_empty_when_no_store(self, provider):
        block = provider.system_prompt_block()
        assert "<memory-context>" in block


class TestBuiltinMemoryProviderHooks:
    @pytest.fixture
    def provider(self, tmp_sediman_dir: Path):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        with patch("sediman.memory.store.MEMORY_DIR", mem_dir), \
             patch("sediman.memory.store.MEMORY_FILE", mem_dir / "MEMORY.md"), \
             patch("sediman.memory.store.USER_FILE", mem_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.store.OLD_USER_FILE", tmp_sediman_dir / "USER.md"), \
             patch("sediman.memory.store.OLD_MEMORY_DB", tmp_sediman_dir / "memory.json"):
            store = MemoryStore()
            yield BuiltinMemoryProvider(store)

    def test_hooks_dont_raise(self, provider):
        import asyncio
        asyncio.run(provider.on_turn_start())
        asyncio.run(provider.on_session_end())
        asyncio.run(provider.on_pre_compress())
        asyncio.run(provider.on_memory_write("memory", "test"))

    def test_prefetch_returns_none(self, provider):
        import asyncio
        result = asyncio.run(provider.prefetch("test"))
        assert result is None
