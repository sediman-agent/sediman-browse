from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from sediman.agent.coding_agent.verifier import InlineVerifier, VerifyLoop
from sediman.agent.coding_agent.types import ProjectInfo, VerifyResult
from sediman.agent.tools.terminal import _format_error_output, _is_error_line, _is_warning_line


class TestInlineVerifier:
    def _make_project(self, **overrides) -> ProjectInfo:
        defaults = {
            "project_type": "Python",
            "root_dir": "/tmp/test",
            "lint_commands": ["ruff check ."],
            "format_commands": [],
            "test_commands": [],
        }
        defaults.update(overrides)
        return ProjectInfo(**defaults)

    @pytest.mark.asyncio
    async def test_track_edit_adds_file(self):
        verifier = InlineVerifier(self._make_project())
        verifier.track_edit("/tmp/test/app.py")
        assert len(verifier._edited_files) == 1

    @pytest.mark.asyncio
    async def test_track_edit_dedup(self):
        verifier = InlineVerifier(self._make_project())
        verifier.track_edit("/tmp/test/app.py")
        verifier.track_edit("/tmp/test/app.py")
        assert len(verifier._edited_files) == 1

    @pytest.mark.asyncio
    async def test_verify_inline_lint_passes(self):
        verifier = InlineVerifier(self._make_project())
        verifier.track_edit("/tmp/test/app.py")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="All checks passed!", stderr=""
            )
            result = await verifier.verify_inline("/tmp/test/app.py")

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_inline_lint_fails(self):
        verifier = InlineVerifier(self._make_project())
        verifier.track_edit("/tmp/test/app.py")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="app.py:5:1: F401 'os' imported but unused",
                stderr="",
            )
            result = await verifier.verify_inline("/tmp/test/app.py")

        assert result is not None
        assert "Verification Failures" in result
        assert "F401" in result

    @pytest.mark.asyncio
    async def test_verify_all_format_and_lint(self):
        verifier = InlineVerifier(
            self._make_project(
                format_commands=["ruff format --check ."],
                lint_commands=["ruff check ."],
            )
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="All good!", stderr=""
            )
            results = await verifier.verify_all()

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_verify_all_aggressive_runs_tests(self):
        verifier = InlineVerifier(
            self._make_project(
                test_commands=["pytest"],
            )
        )
        verifier.track_edit("/tmp/a.py")
        verifier.track_edit("/tmp/b.py")
        verifier.track_edit("/tmp/c.py")
        verifier.track_edit("/tmp/d.py")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="10 passed", stderr=""
            )
            results = await verifier.verify_all(aggressive=True)

        assert any(r.tool == "test" for r in results)

    @pytest.mark.asyncio
    async def test_all_passed_when_no_results(self):
        verifier = InlineVerifier(self._make_project())
        assert verifier.all_passed is True

    @pytest.mark.asyncio
    async def test_all_passed_when_all_success(self):
        verifier = InlineVerifier(self._make_project())
        verifier._all_results = [
            VerifyResult(command="cmd1", success=True, output="ok", exit_code=0),
            VerifyResult(command="cmd2", success=True, output="ok", exit_code=0),
        ]
        assert verifier.all_passed is True

    @pytest.mark.asyncio
    async def test_all_passed_with_failure(self):
        verifier = InlineVerifier(self._make_project())
        verifier._all_results = [
            VerifyResult(command="cmd1", success=True, output="ok", exit_code=0),
            VerifyResult(command="cmd2", success=False, output="fail", exit_code=1),
        ]
        assert verifier.all_passed is False

    @pytest.mark.asyncio
    async def test_summary_with_results(self):
        verifier = InlineVerifier(self._make_project())
        verifier._all_results = [
            VerifyResult(command="ruff check .", success=True, output="ok", exit_code=0),
            VerifyResult(command="pytest", success=False, output="2 failed", exit_code=1),
        ]
        summary = verifier.summary
        assert "1 passed" in summary
        assert "1 failed" in summary

    @pytest.mark.asyncio
    async def test_summary_empty(self):
        verifier = InlineVerifier(self._make_project())
        summary = verifier.summary
        assert "No verification" in summary

    @pytest.mark.asyncio
    async def test_verifyloop_is_verifier(self):
        assert VerifyLoop is InlineVerifier


class TestTerminalErrorFormatting:
    def test_is_error_line_python_traceback(self):
        assert _is_error_line("Traceback (most recent call last):")
        assert _is_error_line("TypeError: 'NoneType' object is not subscriptable")
        assert _is_error_line("ModuleNotFoundError: No module named 'foo'")
        assert _is_error_line("ImportError: cannot import name 'bar'")

    def test_is_error_line_command_errors(self):
        assert _is_error_line("error: something went wrong")
        assert _is_error_line("ERROR: failed to compile")
        assert _is_error_line("fatal: not a git repository")
        assert _is_error_line("panic: runtime error")
        assert _is_error_line("command not found: xyz")
        assert _is_error_line("Permission denied")

    def test_is_error_line_not_error(self):
        assert not _is_error_line("Build successful!")
        assert not _is_error_line("10 tests passed")
        assert not _is_error_line("Installing dependencies...")

    def test_is_warning_line(self):
        assert _is_warning_line("warning: unused variable 'x'")
        assert _is_warning_line("WARNING: deprecated API")
        assert _is_warning_line("DeprecationWarning: use new_api instead")
        assert _is_warning_line("This function is deprecated")

    def test_is_warning_not_warning(self):
        assert not _is_warning_line("Build successful")
        assert not _is_warning_line("error: something went wrong")

    def test_format_error_output_structure(self):
        output = "line1\nline2\nerror: something went wrong\nline3"
        formatted = _format_error_output("test command", 1, output)

        assert "Command failed with exit code 1" in formatted
        assert "test command" in formatted
        assert "Full output" in formatted
        assert "error(s) detected" in formatted
        assert "Action required" in formatted

    def test_format_error_output_no_errors_still_formats(self):
        output = "line1\nline2\nline3"
        formatted = _format_error_output("test cmd", 1, output)

        assert "Command failed with exit code 1" in formatted
        assert "Full output" in formatted

    def test_format_error_output_with_warnings(self):
        output = "warning: something deprecated\nline1"
        formatted = _format_error_output("test cmd", 1, output)

        assert "warning(s)" in formatted or "Action required" in formatted

    def test_format_error_output_empty(self):
        formatted = _format_error_output("test cmd", 127, "")
        assert "Command failed with exit code 127" in formatted


class TestContextCompression:
    def test_compress_tool_results_truncates(self):
        from sediman.agent.tool_dispatch import ToolLoop, ToolRegistry
        from unittest.mock import MagicMock

        loop = ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
        )

        messages = [
            {"role": "tool", "tool_call_id": "1", "content": "x" * 3000},
        ]
        compressed = loop._compress_tool_results(messages)
        assert "truncated" in compressed[0]["content"]
        assert len(compressed[0]["content"]) < 3000

    def test_maybe_compress_splits_when_over(self):
        from sediman.agent.tool_dispatch import ToolLoop, ToolRegistry
        from unittest.mock import MagicMock

        loop = ToolLoop(
            llm=MagicMock(),
            registry=ToolRegistry(),
            max_context_tokens=10,
        )

        full = "a" * 3000
        messages = [
            {"role": "user", "content": "short"},
            {"role": "tool", "tool_call_id": "1", "content": full},
            {"role": "tool", "tool_call_id": "2", "content": full},
            {"role": "tool", "tool_call_id": "3", "content": full},
        ]

        system_len = 0
        compressed = loop._maybe_compress(messages, system_len)

        for m in compressed:
            if m.get("role") == "tool":
                assert len(m.get("content", "")) < 3000, (
                    f"Tool message should be truncated: {len(m.get('content', ''))} chars"
                )
