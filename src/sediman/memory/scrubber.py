"""StreamingContextScrubber — strips <memory-context> blocks from LLM output
to prevent provider context from leaking to the user."""

from __future__ import annotations

import re

_CONTEXT_TAG_RE = re.compile(
    r"<memory-context>.*?</memory-context>",
    re.DOTALL | re.IGNORECASE,
)


def scrub_memory_tags(text: str) -> str:
    return _CONTEXT_TAG_RE.sub("", text).strip()


class StreamingContextScrubber:
    def __init__(self) -> None:
        self._buffer = ""
        self._in_tag = False

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        result_parts: list[str] = []

        while self._buffer:
            if self._in_tag:
                close_idx = self._buffer.find("</memory-context>")
                if close_idx == -1:
                    self._buffer = ""
                    break
                self._buffer = self._buffer[close_idx + len("</memory-context>") :]
                self._in_tag = False
                continue

            open_idx = self._buffer.find("<memory-context>")
            if open_idx == -1:
                safe = self._buffer
                self._buffer = ""
                result_parts.append(safe)
            else:
                result_parts.append(self._buffer[:open_idx])
                self._buffer = self._buffer[open_idx:]
                self._in_tag = True

        return "".join(result_parts)

    def flush(self) -> str:
        remaining = self._buffer
        self._buffer = ""
        self._in_tag = False
        return remaining
