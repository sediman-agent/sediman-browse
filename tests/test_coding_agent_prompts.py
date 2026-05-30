from __future__ import annotations

import pytest

from sediman.agent.coding_agent.prompts import (
    build_system_prompt,
    build_classification_prompt,
    _BASE_SYSTEM_PROMPT,
)
from sediman.agent.coding_agent.types import ProjectInfo


class TestSystemPrompt:
    def test_base_prompt_is_large(self):
        assert len(_BASE_SYSTEM_PROMPT) > 10000

    def test_base_prompt_contains_core_sections(self):
        assert "Core Principles" in _BASE_SYSTEM_PROMPT
        assert "Task-Specific Workflows" in _BASE_SYSTEM_PROMPT
        assert "Anti-Patterns" in _BASE_SYSTEM_PROMPT
        assert "Testing Strategy" in _BASE_SYSTEM_PROMPT
        assert "Security Rules" in _BASE_SYSTEM_PROMPT
        assert "When to Use clarify" in _BASE_SYSTEM_PROMPT
        assert "Structured Plan Format" in _BASE_SYSTEM_PROMPT
        assert "Tools Reference" in _BASE_SYSTEM_PROMPT
        assert "Error Recovery Protocol" in _BASE_SYSTEM_PROMPT
        assert "Git Etiquette" in _BASE_SYSTEM_PROMPT

    def test_base_prompt_contains_bug_fix_workflow(self):
        assert "Fixing a Bug" in _BASE_SYSTEM_PROMPT
        assert "Adding a Feature" in _BASE_SYSTEM_PROMPT
        assert "Refactoring" in _BASE_SYSTEM_PROMPT
        assert "Debugging" in _BASE_SYSTEM_PROMPT
        assert "Code Review" in _BASE_SYSTEM_PROMPT

    def test_base_prompt_contains_anti_patterns(self):
        assert "Blind edits" in _BASE_SYSTEM_PROMPT
        assert "Over-engineering" in _BASE_SYSTEM_PROMPT
        assert "Unrelated refactoring" in _BASE_SYSTEM_PROMPT
        assert "Silent failures" in _BASE_SYSTEM_PROMPT
        assert "Guessing at APIs" in _BASE_SYSTEM_PROMPT

    def test_base_prompt_contains_security_rules(self):
        assert "Never commit secrets" in _BASE_SYSTEM_PROMPT
        assert "Validate untrusted input" in _BASE_SYSTEM_PROMPT
        assert "Don't log sensitive data" in _BASE_SYSTEM_PROMPT

    def test_base_prompt_contains_all_tools(self):
        assert "read_file" in _BASE_SYSTEM_PROMPT
        assert "write_file" in _BASE_SYSTEM_PROMPT
        assert "patch" in _BASE_SYSTEM_PROMPT
        assert "list_files" in _BASE_SYSTEM_PROMPT
        assert "search_files" in _BASE_SYSTEM_PROMPT
        assert "glob" in _BASE_SYSTEM_PROMPT
        assert "terminal" in _BASE_SYSTEM_PROMPT
        assert "git_status" in _BASE_SYSTEM_PROMPT
        assert "git_diff" in _BASE_SYSTEM_PROMPT
        assert "git_log" in _BASE_SYSTEM_PROMPT
        assert "git_commit" in _BASE_SYSTEM_PROMPT
        assert "git_branch" in _BASE_SYSTEM_PROMPT
        assert "web_search" in _BASE_SYSTEM_PROMPT
        assert "web_fetch" in _BASE_SYSTEM_PROMPT
        assert "clarify" in _BASE_SYSTEM_PROMPT
        assert "todo" in _BASE_SYSTEM_PROMPT


class TestBuildSystemPrompt:
    def test_no_project_info(self):
        prompt = build_system_prompt(project_info=None, task="")
        assert "Project Context" not in prompt

    def test_with_project_info(self):
        info = ProjectInfo(
            project_type="Python",
            language="Python",
            lint_commands=["ruff check ."],
            test_commands=["pytest"],
        )
        prompt = build_system_prompt(project_info=info, task="")
        assert "Project Context" in prompt
        assert "Python" in prompt
        assert "ruff check" in prompt
        assert "pytest" in prompt

    def test_with_task(self):
        prompt = build_system_prompt(project_info=None, task="fix the bug")
        assert "Current Task" in prompt
        assert "fix the bug" in prompt

    def test_with_conventions(self):
        info = ProjectInfo(
            project_type="Python",
            language="Python",
            conventions={"line_length": "120", "indent_size": "4"},
        )
        prompt = build_system_prompt(project_info=info, task="")
        assert "line_length" in prompt
        assert "120" in prompt

    def test_with_project_instructions(self):
        info = ProjectInfo(
            project_type="Python",
            language="Python",
            project_instructions="Use async/await for all I/O",
        )
        prompt = build_system_prompt(project_info=info, task="")
        assert "Project Instructions" in prompt
        assert "async/await" in prompt


class TestClassificationPrompt:
    def test_classification_prompt_contains_task(self):
        prompt = build_classification_prompt("install express")
        assert "install express" in prompt
        assert "Category:" in prompt

    def test_classification_prompt_has_many_examples(self):
        prompt = build_classification_prompt("test task")
        examples = prompt.count("→")
        assert examples >= 30

    def test_classification_prompt_has_categories(self):
        prompt = build_classification_prompt("test task")
        assert "**code**" in prompt.lower() or "code" in prompt.lower()
        assert "browser" in prompt.lower()
        assert "conversational" in prompt.lower()

    def test_classification_prompt_has_rules(self):
        prompt = build_classification_prompt("test task")
        assert "reading/writing local files" in prompt.lower()
        assert "PRIMARY action" in prompt

    def test_classification_prompt_code_examples(self):
        prompt = build_classification_prompt("test task")
        assert "add dark mode toggle" in prompt
        assert "write unit tests for the UserService" in prompt
        assert "set up a new Next.js project" in prompt

    def test_classification_prompt_browser_examples(self):
        prompt = build_classification_prompt("test task")
        assert "find me a flight from NYC to London" in prompt
        assert "order pizza from dominos.com" in prompt
        assert "fill out this job application form" in prompt

    def test_classification_prompt_conversational_examples(self):
        prompt = build_classification_prompt("test task")
        assert "how do I use React hooks" in prompt
        assert "what does git status do" in prompt
