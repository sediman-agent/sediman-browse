from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.trace_to_skill import TraceToSkill
from sediman.agent.screen_recorder import RecordedFrame, RecordingSession
from sediman.llm.provider import LLMResponse


def _make_session_with_frames(
    count: int = 5,
    name: str = "test-skill",
    description: str | None = None,
) -> RecordingSession:
    import base64

    session = RecordingSession(
        id="test123",
        name=name,
        started_at=time.monotonic() - 5.0,
        stopped_at=time.monotonic(),
        description=description,
    )
    for i in range(count):
        session.frames.append(RecordedFrame(
            timestamp=time.monotonic() - 5.0 + i,
            screenshot_b64=base64.b64encode(b"fake").decode(),
            cursor_x=100 + i * 10,
            cursor_y=200 + i * 10,
            url=f"https://example.com/step{i}",
            title=f"Page {i}",
            action="click" if i % 2 == 0 else None,
            action_detail=f"Click {i}" if i % 2 == 0 else "",
        ))
    return session


def _make_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], done=True)


def _valid_skill_json(**overrides) -> str:
    data = {
        "should_learn": True,
        "skill_name": "test-skill",
        "description": "A test skill",
        "steps": ["Step 1", "Step 2", "Step 3"],
        "category": "general",
        "when_to_use": "When testing",
        "pitfalls": ["Watch out"],
        "verification": "It worked",
    }
    data.update(overrides)
    return json.dumps(data)


# ── convert() ──────────────────────────────────────────────────


class TestTraceToSkillConvert:
    @pytest.mark.asyncio
    async def test_too_few_frames_returns_none(self):
        mock_llm = AsyncMock()
        converter = TraceToSkill(mock_llm)

        session = RecordingSession(id="x", name="short")
        session.frames.append(RecordedFrame(
            timestamp=1.0, screenshot_b64="abc",
            cursor_x=0, cursor_y=0, url="http://x",
        ))

        result = await converter.convert(session)
        assert result is None
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_frames_returns_none(self):
        mock_llm = AsyncMock()
        converter = TraceToSkill(mock_llm)
        session = RecordingSession(id="x", name="empty")
        result = await converter.convert(session)
        assert result is None

    @pytest.mark.asyncio
    async def test_success(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(10)

        result = await converter.convert(session)
        assert result is not None
        assert result["skill_name"] == "test-skill"
        assert len(result["steps"]) == 3
        assert result["category"] == "general"
        assert result["when_to_use"] == "When testing"
        assert result["pitfalls"] == ["Watch out"]
        assert result["verification"] == "It worked"

    @pytest.mark.asyncio
    async def test_with_description(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5, description="Post to Medium")

        await converter.convert(session)

        call_args = mock_llm.chat.call_args_list[0]
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_msg = messages[1]
        content = user_msg["content"]
        header_text = content[0]["text"]
        assert "Post to Medium" in header_text

    @pytest.mark.asyncio
    async def test_should_not_learn(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"should_learn": False, "reason": "too simple"})
        )

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        result = await converter.convert(session)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_returns_none_text(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(None)

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        result = await converter.convert(session)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_returns_empty_text(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response("")

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        result = await converter.convert(session)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_exception(self):
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM error")

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        result = await converter.convert(session)
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_correct_message_structure(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        await converter.convert(session)

        call_args = mock_llm.chat.call_args_list[0]
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        user_content = messages[1]["content"]
        assert isinstance(user_content, list)
        text_parts = [p for p in user_content if p["type"] == "text"]
        image_parts = [p for p in user_content if p["type"] == "image_url"]
        assert len(text_parts) >= 3
        assert len(image_parts) >= 3

    @pytest.mark.asyncio
    async def test_max_frames_respected(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(50)

        await converter.convert(session, max_frames=5)

        call_args = mock_llm.chat.call_args_list[0]
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        user_content = messages[1]["content"]
        image_parts = [p for p in user_content if p["type"] == "image_url"]
        assert len(image_parts) <= 5

    @pytest.mark.asyncio
    async def test_tools_passed_as_empty(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())

        converter = TraceToSkill(mock_llm)
        session = _make_session_with_frames(5)

        await converter.convert(session)

        call_args = mock_llm.chat.call_args_list[0]
        tools = call_args.kwargs.get("tools")
        assert tools == []


# ── _parse_response() ──────────────────────────────────────────


class TestTraceToSkillParseResponse:
    def test_valid_json(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({
            "should_learn": True,
            "skill_name": "x",
            "description": "d",
            "steps": ["a", "b"],
        })
        result = converter._parse_response(text)
        assert result is not None
        assert result["skill_name"] == "x"
        assert result["steps"] == ["a", "b"]

    def test_json_in_code_block(self):
        converter = TraceToSkill(MagicMock())
        text = '```json\n{"should_learn": true, "skill_name": "x", "description": "d", "steps": ["a", "b"]}\n```'
        result = converter._parse_response(text)
        assert result is not None
        assert result["skill_name"] == "x"

    def test_json_in_plain_code_block(self):
        converter = TraceToSkill(MagicMock())
        text = '```\n{"should_learn": true, "skill_name": "x", "description": "d", "steps": ["a", "b"]}\n```'
        result = converter._parse_response(text)
        assert result is not None

    def test_json_embedded_in_text(self):
        converter = TraceToSkill(MagicMock())
        text = 'Here is my evaluation:\n{"should_learn": true, "skill_name": "x", "description": "d", "steps": ["a", "b"]}\nEnd.'
        result = converter._parse_response(text)
        assert result is not None
        assert result["skill_name"] == "x"

    def test_should_learn_false(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": False, "reason": "too simple"})
        result = converter._parse_response(text)
        assert result is None

    def test_missing_skill_name(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": True, "description": "d", "steps": ["a", "b"]})
        result = converter._parse_response(text)
        assert result is None

    def test_missing_description(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": True, "skill_name": "x", "steps": ["a", "b"]})
        result = converter._parse_response(text)
        assert result is None

    def test_missing_steps(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": True, "skill_name": "x", "description": "d"})
        result = converter._parse_response(text)
        assert result is None

    def test_steps_not_list(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": True, "skill_name": "x", "description": "d", "steps": "not a list"})
        result = converter._parse_response(text)
        assert result is None

    def test_too_few_steps(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({"should_learn": True, "skill_name": "x", "description": "d", "steps": ["only one"]})
        result = converter._parse_response(text)
        assert result is None

    def test_invalid_json(self):
        converter = TraceToSkill(MagicMock())
        result = converter._parse_response("not json at all")
        assert result is None

    def test_json_array_instead_of_object(self):
        converter = TraceToSkill(MagicMock())
        result = converter._parse_response('[{"should_learn": true}]')
        assert result is None

    def test_empty_string(self):
        converter = TraceToSkill(MagicMock())
        result = converter._parse_response("")
        assert result is None

    def test_code_block_with_no_json_inside(self):
        converter = TraceToSkill(MagicMock())
        result = converter._parse_response("```json\nnot json\n```")
        assert result is None

    def test_whitespace_handling(self):
        converter = TraceToSkill(MagicMock())
        text = '  \n  {"should_learn": true, "skill_name": "x", "description": "d", "steps": ["a", "b"]}  \n  '
        result = converter._parse_response(text)
        assert result is not None

    def test_preserves_extra_fields(self):
        converter = TraceToSkill(MagicMock())
        text = json.dumps({
            "should_learn": True,
            "skill_name": "x",
            "description": "d",
            "steps": ["a", "b"],
            "urls_used": ["https://example.com"],
            "elements_interacted": ["button"],
            "category": "social",
        })
        result = converter._parse_response(text)
        assert result is not None
        assert result["urls_used"] == ["https://example.com"]
        assert result["category"] == "social"


# ── _build_user_message() ──────────────────────────────────────


class TestTraceToSkillBuildUserMessage:
    def test_includes_session_metadata(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session_with_frames(5, name="post-medium", description="Post article")

        msg = converter._build_user_message(session, session.frames[:3])
        assert msg["role"] == "user"

        content = msg["content"]
        header = content[0]["text"]
        assert "post-medium" in header
        assert "Post article" in header
        assert "Duration:" in header
        assert "Total frames captured: 5" in header

    def test_includes_frame_data(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session_with_frames(5)
        key = session.frames[:3]

        msg = converter._build_user_message(session, key)
        content = msg["content"]
        all_text = " ".join(p["text"] for p in content if p["type"] == "text")
        assert "[Frame 1]" in all_text
        assert "[Frame 3]" in all_text
        assert "Cursor position:" in all_text

    def test_includes_images(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session_with_frames(5)
        key = session.frames[:3]

        msg = converter._build_user_message(session, key)
        content = msg["content"]
        images = [p for p in content if p["type"] == "image_url"]
        assert len(images) == 3
        for img in images:
            assert img["image_url"]["url"].startswith("data:image/jpeg;base64,")
            assert img["image_url"]["detail"] == "low"

    def test_includes_end_marker(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session_with_frames(3)
        key = session.frames

        msg = converter._build_user_message(session, key)
        content = msg["content"]
        last_text = [p for p in content if p["type"] == "text"][-1]["text"]
        assert "End of Recording" in last_text

    def test_frame_without_cursor_no_cursor_text(self):
        converter = TraceToSkill(MagicMock())
        session = RecordingSession(
            id="x", name="t",
            started_at=time.monotonic() - 1.0,
            stopped_at=time.monotonic(),
        )
        session.frames.append(RecordedFrame(
            timestamp=time.monotonic(), screenshot_b64="abc",
            cursor_x=0, cursor_y=0, url="http://x", action=None,
        ))

        msg = converter._build_user_message(session, session.frames)
        all_text = " ".join(p["text"] for p in msg["content"] if p["type"] == "text")
        assert "Cursor position" not in all_text

    def test_frame_without_action_no_action_text(self):
        converter = TraceToSkill(MagicMock())
        session = RecordingSession(
            id="x", name="t",
            started_at=time.monotonic() - 1.0,
            stopped_at=time.monotonic(),
        )
        session.frames.append(RecordedFrame(
            timestamp=time.monotonic(), screenshot_b64="abc",
            cursor_x=50, cursor_y=50, url="http://x", action=None,
        ))

        msg = converter._build_user_message(session, session.frames)
        all_text = " ".join(p["text"] for p in msg["content"] if p["type"] == "text")
        assert "Action:" not in all_text

    def test_frame_with_action_includes_action(self):
        converter = TraceToSkill(MagicMock())
        session = RecordingSession(
            id="x", name="t",
            started_at=time.monotonic() - 1.0,
            stopped_at=time.monotonic(),
        )
        session.frames.append(RecordedFrame(
            timestamp=time.monotonic(), screenshot_b64="abc",
            cursor_x=0, cursor_y=0, url="http://x",
            action="click", action_detail="clicked submit",
        ))

        msg = converter._build_user_message(session, session.frames)
        all_text = " ".join(p["text"] for p in msg["content"] if p["type"] == "text")
        assert "Action: click" in all_text
        assert "clicked submit" in all_text
