from __future__ import annotations

from unittest.mock import patch
from pathlib import Path

import pytest

from sediman.agent.tools import _handle_skill_manage


class TestSkillManageDeleteAction:
    @pytest.mark.asyncio
    async def test_deletes_existing_skill(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=tmp_path)
            engine.create(name="del-me", description="desc", steps=["a"])

            result = await _handle_skill_manage(action="delete", name="del-me")
            assert result.success is True
            assert "deleted" in result.output.lower()

            fresh_engine = SkillEngine(skills_dir=tmp_path)
            assert fresh_engine.read("del-me") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_error(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            result = await _handle_skill_manage(action="delete", name="nope")
            assert result.success is False
            assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_delete_requires_name(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            result = await _handle_skill_manage(action="delete")
            assert result.success is False
            assert "required" in result.output.lower()


class TestSkillManageCreateWithVerification:
    @pytest.mark.asyncio
    async def test_create_with_verification(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            result = await _handle_skill_manage(
                action="create",
                name="verified-skill",
                description="A verified skill",
                steps=["step 1", "step 2"],
                verification="Page shows confirmation",
            )
            assert result.success is True

            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=tmp_path)
            skill = engine.read("verified-skill")
            assert skill["verification"] == "Page shows confirmation"


class TestSkillManagePatchWithVerification:
    @pytest.mark.asyncio
    async def test_patch_with_verification(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=tmp_path)
            engine.create(name="patch-ver", description="desc", steps=["a"])

            result = await _handle_skill_manage(
                action="patch",
                name="patch-ver",
                verification="New verification check",
            )
            assert result.success is True

            fresh_engine = SkillEngine(skills_dir=tmp_path)
            skill = fresh_engine.read("patch-ver")
            assert skill["verification"] == "New verification check"


class TestSkillManageUnknownAction:
    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, tmp_path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_path):
            result = await _handle_skill_manage(action="foobar")
            assert result.success is False
            assert "Unknown" in result.output
