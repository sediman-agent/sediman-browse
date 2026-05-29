from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.compressor import (
    ContextCompressor,
    COMPRESS_THRESHOLD,
    PROTECT_HEAD,
    _estimate_tokens,
    _prune_tool_results,
)


@pytest.fixture
def compressor():
    llm = MagicMock()
    return ContextCompressor(llm=llm)


class TestUtilityFunctions:
    def test_estimate_tokens(self):
        assert _estimate_tokens("hello world") > 0
        assert _estimate_tokens("") == 1

    def test_estimate_tokens_proportional(self):
        short = _estimate_tokens("a" * 100)
        long = _estimate_tokens("a" * 1000)
        assert long > short

    def test_prune_tool_results_short_messages_unchanged(self):
        msgs = [{"role": "tool", "content": "short"}]
        result = _prune_tool_results(msgs)
        assert result[0]["content"] == "short"

    def test_prune_tool_results_truncates_long_messages(self):
        lines = [f"this is a long line number {i} with extra padding for length" for i in range(20)]
        content = "\n".join(lines)
        msgs = [{"role": "tool", "content": content}]
        result = _prune_tool_results(msgs)
        assert "..." in result[0]["content"]
        assert "total lines" in result[0]["content"]

    def test_prune_tool_results_preserves_non_tool(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        result = _prune_tool_results(msgs)
        assert result == msgs


class TestContextCompressorShouldCompress:
    def test_false_when_below_threshold(self, compressor):
        messages = [{"role": "user", "content": "hi"}] * (COMPRESS_THRESHOLD - 1)
        assert compressor.should_compress(messages) is False

    def test_true_when_above_threshold(self, compressor):
        messages = [{"role": "user", "content": "hi"}] * (COMPRESS_THRESHOLD * 2 + 1)
        assert compressor.should_compress(messages) is True

    def test_false_when_empty(self, compressor):
        assert compressor.should_compress([]) is False

    def test_false_with_poor_history(self, compressor):
        compressor._compression_history = [5, 3]
        messages = [{"role": "user", "content": "hi"}] * (COMPRESS_THRESHOLD * 2 + 1)
        assert compressor.should_compress(messages) is False


class TestContextCompressorCompress:
    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_middle(self, compressor):
        messages = [{"role": "user", "content": "hi"}] * PROTECT_HEAD
        result = await compressor.compress(messages)
        assert result == messages

    @pytest.mark.asyncio
    async def test_compress_removes_middle_messages(self, compressor):
        count = 400
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Summary of middle messages"))
        result = await compressor.compress(messages)

        assert len(result) < len(messages)

    @pytest.mark.asyncio
    async def test_compress_includes_head(self, compressor):
        count = 400
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Summary"))
        result = await compressor.compress(messages)

        assert len(result) < len(messages)
        assert any("msg 0" in m["content"] for m in result[:PROTECT_HEAD])

    @pytest.mark.asyncio
    async def test_compress_summary_failure_falls_back_to_truncation(self, compressor):
        count = 250
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._llm.chat = AsyncMock(return_value=MagicMock(text=None))
        result = await compressor.compress(messages)

        assert len(result) <= COMPRESS_THRESHOLD * 2

    @pytest.mark.asyncio
    async def test_compress_summary_exception_falls_back(self, compressor):
        count = 250
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._llm.chat = AsyncMock(side_effect=Exception("API error"))
        result = await compressor.compress(messages)

        assert len(result) <= COMPRESS_THRESHOLD * 2

    @pytest.mark.asyncio
    async def test_compress_with_previous_summary(self, compressor):
        count = 400
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._previous_summary = "Previous summary here"
        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Updated summary"))
        result = await compressor.compress(messages)

        assert len(result) < len(messages)
        assert compressor._previous_summary == "Updated summary"

    @pytest.mark.asyncio
    async def test_compress_preserves_summary_context(self, compressor):
        count = 400
        messages = [{"role": "user", "content": f"msg {i} " + "x" * 200} for i in range(count)]

        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Summary text"))
        result = await compressor.compress(messages)

        summary_msg = next(m for m in result if m["role"] == "system")
        assert "Summary text" in summary_msg["content"]


class TestContextCompressorGenerateSummary:
    @pytest.mark.asyncio
    async def test_generate_summary_with_previous(self, compressor):
        compressor._previous_summary = "Old summary"
        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Updated summary"))

        result = await compressor._generate_summary([{"role": "user", "content": "new info"}])
        assert result == "Updated summary"

        call_args = compressor._llm.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args.kwargs.get("messages", [])
        user_content = messages[1]["content"]
        assert "Old summary" in user_content
        assert "new info" in user_content

    @pytest.mark.asyncio
    async def test_generate_summary_without_previous(self, compressor):
        compressor._llm.chat = AsyncMock(return_value=MagicMock(text="Fresh summary"))

        result = await compressor._generate_summary([{"role": "user", "content": "data"}])
        assert result == "Fresh summary"

    @pytest.mark.asyncio
    async def test_generate_summary_returns_none_on_failure(self, compressor):
        compressor._llm.chat = AsyncMock(side_effect=Exception("fail"))
        result = await compressor._generate_summary([{"role": "user", "content": "data"}])
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_summary_empty_response(self, compressor):
        compressor._llm.chat = AsyncMock(return_value=MagicMock(text=""))
        result = await compressor._generate_summary([{"role": "user", "content": "data"}])
        assert result is None
