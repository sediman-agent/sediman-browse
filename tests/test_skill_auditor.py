from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sediman.agent.skill_auditor import SkillAuditor
from sediman.llm.provider import LLMResponse


def _make_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], done=True)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def auditor(mock_llm):
    return SkillAuditor(mock_llm)


class TestSkillAuditorIdentifyStale:
    def test_flags_old_skill(self, auditor):
        from datetime import datetime, timezone, timedelta

        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        skills = [{"name": "old-skill", "updated_at": old_date, "last_used_at": None, "use_count": 0}]
        stale = auditor._identify_stale(skills)
        assert "old-skill" in stale

    def test_does_not_flag_recent_skill(self, auditor):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        skills = [{"name": "fresh", "updated_at": recent, "last_used_at": recent, "use_count": 5}]
        stale = auditor._identify_stale(skills)
        assert "fresh" not in stale

    def test_flags_skill_with_no_dates(self, auditor):
        skills = [{"name": "nodate", "updated_at": None, "last_used_at": None}]
        stale = auditor._identify_stale(skills)
        assert "nodate" in stale


class TestSkillAuditorParseResponse:
    def test_parses_valid_json(self, auditor):
        text = '{"actions": [{"skill_name": "x", "action": "delete", "reason": "stale"}], "summary": "cleaned up"}'
        result = auditor._parse_response(text)
        assert result is not None
        assert len(result["actions"]) == 1

    def test_parses_json_in_code_block(self, auditor):
        text = '```json\n{"actions": [], "summary": "all good"}\n```'
        result = auditor._parse_response(text)
        assert result is not None
        assert result["actions"] == []

    def test_returns_none_for_invalid(self, auditor):
        assert auditor._parse_response("not json") is None


class TestSkillAuditorAudit:
    @pytest.mark.asyncio
    async def test_returns_summary_when_no_skills(self, mock_llm, tmp_path):
        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path
        try:
            auditor = SkillAuditor(mock_llm)
            result = await auditor.audit()
            assert result["actions"] == []
        finally:
            engine_mod.GLOBAL_SKILLS_DIR = original

    @pytest.mark.asyncio
    async def test_fast_path_when_no_stale_skills(self, mock_llm, tmp_path):
        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine()
            engine.create(name="audit-test", description="test", steps=["a"])

            auditor = SkillAuditor(mock_llm)
            result = await auditor.audit()
            # Fast path: no stale skills, so no LLM call needed
            assert result["actions"] == []
            assert "active" in result["summary"].lower()
            mock_llm.chat.assert_not_called()
        finally:
            engine_mod.GLOBAL_SKILLS_DIR = original


class TestSkillAuditorApplyActions:
    @pytest.mark.asyncio
    async def test_archive_action_patches_category(self, mock_llm, tmp_path):
        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine()
            engine.create(name="to-archive", description="old", steps=["a"])

            auditor = SkillAuditor(mock_llm)
            result = {
                "actions": [{"skill_name": "to-archive", "action": "archive", "reason": "stale"}],
                "summary": "archived 1 skill",
            }
            await auditor._apply_actions(result, engine)

            archived = engine.read("to-archive")
            assert archived["category"] == "archived"
        finally:
            engine_mod.GLOBAL_SKILLS_DIR = original

    @pytest.mark.asyncio
    async def test_delete_action_removes_skill(self, mock_llm, tmp_path):
        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine()
            engine.create(name="to-delete", description="bad", steps=["a"])

            auditor = SkillAuditor(mock_llm)
            result = {
                "actions": [{"skill_name": "to-delete", "action": "delete", "reason": "redundant"}],
                "summary": "deleted 1 skill",
            }
            await auditor._apply_actions(result, engine)

            assert engine.read("to-delete") is None
        finally:
            engine_mod.GLOBAL_SKILLS_DIR = original
