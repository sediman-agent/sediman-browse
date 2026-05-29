from __future__ import annotations

from unittest.mock import MagicMock

from sediman.agent.subagents.permissions import PermissionRules
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.llm.provider import ToolDefinition


class TestPermissionRules:
    def test_action_for_exact_match(self):
        rules = PermissionRules({"terminal": "deny", "read_file": "allow"})
        assert rules.action_for("terminal") == "deny"
        assert rules.action_for("read_file") == "allow"

    def test_action_for_catch_all(self):
        rules = PermissionRules({"terminal": "deny", "*": "allow"})
        assert rules.action_for("terminal") == "deny"
        assert rules.action_for("read_file") == "allow"
        assert rules.action_for("unknown_tool") == "allow"

    def test_action_for_default(self):
        rules = PermissionRules({})
        assert rules.action_for("anything") == "allow"

    def test_is_allowed(self):
        rules = PermissionRules({"read_file": "allow", "write_file": "deny"})
        assert rules.is_allowed("read_file") is True
        assert rules.is_allowed("write_file") is False

    def test_is_denied(self):
        rules = PermissionRules({"terminal": "deny"})
        assert rules.is_denied("terminal") is True
        assert rules.is_denied("read_file") is False

    def test_is_ask(self):
        rules = PermissionRules({"write_file": "ask"})
        assert rules.is_ask("write_file") is True
        assert rules.is_ask("read_file") is False

    def test_invalid_action_normalized(self):
        rules = PermissionRules({"foo": "invalid"})
        assert rules.action_for("foo") == "allow"

    def test_filter_tools(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="read_file", description="r", parameters={}),
            lambda **kw: MagicMock(),
        )
        registry.register(
            ToolDefinition(name="write_file", description="w", parameters={}),
            lambda **kw: MagicMock(),
        )
        registry.register(
            ToolDefinition(name="terminal", description="t", parameters={}),
            lambda **kw: MagicMock(),
        )

        rules = PermissionRules({"terminal": "deny", "*": "allow"})
        filtered = rules.filter_tools(registry)
        assert filtered.has_tool("read_file")
        assert filtered.has_tool("write_file")
        assert not filtered.has_tool("terminal")

    def test_filter_tools_ask_included(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(name="write_file", description="w", parameters={}),
            lambda **kw: MagicMock(),
        )
        rules = PermissionRules({"write_file": "ask"})
        filtered = rules.filter_tools(registry)
        assert filtered.has_tool("write_file")

    def test_default_classmethod(self):
        rules = PermissionRules.default()
        assert rules.is_ask("terminal")
        assert rules.is_ask("write_file")
        assert rules.is_ask("patch")
        assert rules.is_allowed("read_file")

    def test_browser_only_classmethod(self):
        rules = PermissionRules.browser_only()
        assert rules.is_denied("terminal")
        assert rules.is_denied("write_file")
        assert rules.is_allowed("read_file")
        assert rules.is_allowed("web_search")

    def test_code_only_classmethod(self):
        rules = PermissionRules.code_only()
        assert rules.is_denied("browser")
        assert rules.is_allowed("write_file")
        assert rules.is_allowed("patch")
        assert rules.is_allowed("terminal")

    def test_to_dict(self):
        rules = PermissionRules({"a": "allow", "b": "deny"})
        assert rules.to_dict() == {"a": "allow", "b": "deny"}

    def test_case_insensitive_actions(self):
        rules = PermissionRules({"x": "DENY", "y": "Ask"})
        assert rules.is_denied("x")
        assert rules.is_ask("y")
