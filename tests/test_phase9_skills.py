from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from sediman.skills.format import (
    StepData,
    SkillData,
    parse_skill_json,
    parse_skill_md,
    _extract_examples_from_body,
    _extract_steps_from_body,
)


class TestStepDataNewFields:
    def test_wait_for_field(self):
        step = StepData(description="Wait for modal", wait_for=".modal")
        assert step.wait_for == ".modal"

    def test_condition_field(self):
        step = StepData(description="Click if visible", condition="element.visible")
        assert step.condition == "element.visible"

    def test_on_error_field(self):
        step = StepData(description="Click button", on_error="abort")
        assert step.on_error == "abort"

    def test_screenshot_verify_field(self):
        step = StepData(description="Verify page", screenshot_verify="checkout button present")
        assert step.screenshot_verify == "checkout button present"

    def test_to_json_includes_new_fields(self):
        step = StepData(
            description="Click submit",
            action_type="click",
            selector="#submit",
            wait_for=".success",
            on_error="abort",
        )
        d = step.to_json()
        assert d["wait_for"] == ".success"
        assert d["on_error"] == "abort"

    def test_to_json_omits_empty_new_fields(self):
        step = StepData(description="Navigate", action_type="navigate")
        d = step.to_json()
        assert "wait_for" not in d
        assert "condition" not in d

    def test_from_json_new_fields(self):
        data = {
            "description": "Click",
            "action_type": "click",
            "wait_for": ".result",
            "on_error": "continue",
        }
        step = StepData.from_json(data)
        assert step.wait_for == ".result"
        assert step.on_error == "continue"


class TestSkillDataNewFields:
    def test_inputs_outputs(self):
        skill = SkillData(
            name="test",
            description="test skill",
            inputs=[{"name": "query", "description": "search query", "required": "true"}],
            outputs=[{"name": "results", "description": "search results"}],
        )
        assert len(skill.inputs) == 1
        assert skill.inputs[0]["name"] == "query"

    def test_dependencies(self):
        skill = SkillData(
            name="test",
            description="test",
            dependencies=["skill-a", "skill-b"],
        )
        assert len(skill.dependencies) == 2

    def test_retry_policy(self):
        skill = SkillData(
            name="test",
            description="test",
            retry_policy="retry_on_error",
            timeout_seconds=60,
        )
        assert skill.retry_policy == "retry_on_error"
        assert skill.timeout_seconds == 60

    def test_execution_metrics(self):
        skill = SkillData(
            name="test",
            description="test",
            execution_count=10,
            success_rate=0.85,
            avg_duration_ms=2500,
        )
        assert skill.execution_count == 10
        assert skill.success_rate == 0.85

    def test_to_json_includes_new_fields(self):
        skill = SkillData(
            name="test",
            description="test",
            inputs=[{"name": "x"}],
            retry_policy="retry_once",
            success_rate=0.9,
            execution_count=5,
        )
        d = skill.to_json()
        assert d["inputs"] == [{"name": "x"}]
        assert d["retry_policy"] == "retry_once"
        assert d["success_rate"] == 0.9
        assert d["execution_count"] == 5

    def test_parse_skill_json_new_fields(self):
        data = json.dumps({
            "name": "search",
            "description": "Search the web",
            "inputs": [{"name": "query", "required": "true"}],
            "outputs": [{"name": "results"}],
            "dependencies": ["browser"],
            "retry_policy": "always_retry",
            "timeout_seconds": 30,
            "examples": ["search for python tutorials"],
        })
        skill = parse_skill_json(data)
        assert skill is not None
        assert skill.inputs is not None
        assert skill.inputs[0]["name"] == "query"
        assert skill.dependencies == ["browser"]
        assert skill.retry_policy == "always_retry"
        assert skill.timeout_seconds == 30


class TestSkillMdNewSections:
    def test_to_skill_md_includes_structured_steps(self):
        skill = SkillData(
            name="buy-item",
            description="Buy an item",
            structured_steps=[
                {"action_type": "navigate", "description": "Go to shop", "url": "https://shop.com"},
                {"action_type": "click", "description": "Click buy", "selector": "#buy-btn", "expected_outcome": "Cart page"},
            ],
        )
        md = skill.to_skill_md()
        assert "## Structured Steps" in md
        assert "**navigate**" in md
        assert "**click**" in md
        assert "`#buy-btn`" in md

    def test_to_skill_md_includes_inputs_outputs(self):
        skill = SkillData(
            name="test",
            description="test",
            inputs=[{"name": "query", "description": "search text", "required": "true"}],
            outputs=[{"name": "results", "description": "found items"}],
        )
        md = skill.to_skill_md()
        assert "## Inputs" in md
        assert "`query` (true)" in md
        assert "## Outputs" in md

    def test_to_skill_md_includes_examples(self):
        skill = SkillData(
            name="test",
            description="test",
            examples=["search for shoes", "find cheap laptops"],
        )
        md = skill.to_skill_md()
        assert "## Examples" in md
        assert "search for shoes" in md

    def test_to_skill_md_includes_dependencies(self):
        skill = SkillData(
            name="test",
            description="test",
            dependencies=["browser-skill", "search-skill"],
        )
        md = skill.to_skill_md()
        assert "## Dependencies" in md


class TestExtractExamplesFromBody:
    def test_extracts_examples(self):
        body = "## Description\nA skill\n\n## Examples\n- search for shoes\n- find laptops\n\n## Notes\nstuff"
        examples = _extract_examples_from_body(body)
        assert examples is not None
        assert len(examples) == 2
        assert "search for shoes" in examples[0]

    def test_no_examples_returns_none(self):
        body = "## Description\nA skill\n\n## Steps\n1. Do something"
        examples = _extract_examples_from_body(body)
        assert examples is None


class TestParseSkillMdNewFields:
    def test_parse_md_with_examples(self):
        content = """---
name: search-web
description: "Search the web"
metadata:
  retry_policy: retry_once
  timeout_seconds: 45
  inputs:
    - name: query
      required: "true"
---

# search-web

Search the web for information.

## Examples
- search for python docs
- find recent news
"""
        skill = parse_skill_md(content)
        assert skill is not None
        assert skill.name == "search-web"
        assert skill.retry_policy == "retry_once"
        assert skill.timeout_seconds == 45
        assert skill.examples is not None
        assert len(skill.examples) == 2


class TestSkillEngineNewFields:
    def test_create_with_new_fields(self):
        import tempfile
        import shutil

        tmp = tempfile.mkdtemp()
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=Path(tmp), use_cache=False)
            result = engine.create(
                name="test-skill",
                description="A test skill",
                steps=["Step 1", "Step 2"],
                inputs=[{"name": "query", "required": "true"}],
                outputs=[{"name": "result"}],
                retry_policy="retry_once",
                timeout_seconds=30,
            )
            assert result["inputs"] == [{"name": "query", "required": "true"}]
            assert result["retry_policy"] == "retry_once"
            assert result["timeout_seconds"] == 30
        finally:
            shutil.rmtree(tmp)

    def test_read_preserves_new_fields(self):
        import tempfile
        import shutil

        tmp = tempfile.mkdtemp()
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=Path(tmp), use_cache=False)
            engine.create(
                name="test-skill",
                description="test",
                steps=["step1"],
                dependencies=["dep-a"],
                success_rate=0.9,
            )
            result = engine.read("test-skill")
            assert result is not None
            assert result["dependencies"] == ["dep-a"]
            assert result["success_rate"] == 0.9
        finally:
            shutil.rmtree(tmp)


class TestCanExecuteProgrammatically:
    def test_navigate_only(self):
        from sediman.skills.executor import _can_execute_programmatically
        steps = [{"action_type": "navigate", "url": "http://example.com"}]
        assert _can_execute_programmatically(steps) is True

    def test_mixed_supported(self):
        from sediman.skills.executor import _can_execute_programmatically
        steps = [
            {"action_type": "navigate", "url": "http://example.com"},
            {"action_type": "click", "selector": "#btn"},
            {"action_type": "input", "selector": "#input", "text": "hello"},
        ]
        assert _can_execute_programmatically(steps) is True

    def test_unsupported_action(self):
        from sediman.skills.executor import _can_execute_programmatically
        steps = [{"action_type": "custom_action", "description": "do something"}]
        assert _can_execute_programmatically(steps) is False

    def test_empty_steps(self):
        from sediman.skills.executor import _can_execute_programmatically
        assert _can_execute_programmatically([]) is False


class TestFormatStepsForPrompt:
    def test_structured_steps_with_new_fields(self):
        from sediman.skills.executor import _format_steps_for_prompt
        steps = [
            {"description": "Navigate to shop", "url": "https://shop.com"},
            {"description": "Click buy", "selector": "#buy", "expected_outcome": "Cart page"},
        ]
        result = _format_steps_for_prompt(steps)
        assert "Navigate to shop" in result
        assert "URL: https://shop.com" in result
        assert "Selector: #buy" in result
        assert "Expected: Cart page" in result
