from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from sediman.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestMainGroup:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Sediman" in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert "0.1.1" in result.output


class TestSkillCommands:
    def test_skill_list_empty(self, runner, tmp_sediman_dir):
        with patch("sediman.skills.engine.SKILLS_DIR", tmp_sediman_dir / "skills"):
            result = runner.invoke(main, ["skill", "list"])
        assert result.exit_code == 0
        assert "No skills found" in result.output

    def test_skill_list_with_skills(self, runner, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.SKILLS_DIR", skills_dir):
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="list-test", description="test desc", steps=["s1"])
            result = runner.invoke(main, ["skill", "list"])
        assert result.exit_code == 0
        assert "list-test" in result.output

    def test_skill_show_existing(self, runner, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.SKILLS_DIR", skills_dir):
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="show-me", description="visible skill", steps=["step one"])
            result = runner.invoke(main, ["skill", "show", "show-me"])
        assert result.exit_code == 0
        assert "show-me" in result.output
        assert "visible skill" in result.output
        assert "1. step one" in result.output

    def test_skill_show_missing(self, runner, tmp_sediman_dir):
        with patch("sediman.skills.engine.SKILLS_DIR", tmp_sediman_dir / "skills"):
            result = runner.invoke(main, ["skill", "show", "nonexistent"])
        assert result.exit_code == 1

    def test_skill_delete_existing(self, runner, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.SKILLS_DIR", skills_dir):
            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="del-me", description="bye", steps=[])
            result = runner.invoke(main, ["skill", "delete", "--yes", "del-me"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_skill_delete_missing(self, runner, tmp_sediman_dir):
        with patch("sediman.skills.engine.SKILLS_DIR", tmp_sediman_dir / "skills"):
            result = runner.invoke(main, ["skill", "delete", "nope"])
        assert result.exit_code == 1


class TestScheduleCommands:
    def test_schedule_list_empty(self, runner, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = runner.invoke(main, ["schedule", "list"])
        assert result.exit_code == 0
        assert "No scheduled tasks" in result.output

    def test_schedule_add_and_list(self, runner, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            result = runner.invoke(main, ["schedule", "add", "0 * * * *", "test task"])
            assert result.exit_code == 0
            assert "Scheduled" in result.output

            result = runner.invoke(main, ["schedule", "list"])
            assert "test task" in result.output

    def test_schedule_remove(self, runner, tmp_sediman_dir):
        from sediman.scheduler.cron import CronManager

        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            job_id = cron.add_job(cron_expr="0 * * * *", task="remove me")
            result = runner.invoke(main, ["schedule", "remove", "--yes", job_id])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_schedule_remove_missing(self, runner, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = runner.invoke(main, ["schedule", "remove", "fake"])
        assert result.exit_code == 1


class TestMemoryCommand:
    def test_memory_empty(self, runner, tmp_sediman_dir):
        with patch("sediman.memory.prompt.MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
             patch("sediman.memory.prompt.USER_FILE", tmp_sediman_dir / "USER.md"):
            result = runner.invoke(main, ["memory"])
        assert "No memory stored yet" in result.output

    def test_memory_with_content(self, runner, tmp_sediman_dir):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text("I remember things")
        result = runner.invoke(main, ["memory"])
        assert "I remember things" in result.output
