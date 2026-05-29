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
        self._vector_store = None

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

    def get_system_prompt_for_task(self, task: str, max_chars: int = 1500) -> str:
        if not self._initialized:
            self._store.load_snapshot()
        return self._store.format_for_system_prompt_filtered(task, max_chars=max_chars)

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
        import asyncio
        if tool_name == "memory":
            return await asyncio.to_thread(self._handle_memory_tool, arguments)
        return f"Unknown memory tool: {tool_name}"

    def _handle_memory_tool(self, arguments: dict[str, Any]) -> str:
        action = arguments.get("action", "")
        target = arguments.get("target", "memory")
        content = arguments.get("content", "")
        old_entry = arguments.get("old_entry", "")

        if action == "add":
            result = self._store.add_or_consolidate(target, content)
            if result.success:
                self._store.refresh_snapshot()
                self._index_entry(content, target)
        elif action == "replace":
            result = self._store.replace(target, old_entry, content)
            if result.success:
                self._store.refresh_snapshot()
                self._unindex_entry(old_entry)
                self._index_entry(content, target)
        elif action == "remove":
            result = self._store.remove(target, old_entry)
            if result.success:
                self._store.refresh_snapshot()
                self._unindex_entry(old_entry)
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
        all_entries = self._store.get_all_entries()
        mem_entries = all_entries.get("memory", [])
        user_entries = all_entries.get("user", [])

        entries_text = "MEMORY entries:\n"
        for i, e in enumerate(mem_entries):
            meta = self._get_entry_meta(e)
            type_tag = f" [{meta.type}]" if meta else ""
            access_tag = f" (accessed {meta.access_count}x)" if meta else ""
            entries_text += f"  [{i}]{type_tag}{access_tag} {e}\n"
        if user_entries:
            entries_text += "USER entries:\n"
            for i, e in enumerate(user_entries):
                entries_text += f"  [U{i}] {e}\n"

        review_prompt = (
            f"{system_prompt}\n\n"
            f"Conversation:\n{conv_text}\n\n"
            f"Memory usage: {usage.formatted}\n"
            f"{entries_text}\n"
            'Respond with JSON: {"changes": [{"action": "add"|"replace"|"remove", '
            '"target": "memory"|"user", "content": "...", "old_entry": "...", '
            '"reason": "...", "type": "fact"|"preference"|"procedure"|"episodic"}]}\n'
            "Only include changes that improve memory. "
            "Look for: contradictions with new info, outdated entries, missing preferences, "
            "redundant entries that should be merged.\n"
            "Omit the changes field if nothing to do."
        )

        messages = [
            {"role": "user", "content": review_prompt},
        ]

        try:
            response = await self._llm.chat(messages=messages, tools=[])
            text = (response.text or "").strip()
            if not text:
                return

            changes = self._parse_review_changes(text)
            if not changes:
                return

            applied = 0
            for change in changes:
                action = change.get("action", "")
                target = change.get("target", "memory")
                content_val = change.get("content", "")
                old_entry_val = change.get("old_entry", "")
                reason = change.get("reason", "background_review")

                if action == "add" and content_val:
                    if self._check_for_contradiction(target, content_val):
                        logger.info(
                            "review_skip_contradiction",
                            content=content_val[:60],
                        )
                        continue
                    result = self._store.add_or_consolidate(target, content_val)
                    if result.success:
                        applied += 1
                        self._index_entry(content_val, target)
                elif action == "replace" and content_val and old_entry_val:
                    result = self._store.replace(target, old_entry_val, content_val)
                    if result.success:
                        applied += 1
                        self._unindex_entry(old_entry_val)
                        self._index_entry(content_val, target)
                elif action == "remove" and old_entry_val:
                    result = self._store.remove(target, old_entry_val, reason=reason)
                    if result.success:
                        applied += 1
                        self._unindex_entry(old_entry_val)

            if applied > 0:
                self._store.refresh_snapshot()
                logger.info("memory_review_applied", changes=applied)

        except Exception as e:
            logger.debug("memory_review_failed", error=str(e))

    def _check_for_contradiction(self, target: str, new_content: str) -> bool:
        entries = self._store.get_all_entries().get(target, [])
        new_lower = new_content.lower().strip()

        negation_pairs = [
            ("always", "never"), ("like", "hate"), ("prefer", "avoid"),
            ("use", "don't use"), ("want", "don't want"),
        ]
        for entry in entries:
            entry_lower = entry.lower().strip()
            if new_lower == entry_lower:
                return True
            for w1, w2 in negation_pairs:
                if w1 in entry_lower and w2 in new_lower:
                    if self._text_similarity(entry_lower, new_lower) > 0.5:
                        return True
                if w2 in entry_lower and w1 in new_lower:
                    if self._text_similarity(entry_lower, new_lower) > 0.5:
                        return True
        return False

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / max(len(words_a | words_b), 1)

    def _get_entry_meta(self, content: str) -> Any:
        try:
            from sediman.memory.entry import MemoryEntryMeta, load_entry_meta
            entry_id = MemoryEntryMeta.make_id(content)
            return load_entry_meta(entry_id)
        except Exception:
            return None

    def _parse_review_changes(self, text: str) -> list[dict[str, str]]:
        import json as _json

        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]

        try:
            data = _json.loads(text)
        except _json.JSONDecodeError:
            return []

        changes = data.get("changes")
        if not isinstance(changes, list):
            return []

        valid = []
        for c in changes:
            if not isinstance(c, dict):
                continue
            if c.get("action") in ("add", "replace", "remove"):
                valid.append(c)

        return valid[:5]

    async def on_session_end(self) -> None:
        for provider in [self._builtin, self._external]:
            if provider:
                try:
                    await provider.on_session_end()
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

    async def get_preference_context(self) -> str | None:
        try:
            from sediman.memory.preferences import PreferenceLearner
            learner = PreferenceLearner()
            summary = await learner.get_preference_summary()
            high = summary.get("highly_rated", [])
            low = summary.get("low_rated", [])
            if not high and not low:
                return None
            parts: list[str] = []
            if high:
                names = [s["skill_name"] for s in high[:5]]
                parts.append(f"Highly rated skills (prefer): {', '.join(names)}")
            if low:
                names = [s["skill_name"] for s in low[:5]]
                parts.append(f"Low rated skills (avoid): {', '.join(names)}")
            return "; ".join(parts)
        except Exception as e:
            logger.debug("preference_context_failed", error=str(e))
            return None

    async def get_trajectory_context(self, task: str, limit: int = 3) -> str | None:
        try:
            from sediman.memory.trajectories import TrajectoryDB
            db = TrajectoryDB()
            similar = await db.query_similar_tasks(task, limit=limit, min_success_rate=0.5)
            if not similar:
                return None
            parts: list[str] = []
            for t in similar[:limit]:
                if t.success and t.result:
                    parts.append(
                        f"- Similar task '{t.task[:60]}': {t.result[:150]}"
                    )
            if not parts:
                return None
            return "\n".join(parts)
        except Exception as e:
            logger.debug("trajectory_context_failed", error=str(e))
            return None

    def get_relevant_context(self, query: str, limit: int = 5) -> list[str]:
        try:
            vs = self._get_vector_store()
            results = vs.search(query, k=limit, threshold=0.2)
            matched = [r["text"] for r in results if r.get("text")]
            if matched:
                self._record_access_for_matched(matched)
                return matched
        except Exception as e:
            logger.debug("vector_relevant_context_failed", error=str(e))

        all_entries = self._store.get_all_entries().get("memory", [])
        query_lower = query.lower()
        scored = []
        for entry in all_entries:
            content_lower = entry.lower()
            score = sum(1 for word in query_lower.split() if word in content_lower)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: -x[0])
        matched = [s[1] for s in scored[:limit]]
        self._record_access_for_matched(matched)
        return matched

    def _record_access_for_matched(self, entries: list[str]) -> None:
        for entry in entries:
            try:
                self._store.record_access(entry)
            except Exception:
                pass

    def _index_entry(self, content: str, target: str) -> None:
        try:
            vs = self._get_vector_store()
            vs.add(content, metadata={"target": target, "source": "memory"})
        except Exception as e:
            logger.debug("memory_index_failed", error=str(e))

    async def _async_index_entry(self, content: str, target: str) -> None:
        try:
            vs = self._get_vector_store()
            await vs.async_add(content, metadata={"target": target, "source": "memory"})
        except Exception as e:
            logger.debug("memory_index_failed", error=str(e))

    def _unindex_entry(self, content: str) -> None:
        try:
            vs = self._get_vector_store()
            vs.remove(content)
        except Exception as e:
            logger.debug("memory_unindex_failed", error=str(e))

    async def _async_get_relevant_context(self, query: str, limit: int = 5) -> list[str]:
        try:
            vs = self._get_vector_store()
            results = await vs.async_search(query, k=limit, threshold=0.2)
            matched = [r["text"] for r in results if r.get("text")]
            if matched:
                self._record_access_for_matched(matched)
                return matched
        except Exception as e:
            logger.debug("vector_relevant_context_failed", error=str(e))
            return self.get_relevant_context(query, limit=limit)

    def _get_vector_store(self):
        from sediman.memory.vector import VectorStore
        if self._vector_store is None:
            self._vector_store = VectorStore()
        return self._vector_store

    def load_all_memory(self) -> str:
        all_entries = self._store.get_all_entries()
        parts = []
        mem = all_entries.get("memory", [])
        user = all_entries.get("user", [])
        if mem:
            parts.append("\n".join(mem))
        if user:
            parts.append("\n".join(user))
        return "\n\n".join(parts)

    def get_memory_size(self) -> int:
        return self._store.get_usage("memory").chars

    def get_store(self) -> MemoryStore:
        return self._store
