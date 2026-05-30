from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.healer import heal_skill
from sediman.llm.provider import LLMResponse


class TestHealSkill:
    @pytest.mark.asyncio
    async def test_patches_skill_with_new_steps(self, tmp_sediman_dir):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "broken-skill", "steps": ["old step"], "version": 1}

        llm.chat = AsyncMock(return_value=LLMResponse(
            text=json.dumps({"steps": ["new step 1", "new step 2"], "reason": "page changed"})
        ))

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="broken-skill", description="test", steps=["old step"])

            result = await heal_skill(skill, "error context", browser, llm)

        assert result is not None
        assert result["version"] == 2
        assert result["steps"] == ["new step 1", "new step 2"]

    @pytest.mark.asyncio
    async def test_returns_none_when_no_response(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["s"]}

        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        result = await heal_skill(skill, "error", browser, llm)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_unfixable(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["s"]}

        llm.chat = AsyncMock(return_value=LLMResponse(
            text=json.dumps({"error": "site no longer exists"})
        ))

        result = await heal_skill(skill, "error", browser, llm)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_empty_steps(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["s"]}

        llm.chat = AsyncMock(return_value=LLMResponse(
            text=json.dumps({"steps": [], "reason": "no steps needed"})
        ))

        result = await heal_skill(skill, "error", browser, llm)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_json_in_code_blocks(self, tmp_sediman_dir):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "code-block-skill", "steps": ["old"], "version": 1}

        response_with_code_block = """Here are the updated steps:

```json
{"steps": ["updated step"], "reason": "layout changed"}
```
"""
        llm.chat = AsyncMock(return_value=LLMResponse(text=response_with_code_block))

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="code-block-skill", description="test", steps=["old"])

            result = await heal_skill(skill, "error", browser, llm)

        assert result is not None
        assert result["steps"] == ["updated step"]

    @pytest.mark.asyncio
    async def test_handles_plain_code_blocks(self, tmp_sediman_dir):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "plain-code", "steps": ["old"], "version": 1}

        response = """```
{"steps": ["new"], "reason": "fix"}
```"""
        llm.chat = AsyncMock(return_value=LLMResponse(text=response))

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="plain-code", description="test", steps=["old"])

            result = await heal_skill(skill, "error", browser, llm)

        assert result is not None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["s"]}

        llm.chat = AsyncMock(return_value=LLMResponse(text="not json at all"))

        result = await heal_skill(skill, "error", browser, llm)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["s"]}

        llm.chat = AsyncMock(side_effect=RuntimeError("API timeout"))

        result = await heal_skill(skill, "error", browser, llm)
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_error_context_to_llm(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "x", "steps": ["step one"]}

        llm.chat = AsyncMock(return_value=LLMResponse(text=None))

        await heal_skill(skill, "Element not found: #submit-btn", browser, llm)

        call_args = llm.chat.call_args
        # chat(messages=..., tools=...)
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages") or call_args[0][0]
        assert "Element not found" in messages[1]["content"]
        assert "step one" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_skill_with_no_steps_key(self):
        browser = MagicMock()
        llm = MagicMock()
        skill = {"name": "no-steps"}

        llm.chat = AsyncMock(return_value=LLMResponse(text=None))
        # Should not raise
        result = await heal_skill(skill, "error", browser, llm)
        assert result is None
