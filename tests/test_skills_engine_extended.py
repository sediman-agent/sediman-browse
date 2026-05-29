from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.skills.engine import SkillEngine


@pytest.fixture
def engine(tmp_sediman_dir: Path):
    skills_dir = tmp_sediman_dir / "skills"
    with patch("sediman.skills.engine.SKILLS_DIR", skills_dir):
        yield SkillEngine(skills_dir=skills_dir)


class TestFindSimilar:
    def test_returns_none_when_no_skills(self, engine):
        result = engine.find_similar("test", "test description")
        assert result is None

    def test_finds_exact_name_match(self, engine):
        engine.create(name="exact-skill", description="does something", steps=["a"])
        result = engine.find_similar("exact-skill", "does something")
        assert result is not None
        assert result["name"] == "exact-skill"

    def test_finds_semantic_match_via_vector_store(self, engine):
        engine.create(
            name="search-google",
            description="Search Google for a given query",
            steps=["navigate", "input", "click"],
        )

        with patch("sediman.memory.vector.VectorStore") as MockVectorStore:
            mock_vs = MagicMock()
            mock_vs.search.return_value = [
                {
                    "text": "search-google: Search Google for a given query",
                    "score": 0.85,
                    "metadata": {"name": "search-google"},
                }
            ]
            MockVectorStore.return_value = mock_vs

            result = engine.find_similar(
                "google-search", "Run a search on Google and get results"
            )
            assert result is not None
            assert result["name"] == "search-google"

    def test_vector_fallback_on_exception(self, engine):
        engine.create(name="fallback-test", description="cooking pasta carbonara", steps=["a"])

        with patch("sediman.memory.vector.VectorStore") as MockVectorStore:
            MockVectorStore.side_effect = ImportError("no module")

            result = engine.find_similar("nonexistent", "quantum physics experiments")
            assert result is None

    def test_similarity_threshold_filters_low_scores(self, engine):
        engine.create(
            name="unrelated",
            description="Completely different topic about cooking pasta",
            steps=["a"],
        )

        with patch("sediman.memory.vector.VectorStore") as MockVectorStore:
            mock_vs = MagicMock()
            mock_vs.search.return_value = []
            MockVectorStore.return_value = mock_vs

            result = engine.find_similar(
                "programming", "Write Python code to sort a list", threshold=0.8
            )
            assert result is None


class TestVerifyAndRollback:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_skill(self, engine):
        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": True, "fail_reason": ""}
            result = await engine.verify_and_rollback("nonexistent", "verify prompt", llm=MagicMock())
            assert result is None

    @pytest.mark.asyncio
    async def test_verify_passed_returns_skill(self, engine):
        engine.create(name="test-skill", description="desc", steps=["a"], verification="check x")

        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": True, "fail_reason": ""}
            result = await engine.verify_and_rollback("test-skill", "verify prompt", llm=MagicMock())
            assert result is not None
            assert result["name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_verify_failed_rolls_back(self, engine):
        engine.create(name="rollback-skill", description="v1", steps=["step 1"], verification="check 1")
        engine.patch("rollback-skill", {"description": "v2", "steps": ["step 2"]})

        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": False, "fail_reason": "broken"}
            result = await engine.verify_and_rollback("rollback-skill", "verify prompt", llm=MagicMock())

        assert result is not None
        assert result["description"] == "v1"
        assert result["steps"] == ["step 1"]

    @pytest.mark.asyncio
    async def test_verify_failed_no_history_returns_none(self, engine):
        engine.create(name="new-skill", description="v1", steps=["step 1"])

        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": False, "fail_reason": "broken"}
            result = await engine.verify_and_rollback("new-skill", "verify prompt", llm=MagicMock())

        assert result is None

    @pytest.mark.asyncio
    async def test_pass_screenshot_to_verify(self, engine):
        engine.create(name="ss-skill", description="desc", steps=["a"])

        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": True, "fail_reason": ""}
            result = await engine.verify_and_rollback(
                "ss-skill",
                "verify prompt",
                llm=MagicMock(),
                screenshot_path="/tmp/test.png",
                dom_snapshot="<html></html>",
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_verify_failed_keeps_reason(self, engine):
        engine.create(name="fail-skill", description="v1", steps=["a"], verification="x")
        engine.patch("fail-skill", {"steps": ["b"]})

        with patch("sediman.skills.healer.verify_skill") as mock_verify:
            mock_verify.return_value = {"passed": False, "fail_reason": "element not found"}
            result = await engine.verify_and_rollback("fail-skill", "verify prompt", llm=MagicMock())

        assert result is not None
        assert result["description"] == "v1"
