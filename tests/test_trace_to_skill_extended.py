from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from sediman.agent.trace_to_skill import TraceToSkill
from sediman.agent.screen_recorder import ActionEvent, RecordedFrame, RecordingSession
from sediman.llm.provider import LLMResponse


def _make_session(
    frame_count: int = 5,
    name: str = "test-skill",
    description: str | None = None,
    with_actions: bool = True,
    with_dom: bool = False,
) -> RecordingSession:
    import base64

    session = RecordingSession(
        id="test123",
        name=name,
        started_at=time.monotonic() - 10.0,
        stopped_at=time.monotonic(),
        description=description,
    )
    for i in range(frame_count):
        dom = []
        if with_dom:
            dom = [
                {"tag": "INPUT", "type": "text", "name": "q", "placeholder": "Search"},
                {"tag": "BUTTON", "text": "Search", "id": "search-btn"},
            ]
        session.frames.append(
            RecordedFrame(
                timestamp=time.monotonic() - 10.0 + i,
                screenshot_b64=base64.b64encode(b"fake").decode(),
                cursor_x=100 + i * 10,
                cursor_y=200 + i * 10,
                url=f"https://example.com/step{i}",
                title=f"Page {i}",
                action="click" if i % 2 == 0 else None,
                action_detail=f"Click {i}" if i % 2 == 0 else "",
                dom_summary=dom,
            )
        )
    if with_actions:
        session.actions.append(ActionEvent(
            timestamp=1.0, action_type="navigate",
            detail="Navigate to https://google.com",
            url="https://google.com",
        ))
        session.actions.append(ActionEvent(
            timestamp=2.0, action_type="input",
            detail="Type 'python async' in search",
            url="https://google.com",
            text="python async",
        ))
        session.actions.append(ActionEvent(
            timestamp=3.0, action_type="click",
            detail="Click 'Search' button",
            url="https://google.com/search",
            text="Search",
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
    }
    data.update(overrides)
    return json.dumps(data)


class TestTraceToSkillSummarizeActions:
    def test_empty_actions(self):
        converter = TraceToSkill(MagicMock())
        result = converter._summarize_actions([])
        assert result == ""

    def test_actions_with_detail(self):
        converter = TraceToSkill(MagicMock())
        actions = [
            ActionEvent(timestamp=1.0, action_type="click", detail="Submit button"),
            ActionEvent(timestamp=2.0, action_type="input", detail="Type 'hello'", url="https://x.com"),
        ]
        result = converter._summarize_actions(actions)
        assert "click" in result
        assert "Submit button" in result
        assert "input" in result
        assert "Type 'hello'" in result
        assert "x.com" in result

    def test_action_without_detail_uses_type(self):
        converter = TraceToSkill(MagicMock())
        actions = [
            ActionEvent(timestamp=1.0, action_type="scroll", detail=""),
        ]
        result = converter._summarize_actions(actions)
        assert "scroll" in result

    def test_actions_truncated_at_30(self):
        converter = TraceToSkill(MagicMock())
        actions = [
            ActionEvent(timestamp=float(i), action_type="click", detail=f"action {i}")
            for i in range(50)
        ]
        result = converter._summarize_actions(actions)
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 30


class TestTraceToSkillFormatDomSummary:
    def test_empty_dom(self):
        converter = TraceToSkill(MagicMock())
        result = converter._format_dom_summary([])
        assert result == ""

    def test_basic_element(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "BUTTON", "text": "Submit"}]
        result = converter._format_dom_summary(dom)
        assert "BUTTON" in result
        assert "Submit" in result

    def test_element_with_id(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "DIV", "id": "main"}]
        result = converter._format_dom_summary(dom)
        assert "#main" in result

    def test_element_with_role(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "DIV", "role": "navigation"}]
        result = converter._format_dom_summary(dom)
        assert "[role=navigation]" in result

    def test_element_with_aria_label(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "SPAN", "aria-label": "Close"}]
        result = converter._format_dom_summary(dom)
        assert 'aria="Close"' in result

    def test_element_with_href(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "A", "href": "https://example.com"}]
        result = converter._format_dom_summary(dom)
        assert "→ https://example.com" in result

    def test_element_with_placeholder(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "INPUT", "placeholder": "Enter name"}]
        result = converter._format_dom_summary(dom)
        assert 'placeholder="Enter name"' in result

    def test_element_with_type(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "INPUT", "type": "email"}]
        result = converter._format_dom_summary(dom)
        assert "type=email" in result

    def test_truncated_at_20(self):
        converter = TraceToSkill(MagicMock())
        dom = [{"tag": "DIV", "text": f"item {i}"} for i in range(30)]
        result = converter._format_dom_summary(dom)
        lines = [line for line in result.strip().split("\n") if line.strip()]
        assert len(lines) == 20

    def test_all_attributes_combined(self):
        converter = TraceToSkill(MagicMock())
        dom = [{
            "tag": "INPUT",
            "text": "Email",
            "id": "email-field",
            "role": "textbox",
            "aria-label": "Email address",
            "placeholder": "you@example.com",
            "type": "email",
        }]
        result = converter._format_dom_summary(dom)
        assert "INPUT" in result
        assert "#email-field" in result
        assert "[role=textbox]" in result
        assert "type=email" in result


class TestTraceToSkillExtractVariables:
    @pytest.mark.asyncio
    async def test_no_learn_returns_unchanged(self):
        mock_llm = AsyncMock()
        converter = TraceToSkill(mock_llm)
        data = {"should_learn": False}
        result = await converter._extract_variables(
            RecordingSession(id="x", name="t", started_at=1.0),
            data,
        )
        assert result == {"should_learn": False}
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_actions_returns_data_without_variables(self):
        mock_llm = AsyncMock()
        converter = TraceToSkill(mock_llm)
        data = {"should_learn": True, "steps": ["step1", "step2"]}
        session = RecordingSession(id="x", name="t", started_at=1.0)
        result = await converter._extract_variables(session, data)
        assert "variables" not in result or result.get("variables") == []
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracts_variables_from_llm(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"variables": ["search_query", "target_url"]})
        )
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["step1", "step2", "step3"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == ["search_query", "target_url"]
        assert mock_llm.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_extracts_variables_in_code_block(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            '```json\n{"variables": ["query"]}\n```'
        )
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1", "s2"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == ["query"]

    @pytest.mark.asyncio
    async def test_extracts_variables_in_plain_code_block(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            '```\n{"variables": ["name"]}\n```'
        )
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1", "s2"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == ["name"]

    @pytest.mark.asyncio
    async def test_llm_returns_none_text(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(None)
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == []

    @pytest.mark.asyncio
    async def test_llm_raises_exception(self):
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM error")
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == []

    @pytest.mark.asyncio
    async def test_llm_returns_invalid_json(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response("not json at all")
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == []

    @pytest.mark.asyncio
    async def test_llm_returns_non_list_variables(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"variables": "not a list"})
        )
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == []

    @pytest.mark.asyncio
    async def test_preserves_existing_variables(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"variables": ["new_var"]})
        )
        converter = TraceToSkill(mock_llm)

        session = _make_session(with_actions=True)
        data = {"should_learn": True, "steps": ["s1"], "variables": ["old_var"]}
        result = await converter._extract_variables(session, data)

        assert result["variables"] == ["new_var"]


class TestTraceToSkillRefineSteps:
    @pytest.mark.asyncio
    async def test_too_few_steps_returns_unchanged(self):
        mock_llm = AsyncMock()
        converter = TraceToSkill(mock_llm)
        session = _make_session()
        data = {"steps": ["only", "two"]}
        result = await converter._refine_steps(session, data)
        assert result == data
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_refines_steps_from_llm(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"steps": ["Refined step 1", "Refined step 2", "Refined step 3"]})
        )
        converter = TraceToSkill(mock_llm)
        session = _make_session(with_dom=True)
        data = {"should_learn": True, "steps": ["Step 1", "Step 2", "Step 3"]}

        result = await converter._refine_steps(session, data)
        assert result["steps"] == ["Refined step 1", "Refined step 2", "Refined step 3"]

    @pytest.mark.asyncio
    async def test_refine_steps_in_code_block(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            '```json\n{"steps": ["A", "B", "C"]}\n```'
        )
        converter = TraceToSkill(mock_llm)
        session = _make_session(with_dom=True)
        data = {"steps": ["s1", "s2", "s3"]}

        result = await converter._refine_steps(session, data)
        assert result["steps"] == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_refine_llm_exception_returns_unchanged(self):
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM fail")
        converter = TraceToSkill(mock_llm)
        session = _make_session()
        original = ["s1", "s2", "s3"]
        data = {"steps": list(original)}

        result = await converter._refine_steps(session, data)
        assert result["steps"] == original

    @pytest.mark.asyncio
    async def test_refine_llm_invalid_json_returns_unchanged(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response("not json")
        converter = TraceToSkill(mock_llm)
        session = _make_session()
        original = ["s1", "s2", "s3"]
        data = {"steps": list(original)}

        result = await converter._refine_steps(session, data)
        assert result["steps"] == original

    @pytest.mark.asyncio
    async def test_refine_llm_too_few_steps_returns_unchanged(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"steps": ["only one"]})
        )
        converter = TraceToSkill(mock_llm)
        session = _make_session()
        original = ["s1", "s2", "s3"]
        data = {"steps": list(original)}

        result = await converter._refine_steps(session, data)
        assert result["steps"] == original

    @pytest.mark.asyncio
    async def test_refine_uses_session_description(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(
            json.dumps({"steps": ["A", "B", "C"]})
        )
        converter = TraceToSkill(mock_llm)
        session = _make_session(description="Search Google")
        data = {"steps": ["s1", "s2", "s3"]}

        await converter._refine_steps(session, data)

        call_args = mock_llm.chat.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][0]
        prompt = messages[1]["content"]
        assert "Search Google" in prompt


class TestTraceToSkillConvertMultiStep:
    @pytest.mark.asyncio
    async def test_convert_calls_extract_variables(self):
        call_count = [0]

        async def mock_chat(messages, tools):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_response(_valid_skill_json())
            if call_count[0] == 2:
                return _make_response(json.dumps({"variables": ["query"]}))
            if call_count[0] == 3:
                return _make_response(json.dumps({"steps": ["A", "B", "C"]}))
            return _make_response(_valid_skill_json())

        mock_llm = AsyncMock()
        mock_llm.chat = mock_chat

        converter = TraceToSkill(mock_llm)
        session = _make_session(10, with_actions=True, with_dom=True)

        result = await converter.convert(session)
        assert result is not None
        assert result.get("variables") == ["query"]
        assert result["steps"] == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_convert_with_dom_in_user_message(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = _make_response(_valid_skill_json())
        converter = TraceToSkill(mock_llm)

        session = _make_session(5, with_actions=True, with_dom=True)
        await converter.convert(session)

        first_call = mock_llm.chat.call_args_list[0]
        messages = first_call.kwargs.get("messages") or first_call[0][0]
        user_msg = messages[1]
        content = user_msg["content"]
        all_text = " ".join(p["text"] for p in content if p["type"] == "text")
        assert "DOM elements" in all_text
        assert "Search" in all_text


class TestTraceToSkillBuildUserMessageEnhanced:
    def test_includes_action_summary(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session(5, with_actions=True)
        msg = converter._build_user_message(session, session.frames[:3])
        header = msg["content"][0]["text"]
        assert "Action summary" in header
        assert "navigate" in header

    def test_dom_summary_per_frame(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session(3, with_dom=True)
        msg = converter._build_user_message(session, session.frames)
        all_text = " ".join(p["text"] for p in msg["content"] if p["type"] == "text")
        assert "DOM elements" in all_text
        assert "BUTTON" in all_text

    def test_no_dom_summary_when_empty(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session(3, with_dom=False)
        msg = converter._build_user_message(session, session.frames)
        all_text = " ".join(p["text"] for p in msg["content"] if p["type"] == "text")
        assert "DOM elements" not in all_text

    def test_end_marker_includes_variable_instructions(self):
        converter = TraceToSkill(MagicMock())
        session = _make_session(3)
        msg = converter._build_user_message(session, session.frames)
        last_text = [p for p in msg["content"] if p["type"] == "text"][-1]["text"]
        assert "variables" in last_text.lower()
        assert "verification" in last_text.lower()
        assert "when_to_use" in last_text.lower()
        assert "pitfalls" in last_text.lower()
