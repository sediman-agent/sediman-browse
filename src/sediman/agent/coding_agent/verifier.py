from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any, Callable

import structlog

from sediman.agent.coding_agent.types import ProjectInfo, VerifyResult

logger = structlog.get_logger()

_VERIFY_TIMEOUT = 60


class InlineVerifier:
    def __init__(
        self,
        project_info: ProjectInfo,
        on_progress: Callable[[str, str], None] | None = None,
    ):
        self.project = project_info
        self._on_progress = on_progress
        self._edited_files: set[str] = set()
        self._all_results: list[VerifyResult] = []
        self._run_at_end: bool = False

    def track_edit(self, file_path: str) -> None:
        self._edited_files.add(str(Path(file_path).resolve()))

    async def verify_inline(self, file_path: str | None = None) -> str | None:
        results: list[VerifyResult] = []

        if file_path:
            await self._run_lint_on_file(file_path, results)
        else:
            await self._run_format_check(results)

        self._all_results.extend(results)

        if results:
            failures = [r for r in results if not r.success]
            if failures:
                error_text = self._format_as_tool_feedback(failures)
                self._emit("verify", f"{len(failures)} check(s) failed")
                return error_text
            else:
                self._emit("verify", f"All {len(results)} check(s) passed")

        return None

    async def verify_all(self, aggressive: bool = False) -> list[VerifyResult]:
        results: list[VerifyResult] = []

        await self._run_format_check(results)
        await self._run_lint_all(results)

        if aggressive or len(self._edited_files) > 3:
            await self._run_tests(results)

        self._all_results.extend(results)
        return results

    async def _run_lint_on_file(
        self, file_path: str, results: list[VerifyResult]
    ) -> None:
        for cmd in self.project.lint_commands:
            target_cmd = f"{cmd} {file_path}" if "pre-commit" not in cmd else cmd
            result = await self._run_command(target_cmd, "lint")
            results.append(result)
            return

        if not self.project.lint_commands:
            ext = Path(file_path).suffix
            if ext == ".py":
                result = await self._run_command(
                    f"ruff check {file_path}", "lint"
                )
                results.append(result)
            elif ext in (".ts", ".tsx", ".js", ".jsx"):
                if any("eslint" in c.lower() for c in self.project.lint_commands):
                    result = await self._run_command(
                        f"npx eslint {file_path}", "lint"
                    )
                    results.append(result)

    async def _run_format_check(self, results: list[VerifyResult]) -> None:
        for cmd in self.project.format_commands:
            result = await self._run_command(cmd, "format")
            results.append(result)

    async def _run_lint_all(self, results: list[VerifyResult]) -> None:
        ran = False
        for cmd in self.project.lint_commands:
            result = await self._run_command(cmd, "lint")
            results.append(result)
            ran = True

        if not ran:
            self._emit("verify", "No lint commands configured.")

    async def _run_tests(self, results: list[VerifyResult]) -> None:
        ran = False
        for cmd in self.project.test_commands:
            result = await self._run_command(cmd, "test", timeout=120)
            results.append(result)
            ran = True

        if not ran:
            self._emit("verify", "No test commands configured.")

    async def _run_command(
        self, cmd: str, tool: str = "", timeout: int = _VERIFY_TIMEOUT
    ) -> VerifyResult:
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.project.root_dir or None,
                ),
            )
            output = (proc.stdout + proc.stderr).strip()
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"
            return VerifyResult(
                command=cmd,
                success=proc.returncode == 0,
                output=output,
                exit_code=proc.returncode,
                tool=tool,
            )
        except subprocess.TimeoutExpired:
            return VerifyResult(
                command=cmd,
                success=False,
                output=f"Command timed out after {timeout}s",
                exit_code=-1,
                tool=tool,
            )
        except Exception as e:
            return VerifyResult(
                command=cmd,
                success=False,
                output=str(e),
                exit_code=-1,
                tool=tool,
            )

    def _format_as_tool_feedback(self, failures: list[VerifyResult]) -> str:
        lines = [
            "## Verification Failures",
            "",
            f"The following {len(failures)} verification check(s) failed. "
            "Please fix these issues:",
            "",
        ]
        for r in failures:
            lines.append(f"### `{r.command}` (exit code {r.exit_code})")
            if r.output:
                lines.append("```")
                lines.append(r.output)
                lines.append("```")
            lines.append("")
        return "\n".join(lines)

    def _emit(self, action: str, detail: str = "") -> None:
        if self._on_progress:
            try:
                self._on_progress(action, detail)
            except Exception:
                pass

    @property
    def all_passed(self) -> bool:
        return (
            all(r.success for r in self._all_results)
            if self._all_results
            else True
        )

    @property
    def summary(self) -> str:
        if not self._all_results:
            return "No verification commands run."
        passed = sum(1 for r in self._all_results if r.success)
        failed = len(self._all_results) - passed
        lines = [f"Verification: {passed} passed, {failed} failed"]
        for r in self._all_results:
            status = "PASS" if r.success else "FAIL"
            lines.append(f"  [{status}] {r.command}")
        if failed > 0:
            lines.append(
                "\nReview failures above and fix before considering the task complete."
            )
        return "\n".join(lines)


VerifyLoop = InlineVerifier
