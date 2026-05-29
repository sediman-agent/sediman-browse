from __future__ import annotations

import json
from pathlib import Path
import pytest

from sediman.skills.engine import SkillEngine


@pytest.fixture
def engine(tmp_sediman_dir: Path):
    skills_dir = tmp_sediman_dir / "skills"
    yield SkillEngine(skills_dir=skills_dir)


class TestSkillEngineCreate:
    def test_creates_skill_directory_and_files(self, engine):
        result = engine.create(
            name="test-skill",
            description="A test skill",
            steps=["step 1", "step 2"],
        )
        assert (engine.skills_dir / "test-skill").is_dir()
        assert (engine.skills_dir / "test-skill" / "skill.json").exists()
        assert (engine.skills_dir / "test-skill" / "SKILL.md").exists()

    def test_returns_skill_data(self, engine):
        result = engine.create(
            name="my-skill",
            description="Does things",
            steps=["do something"],
        )
        assert result["name"] == "my-skill"
        assert result["description"] == "Does things"
        assert result["steps"] == ["do something"]
        assert result["version"] == 1

    def test_skill_json_is_valid(self, engine):
        engine.create(name="x", description="x", steps=["a"])
        data = json.loads((engine.skills_dir / "x" / "skill.json").read_text())
        assert data["name"] == "x"

    def test_skill_md_is_human_readable(self, engine):
        engine.create(name="hello", description="Says hello", steps=["open page", "click"])
        md = (engine.skills_dir / "hello" / "SKILL.md").read_text()
        assert "# hello" in md
        assert "Says hello" in md
        assert "1. open page" in md


class TestSkillEngineRead:
    def test_reads_existing_skill(self, engine):
        engine.create(name="read-test", description="desc", steps=["s1"])
        result = engine.read("read-test")
        assert result is not None
        assert result["name"] == "read-test"

    def test_returns_none_for_missing(self, engine):
        assert engine.read("nonexistent") is None


class TestSkillEngineList:
    def test_lists_all_skills(self, engine):
        engine.create(name="a", description="first", steps=[])
        engine.create(name="b", description="second", steps=[])
        skills = engine.list_skills()
        assert len(skills) == 2
        names = [s["name"] for s in skills]
        assert "a" in names
        assert "b" in names

    def test_returns_empty_when_no_skills(self, tmp_path):
        engine = SkillEngine(skills_dir=tmp_path / "empty")
        assert engine.list_skills() == []

    def test_skips_non_skill_dirs(self, engine):
        engine.skills_dir.mkdir(parents=True, exist_ok=True)
        (engine.skills_dir / "not-a-skill").mkdir()
        engine.create(name="real", description="real skill", steps=[])
        skills = engine.list_skills()
        assert len(skills) == 1


class TestSkillEnginePatch:
    def test_updates_description_and_steps(self, engine):
        engine.create(name="patch-me", description="old", steps=["old step"])
        result = engine.patch("patch-me", {"description": "new", "steps": ["new step"]})
        assert result is not None
        assert result["description"] == "new"
        assert result["steps"] == ["new step"]

    def test_increments_version(self, engine):
        engine.create(name="versioned", description="v1", steps=[])
        result = engine.patch("versioned", {"description": "v2"})
        assert result["version"] == 2

    def test_returns_none_for_missing(self, engine):
        assert engine.patch("missing", {"description": "x"}) is None


class TestSkillEngineDelete:
    def test_deletes_existing_skill(self, engine):
        engine.create(name="delete-me", description="bye", steps=[])
        assert engine.delete("delete-me") is True
        assert not (engine.skills_dir / "delete-me").exists()

    def test_returns_false_for_missing(self, engine):
        assert engine.delete("nonexistent") is False


class TestSkillEngineSummaries:
    def test_formats_skill_list(self, engine):
        engine.create(name="sum-skill", description="summary test", steps=[])
        summaries = engine.get_skill_summaries()
        assert "sum-skill" in summaries
        assert "summary test" in summaries

    def test_returns_empty_string_when_no_skills(self, tmp_path):
        engine = SkillEngine(skills_dir=tmp_path / "empty")
        assert engine.get_skill_summaries() == ""


class TestSkillEngineVersionHistory:
    def test_patch_creates_history_snapshot(self, engine):
        engine.create(name="hist-test", description="v1", steps=["a", "b"])
        engine.patch("hist-test", {"description": "v2", "steps": ["c", "d"]})

        history_dir = engine.skills_dir / "hist-test" / "history"
        assert history_dir.exists()
        assert (history_dir / "skill.json.v1").exists()
        assert (history_dir / "SKILL.md.v1").exists()

        v1_data = json.loads((history_dir / "skill.json.v1").read_text())
        assert v1_data["description"] == "v1"
        assert v1_data["steps"] == ["a", "b"]

    def test_multiple_patches_create_multiple_snapshots(self, engine):
        engine.create(name="multi-hist", description="v1", steps=["a"])
        engine.patch("multi-hist", {"description": "v2"})
        engine.patch("multi-hist", {"description": "v3"})

        history_dir = engine.skills_dir / "multi-hist" / "history"
        assert (history_dir / "skill.json.v1").exists()
        assert (history_dir / "skill.json.v2").exists()

    def test_rollback_restores_previous_version(self, engine):
        engine.create(name="rollback-test", description="original", steps=["s1", "s2"])
        engine.patch("rollback-test", {"description": "updated", "steps": ["s3"]})

        result = engine.rollback("rollback-test")
        assert result is not None
        assert result["description"] == "original"
        assert result["steps"] == ["s1", "s2"]
        assert result["version"] == 3

    def test_rollback_to_specific_version(self, engine):
        engine.create(name="spec-ver", description="v1", steps=["a"])
        engine.patch("spec-ver", {"description": "v2"})
        engine.patch("spec-ver", {"description": "v3"})

        result = engine.rollback("spec-ver", target_version=1)
        assert result is not None
        assert result["description"] == "v1"

    def test_rollback_returns_none_for_invalid_version(self, engine):
        engine.create(name="no-rollback", description="v1", steps=["a"])
        assert engine.rollback("no-rollback", target_version=5) is None
        assert engine.rollback("no-rollback", target_version=0) is None

    def test_rollback_returns_none_for_missing_skill(self, engine):
        assert engine.rollback("nonexistent") is None

    def test_rollback_snapshots_current_before_restoring(self, engine):
        engine.create(name="snap-test", description="v1", steps=["a"])
        engine.patch("snap-test", {"description": "v2"})

        engine.rollback("snap-test")

        history_dir = engine.skills_dir / "snap-test" / "history"
        assert (history_dir / "skill.json.v2").exists()

    def test_list_history_returns_versions(self, engine):
        engine.create(name="list-hist", description="v1", steps=["a"])
        engine.patch("list-hist", {"description": "v2"})
        engine.patch("list-hist", {"description": "v3"})

        history = engine.list_history("list-hist")
        assert len(history) == 2
        versions = [h["version"] for h in history]
        assert 1 in versions
        assert 2 in versions

    def test_list_history_empty_for_new_skill(self, engine):
        engine.create(name="no-hist", description="desc", steps=["a"])
        assert engine.list_history("no-hist") == []


class TestSkillEngineUsageTracking:
    def test_record_usage_increments_count(self, engine):
        engine.create(name="usage-test", description="desc", steps=["a"])

        engine.record_usage("usage-test")
        engine.record_usage("usage-test")

        result = engine.read("usage-test")
        assert result["use_count"] == 2
        assert result["last_used_at"] is not None

    def test_record_usage_returns_none_for_missing(self, engine):
        assert engine.record_usage("nonexistent") is None

    def test_usage_fields_in_list_output(self, engine):
        engine.create(name="list-usage", description="desc", steps=["a"])
        engine.record_usage("list-usage")

        skills = engine.list_skills()
        match = [s for s in skills if s["name"] == "list-usage"][0]
        assert match["use_count"] == 1
        assert match["last_used_at"] is not None

    def test_create_with_verification(self, engine):
        result = engine.create(
            name="verified",
            description="desc",
            steps=["a", "b"],
            verification="Page contains expected data",
        )
        assert result["verification"] == "Page contains expected data"

        md = (engine.skills_dir / "verified" / "SKILL.md").read_text()
        assert "## Verification" in md
        assert "Page contains expected data" in md

    def test_patch_updates_verification(self, engine):
        engine.create(name="ver-patch", description="desc", steps=["a"], verification="old check")
        engine.patch("ver-patch", {"verification": "new check"})

        result = engine.read("ver-patch")
        assert result["verification"] == "new check"

    def test_rollback_preserves_usage_and_verification(self, engine):
        engine.create(
            name="rollback-full",
            description="v1",
            steps=["a"],
            verification="v1 check",
        )
        engine.record_usage("rollback-full")
        engine.patch("rollback-full", {"description": "v2", "verification": "v2 check"})

        result = engine.rollback("rollback-full")
        assert result is not None
        assert result["description"] == "v1"
        assert result["verification"] == "v1 check"
