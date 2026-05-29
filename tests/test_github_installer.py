from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sediman.skills.hub import (
    GitHubInstaller,
    HubClient,
    LockEntry,
    SkillLockFile,
    _hash_skill_dir,
    _now_iso,
)


class TestLockEntry:
    def test_to_json_roundtrip(self):
        entry = LockEntry(
            source="anthropics/skills",
            source_type="github",
            source_url="https://github.com/anthropics/skills",
            skill_path="skills/frontend-design/SKILL.md",
            skill_folder_hash="abc123",
            installed_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        d = entry.to_json()
        assert d["source"] == "anthropics/skills"
        assert d["sourceType"] == "github"
        assert d["skillFolderHash"] == "abc123"
        assert d["installedAt"] == "2026-01-01T00:00:00+00:00"

    def test_from_json(self):
        data = {
            "source": "owner/repo",
            "sourceType": "hub",
            "sourceUrl": "https://example.com",
            "skillPath": "SKILL.md",
            "skillFolderHash": "deadbeef",
            "installedAt": "2026-05-01T00:00:00Z",
            "updatedAt": "2026-05-02T00:00:00Z",
        }
        entry = LockEntry.from_json(data)
        assert entry.source == "owner/repo"
        assert entry.source_type == "hub"
        assert entry.skill_folder_hash == "deadbeef"

    def test_to_json_omits_empty_fields(self):
        entry = LockEntry(
            source="x/y", source_type="github", source_url="https://github.com/x/y"
        )
        d = entry.to_json()
        assert "skillFolderHash" not in d
        assert "installedAt" not in d
        assert "updatedAt" not in d

    def test_from_json_defaults(self):
        entry = LockEntry.from_json({"source": "a/b"})
        assert entry.source_type == "unknown"
        assert entry.source_url == ""
        assert entry.skill_path == "SKILL.md"


class TestSkillLockFile:
    def test_reads_missing_file(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "nonexistent.json")
        data = lock._read()
        assert data == {"version": 1, "skills": {}}

    def test_reads_corrupt_file(self, tmp_path: Path):
        p = tmp_path / "lock.json"
        p.write_text("not json{{{")
        lock = SkillLockFile(path=p)
        data = lock._read()
        assert data == {"version": 1, "skills": {}}

    def test_set_and_get(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        entry = LockEntry(
            source="owner/repo",
            source_type="github",
            source_url="https://github.com/owner/repo",
            skill_folder_hash="abc",
            installed_at=_now_iso(),
            updated_at=_now_iso(),
        )
        lock.set("my-skill", entry)
        result = lock.get("my-skill")
        assert result is not None
        assert result.source == "owner/repo"
        assert result.source_type == "github"
        assert result.skill_folder_hash == "abc"

    def test_get_missing_returns_none(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        assert lock.get("nonexistent") is None

    def test_remove(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        lock.set("x", LockEntry(source="a", source_type="github", source_url=""))
        lock.set("y", LockEntry(source="b", source_type="hub", source_url=""))
        lock.remove("x")
        assert lock.get("x") is None
        assert lock.get("y") is not None

    def test_remove_missing_is_noop(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        lock.remove("nonexistent")

    def test_list_all(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        lock.set("a", LockEntry(source="a", source_type="github", source_url=""))
        lock.set("b", LockEntry(source="b", source_type="hub", source_url=""))
        entries = lock.list_all()
        assert len(entries) == 2
        assert "a" in entries
        assert "b" in entries

    def test_list_all_empty(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        assert lock.list_all() == {}

    def test_overwrite_existing(self, tmp_path: Path):
        lock = SkillLockFile(path=tmp_path / "lock.json")
        lock.set("x", LockEntry(source="v1", source_type="github", source_url=""))
        lock.set("x", LockEntry(source="v2", source_type="hub", source_url=""))
        result = lock.get("x")
        assert result is not None
        assert result.source == "v2"
        assert result.source_type == "hub"

    def test_persists_to_disk(self, tmp_path: Path):
        p = tmp_path / "lock.json"
        lock = SkillLockFile(path=p)
        lock.set(
            "x",
            LockEntry(
                source="owner/repo",
                source_type="github",
                source_url="https://github.com/owner/repo",
            ),
        )
        raw = json.loads(p.read_text())
        assert "x" in raw["skills"]
        assert raw["skills"]["x"]["sourceType"] == "github"

    def test_creates_parent_dir(self, tmp_path: Path):
        p = tmp_path / "deep" / "nested" / "lock.json"
        lock = SkillLockFile(path=p)
        lock.set("x", LockEntry(source="a", source_type="github", source_url=""))
        assert p.exists()


class TestNowIso:
    def test_returns_iso_string(self):
        result = _now_iso()
        assert "T" in result
        assert len(result) > 20

    def test_includes_timezone(self):
        result = _now_iso()
        assert "+" in result or "Z" in result or "-" in result[10:]


class TestHashSkillDir:
    def test_hashes_file_contents(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.json").write_text('{"name":"test"}')
        (skill_dir / "SKILL.md").write_text("# test")
        h = _hash_skill_dir(skill_dir)
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_contents_different_hash(self, tmp_path: Path):
        d1 = tmp_path / "a"
        d1.mkdir()
        (d1 / "f.txt").write_text("hello")
        d2 = tmp_path / "b"
        d2.mkdir()
        (d2 / "f.txt").write_text("world")
        assert _hash_skill_dir(d1) != _hash_skill_dir(d2)

    def test_empty_dir(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()
        h = _hash_skill_dir(d)
        assert len(h) == 40


class TestGitHubInstallerParseRef:
    def test_owner_repo(self):
        installer = GitHubInstaller()
        owner, repo, skill_name, branch = installer.parse_ref("anthropics/skills")
        assert owner == "anthropics"
        assert repo == "skills"
        assert skill_name == "skills"

    def test_owner_repo_at_skill(self):
        installer = GitHubInstaller()
        owner, repo, skill_name, branch = installer.parse_ref(
            "anthropics/skills@frontend-design"
        )
        assert owner == "anthropics"
        assert repo == "skills"
        assert skill_name == "frontend-design"

    def test_invalid_ref_single_part(self):
        installer = GitHubInstaller()
        with pytest.raises(ValueError, match="Invalid GitHub reference"):
            installer.parse_ref("just-a-name")

    def test_default_branch_is_main(self):
        installer = GitHubInstaller()
        _, _, _, branch = installer.parse_ref("owner/repo")
        assert branch == "main"


class TestGitHubInstallerGetSkill:
    def test_get_skill_from_json(self):
        installer = GitHubInstaller()
        skill_json = json.dumps(
            {"name": "test-skill", "description": "A test skill", "steps": ["s1"]}
        )
        with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
            skill, source = installer.get_skill("owner/repo@test-skill")
        assert skill is not None
        assert skill.name == "test-skill"
        assert source == "github:owner/repo"

    def test_get_skill_from_md_fallback(self):
        installer = GitHubInstaller()
        skill_md = "---\nname: md-skill\ndescription: A markdown skill\n---\n# md-skill\n## Steps\n1. Do it\n"
        with (
            patch.object(installer, "_fetch_skill_json", return_value=None),
            patch.object(installer, "_fetch_skill_md", return_value=skill_md),
        ):
            skill, source = installer.get_skill("owner/repo@md-skill")
        assert skill is not None
        assert skill.name == "md-skill"
        assert source == "github:owner/repo"

    def test_get_skill_not_found(self):
        installer = GitHubInstaller()
        with (
            patch.object(installer, "_fetch_skill_json", return_value=None),
            patch.object(installer, "_fetch_skill_md", return_value=None),
        ):
            skill, msg = installer.get_skill("owner/repo@missing")
        assert skill is None
        assert "not found" in msg.lower() or "Skill not found" in msg

    def test_get_skill_invalid_ref(self):
        installer = GitHubInstaller()
        skill, msg = installer.get_skill("invalid")
        assert skill is None
        assert "Invalid" in msg

    def test_get_skill_sets_source(self):
        installer = GitHubInstaller()
        skill_json = json.dumps({"name": "s", "description": "d", "steps": ["s1"]})
        with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
            skill, _ = installer.get_skill("vercel-labs/agent-skills@react")
        assert skill.source == "github:vercel-labs/agent-skills"


class TestGitHubInstallerInstall:
    def test_install_success(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        installer = GitHubInstaller()
        skill_json = json.dumps(
            {"name": "gh-skill", "description": "From GitHub", "steps": ["s1"]}
        )
        with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
            ok, msg = installer.install("owner/repo@gh-skill", engine)
        assert ok
        assert "gh-skill" in msg
        assert engine.read("gh-skill") is not None

    def test_install_creates_lock_entry(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "skills-lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            installer = GitHubInstaller()
            skill_json = json.dumps(
                {"name": "locked-skill", "description": "Lock tracked", "steps": ["s1"]}
            )
            with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
                ok, _ = installer.install("owner/repo@locked-skill", engine)
            assert ok
            lock = SkillLockFile(path=lock_path)
            entry = lock.get("locked-skill")
            assert entry is not None
            assert entry.source_type == "github"
            assert entry.source == "owner/repo"

    def test_install_already_exists(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        engine.create(name="existing", description="Already here", steps=[])
        installer = GitHubInstaller()
        skill_json = json.dumps(
            {"name": "existing", "description": "From GitHub", "steps": ["s1"]}
        )
        with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
            ok, msg = installer.install("owner/repo@existing", engine)
        assert not ok
        assert "already exists" in msg

    def test_install_force_overwrites(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        engine.create(name="existing", description="Old", steps=[])
        installer = GitHubInstaller()
        skill_json = json.dumps(
            {"name": "existing", "description": "New from GitHub", "steps": ["new"]}
        )
        with patch.object(installer, "_fetch_skill_json", return_value=skill_json):
            ok, msg = installer.install("owner/repo@existing", engine, force=True)
        assert ok
        data = engine.read("existing")
        assert data["description"] == "New from GitHub"

    def test_install_not_found_on_github(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        installer = GitHubInstaller()
        with (
            patch.object(installer, "_fetch_skill_json", return_value=None),
            patch.object(installer, "_fetch_skill_md", return_value=None),
        ):
            ok, msg = installer.install("owner/repo@missing", engine)
        assert not ok

    def test_install_invalid_engine(self):
        installer = GitHubInstaller()
        ok, msg = installer.install("owner/repo@x", "not an engine")
        assert not ok
        assert "Invalid engine" in msg

    def test_install_invalid_ref(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        installer = GitHubInstaller()
        ok, msg = installer.install("bad-ref", engine)
        assert not ok
        assert "Invalid" in msg

    def test_install_validation_failure(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        installer = GitHubInstaller()
        bad_json = json.dumps({"name": "", "description": "", "steps": []})
        with patch.object(installer, "_fetch_skill_json", return_value=bad_json):
            ok, msg = installer.install("owner/repo@bad", engine)
        assert not ok
        assert "Validation failed" in msg


class TestGitHubInstallerCheckUpdate:
    def test_no_lock_entry(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            installer = GitHubInstaller()
            ok, msg = installer.check_update("unknown", engine)
        assert not ok
        assert "No GitHub source" in msg

    def test_non_github_source(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "hub-skill",
                LockEntry(source="hub", source_type="hub", source_url=""),
            )
            installer = GitHubInstaller()
            ok, msg = installer.check_update("hub-skill", engine)
        assert not ok
        assert "No GitHub source" in msg

    def test_skill_not_installed(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "gone",
                LockEntry(source="owner/repo", source_type="github", source_url=""),
            )
            installer = GitHubInstaller()
            ok, msg = installer.check_update("gone", engine)
        assert not ok
        assert "not installed" in msg


class TestGitHubInstallerUpdateSkill:
    def test_update_success(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            engine.create(name="updatable", description="v1", steps=["old"])
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "updatable",
                LockEntry(
                    source="owner/repo",
                    source_type="github",
                    source_url="https://github.com/owner/repo",
                    skill_folder_hash=_hash_skill_dir(skills_dir / "updatable"),
                    installed_at=_now_iso(),
                    updated_at=_now_iso(),
                ),
            )

            installer = GitHubInstaller()
            new_json = json.dumps(
                {"name": "updatable", "description": "v2 updated", "steps": ["new"]}
            )
            with patch.object(installer, "_fetch_skill_json", return_value=new_json):
                ok, msg = installer.update_skill("updatable", engine)
            assert ok
            assert "Updated" in msg
            data = engine.read("updatable")
            assert data["description"] == "v2 updated"

    def test_update_no_github_source(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            installer = GitHubInstaller()
            ok, msg = installer.update_skill("nope", engine)
        assert not ok

    def test_update_remote_not_found(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            engine.create(name="broken", description="desc", steps=["s1"])
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "broken",
                LockEntry(source="owner/repo", source_type="github", source_url=""),
            )
            installer = GitHubInstaller()
            with (
                patch.object(installer, "_fetch_skill_json", return_value=None),
                patch.object(installer, "_fetch_skill_md", return_value=None),
            ):
                ok, msg = installer.update_skill("broken", engine)
            assert not ok

    def test_update_preserves_installed_at(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine

        lock_path = tmp_path / "lock.json"
        skills_dir = tmp_path / "skills"
        engine = SkillEngine(skills_dir=skills_dir)
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            original_time = "2026-01-01T00:00:00+00:00"
            engine.create(name="tracked", description="v1", steps=["s1"])
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "tracked",
                LockEntry(
                    source="owner/repo",
                    source_type="github",
                    source_url="",
                    installed_at=original_time,
                    updated_at=original_time,
                ),
            )
            installer = GitHubInstaller()
            new_json = json.dumps(
                {"name": "tracked", "description": "v2", "steps": ["s2"]}
            )
            with patch.object(installer, "_fetch_skill_json", return_value=new_json):
                ok, _ = installer.update_skill("tracked", engine)
            assert ok
            entry = lock.get("tracked")
            assert entry.installed_at == original_time
            assert entry.updated_at != original_time


class TestHubClientUsesHttpx:
    def test_client_uses_httpx(self):
        client = HubClient()
        assert hasattr(client, "_http")

    def test_fetch_json_uses_httpx(self):
        client = HubClient()
        with patch.object(client._http, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = [{"name": "test"}]
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            result = client._fetch_json("index.json")
            assert result == [{"name": "test"}]
            mock_get.assert_called_once()

    def test_fetch_text_uses_httpx(self):
        client = HubClient()
        with patch.object(client._http, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "---\nname: test\n---\n# test"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            result = client._fetch_text("skills/test/SKILL.md")
            assert result is not None
            assert "test" in result


class TestHubInstallDoesNotBlockWarnings:
    def test_install_succeeds_with_warnings(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()
        skill = SkillData(name="warn-skill", description="short", steps=[])
        with patch.object(client, "get_skill", return_value=skill):
            ok, msg = client.install("warn-skill", engine)
        assert ok
        assert "warn-skill" in msg

    def test_install_creates_lock_entry(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine
        from sediman.skills.format import SkillData

        lock_path = tmp_path / "lock.json"
        engine = SkillEngine(skills_dir=tmp_path / "skills")
        with patch("sediman.skills.hub._LOCK_FILE", lock_path):
            client = HubClient()
            skill = SkillData(
                name="lock-test", description="Lock test skill", steps=["s1"]
            )
            with patch.object(client, "get_skill", return_value=skill):
                ok, _ = client.install("lock-test", engine)
            assert ok
            lock = SkillLockFile(path=lock_path)
            entry = lock.get("lock-test")
            assert entry is not None
            assert entry.source_type == "hub"

    def test_install_still_blocks_on_errors(self, tmp_path: Path):
        from sediman.skills.engine import SkillEngine
        from sediman.skills.format import SkillData

        engine = SkillEngine(skills_dir=tmp_path / "skills")
        client = HubClient()
        bad_skill = SkillData(name="", description="", steps=[])
        with patch.object(client, "get_skill", return_value=bad_skill):
            ok, msg = client.install("bad", engine)
        assert not ok
        assert "validation failed" in msg.lower()


class TestHubClientCachingWithTTL:
    def test_cache_expires(self):
        client = HubClient()
        mock_index = [{"name": "a"}]
        with (
            patch.object(client, "_fetch_json", return_value=mock_index),
            patch("sediman.skills.hub._CACHE_TTL", 0.0),
        ):
            import sediman.skills.hub as hub_mod

            hub_mod._HUB_CACHE = None
            hub_mod._CACHE_TS = 0.0
            r1 = client._get_index()
            assert len(r1) == 1


class TestHubBrowseWithSourceField:
    def test_browse_sets_source_to_hub(self):
        client = HubClient()
        mock_index = [{"name": "a", "description": "d", "category": "c"}]
        with patch.object(client, "_get_index", return_value=mock_index):
            results = client.browse()
        assert results[0].source == "hub"
