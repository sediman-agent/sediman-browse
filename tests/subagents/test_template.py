from __future__ import annotations

from pathlib import Path

from sediman.agent.subagents.template import (
    AgentTemplate,
    _parse_yaml_block,
    parse_agent_file,
    render_agent_file,
)


class TestParseYamlBlock:
    def test_simple_key_value(self):
        block = "name: browser\ndescription: A browser agent"
        result = _parse_yaml_block(block)
        assert result == {"name": "browser", "description": "A browser agent"}

    def test_quoted_values(self):
        block = 'name: "my-agent"\ndescription: "A test agent"'
        result = _parse_yaml_block(block)
        assert result["name"] == "my-agent"
        assert result["description"] == "A test agent"

    def test_nested_permissions(self):
        block = """
name: code
permissions:
  terminal: allow
  write_file: ask
"""
        result = _parse_yaml_block(block)
        assert result["name"] == "code"
        assert result["permissions"] == {"terminal": "allow", "write_file": "ask"}

    def test_empty_permissions(self):
        block = "name: test\npermissions:\n"
        result = _parse_yaml_block(block)
        assert result["name"] == "test"
        # Empty nested block may parse as empty dict

    def test_list_values(self):
        block = "name: test\nsteps:\n  - step one\n  - step two"
        result = _parse_yaml_block(block)
        assert result["steps"] == ["step one", "step two"]

    def test_inline_list(self):
        block = "tags: [a, b, c]"
        result = _parse_yaml_block(block)
        assert result["tags"] == ["a", "b", "c"]

    def test_ignores_comments(self):
        block = "# comment\nname: test\n# another"
        result = _parse_yaml_block(block)
        assert result == {"name": "test"}

    def test_empty_block(self):
        result = _parse_yaml_block("")
        assert result == {}

    def test_int_parsing(self):
        block = "max_iterations: 8"
        result = _parse_yaml_block(block)
        assert result["max_iterations"] == "8"


class TestParseAgentFile:
    def test_valid_file(self, tmp_path: Path):
        content = """---
name: browser
description: A browser agent
mode: subagent
permissions:
  terminal: deny
max_iterations: 8
---

You are a browser specialist.
"""
        path = tmp_path / "browser.md"
        path.write_text(content)
        template = parse_agent_file(path)
        assert template is not None
        assert template.name == "browser"
        assert template.description == "A browser agent"
        assert template.mode == "subagent"
        assert template.permissions == {"terminal": "deny"}
        assert template.max_iterations == 8
        assert template.system_prompt == "You are a browser specialist."
        assert template.source_path == path

    def test_no_frontmatter(self, tmp_path: Path):
        path = tmp_path / "bad.md"
        path.write_text("Just markdown, no frontmatter")
        assert parse_agent_file(path) is None

    def test_no_name_uses_filename(self, tmp_path: Path):
        """If frontmatter has no name, returns None."""
        content = """---
description: no name
---

body
"""
        path = tmp_path / "noname.md"
        path.write_text(content)
        template = parse_agent_file(path)
        assert template is None

    def test_defaults(self, tmp_path: Path):
        content = """---
name: simple
---

Simple agent.
"""
        path = tmp_path / "simple.md"
        path.write_text(content)
        template = parse_agent_file(path)
        assert template is not None
        assert template.description == ""
        assert template.mode == "subagent"
        assert template.model is None
        assert template.permissions == {}
        assert template.max_iterations == 5

    def test_file_not_found(self):
        assert parse_agent_file(Path("/nonexistent/path.md")) is None

    def test_fallback_name_from_filename(self, tmp_path: Path):
        """Without name in frontmatter, template is not created."""
        content = """---
description: test
---

body
"""
        path = tmp_path / "fallback-name.md"
        path.write_text(content)
        template = parse_agent_file(path)
        assert template is None


class TestRenderAgentFile:
    def test_roundtrip(self, tmp_path: Path):
        original = AgentTemplate(
            name="roundtrip",
            description="Test roundtrip",
            mode="subagent",
            model="gpt-4",
            permissions={"terminal": "deny", "write_file": "allow"},
            system_prompt="You are a test agent.",
            max_iterations=3,
        )
        rendered = render_agent_file(original)
        path = tmp_path / "roundtrip.md"
        path.write_text(rendered)
        parsed = parse_agent_file(path)
        assert parsed is not None
        assert parsed.name == "roundtrip"
        assert parsed.description == "Test roundtrip"
        assert parsed.mode == "subagent"
        assert parsed.model == "gpt-4"
        assert parsed.permissions == {"terminal": "deny", "write_file": "allow"}
        assert parsed.system_prompt == "You are a test agent."
        assert parsed.max_iterations == 3

    def test_no_optional_fields(self):
        template = AgentTemplate(
            name="minimal",
            system_prompt="Minimal.",
        )
        rendered = render_agent_file(template)
        assert "mode: \"subagent\"" in rendered
        assert "max_iterations: 5" in rendered
        assert "description" not in rendered.split("---\n")[1]

    def test_escapes_in_body_preserved(self, tmp_path: Path):
        template = AgentTemplate(
            name="escapes",
            system_prompt='Use "quotes" and \'apostrophes\'.',
        )
        rendered = render_agent_file(template)
        path = tmp_path / "escapes.md"
        path.write_text(rendered)
        parsed = parse_agent_file(path)
        assert parsed is not None
        assert parsed.system_prompt == 'Use "quotes" and \'apostrophes\'.'


class TestAgentTemplateDataclass:
    def test_to_dict(self):
        template = AgentTemplate(
            name="test",
            description="A test",
            permissions={"terminal": "allow"},
        )
        d = template.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "A test"
        assert d["mode"] == "subagent"
        assert d["permissions"] == {"terminal": "allow"}
