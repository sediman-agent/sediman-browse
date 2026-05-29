"""Comprehensive edge-case tests for skills/hub.py — caching, network errors, install edge cases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sediman.skills.format import SkillData
from sediman.skills.hub import HubClient, HubSkillSummary, DEFAULT_REGISTRY_URL


class TestHubClientInitEdgeCases:
    def test_strips_multiple_trailing_slashes(self):
        client = HubClient(registry_url="https://example.com/hub///")
        assert client.registry_url == "https://example.com/hub///".rstrip("/")

    def test_empty_custom_url(self):
        client = HubClient(registry_url="")
        assert client.registry_url == DEFAULT_REGISTRY_URL

    def test_none_url_uses_default(self):
        client = HubClient(registry_url=None)
        assert client.registry_url == DEFAULT_REGISTRY_URL


class TestHubClientSearchEdgeCases:
    def test_case_insensitive_search(self):
        client = HubClient()
        mock_index = [
            {"name": "Google-Search", "description": "Search", "category": "search"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("google")
            assert len(results) == 1

    def test_search_in_category(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "tool", "category": "finance"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("finance")
            assert len(results) == 1

    def test_empty_query_matches_all(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "first", "category": "x"},
            {"name": "b", "description": "second", "category": "y"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("")
            assert len(results) == 2

    def test_index_with_missing_fields(self):
        client = HubClient()
        mock_index = [
            {"name": "incomplete"},  # Missing description and category
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.search("incomplete")
            assert len(results) == 1
            assert results[0].description == ""
            assert results[0].category == "general"


class TestHubClientBrowseEdgeCases:
    def test_browse_with_no_matching_category(self):
        client = HubClient()
        mock_index = [
            {"name": "a", "description": "first", "category": "search"},
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse(category="nonexistent")
            assert results == []

    def test_browse_preserves_all_fields(self):
        client = HubClient()
        mock_index = [
            {
                "name": "full",
                "description": "desc",
                "category": "cat",
                "author": "alice",
                "version": 3,
                "installs": 100,
                "trust": "trusted",
                "variables": ["X"],
                "schedule": "0 * * * *",
            },
        ]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse()
            assert results[0].author == "alice"
            assert results[0].version == 3
            assert results[0].installs == 100
            assert results[0].trust == "trusted"
            assert results[0].variables == ["X"]
            assert results[0].schedule == "0 * * * *"

    def test_browse_with_default_values(self):
        client = HubClient()
        mock_index = [{"name": "minimal"}]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse()
            assert results[0].version == 1
            assert results[0].installs == 0
            assert results[0].trust == "community"


class TestHubClientGetSkillEdgeCases:
    def test_json_parse_failure_falls_back_to_md(self):
        client = HubClient()
        # _fetch_text returns the raw text, not parsed JSON
        # get_skill first tries JSON path: fetches text, then parse_skill_json
        # "not json" will fail parse_skill_json -> None, then tries MD
        invalid_json_text = "not json at all"
        valid_md_text = "---\nname: fallback\ndescription: MD fallback\n---\n# fallback\n## Steps\n1. Step"

        with patch.object(client, "_fetch_text") as mock_fetch:
            # First call: skill.json path -> returns invalid text
            # Second call: SKILL.md path -> returns valid MD
            mock_fetch.side_effect = [invalid_json_text, valid_md_text]
            skill = client.get_skill("test")

        assert skill is not None
        assert skill.name == "fallback"
        assert skill.source == "hub"

    def test_both_formats_fail(self):
        client = HubClient()
        with patch.object(client, "_fetch_text", return_value=None):
            skill = client.get_skill("missing")
            assert skill is None

    def test_json_skill_source_set_to_hub(self):
        client = HubClient()
        skill_json = json.dumps({"name": "x", "description": "d", "steps": ["s"]})

        with patch.object(client, "_fetch_text") as mock_fetch:
            mock_fetch.side_effect = [skill_json, None]
            skill = client.get_skill("x")

        assert skill.source == "hub"


class TestHubClientInstallEdgeCases:
    def test_install_with_warnings_without_force(self, tmp_path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        skill = SkillData(name="warn-skill", description="short", steps=[])
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("warn-skill", engine)

        assert ok

    def test_install_with_warnings_with_force(self, tmp_path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        skill = SkillData(name="warn-skill", description="short", steps=[])
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("warn-skill", engine, force=True)

        assert ok

    def test_install_with_variables(self, tmp_path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        skill = SkillData(
            name="var-skill",
            description="Has variables",
            steps=["s"],
            variables=["QUERY", "LIMIT"],
        )
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("var-skill", engine)

        assert ok
        data = engine.read("var-skill")
        assert data is not None

    def test_install_with_schedule(self, tmp_path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()

        skill = SkillData(
            name="sched-skill",
            description="Has schedule",
            steps=["s"],
            schedule="0 9 * * *",
        )
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("sched-skill", engine)

        assert ok
        data = engine.read("sched-skill")
        assert data is not None


class TestHubClientInfoEdgeCases:
    def test_info_includes_all_fields(self):
        client = HubClient()
        skill = SkillData(
            name="full-info",
            description="Full info skill",
            steps=["s1", "s2"],
            category="finance",
            version=3,
            author="bob",
            variables=["X"],
            schedule="0 * * * *",
            license="MIT",
        )
        with patch.object(client, "get_skill", return_value=skill):
            info = client.info("full-info")

        assert info is not None
        assert info["name"] == "full-info"
        assert info["category"] == "finance"
        assert info["version"] == 3
        assert info["author"] == "bob"
        assert info["variables"] == ["X"]
        assert info["schedule"] == "0 * * * *"
        assert info["steps"] == ["s1", "s2"]
        assert info["license"] == "MIT"
        assert "trust" in info
        assert "warnings" in info


class TestHubClientPublishEdgeCases:
    def test_publish_includes_trust_level(self):
        client = HubClient()
        skill = SkillData(
            name="pub-trust",
            description="A publishable skill for testing",
            steps=["s1"],
        )
        ok, msg = client.publish(skill)
        assert ok
        assert "community" in msg

    def test_publish_bundled_skill(self):
        client = HubClient()
        skill = SkillData(
            name="bundled-pub",
            description="A bundled skill being published",
            steps=["s1"],
            source="bundled",
        )
        ok, msg = client.publish(skill)
        assert ok
        assert "bundled" in msg

    def test_publish_destructive_skill_fails(self):
        client = HubClient()
        skill = SkillData(
            name="bad-pub", description="rm -rf / everything", steps=["destroy"]
        )
        ok, msg = client.publish(skill)
        assert not ok


class TestHubSkillSummaryDefaults:
    def test_all_defaults(self):
        s = HubSkillSummary(name="n", description="d", category="c")
        assert s.author is None
        assert s.version == 1
        assert s.installs == 0
        assert s.trust == "community"
        assert s.variables is None
        assert s.schedule is None

    def test_custom_values(self):
        s = HubSkillSummary(
            name="n",
            description="d",
            category="c",
            author="alice",
            version=5,
            installs=42,
            trust="trusted",
            variables=["X"],
            schedule="* * * * *",
        )
        assert s.author == "alice"
        assert s.version == 5
        assert s.installs == 42
        assert s.trust == "trusted"
        assert s.variables == ["X"]
        assert s.schedule == "* * * * *"


class TestHubGetIndex:
    def setup_method(self):
        import sediman.skills.hub as hub_module

        hub_module._HUB_CACHE = None
        hub_module._CACHE_TS = 0.0

    def test_returns_empty_on_fetch_failure(self):
        client = HubClient()
        with patch.object(client, "_fetch_json", return_value=None):
            index = client._get_index()
            assert index == []

    def test_returns_empty_on_non_list_response(self):
        client = HubClient()
        with patch.object(client, "_fetch_json", return_value={"error": "not found"}):
            index = client._get_index()
            assert index == []

    def test_caches_index(self):
        import sediman.skills.hub as hub_module

        client = HubClient()
        mock_data = [{"name": "cached"}]

        with patch.object(client, "_fetch_json", return_value=mock_data):
            index1 = client._get_index()
            index2 = client._get_index()

        assert index1 == index2
