from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.llm.provider import LLMResponse
from sediman.skills.healer import heal_skill, verify_skill, _safe_read_screenshot, _truncate_dom


class TestSafeReadScreenshot:
    def test_returns_none_for_none_path(self):
        assert _safe_read_screenshot(None) is None

    def test_returns_none_for_missing_file(self):
        assert _safe_read_screenshot("/nonexistent/path.png") is None

    def test_returns_b64_for_valid_file(self, tmp_path):
        png = tmp_path / "test.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = _safe_read_screenshot(str(png))
        assert result is not None
        assert isinstance(result, str)

    def test_skips_large_file(self, tmp_path):
        large = tmp_path / "large.png"
        large.write_bytes(b"\x00" * (6 * 1024 * 1024))
        assert _safe_read_screenshot(str(large)) is None


class TestTruncateDom:
    def test_returns_none_for_none(self):
        assert _truncate_dom(None) is None

    def test_short_dom_passes_through(self):
        dom = "<html><body>short</body></html>"
        assert _truncate_dom(dom) == dom

    def test_long_dom_truncated(self):
        dom = "x" * 5000
        result = _truncate_dom(dom, max_chars=100)
        assert result is not None
        assert len(result) == 100

    def test_empty_string(self):
        assert _truncate_dom("") == ""


class TestHealSkillWithScreenshot:
    @pytest.mark.asyncio
    async def test_passes_screenshot_path(self, tmp_sediman_dir):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "ss-skill", "steps": ["old step"], "version": 1}

        llm.chat = AsyncMock(
            return_value=LLMResponse(
                text=json.dumps({"steps": ["new step"], "reasoning": "fixed"})
            )
        )

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="ss-skill", description="test", steps=["old step"])

            result = await heal_skill(
                skill, "error", browser, llm, engine=engine,
                screenshot_path="/tmp/fake.png",
            )

        assert result is not None
        assert result["steps"] == ["new step"]

    @pytest.mark.asyncio
    async def test_passes_dom_snapshot(self, tmp_sediman_dir):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "dom-skill", "steps": ["old"], "version": 1}

        llm.chat = AsyncMock(
            return_value=LLMResponse(
                text=json.dumps({"steps": ["new"], "reasoning": "dom used"})
            )
        )

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="dom-skill", description="test", steps=["old"])

            result = await heal_skill(
                skill, "error", browser, llm, engine=engine,
                dom_snapshot="<html><body><button>Click</button></body></html>",
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_includes_dom_in_prompt(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "check-dom", "steps": ["old"]}

        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        await heal_skill(
            skill, "error", browser, llm,
            dom_snapshot="<button id='submit'>Submit</button>",
        )

        call_args = llm.chat.call_args
        messages = (
            call_args.kwargs.get("messages")
            or call_args[1].get("messages")
            or call_args[0][0]
        )
        all_text = " ".join(
            m["content"] if isinstance(m["content"], str) else str(m["content"])
            for m in messages
        )
        assert "DOM snapshot" in all_text

    @pytest.mark.asyncio
    async def test_screenshot_included_as_image(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "img-test", "steps": ["old"]}

        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        png_path = Path("/tmp/test_healer_img.png")
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        try:
            with patch("sediman.skills.healer._safe_read_screenshot", return_value="fakebase64=="):
                await heal_skill(
                    skill, "error", browser, llm,
                    screenshot_path=str(png_path),
                )

            call_args = llm.chat.call_args
            messages = (
                call_args.kwargs.get("messages")
                or call_args[1].get("messages")
                or call_args[0][0]
            )
            contents = messages[-1].get("content", [])
            has_image = any(
                isinstance(c, dict) and c.get("type") == "image_url"
                for c in (contents if isinstance(contents, list) else [])
            )
            assert has_image
        finally:
            png_path.unlink(missing_ok=True)


class TestVerifySkill:
    @pytest.mark.asyncio
    async def test_verify_passed(self):
        llm = MagicMock()
        llm.chat = AsyncMock(
            return_value=LLMResponse(text='{"passed": true, "fail_reason": ""}')
        )
        result = await verify_skill(
            "test-skill",
            {"name": "test-skill", "description": "test"},
            "verify it works",
            llm,
        )
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_verify_failed(self):
        llm = MagicMock()
        llm.chat = AsyncMock(
            return_value=LLMResponse(text='{"passed": false, "fail_reason": "element not found"}')
        )
        result = await verify_skill(
            "test-skill",
            {"name": "test-skill", "description": "test"},
            "verify it works",
            llm,
        )
        assert result["passed"] is False
        assert "not found" in result["fail_reason"]

    @pytest.mark.asyncio
    async def test_verify_no_response(self):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(text=None))
        result = await verify_skill(
            "test-skill",
            {"name": "test-skill", "description": "test"},
            "verify it works",
            llm,
        )
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_verify_with_screenshot_path(self):
        llm = MagicMock()
        llm.chat = AsyncMock(
            return_value=LLMResponse(text='{"passed": true, "fail_reason": ""}')
        )
        with patch("sediman.skills.healer._safe_read_screenshot", return_value="fakebase64=="):
            result = await verify_skill(
                "test-skill",
                {"name": "test-skill"},
                "verify it works",
                llm,
                screenshot_path="/tmp/screen.png",
            )
        assert result["passed"] is True

    @pytest.mark.asyncio
    async def test_verify_with_dom_snapshot(self):
        llm = MagicMock()
        llm.chat = AsyncMock(
            return_value=LLMResponse(text='{"passed": true, "fail_reason": ""}')
        )
        result = await verify_skill(
            "test-skill",
            {"name": "test-skill"},
            "verify it works",
            llm,
            dom_snapshot="<html><body>ok</body></html>",
        )
        assert result["passed"] is True
