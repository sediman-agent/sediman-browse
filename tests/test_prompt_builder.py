from __future__ import annotations

from unittest.mock import patch

import pytest

from sediman.agent.prompts.builder import PromptBuilder, _template_cache


@pytest.fixture(autouse=True)
def _clear_template_cache():
    _template_cache.pop("system_turbo.md", None)
    yield
    _template_cache.pop("system_turbo.md", None)


class TestTurboModePrompt:
    def test_turbo_template_loads(self):
        b = PromptBuilder(turbo_mode=True)
        prompt = b.build_system_prompt()
        assert "Turbo mode" in prompt
        assert "browser" in prompt.lower()

    def test_turbo_template_has_action_format(self):
        b = PromptBuilder(turbo_mode=True)
        prompt = b.build_system_prompt()
        assert "action_format" in prompt or "browser actions" in prompt.lower()

    def test_turbo_excludes_persona_when_no_soul(self, tmp_path):
        with patch("sediman.agent.prompts.builder.SOUL_FILE", tmp_path / "SOUL.md"):
            b = PromptBuilder(turbo_mode=True)
            prompt = b.build_system_prompt()
            assert "<persona>" not in prompt

    def test_turbo_includes_skills(self):
        b = PromptBuilder(turbo_mode=True)
        prompt = b.build_system_prompt(skill_summaries="my-skill: does stuff")
        assert "my-skill" in prompt
        assert "<available_skills>" in prompt

    def test_turbo_excludes_project_context(self, tmp_path):
        with patch("sediman.agent.prompts.builder.SOUL_FILE", tmp_path / "SOUL.md"), \
             patch("sediman.agent.prompts.builder.CONTEXT_FILE", tmp_path / "CONTEXT.md"):
            (tmp_path / "CONTEXT.md").write_text("secret project data")
            b = PromptBuilder(turbo_mode=True)
            prompt = b.build_system_prompt()
            assert "secret project data" not in prompt

    def test_turbo_excludes_memory_context(self):
        b = PromptBuilder(turbo_mode=True)
        prompt = b.build_system_prompt(memory_context="remember user likes pizza")
        assert "pizza" not in prompt

    def test_turbo_mode_name(self):
        b = PromptBuilder(turbo_mode=True)
        assert b._template_name == "system_turbo.md"

    def test_turbo_is_not_flash(self):
        b = PromptBuilder(turbo_mode=True)
        assert b.flash_mode is False
        assert b.turbo_mode is True

    def test_flash_mode_name(self):
        b = PromptBuilder(flash_mode=True)
        assert b._template_name == "system_flash.md"

    def test_full_mode_name(self):
        b = PromptBuilder()
        assert b._template_name == "system_full.md"

    def test_full_mode_includes_persona(self, tmp_path):
        soul = tmp_path / "SOUL.md"
        soul.write_text("I am a test agent.")
        with patch("sediman.agent.prompts.builder.SOUL_FILE", soul):
            b = PromptBuilder()
            prompt = b.build_system_prompt()
            assert "<persona>" in prompt
            assert "test agent" in prompt

    def test_full_mode_includes_memory(self):
        b = PromptBuilder()
        prompt = b.build_system_prompt(memory_context="user prefers dark mode")
        assert "dark mode" in prompt

    def test_full_mode_includes_project_context(self, tmp_path):
        ctx = tmp_path / "CONTEXT.md"
        ctx.write_text("project-x backend")
        with patch("sediman.agent.prompts.builder.CONTEXT_FILE", ctx), \
             patch("sediman.agent.prompts.builder.SOUL_FILE", tmp_path / "SOUL.md"):
            b = PromptBuilder()
            prompt = b.build_system_prompt()
            assert "project-x" in prompt

    def test_skill_executor_prompt_includes_verification(self):
        b = PromptBuilder()
        prompt = b.build_skill_executor_prompt(
            skill_name="test-skill",
            description="A test skill",
            steps=["navigate to google.com", "search for python"],
            verification="page shows python results",
        )
        assert "test-skill" in prompt
        assert "python results" in prompt

    def test_skill_executor_prompt_default_verification(self):
        b = PromptBuilder()
        prompt = b.build_skill_executor_prompt(
            skill_name="s",
            description="d",
            steps=["step 1"],
        )
        assert "expected outcome" in prompt.lower()
