from __future__ import annotations

from dataclasses import dataclass

import structlog

from sediman.agent.tool_dispatch import ToolRegistry

logger = structlog.get_logger()

_VALID_ACTIONS = {"allow", "ask", "deny"}
_DEFAULT_RULE = "allow"


@dataclass
class PermissionRules:
    """Permission rules for a subagent, keyed by tool name.

    Rules are evaluated in order; the last matching rule wins.
    Special key "*" is a catch-all.
    """

    rules: dict[str, str]

    def __post_init__(self) -> None:
        # Normalize actions
        cleaned: dict[str, str] = {}
        for key, val in self.rules.items():
            low = val.lower().strip()
            if low not in _VALID_ACTIONS:
                logger.warning("invalid_permission_action", key=key, val=val)
                low = _DEFAULT_RULE
            cleaned[key] = low
        self.rules = cleaned

    def action_for(self, tool_name: str) -> str:
        """Return the effective action for a tool name."""
        if tool_name in self.rules:
            return self.rules[tool_name]
        if "*" in self.rules:
            return self.rules["*"]
        return _DEFAULT_RULE

    def is_allowed(self, tool_name: str) -> bool:
        return self.action_for(tool_name) == "allow"

    def is_denied(self, tool_name: str) -> bool:
        return self.action_for(tool_name) == "deny"

    def is_ask(self, tool_name: str) -> bool:
        return self.action_for(tool_name) == "ask"

    def filter_tools(self, full_registry: ToolRegistry) -> ToolRegistry:
        """Return a new ToolRegistry containing only allowed tools."""
        filtered = ToolRegistry()
        for name in full_registry.list_tools():
            if self.is_denied(name):
                continue
            if self.is_allowed(name) or self.is_ask(name):
                definition = full_registry.get_definition(name)
                handler = full_registry._handlers.get(name)
                if definition and handler is not None:
                    filtered.register(definition, handler)
        return filtered

    def to_dict(self) -> dict[str, str]:
        return dict(self.rules)

    @classmethod
    def default(cls) -> PermissionRules:
        """Safe default for auto-created agents: terminal/write/patch ask, rest allow."""
        return cls({
            "terminal": "ask",
            "write_file": "ask",
            "patch": "ask",
            "delete": "ask",
            "*": "allow",
        })

    @classmethod
    def browser_only(cls) -> PermissionRules:
        return cls({
            "terminal": "deny",
            "write_file": "deny",
            "patch": "deny",
            "delete": "deny",
            "read_file": "allow",
            "list_files": "allow",
            "skill_manage": "allow",
            "browser": "allow",
            "web_search": "allow",
            "*": "deny",
        })

    @classmethod
    def code_only(cls) -> PermissionRules:
        return cls({
            "browser": "deny",
            "web_search": "allow",
            "read_file": "allow",
            "write_file": "allow",
            "patch": "allow",
            "list_files": "allow",
            "search_files": "allow",
            "terminal": "allow",
            "delegate_task": "deny",
            "*": "deny",
        })
