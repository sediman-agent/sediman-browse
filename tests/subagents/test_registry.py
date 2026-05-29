from __future__ import annotations

from pathlib import Path

import pytest

from sediman.agent.subagents.registry import SubagentRegistry
from sediman.agent.subagents.template import AgentTemplate, render_agent_file


class TestSubagentRegistry:
    def test_loads_builtin_agents(self):
        registry = SubagentRegistry()
        # Should have at least the 5 built-ins we created
        names = registry.names()
        assert "browser" in names
        assert "explore" in names
        assert "review" in names
        assert "code" in names
        assert "debug" in names

    def test_get_existing(self):
        registry = SubagentRegistry()
        browser = registry.get("browser")
        assert browser is not None
        assert browser.name == "browser"
        assert "browse" in browser.description.lower()

    def test_get_missing(self):
        registry = SubagentRegistry()
        assert registry.get("nonexistent") is None

    def test_list_returns_all(self):
        registry = SubagentRegistry()
        agents = registry.list()
        names = [a.name for a in agents]
        assert "browser" in names
        assert "explore" in names

    def test_user_overrides_builtin(self, tmp_path: Path):
        user_dir = tmp_path / "agents"
        user_dir.mkdir()
        # Create a user override for "browser"
        custom = AgentTemplate(
            name="browser",
            description="Custom browser",
            system_prompt="Custom browser agent.",
        )
        (user_dir / "browser.md").write_text(render_agent_file(custom))

        registry = SubagentRegistry(user_dir=user_dir)
        browser = registry.get("browser")
        assert browser is not None
        assert browser.description == "Custom browser"
        assert browser.system_prompt == "Custom browser agent."

    def test_save_new_agent(self, tmp_path: Path):
        user_dir = tmp_path / "agents"
        registry = SubagentRegistry(user_dir=user_dir)
        template = AgentTemplate(
            name="my-agent",
            description="A custom agent",
            system_prompt="Do custom things.",
        )
        path = registry.save(template)
        assert path.exists()
        assert registry.get("my-agent") is not None

    def test_delete_user_agent(self, tmp_path: Path):
        user_dir = tmp_path / "agents"
        registry = SubagentRegistry(user_dir=user_dir)
        template = AgentTemplate(
            name="temp-agent",
            description="Temporary",
            system_prompt="tmp",
        )
        registry.save(template)
        assert registry.exists("temp-agent")
        assert registry.delete("temp-agent") is True
        assert not registry.exists("temp-agent")

    def test_cannot_delete_builtin(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "agents")
        assert registry.delete("browser") is False
        assert registry.exists("browser")

    def test_delete_missing_returns_false(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "agents")
        assert registry.delete("missing") is False

    def test_reload(self, tmp_path: Path):
        user_dir = tmp_path / "agents"
        registry = SubagentRegistry(user_dir=user_dir)
        registry.save(
            AgentTemplate(name="dynamic", description="Dynamic", system_prompt="dyn")
        )
        assert registry.exists("dynamic")
        # Simulate external deletion
        (user_dir / "dynamic.md").unlink()
        registry.reload()
        assert not registry.exists("dynamic")

    def test_get_summaries(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "agents")
        summaries = registry.get_summaries()
        assert "Available subagents:" in summaries
        assert "browser:" in summaries

    def test_to_dict(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "agents")
        data = registry.to_dict()
        assert "browser" in data
        assert data["browser"]["description"] != ""

    def test_invalid_name_raises_on_save(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "agents")
        with pytest.raises(ValueError):
            registry.save(
                AgentTemplate(name="UPPERCASE", description="Bad", system_prompt="bad")
            )

    def test_empty_user_dir(self, tmp_path: Path):
        registry = SubagentRegistry(user_dir=tmp_path / "empty")
        # Still has builtins
        assert "browser" in registry.names()
