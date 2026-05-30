from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sediman.skills.format import SkillData
from sediman.skills.hub import HubClient, HubSkillSummary, DEFAULT_REGISTRY_URL


def _make_engine(**kwargs):
    from sediman.skills.engine import SkillEngine
    engine = MagicMock(spec=SkillEngine, **kwargs)
    return engine


class TestHubClientInit:
    def test_default_registry(self):
        client = HubClient()
        assert client.registry_url == DEFAULT_REGISTRY_URL

    def test_custom_registry(self):
        client = HubClient(registry_url="https://example.com/hub")
        assert client.registry_url == "https://example.com/hub"

    def test_trailing_slash_stripped(self):
        client = HubClient(registry_url="https://example.com/hub/")
        assert client.registry_url == "https://example.com/hub"


class TestHubClientSearch:
    def test_search_filters_by_query(self):
        client = HubClient()
        mock_index = [
            {"name": "google-search", "description": "Search Google", "category": "search"},
            {"name": "web-scraper", "description": "Scrape websites", "category": "data"},
            {"name": "stock-tracker", "description": "Track stocks", "category": "finance"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("google")
            assert len(results) == 1
            assert results[0].name == "google-search"

    def test_search_matches_description(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "scrape data from websites", "category": "data"},
            {"name": "b", "description": "search the web", "category": "search"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("scrape")
            assert len(results) == 1
            assert results[0].name == "a"

    def test_search_no_results(self):
        client = HubClient()
        with patch.object(client, "_get_index", return_value=[]):
            results = client.search("nonexistent")
            assert results == []


class TestHubClientBrowse:
    def test_browse_all(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "First", "category": "search"},
            {"name": "b", "description": "Second", "category": "data"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse()
            assert len(results) == 2

    def test_browse_by_category(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "First", "category": "search"},
            {"name": "b", "description": "Second", "category": "data"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse(category="search")
            assert len(results) == 1
            assert results[0].name == "a"

    def test_browse_empty(self):
        client = HubClient()
        with patch.object(client, "_get_index", return_value=[]):
            results = client.browse()
            assert results == []


class TestHubClientGetSkill:
    def test_get_skill_from_json(self):
        client = HubClient()
        skill_json = json.dumps({
            "name": "test",
            "description": "Test skill with enough text",
            "steps": ["step 1"],
        })
        with patch.object(client, "_fetch_text") as mock_fetch:
            mock_fetch.side_effect = [skill_json, None]
            skill = client.get_skill("test")
            assert skill is not None
            assert skill.name == "test"
            assert skill.source == "hub"

    def test_get_skill_from_md_fallback(self):
        client = HubClient()
        skill_md = "---\nname: md-skill\ndescription: A markdown skill\n---\n# md-skill\n## Steps\n1. Do it\n"
        with patch.object(client, "_fetch_text") as mock_fetch:
            mock_fetch.side_effect = [None, skill_md]
            skill = client.get_skill("md-skill")
            assert skill is not None
            assert skill.name == "md-skill"

    def test_get_skill_not_found(self):
        client = HubClient()
        with patch.object(client, "_fetch_text", return_value=None):
            skill = client.get_skill("nonexistent")
            assert skill is None


class TestHubClientInstall:
    def test_install_success(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        client = HubClient()

        skill = SkillData(name="hub-skill", description="From the hub", steps=["s1"])
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("hub-skill", engine)
            assert ok
            assert "hub-skill" in msg
            assert engine.read("hub-skill") is not None

    def test_install_already_exists(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        engine.create(name="existing", description="Already here", steps=[])
        client = HubClient()

        ok, msg = client.install("existing", engine)
        assert not ok
        assert "already exists" in msg

    def test_install_force_overwrites(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        engine.create(name="existing", description="Old desc", steps=[])
        client = HubClient()

        skill = SkillData(name="existing", description="New desc from hub", steps=["new"])
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("existing", engine, force=True)
            assert ok
            data = engine.read("existing")
            assert data["description"] == "New desc from hub"

    def test_install_not_found_in_hub(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        with patch.object(client, "get_skill", return_value=None):
            ok, msg = client.install("missing", engine)
            assert not ok
            assert "not found" in msg

    def test_install_invalid_skill(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        bad_skill = SkillData(name="", description="", steps=[])
        with patch.object(client, "get_skill", return_value=bad_skill):
            ok, msg = client.install("bad", engine)
            assert not ok
            assert "validation failed" in msg.lower()

    def test_install_invalid_engine(self):
        client = HubClient()
        ok, msg = client.install("x", "not an engine")
        assert not ok
        assert "Invalid engine" in msg


class TestHubClientInfo:
    def test_info_existing_skill(self):
        client = HubClient()
        skill = SkillData(name="info-test", description="Info test skill", steps=["s1"])
        with patch.object(client, "get_skill", return_value=skill):
            info = client.info("info-test")
            assert info is not None
            assert info["name"] == "info-test"
            assert info["trust"] == "community"

    def test_info_not_found(self):
        client = HubClient()
        with patch.object(client, "get_skill", return_value=None):
            info = client.info("missing")
            assert info is None


class TestHubClientPublish:
    def test_publish_valid_skill(self):
        client = HubClient()
        skill = SkillData(name="pub-test", description="Publishable skill with good description", steps=["s1"])
        ok, msg = client.publish(skill)
        assert ok
        assert "PR" in msg

    def test_publish_invalid_skill(self):
        client = HubClient()
        skill = SkillData(name="", description="", steps=[])
        ok, msg = client.publish(skill)
        assert not ok
        assert "Validation failed" in msg


class TestHubSkillSummary:
    def test_defaults(self):
        s = HubSkillSummary(name="x", description="d", category="c")
        assert s.trust == "community"
        assert s.installs == 0
        assert s.version == 1
        assert s.author is None
        assert s.variables is None


class TestHubClientGetSkillLocal:
    def test_get_skill_local_fallback(self):
        client = HubClient()
        with patch.object(client, "_fetch_text", return_value=None):
            skill = client.get_skill("algorithmic-art")
            assert skill is not None
            assert skill.name == "algorithmic-art"
            assert skill.source == "anthropics/skills"

    def test_get_skill_local_missing(self):
        client = HubClient()
        with patch.object(client, "_fetch_text", return_value=None):
            skill = client.get_skill("zzz-nonexistent-skill-xyz")
            assert skill is None

    def test_install_local_skill(self):
        client = HubClient()
        engine = _make_engine()
        engine.read.return_value = None
        engine._skill_path.return_value = Path("/tmp/fake-skill-dir")
        with patch.object(client, "_fetch_text", return_value=None):
            ok, msg = client.install("algorithmic-art", engine, force=False)
            assert ok
            assert "algorithmic-art" in msg

    def test_install_nonexistent_skill(self):
        client = HubClient()
        engine = _make_engine()
        engine.read.return_value = None
        with patch.object(client, "_fetch_text", return_value=None):
            ok, msg = client.install("zzz-nonexistent-skill-xyz", engine, force=False)
            assert not ok
            assert "not found" in msg


class TestHubClientBrowseLocal:
    def test_browse_returns_local_skills_when_remote_empty(self):
        client = HubClient()
        with patch.object(client, "_fetch_json", return_value=None):
            results = client.browse()
            assert len(results) > 0
            assert all(isinstance(r, HubSkillSummary) for r in results)

    def test_browse_no_null_fields(self):
        client = HubClient()
        with patch.object(client, "_fetch_json", return_value=None):
            results = client.browse()
            for r in results:
                assert r.author is not None, f"{r.name} has null author"
                assert isinstance(r.author, str), f"{r.name} author is not str"
                assert r.variables is not None, f"{r.name} has null variables"
                assert isinstance(r.variables, list), f"{r.name} variables is not list"
                assert r.schedule is not None, f"{r.name} has null schedule"
                assert isinstance(r.schedule, str), f"{r.name} schedule is not str"

    def test_search_no_null_fields(self):
        client = HubClient()
        with patch.object(client, "_fetch_json", return_value=None):
            results = client.search("art")
            assert len(results) > 0
            for r in results:
                assert isinstance(r.author, str), f"{r.name} author is not str"
                assert isinstance(r.variables, list), f"{r.name} variables is not list"
