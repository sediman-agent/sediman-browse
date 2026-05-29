from __future__ import annotations

from typing import Any

import structlog

from sediman.agent.prompts.builder import _load_template

logger = structlog.get_logger()

COMPRESS_THRESHOLD = 20
PROTECT_TAIL_TOKENS = 8000
PROTECT_HEAD = 2
_MIN_COMPRESSION_SAVING_PCT = 10


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _prune_tool_results(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    pruned = []
    for msg in messages:
        content = msg.get("content", "")
        role = msg.get("role", "")
        if role == "tool" and len(content) > 200:
            lines = content.split("\n")
            if len(lines) > 5:
                summary_lines = lines[:3]
                tail_preview = lines[-1][:80] if lines else ""
                summary = "\n".join(summary_lines)
                summary += f"\n... ({len(lines)} total lines, {len(content)} chars)"
                if tail_preview:
                    summary += f"\n{tail_preview}"
                pruned.append({**msg, "content": summary})
                continue
        pruned.append(msg)
    return pruned


class ContextCompressor:
    def __init__(self, llm: Any):
        self._llm = llm
        self._previous_summary: str | None = None
        self._compression_history: list[float] = []

    def should_compress(self, messages: list[dict[str, str]]) -> bool:
        if len(messages) < COMPRESS_THRESHOLD * 2:
            return False
        if len(self._compression_history) >= 2:
            last_two = self._compression_history[-2:]
            if all(s < _MIN_COMPRESSION_SAVING_PCT for s in last_two):
                return False
        return True

    async def compress(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        messages = _prune_tool_results(messages)

        head = messages[:PROTECT_HEAD]

        tail_cutoff = len(messages)
        token_budget = 0
        for i in range(len(messages) - 1, -1, -1):
            token_budget += _estimate_tokens(messages[i].get("content", ""))
            if token_budget >= PROTECT_TAIL_TOKENS:
                tail_cutoff = i
                break
        tail_cutoff = max(tail_cutoff, PROTECT_HEAD)

        tail = messages[tail_cutoff:]
        middle = messages[PROTECT_HEAD:tail_cutoff]

        if not middle:
            return messages

        summary_text = await self._generate_summary(middle)
        if summary_text is None:
            cut = messages[-(COMPRESS_THRESHOLD * 2):]
            saving = (1 - len(cut) / len(messages)) * 100
            self._compression_history.append(saving)
            logger.info("context_compressed_no_summary", removed=len(middle), kept=len(cut))
            return cut

        summary_msg = {
            "role": "system",
            "content": f"[CONTEXT COMPACTION] Earlier conversation was summarized:\n\n{summary_text}",
        }

        self._previous_summary = summary_text
        compressed = head + [summary_msg] + tail
        saving = (1 - len(compressed) / len(messages)) * 100
        self._compression_history.append(saving)
        logger.info(
            "context_compressed",
            before=len(messages),
            after=len(compressed),
            middle_removed=len(middle),
            saving_pct=f"{saving:.1f}%",
        )
        return compressed

    async def _generate_summary(self, messages: list[dict[str, str]]) -> str | None:
        from sediman.utils import format_conversation_context

        conversation_text = format_conversation_context(
            messages, limit=len(messages), max_chars=500
        )
        system_prompt = _load_template("compression.md")

        if self._previous_summary:
            user_prompt = (
                "Update the following summary with new information from the conversation below. "
                "Keep the same format. Add new progress, update in-progress items, remove completed items.\n\n"
                f"Previous summary:\n{self._previous_summary}\n\n"
                f"New conversation:\n{conversation_text}"
            )
        else:
            user_prompt = f"Conversation to summarize:\n\n{conversation_text}"

        try:
            response = await self._llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[],
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            logger.debug("compression_summary_failed", error=str(e))

        return None
