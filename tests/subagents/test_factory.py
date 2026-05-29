from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sediman.agent.subagents.factory import SubagentFactory
from sediman.agent.subagents.registry import SubagentRegistry
from sediman.agent.subagents.template import AgentTemplate


class TestSubagentFactory:
    @pytest.fixture
    def registry(self, tmp_path):
        user_dir = tmp_path / "agents"
        return SubagentRegistry(user_dir=user_dir)

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def factory(self, registry, mock_llm):
        return SubagentFactory(
            registry=registry,
            llm_provider=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_spawn_unknown_agent(self, factory):
        result = await factory.spawn("nonexistent", "task")
        assert result.success is False
        assert "Unknown subagent" in result.summary

    @pytest.mark.asyncio
    async def test_spawn_known_agent(self, factory, registry, mock_llm):
        registry.save(
            AgentTemplate(
                name="test-agent",
                description="A test",
                system_prompt="Test.",
            )
        )
        # Mock the session.run inside spawn
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Done.", tool_calls=[]))

        result = await factory.spawn("test-agent", "do thing")
        assert result.success is True
        assert result.summary == "Done."

    @pytest.mark.asyncio
    async def test_max_depth_exceeded(self, factory):
        result = await factory.spawn("browser", "task", depth=3)
        assert result.success is False
        assert "depth" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_spawn_parallel(self, factory, registry, mock_llm):
        registry.save(
            AgentTemplate(
                name="parallel-agent",
                description="Parallel",
                system_prompt="Parallel.",
            )
        )
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Done.", tool_calls=[]))

        specs = [
            ("parallel-agent", "task1"),
            ("parallel-agent", "task2"),
        ]
        results = await factory.spawn_parallel(specs)
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_spawn_parallel_depth_exceeded(self, factory):
        specs = [("browser", "task")]
        results = await factory.spawn_parallel(specs, depth=3)
        assert len(results) == 1
        assert results[0].success is False

    def test_list_available(self, factory, registry):
        available = factory.list_available()
        names = [a["name"] for a in available]
        assert "browser" in names
        assert "explore" in names

    @pytest.mark.asyncio
    async def test_browser_isolation_flag(self, factory, registry, mock_llm):
        registry.save(
            AgentTemplate(
                name="iso-agent",
                description="Isolation test",
                system_prompt="Test.",
            )
        )
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Done.", tool_calls=[]))

        result = await factory.spawn(
            "iso-agent", "task", browser_isolation=True
        )
        assert result.success is True
