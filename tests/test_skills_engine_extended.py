from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.engine import SkillEngine


@pytest.fixture
def engine(tmp_sediman_dir: Path):
    skills_dir = tmp_sediman_dir / "skills"
    with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
        yield SkillEngine(skills_dir=skills_dir)


class TestFindSimilar:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skills(self, engine):
        with patch("sediman.skills.search.SkillSearchEngine") as MockSearch:
            mock_search = MagicMock()
            mock_search.search = AsyncMock(return_value=[])
            mock_search.ensure_loaded = AsyncMock(return_value=None)
            MockSearch.return_value = mock_search
            result = await engine.find_similar("test description")
            assert result == []

    @pytest.mark.asyncio
    async def test_finds_exact_name_match(self, engine):
        engine.create(name="exact-skill", description="does something", steps=["a"])
        with patch("sediman.skills.search.SkillSearchEngine") as MockSearch:
            from sediman.skills.search import SkillSearchResult
            mock_search = MagicMock()
            mock_search.search = AsyncMock(return_value=[
                SkillSearchResult(
                    name="exact-skill",
                    description="does something",
                    score=0.95,
                    scope="internal",
                    source="local",
                    path="",
                )
            ])
            mock_search.ensure_loaded = AsyncMock(return_value=None)
            MockSearch.return_value = mock_search
            result = await engine.find_similar("exact-skill does something")
            assert result is not None
            assert result[0]["name"] == "exact-skill"

    @pytest.mark.asyncio
    async def test_falls_back_to_keyword_on_search_error(self, engine):
        engine.create(name="fallback-test", description="cooking pasta carbonara", steps=["a"])

        with patch("sediman.skills.search.SkillSearchEngine") as MockSearch:
            MockSearch.return_value.search = AsyncMock(side_effect=RuntimeError("broken"))

            result = await engine.find_similar("quantum physics experiments")
            # No keyword overlap with "cooking pasta carbonara", so empty
            assert result == []

    @pytest.mark.asyncio
    async def test_keyword_fallback_finds_match(self, engine):
        engine.create(
            name="cooking-skill",
            description="A skill about cooking pasta carbonara",
            steps=["a"],
        )

        with patch("sediman.skills.search.SkillSearchEngine") as MockSearch:
            MockSearch.return_value.search = AsyncMock(side_effect=RuntimeError("broken"))

            result = await engine.find_similar("cooking pasta")
            assert result is not None
            assert len(result) > 0
            assert result[0]["name"] == "cooking-skill"

    @pytest.mark.asyncio
    async def test_respects_limit(self, engine):
        engine.create(name="skill-a", description="about cooking food", steps=["a"])
        engine.create(name="skill-b", description="about baking food", steps=["b"])
        engine.create(name="skill-c", description="about grilling food", steps=["c"])

        with patch("sediman.skills.search.SkillSearchEngine") as MockSearch:
            MockSearch.return_value.search = AsyncMock(side_effect=RuntimeError("broken"))

            result = await engine.find_similar("food cooking", limit=2)
            assert len(result) <= 2


class TestVerifyAndRollback:
    def test_returns_false_for_missing_skill(self, engine):
        ok, msg = engine.verify_and_rollback("nonexistent")
        assert ok is False
        assert "not found" in msg

    def test_returns_true_for_existing_skill(self, engine):
        engine.create(name="test-skill", description="desc", steps=["a"], verification="check x")
        ok, msg = engine.verify_and_rollback("test-skill")
        assert ok is True
        assert "test-skill" in msg

    def test_accepts_llm_param(self, engine):
        engine.create(name="test-skill", description="desc", steps=["a"])
        ok, msg = engine.verify_and_rollback("test-skill", llm=MagicMock())
        assert ok is True

    def test_returns_tuple_bool_str(self, engine):
        engine.create(name="tuple-skill", description="desc", steps=["a"])
        result = engine.verify_and_rollback("tuple-skill")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)
