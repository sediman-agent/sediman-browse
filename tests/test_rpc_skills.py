from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


class TestHandleSkillsSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, tmp_sediman_dir: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="google-search", description="Search Google for things", steps=["step 1"])
        engine.create(name="web-scraper", description="Scrape websites for data", steps=["step 1"])

        from sediman.rpc_server import handle_skills_search

        result = await handle_skills_search({"query": "google"})
        assert len(result) >= 1
        names = [r["name"] for r in result]
        assert "google-search" in names

    @pytest.mark.asyncio
    async def test_search_empty_query_raises(self):
        from sediman.rpc_server import handle_skills_search

        with pytest.raises(ValueError, match="query is required"):
            await handle_skills_search({"query": ""})

    @pytest.mark.asyncio
    async def test_search_missing_query_raises(self):
        from sediman.rpc_server import handle_skills_search

        with pytest.raises(ValueError, match="query is required"):
            await handle_skills_search({})

    @pytest.mark.asyncio
    async def test_search_no_matches_returns_empty(self, tmp_sediman_dir: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="alpha", description="First skill", steps=["s1"])

        from sediman.rpc_server import handle_skills_search

        result = await handle_skills_search({"query": "nonexistent_xyz"})
        assert result == []

    @pytest.mark.asyncio
    async def test_search_result_has_expected_fields(self, tmp_sediman_dir: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="stock-checker", description="Check stock prices", steps=["s1"], category="finance")

        from sediman.rpc_server import handle_skills_search

        result = await handle_skills_search({"query": "stock"})
        assert len(result) >= 1
        first = result[0]
        assert "name" in first
        assert "description" in first
        assert "score" in first
        assert "category" in first

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, tmp_sediman_dir: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        for i in range(20):
            engine.create(name=f"skill-{i:02d}", description=f"Skill number {i}", steps=["s1"])

        from sediman.rpc_server import handle_skills_search

        result = await handle_skills_search({"query": "skill", "limit": 5})
        assert len(result) <= 5


class TestHandleHubPublish:
    @pytest.mark.asyncio
    async def test_publish_missing_name_raises(self):
        from sediman.rpc_server import handle_hub_publish

        with pytest.raises(ValueError, match="name is required"):
            await handle_hub_publish({})

    @pytest.mark.asyncio
    async def test_publish_empty_name_raises(self):
        from sediman.rpc_server import handle_hub_publish

        with pytest.raises(ValueError, match="name is required"):
            await handle_hub_publish({"name": ""})

    @pytest.mark.asyncio
    async def test_publish_nonexistent_skill_raises(self, tmp_sediman_dir: Path):
        from sediman.rpc_server import handle_hub_publish

        with pytest.raises(ValueError, match="not found locally"):
            await handle_hub_publish({"name": "nonexistent-skill"})

    @pytest.mark.asyncio
    async def test_publish_calls_hub_publish(self, tmp_sediman_dir: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="my-skill", description="A skill to publish", steps=["step 1"])

        with patch("sediman.skills.hub.HubClient.publish", return_value="PR created") as mock_publish:
            from sediman.rpc_server import handle_hub_publish

            result = await handle_hub_publish({"name": "my-skill"})
            assert result["published"] == "my-skill"
            mock_publish.assert_called_once()


class TestHandleSkillsSearchRegistered:
    def test_skills_search_in_handlers(self):
        from sediman.rpc_server import HANDLERS

        assert "skills.search" in HANDLERS

    def test_hub_publish_in_handlers(self):
        from sediman.rpc_server import HANDLERS

        assert "hub.publish" in HANDLERS
