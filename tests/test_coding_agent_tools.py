from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.coding_agent.monitor import run_monitor, MonitorResult, MonitorEvent
from sediman.agent.coding_agent.tools import (
    _handle_git_commit,
    _handle_git_branch,
    _handle_glob,
    create_coding_tool_registry,
)
from sediman.agent.tool_dispatch import ToolResult


class TestMonitor:
    @pytest.mark.asyncio
    async def test_run_simple_command(self):
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stderr = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(side_effect=[b"hello\n", b""])
            mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
            mock_proc.wait = AsyncMock(return_value=0)
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await asyncio.wait_for(
                run_monitor("echo hello", timeout=10), timeout=5
            )

            assert isinstance(result, MonitorResult)
            assert result.exit_code == 0
            assert not result.timed_out

    @pytest.mark.asyncio
    async def test_command_not_found(self):
        with patch("asyncio.create_subprocess_shell", side_effect=FileNotFoundError):
            result = await run_monitor("nonexistent_command_xyz", timeout=10)
            assert result.exit_code == -1
            assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_events_captured(self):
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stderr = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(
                side_effect=[b"line1\n", b"line2\n", b""]
            )
            mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
            mock_proc.wait = AsyncMock(return_value=0)
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await asyncio.wait_for(
                run_monitor("some command", timeout=10), timeout=5
            )

            assert len(result.events) >= 1
            assert result.events[0].line == "line1"

    @pytest.mark.asyncio
    async def test_on_line_callback(self):
        lines_captured = []

        async def on_line(event):
            lines_captured.append(event.line)

        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stderr = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(
                side_effect=[b"a\n", b""]
            )
            mock_proc.stderr.readline = AsyncMock(side_effect=[b""])
            mock_proc.wait = AsyncMock(return_value=0)
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await asyncio.wait_for(
                run_monitor("cmd", timeout=10, on_line=on_line), timeout=5
            )

            assert lines_captured == ["a"]

    @pytest.mark.asyncio
    async def test_stderr_captured_separately(self):
        with patch("asyncio.create_subprocess_shell") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stderr = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(
                side_effect=[b"out\n", b""]
            )
            mock_proc.stderr.readline = AsyncMock(
                side_effect=[b"err\n", b""]
            )
            mock_proc.wait = AsyncMock(return_value=0)
            mock_proc.returncode = 0
            mock_create.return_value = mock_proc

            result = await asyncio.wait_for(
                run_monitor("cmd", timeout=10), timeout=5
            )

            streams = {e.stream for e in result.events}
            assert "stdout" in streams
            assert "stderr" in streams

    def test_monitor_result_defaults(self):
        result = MonitorResult()
        assert result.exit_code is None
        assert result.output == ""
        assert result.events == []
        assert not result.timed_out

    def test_monitor_event_fields(self):
        event = MonitorEvent(line="test", stream="stdout", timestamp=1.0)
        assert event.line == "test"
        assert event.stream == "stdout"
        assert event.timestamp == 1.0


class TestGitTools:
    @pytest.mark.asyncio
    async def test_git_commit_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="[main abc1234] Fix bug",
                stderr="",
            )

            result = await _handle_git_commit(message="Fix bug")

            assert result.success
            assert "Fix bug" in result.output
            assert result.data["message"] == "Fix bug"

    @pytest.mark.asyncio
    async def test_git_commit_no_message(self):
        result = await _handle_git_commit(message=None)
        assert not result.success
        assert "required" in result.output.lower()

    @pytest.mark.asyncio
    async def test_git_commit_empty_message(self):
        result = await _handle_git_commit(message="   ")
        assert not result.success

    @pytest.mark.asyncio
    async def test_git_commit_with_specific_files(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="[main def5678] Update API types",
                stderr="",
            )

            result = await _handle_git_commit(
                message="Update API types",
                files=["src/types.ts", "src/api.ts"],
            )

            assert result.success
            assert mock_run.call_count == 2  # git add + git commit

    @pytest.mark.asyncio
    async def test_git_commit_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="nothing to commit",
            )

            result = await _handle_git_commit(message="test")

            assert not result.success
            assert "nothing to commit" in result.output

    @pytest.mark.asyncio
    async def test_git_commit_git_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = await _handle_git_commit(message="test")
            assert not result.success
            assert "not installed" in result.output.lower()

    @pytest.mark.asyncio
    async def test_git_branch_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="* main\n  feature/auth\n  feature/api",
                stderr="",
            )

            result = await _handle_git_branch(action="list")

            assert result.success
            assert "main" in result.output
            assert "feature/auth" in result.output

    @pytest.mark.asyncio
    async def test_git_branch_create(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Switched to a new branch 'feature/test'",
                stderr="",
            )

            result = await _handle_git_branch(
                action="create", name="feature/test"
            )

            assert result.success
            assert result.data["action"] == "create"

    @pytest.mark.asyncio
    async def test_git_branch_create_no_name(self):
        result = await _handle_git_branch(action="create", name=None)
        assert not result.success
        assert "required" in result.output.lower()

    @pytest.mark.asyncio
    async def test_git_branch_switch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Switched to branch 'main'",
                stderr="",
            )

            result = await _handle_git_branch(
                action="switch", name="main"
            )

            assert result.success

    @pytest.mark.asyncio
    async def test_git_branch_current(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="feature/auth",
                stderr="",
            )

            result = await _handle_git_branch(action="current")

            assert result.success
            assert "feature/auth" in result.output

    @pytest.mark.asyncio
    async def test_git_branch_unknown_action(self):
        result = await _handle_git_branch(action="delete", name="old")
        assert not result.success
        assert "unknown action" in result.output.lower()

    @pytest.mark.asyncio
    async def test_git_branch_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )

            result = await _handle_git_branch(action="list")

            assert not result.success


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_no_pattern(self):
        result = await _handle_glob(pattern=None)
        assert not result.success
        assert "required" in result.output.lower()

    @pytest.mark.asyncio
    async def test_glob_matches_files(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "test_a.py").write_text("x")
            (base / "test_b.py").write_text("y")
            (base / "other.ts").write_text("z")

            result = await _handle_glob(pattern="*.py", path=str(base))

            assert result.success
            assert result.data["count"] == 2
            assert any("test_a.py" in f for f in result.data["files"])
            assert any("test_b.py" in f for f in result.data["files"])

    @pytest.mark.asyncio
    async def test_glob_no_matches(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "test.py").write_text("x")

            result = await _handle_glob(pattern="*.rs", path=str(base))

            assert result.success
            assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_glob_directory_not_found(self):
        result = await _handle_glob(
            pattern="*.py", path="/nonexistent/path/xyz"
        )
        assert not result.success


class TestWebFetchAlias:
    def test_web_fetch_registered_in_coding_registry(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()
        assert "web_fetch" in names

    def test_web_fetch_same_handler_as_web_extract(self):
        registry = create_coding_tool_registry()
        assert registry._handlers["web_fetch"] is registry._handlers["web_extract"]

    def test_web_fetch_different_description(self):
        registry = create_coding_tool_registry()
        fetch_def = registry.get_definition("web_fetch")
        extract_def = registry.get_definition("web_extract")
        assert fetch_def.description != extract_def.description
        assert "markdown" in fetch_def.description.lower()


class TestCodingToolRegistryCount:
    def test_all_tools_registered(self):
        registry = create_coding_tool_registry()
        names = registry.list_tools()

        assert "glob" in names
        assert "git_status" in names
        assert "git_diff" in names
        assert "git_log" in names
        assert "git_commit" in names
        assert "git_branch" in names
        assert "web_fetch" in names
        assert "terminal" in names
        assert "read_file" in names
        assert "write_file" in names
        assert "patch" in names
        assert "list_files" in names
        assert "search_files" in names
        assert "web_search" in names
        assert "web_extract" in names
        assert "clarify" in names
        assert "todo" in names
        assert "delegate_task" in names
        assert "skill_search" in names
        assert "skill_manage" in names
