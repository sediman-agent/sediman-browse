from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from sediman.skills.engine import SkillEngine
from sediman.skills.hub import SkillLockFile, LockEntry


class TestBundledAutoInstall:
    def test_bundled_skill_exists_on_disk(self):
        bundled = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "sediman"
            / "skills"
            / "bundled"
            / "find-skills"
        )
        assert bundled.is_dir()
        assert (bundled / "SKILL.md").exists()

    def test_bundled_skill_is_loadable(self):
        from sediman.skills.format import load_skill

        bundled = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "sediman"
            / "skills"
            / "bundled"
            / "find-skills"
        )
        skill = load_skill(bundled)
        assert skill is not None
        assert skill.name == "find-skills"
        assert len(skill.description) > 10

    def test_bundled_skill_can_be_installed_manually(self, tmp_path: Path):
        from sediman.skills.format import load_skill
        from sediman.skills.engine import SkillEngine

        bundled = (
            Path(__file__).resolve().parent.parent
            / "src"
            / "sediman"
            / "skills"
            / "bundled"
            / "find-skills"
        )
        skill = load_skill(bundled)
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        result = engine.install(skill)
        assert result["name"] == "find-skills"


class TestDeleteCleansUpLock:
    def test_delete_removes_lock_entry(self, tmp_path: Path):
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            engine.create(name="to-delete", description="Will be deleted", steps=["s1"])
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "to-delete",
                LockEntry(source="hub", source_type="hub", source_url=""),
            )
            assert lock.get("to-delete") is not None
            engine.delete("to-delete")
            assert lock.get("to-delete") is None

    def test_delete_missing_skill_is_noop_for_lock(self, tmp_path: Path):
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            result = engine.delete("nonexistent")
            assert result is False


class TestEngineInstallMethod:
    def test_install_creates_skill(self, tmp_path: Path):
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        skill = SkillData(
            name="installed", description="Directly installed", steps=["s1"]
        )
        result = engine.install(skill)
        assert result is not None
        assert result["name"] == "installed"
        assert engine.read("installed") is not None

    def test_install_creates_skill_json_and_md(self, tmp_path: Path):
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        skill = SkillData(name="files-test", description="Check files", steps=["s1"])
        engine.install(skill)
        skill_dir = tmp_path / "skills" / "files-test"
        assert (skill_dir / "skill.json").exists()
        assert (skill_dir / "SKILL.md").exists()

    def test_install_overwrites_existing(self, tmp_path: Path):
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        engine.create(name="overwrite", description="v1", steps=["s1"])
        skill = SkillData(name="overwrite", description="v2", steps=["s2"])
        engine.install(skill)
        data = engine.read("overwrite")
        assert data["description"] == "v2"

    def test_install_with_all_fields(self, tmp_path: Path):
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        skill = SkillData(
            name="full-skill",
            description="Full skill",
            steps=["s1", "s2"],
            category="finance",
            variables=["QUERY"],
            schedule="0 * * * *",
            when_to_use="When you need finance data",
            pitfalls=["API rate limits"],
            verification="Check data is non-empty",
            author="test",
            source="hub",
        )
        result = engine.install(skill)
        assert result["name"] == "full-skill"
        assert result["category"] == "finance"
        assert result["variables"] == ["QUERY"]
        assert result["when_to_use"] == "When you need finance data"

    def test_install_sets_source(self, tmp_path: Path):
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        skill = SkillData(
            name="src-test", description="d", steps=["s1"], source="github:owner/repo"
        )
        result = engine.install(skill)
        assert result["source"] == "github:owner/repo"


class TestSkillLockFileIntegration:
    def test_full_lifecycle(self, tmp_path: Path):
        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "a",
                LockEntry(
                    source="o/r1",
                    source_type="github",
                    source_url="https://github.com/o/r1",
                ),
            )
            lock.set(
                "b",
                LockEntry(
                    source="o/r2",
                    source_type="github",
                    source_url="https://github.com/o/r2",
                ),
            )
            lock.set("c", LockEntry(source="hub", source_type="hub", source_url=""))

            assert len(lock.list_all()) == 3
            assert lock.get("a").source == "o/r1"

            lock.remove("b")
            assert len(lock.list_all()) == 2
            assert lock.get("b") is None

            lock.set(
                "a",
                LockEntry(source="o/r1-updated", source_type="github", source_url=""),
            )
            assert lock.get("a").source == "o/r1-updated"

            raw = json.loads(lock_path.read_text())
            assert raw["version"] == 1
            assert len(raw["skills"]) == 2

    def test_multiple_lockfiles_dont_interfere(self, tmp_path: Path):
        lock1 = SkillLockFile(path=tmp_path / "lock1.json")
        lock2 = SkillLockFile(path=tmp_path / "lock2.json")
        lock1.set("x", LockEntry(source="a", source_type="github", source_url=""))
        lock2.set("y", LockEntry(source="b", source_type="hub", source_url=""))
        assert lock1.get("x") is not None
        assert lock1.get("y") is None
        assert lock2.get("y") is not None
        assert lock2.get("x") is None
