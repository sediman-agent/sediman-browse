from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sediman.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_skills(tmp_sediman_dir: Path):
    skills_dir = tmp_sediman_dir / "skills"
    with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
        yield skills_dir


class TestSkillInstallFromGitHub:
    def test_install_from_github(self, runner: CliRunner, tmp_skills: Path):
        skill_json = json.dumps(
            {"name": "gh-test", "description": "From GitHub", "steps": ["s1"]}
        )
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
        ):
            mock_installer = MagicMock()
            mock_installer.install.return_value = (
                True,
                "Installed gh-test from owner/repo",
            )
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "install", "owner/repo@gh-test"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_install_from_github_failure(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
        ):
            mock_installer = MagicMock()
            mock_installer.install.return_value = (False, "Skill not found")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "install", "owner/repo@missing"])
        assert result.exit_code == 1

    def test_install_with_force(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
        ):
            mock_installer = MagicMock()
            mock_installer.install.return_value = (True, "Installed with force")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(
                main, ["skill", "install", "owner/repo@skill", "--force"]
            )
        assert result.exit_code == 0

    def test_install_auto_detects_github_for_slash_ref(
        self, runner: CliRunner, tmp_skills: Path
    ):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockGH,
            patch("sediman.skills.hub.HubClient") as MockHub,
        ):
            mock_gh = MagicMock()
            mock_gh.install.return_value = (True, "OK")
            MockGH.return_value = mock_gh
            runner.invoke(main, ["skill", "install", "owner/repo@skill"])
            MockGH.assert_called_once()
            MockHub.assert_not_called()


class TestSkillInstallFromHub:
    def test_install_from_hub_by_name(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.HubClient") as MockHub,
        ):
            mock_client = MagicMock()
            mock_client.install.return_value = (True, "Installed hub-skill")
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "install", "hub-skill"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_install_from_hub_with_flag(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.HubClient") as MockHub,
            patch("sediman.skills.hub.GitHubInstaller") as MockGH,
        ):
            mock_client = MagicMock()
            mock_client.install.return_value = (True, "Installed")
            MockHub.return_value = mock_client
            result = runner.invoke(
                main, ["skill", "install", "some-name", "--from", "hub"]
            )
        assert result.exit_code == 0
        MockHub.assert_called_once()
        MockGH.assert_not_called()

    def test_install_from_hub_failure(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.HubClient") as MockHub,
        ):
            mock_client = MagicMock()
            mock_client.install.return_value = (False, "Not found")
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "install", "missing"])
        assert result.exit_code == 1


class TestSkillSearch:
    def test_search_with_results(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import HubSkillSummary

        with patch("sediman.skills.hub.HubClient") as MockHub:
            mock_client = MagicMock()
            mock_client.search.return_value = [
                HubSkillSummary(
                    name="web-scraper", description="Scrape websites", category="data"
                ),
            ]
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "search", "scrape"])
        assert result.exit_code == 0
        assert "web-scraper" in result.output

    def test_search_no_results(self, runner: CliRunner, tmp_skills: Path):
        with patch("sediman.skills.hub.HubClient") as MockHub:
            mock_client = MagicMock()
            mock_client.search.return_value = []
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "search", "nonexistent"])
        assert result.exit_code == 0
        assert "No skills" in result.output

    def test_search_with_category(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import HubSkillSummary

        with patch("sediman.skills.hub.HubClient") as MockHub:
            mock_client = MagicMock()
            mock_client.browse.return_value = [
                HubSkillSummary(name="a", description="scrape tool", category="data"),
            ]
            MockHub.return_value = mock_client
            result = runner.invoke(
                main, ["skill", "search", "scrape", "--category", "data"]
            )
        assert result.exit_code == 0


class TestSkillUpdate:
    def test_update_specific_skill(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_installer = MagicMock()
            mock_installer.update_skill.return_value = (True, "Updated skill")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "update", "my-skill"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_update_all(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import LockEntry

        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_lock = MagicMock()
            mock_lock.list_all.return_value = {
                "a": LockEntry(source="o/r", source_type="github", source_url=""),
                "b": LockEntry(source="o/r2", source_type="github", source_url=""),
            }
            MockLock.return_value = mock_lock
            mock_installer = MagicMock()
            mock_installer.update_skill.return_value = (True, "Updated")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "update", "--all"])
        assert result.exit_code == 0
        assert mock_installer.update_skill.call_count == 2

    def test_update_no_name_no_all(self, runner: CliRunner, tmp_skills: Path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills):
            result = runner.invoke(main, ["skill", "update"])
        assert result.exit_code == 1

    def test_update_failure(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_installer = MagicMock()
            mock_installer.update_skill.return_value = (False, "No GitHub source")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "update", "local-skill"])
        assert result.exit_code == 1


class TestSkillOutdated:
    def test_outdated_with_updates(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import LockEntry

        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_lock = MagicMock()
            mock_lock.list_all.return_value = {
                "old-skill": LockEntry(
                    source="o/r", source_type="github", source_url=""
                ),
            }
            MockLock.return_value = mock_lock
            mock_installer = MagicMock()
            mock_installer.check_update.return_value = (True, "Update available")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "outdated"])
        assert result.exit_code == 0
        assert "old-skill" in result.output

    def test_outdated_all_up_to_date(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import LockEntry

        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.GitHubInstaller") as MockInstaller,
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_lock = MagicMock()
            mock_lock.list_all.return_value = {
                "fresh": LockEntry(source="o/r", source_type="github", source_url=""),
            }
            MockLock.return_value = mock_lock
            mock_installer = MagicMock()
            mock_installer.check_update.return_value = (False, "Up to date")
            MockInstaller.return_value = mock_installer
            result = runner.invoke(main, ["skill", "outdated"])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_outdated_no_tracked_skills(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.SkillLockFile") as MockLock,
        ):
            mock_lock = MagicMock()
            mock_lock.list_all.return_value = {}
            MockLock.return_value = mock_lock
            result = runner.invoke(main, ["skill", "outdated"])
        assert result.exit_code == 0
        assert "No tracked" in result.output


class TestSkillInfo:
    def test_skill_info_existing(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.engine import SkillEngine

        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills):
            engine = SkillEngine(skills_dir=tmp_skills)
            engine.create(
                name="info-test", description="Test skill for info", steps=["s1"]
            )
            result = runner.invoke(main, ["skill", "info", "info-test"])
        assert result.exit_code == 0
        assert "info-test" in result.output
        assert "Test skill for info" in result.output

    def test_skill_info_missing(self, runner: CliRunner, tmp_skills: Path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills):
            result = runner.invoke(main, ["skill", "info", "nonexistent"])
        assert result.exit_code == 1

    def test_skill_info_with_lock_entry(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.engine import SkillEngine
        from sediman.skills.hub import LockEntry, SkillLockFile

        lock_path = tmp_skills.parent / "skills-lock.json"
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub._LOCK_FILE", lock_path),
        ):
            engine = SkillEngine(skills_dir=tmp_skills)
            engine.create(name="tracked", description="Tracked skill", steps=["s1"])
            lock = SkillLockFile(path=lock_path)
            lock.set(
                "tracked",
                LockEntry(
                    source="owner/repo",
                    source_type="github",
                    source_url="https://github.com/owner/repo",
                    installed_at="2026-01-01T00:00:00+00:00",
                ),
            )
            result = runner.invoke(main, ["skill", "info", "tracked"])
        assert result.exit_code == 0
        assert "owner/repo" in result.output
        assert "github" in result.output


class TestLegacyHubCommands:
    def test_hub_browse(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import HubSkillSummary

        with patch("sediman.skills.hub.HubClient") as MockHub:
            mock_client = MagicMock()
            mock_client.browse.return_value = [
                HubSkillSummary(name="a", description="desc", category="c"),
            ]
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "hub", "browse"])
        assert result.exit_code == 0
        assert "a" in result.output

    def test_hub_install(self, runner: CliRunner, tmp_skills: Path):
        with (
            patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_skills),
            patch("sediman.skills.hub.HubClient") as MockHub,
        ):
            mock_client = MagicMock()
            mock_client.install.return_value = (True, "Installed legacy-skill")
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "hub", "install", "legacy-skill"])
        assert result.exit_code == 0
        assert "Installed" in result.output

    def test_hub_search(self, runner: CliRunner, tmp_skills: Path):
        from sediman.skills.hub import HubSkillSummary

        with patch("sediman.skills.hub.HubClient") as MockHub:
            mock_client = MagicMock()
            mock_client.search.return_value = [
                HubSkillSummary(name="found", description="desc", category="c"),
            ]
            MockHub.return_value = mock_client
            result = runner.invoke(main, ["skill", "hub", "search", "test"])
        assert result.exit_code == 0
        assert "found" in result.output


class TestSkillInstallBundled:
    def test_install_bundled_no_dir(self, runner: CliRunner, tmp_sediman_dir: Path):
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_sediman_dir / "skills"):
            result = runner.invoke(main, ["skill", "install-bundled"])
        assert result.exit_code == 1 or "No bundled" in result.output
