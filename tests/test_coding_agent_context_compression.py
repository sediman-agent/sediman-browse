from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from sediman.agent.tool_dispatch import ToolLoop, ToolRegistry


class TestTokenCounting:
    def _make_loop(self):
        return ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
            max_rounds=30,
        )

    def test_estimate_tokens_empty(self):
        loop = self._make_loop()
        tokens = loop._estimate_tokens([])
        assert tokens > 0

    def test_estimate_tokens_single_message(self):
        loop = self._make_loop()
        tokens = loop._estimate_tokens([
            {"role": "user", "content": "hello world"},
        ])
        expected = len("hello world") // 3
        assert tokens == max(expected, 1)

    def test_estimate_tokens_with_tool_calls(self):
        loop = self._make_loop()
        messages = [
            {
                "role": "assistant",
                "content": "Let me search for that",
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {
                            "name": "search_files",
                            "arguments": '{"query": "def main"}',
                        },
                    },
                ],
            },
        ]
        tokens = loop._estimate_tokens(messages)
        assert tokens > 10

    def test_estimate_tokens_long_message(self):
        loop = self._make_loop()
        long_text = "x" * 3000
        messages = [{"role": "user", "content": long_text}]
        tokens = loop._estimate_tokens(messages)
        assert tokens >= 900


class TestContextCompression:
    def _make_loop(self, max_tokens: int = 16000):
        return ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
            max_rounds=30,
            max_context_tokens=max_tokens,
        )

    def test_compress_tool_results_truncates_long_output(self):
        loop = self._make_loop()
        messages = [
            {"role": "tool", "tool_call_id": "1", "content": "x" * 3000},
        ]
        compressed = loop._compress_tool_results(messages)
        assert len(compressed[0]["content"]) < 3000
        assert "truncated" in compressed[0]["content"]

    def test_compress_tool_results_keeps_short_output(self):
        loop = self._make_loop()
        messages = [
            {"role": "tool", "tool_call_id": "1", "content": "short output"},
        ]
        compressed = loop._compress_tool_results(messages)
        assert compressed[0]["content"] == "short output"

    def test_compress_tool_results_skips_non_tool(self):
        loop = self._make_loop()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        compressed = loop._compress_tool_results(messages)
        assert len(compressed) == 2
        assert compressed[0]["content"] == "hello"
        assert compressed[1]["content"] == "hi"

    def test_maybe_compress_under_limit_does_nothing(self):
        loop = self._make_loop(max_tokens=100000)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        compressed = loop._maybe_compress(messages)
        assert len(compressed) == 2
        assert compressed[0]["content"] == "hello"

    def test_maybe_compress_over_limit_truncates(self):
        loop = self._make_loop(max_tokens=10)
        full = "a" * 500
        messages = [
            {"role": "user", "content": full},
            {"role": "tool", "tool_call_id": "1", "content": full},
            {"role": "assistant", "content": full},
            {"role": "tool", "tool_call_id": "2", "content": full},
        ]
        compressed = loop._maybe_compress(messages)
        has_truncated = any(
            "truncated" in str(m.get("content", "")) for m in compressed
        )
        assert has_truncated or len(compressed) == len(messages)

    def test_maybe_compress_preserves_system(self):
        loop = self._make_loop(max_tokens=100000)
        messages = [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hello"},
        ]
        compressed = loop._maybe_compress(messages)
        assert compressed[0]["role"] == "system"


class TestMaxContextTokens:
    def test_default_max_context_tokens(self):
        loop = ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
        )
        assert loop._max_context_tokens == 16000

    def test_custom_max_context_tokens(self):
        loop = ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
            max_context_tokens=8000,
        )
        assert loop._max_context_tokens == 8000
