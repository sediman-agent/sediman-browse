"""MemoryManager — orchestrator for builtin + optional external memory providers."""

from __future__ import annotations

from typing import Any

import structlog

from sediman.llm.provider import LLMProvider
from sediman.memory.providers import BuiltinMemoryProvider, MemoryProvider
from sediman.memory.store import MemoryStore

logger = structlog.get_logger()


class MemoryManager:
    def __init__(
        self,
        llm: LLMProvider | None = None,
        review_interval: int = 10,
    ) -> None:
        self._store = MemoryStore()
        self._builtin = BuiltinMemoryProvider(self._store)
        self._external: MemoryProvider | None = None
        self._llm = llm
        self._turn_count = 0
        self._review_interval = review_interval
        self._initialized = False

    # ── Lifecycle ────────────────────────────────────────────────

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self._builtin.initialize()
        if self._external:
            try:
                await self._external.initialize()
            except Exception as e:
                logger.warning("external_provider_init_failed", error=str(e))
        self._initialized = True

    # ── System prompt ────────────────────────────────────────────

    def get_snapshot(self) -> str:
        return self._store.snapshot or ""

    def get_system_prompt_block(self) -> str:
        return self._builtin.system_prompt_block()

    # ── Tool schemas ─────────────────────────────────────────────

    def get_tool_schemas(self) -> list[Any]:
        from sediman.llm.provider import ToolDefinition

        schemas: list[ToolDefinition] = self._builtin.get_tool_schemas()
        if self._external:
            try:
                schemas.extend(self._external.get_tool_schemas())
            except Exception:
                pass
        return schemas

    def has_tool(self, name: str) -> bool:
        return name == "memory"

    # ── Tool call routing ────────────────────────────────────────

    async def handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == "memory":
            return self._handle_memory_tool(arguments)
        return f"Unknown memory tool: {tool_name}"

    def _handle_memory_tool(self, arguments: dict[str, Any]) -> str:
        action = arguments.get("action", "")
        target = arguments.get("target", "memory")
        content = arguments.get("content", "")
        old_entry = arguments.get("old_entry", "")

        if action == "add":
            result = self._store.add(target, content)
        elif action == "replace":
            result = self._store.replace(target, old_entry, content)
        elif action == "remove":
            result = self._store.remove(target, old_entry)
        else:
            return f"Unknown memory action: {action}"

        lines = [result.message]
        if result.usage:
            lines.append(
                f"  {target.upper()} usage: {result.usage.formatted}, {len(result.usage.entries)} entries"
            )
            for i, entry in enumerate(result.usage.entries, 1):
                preview = entry[:80] + ("..." if len(entry) > 80 else "")
                lines.append(f"  {i}. {preview}")
        return "\n".join(lines)

    # ── Turn tracking + background review ────────────────────────

    async def on_turn_start(self) -> None:
        self._turn_count += 1

    def should_review(self) -> bool:
        return self._turn_count > 0 and self._turn_count % self._review_interval == 0

    async def run_background_review(self, conversation: list[dict[str, str]]) -> None:
        if not self._llm:
            return

        try:
            from sediman.agent.prompts.builder import _load_template
        except ImportError:
            return

        system_prompt = _load_template("memory_review.md")
        if not system_prompt:
            return

        recent = conversation[-20:]
        conv_parts = []
        for msg in recent:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")[:300]
            conv_parts.append(f"{role}: {content}")
        conv_text = "\n".join(conv_parts)

        usage = self._store.get_usage("memory")

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Conversation:\n{conv_text}\n\nMemory usage: {usage.formatted}"
                ),
            },
        ]

        tools = self._builtin.get_tool_schemas()
        try:
            response = await self._llm.chat(messages=messages, tools=tools)
            if response.tool_calls:
                for tc in response.tool_calls:
                    if tc.name == "memory":
                        result = self._handle_memory_tool(tc.arguments)
                        logger.info(
                            "review_memory_op",
                            action=tc.arguments.get("action"),
                            result=result[:100],
                        )
        except Exception as e:
            logger.debug("memory_review_failed", error=str(e))

    # ── Broadcast hooks ──────────────────────────────────────────

    async def on_session_end(self) -> None:
        for provider in [self._builtin, self._external]:
            if provider:
                try:
                    await provider.on_session_end()
                except Exception:
                    pass

    async def on_pre_compress(self) -> None:
        for provider in [self._builtin, self._external]:
            if provider:
                try:
                    await provider.on_pre_compress()
                except Exception:
                    pass

    async def on_memory_write(self, target: str, content: str) -> None:
        for provider in [self._builtin, self._external]:
            if provider:
                try:
                    await provider.on_memory_write(target, content)
                except Exception:
                    pass

    # ── External provider management ─────────────────────────────

    def register_external(self, provider: MemoryProvider) -> None:
        if self._external:
            logger.warning(
                "external_provider_already_set", current=self._external.name()
            )
            return
        self._external = provider

    # ── Direct store access for TUI/API ──────────────────────────

    def get_store(self) -> MemoryStore:
        return self._store
