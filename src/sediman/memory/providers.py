"""MemoryProvider ABC and BuiltinMemoryProvider."""
from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from sediman.llm.provider import ToolDefinition
from sediman.memory.store import MemoryStore

logger = structlog.get_logger()

MEMORY_TOOL_SCHEMA = ToolDefinition(
    name="memory",
    description=(
        "Manage your persistent memory. Save durable facts about the user, "
        "environment, tool quirks, and stable conventions. "
        "Memory is injected into every future session's system prompt."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "replace", "remove"],
                "description": "add a new entry, replace an existing one, or remove one",
            },
            "target": {
                "type": "string",
                "enum": ["memory", "user"],
                "description": (
                    "'memory' for your personal notes (environment, tools, conventions). "
                    "'user' for user profile (preferences, communication style, expectations)."
                ),
            },
            "content": {
                "type": "string",
                "description": "The entry text (required for add and replace). Keep concise: 1-3 sentences, standalone facts.",
            },
            "old_entry": {
                "type": "string",
                "description": "Exact text of the existing entry to match (required for replace and remove).",
            },
        },
        "required": ["action", "target"],
    },
)


class MemoryProvider(ABC):
    @staticmethod
    @abstractmethod
    def name() -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    def get_tool_schemas(self) -> list[ToolDefinition]: ...

    def system_prompt_block(self) -> str:
        return ""

    async def prefetch(self, query: str) -> str | None:
        return None

    async def on_turn_start(self) -> None:
        pass

    async def on_session_end(self) -> None:
        pass

    async def on_pre_compress(self) -> None:
        pass

    async def on_memory_write(self, target: str, content: str) -> None:
        pass


class BuiltinMemoryProvider(MemoryProvider):
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @staticmethod
    def name() -> str:
        return "builtin"

    def is_available(self) -> bool:
        return True

    async def initialize(self) -> None:
        self._store.load_snapshot()

    def get_tool_schemas(self) -> list[ToolDefinition]:
        return [MEMORY_TOOL_SCHEMA]

    def system_prompt_block(self) -> str:
        return self._store.format_for_system_prompt()
