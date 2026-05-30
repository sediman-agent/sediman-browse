from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from sediman.agent.coding_agent.context import discover_project
from sediman.agent.coding_agent.hooks import (
    HookPipeline,
    HookContext,
    PreHookResult,
    create_default_pipeline,
)
from sediman.agent.coding_agent.prompts import build_system_prompt
from sediman.agent.coding_agent.tools import create_coding_tool_registry
from sediman.agent.coding_agent.types import CodingResult, ProjectInfo
from sediman.agent.coding_agent.verifier import InlineVerifier
from sediman.agent.tool_dispatch import ToolLoop, ToolRegistry, ToolResult
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()

_MAX_ROUNDS = 30
_MAX_CONSECUTIVE_ERRORS = 3
_VERIFY_AFTER_EDITS = True


class CodingAgent:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry | None = None,
        max_rounds: int = _MAX_ROUNDS,
        on_step: Callable[[str, str], None] | None = None,
        on_streaming_text: Callable[[str, str], None] | None = None,
        project_info: ProjectInfo | None = None,
        auto_discover_project: bool = True,
        verify_after_edits: bool = _VERIFY_AFTER_EDITS,
        hooks: HookPipeline | None = None,
        enable_hooks: bool = True,
    ):
        self.llm = llm_provider
        self.registry = tool_registry or create_coding_tool_registry()
        self.max_rounds = max(max_rounds, 10)
        self._on_step = on_step
        self._on_streaming_text = on_streaming_text
        self._verify_after_edits = verify_after_edits

        if project_info:
            self.project = project_info
        elif auto_discover_project:
            try:
                self.project = discover_project()
            except Exception:
                self.project = ProjectInfo()
        else:
            self.project = ProjectInfo()

        self._verifier: InlineVerifier | None = None
        self._consecutive_errors = 0
        self._edited_files: list[str] = []
        self._hook_pipeline = hooks or (create_default_pipeline() if enable_hooks else None)
        self._session_id = str(int(time.time() * 1000))[-8:]

    def _emit_step(self, action: str, detail: str = "") -> None:
        if self._on_step:
            try:
                self._on_step(action, detail)
            except Exception:
                pass

    def _emit_token(self, token: str, phase: str = "responding") -> None:
        if self._on_streaming_text:
            try:
                self._on_streaming_text(token, phase)
            except Exception:
                pass

    async def run(self, task: str) -> CodingResult:
        logger.info(
            "coding_agent_start",
            task=task[:80],
            project_type=self.project.project_type,
            max_rounds=self.max_rounds,
            hooks_enabled=self._hook_pipeline is not None,
        )

        self._emit_step("coding: analyzing", detail=task[:100])

        system_prompt = build_system_prompt(
            project_info=self.project,
            task=task,
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": task},
        ]

        tool_loop = ToolLoop(
            llm=self.llm,
            registry=self.registry,
            max_rounds=self.max_rounds,
            max_context_tokens=16000,
        )

        tool_names: list[str] = []
        self._edited_files = []
        self._consecutive_errors = 0
        iterations = 0
        start = time.monotonic()
        errors_encountered: list[str] = []
        verifications_passed = 0
        verifications_failed = 0

        if self._verifier is None and self._verify_after_edits:
            self._verifier = InlineVerifier(
                project_info=self.project,
                on_progress=self._on_step,
            )

        async def on_tool_call(name: str, args: dict[str, Any]) -> None:
            nonlocal tool_names
            tool_names.append(name)

            ctx = HookContext(
                tool_name=name,
                tool_input=args,
                session_id=self._session_id,
                agent_name="coding_agent",
            )

            if self._hook_pipeline:
                pre_result = await self._hook_pipeline.run_pre(name, args, ctx)
                if not pre_result.allowed:
                    self._emit_step(
                        f"coding: blocked",
                        detail=f"{name}: {pre_result.reason[:100]}",
                    )
                    return
                if pre_result.modified_input:
                    args.update(pre_result.modified_input)

            cmd_preview = self._format_tool_preview(name, args)

            if name in ("write_file", "patch") and args.get("path"):
                file_path = str(args["path"])
                if file_path not in self._edited_files:
                    self._edited_files.append(file_path)
                if self._verifier:
                    self._verifier.track_edit(file_path)

            self._emit_step(
                f"coding: {name}",
                detail=cmd_preview,
            )

        def on_streaming_text(token: str) -> None:
            self._emit_token(token, "responding")

        self._emit_token("", "thinking")

        try:
            response = await tool_loop.run_streaming(
                messages=messages,
                system=system_prompt,
                on_tool_call=on_tool_call,
                on_streaming_text=on_streaming_text,
            )
            iterations = tool_loop.max_rounds

            if self._edited_files and self._verify_after_edits and self._verifier:
                self._emit_step(
                    "coding: verifying",
                    detail=f"{len(self._edited_files)} file(s) edited",
                )
                verify_results = await self._verifier.verify_all(aggressive=False)
                for r in verify_results:
                    status = "PASS" if r.success else "FAIL"
                    self._emit_step(
                        f"verify: {status}",
                        detail=f"{r.command[:80]}",
                    )
                verifications_passed = sum(1 for r in verify_results if r.success)
                verifications_failed = len(verify_results) - verifications_passed

            result_text = response.text or "No result returned."
            tool_summary = self._analyze_tool_results(tool_names, errors_encountered)

            if tool_summary:
                result_text += f"\n\n{tool_summary}"

            if verifications_passed > 0 or verifications_failed > 0:
                result_text += (
                    f"\n\n[Verification: {verifications_passed} passed, "
                    f"{verifications_failed} failed]"
                )
                if self._verifier:
                    result_text += f"\n{self._verifier.summary}"

        except Exception as e:
            logger.error("coding_agent_error", error=str(e))
            result_text = f"Coding task failed: {e}"
            errors_encountered.append(str(e))
            self._emit_step("coding: failed", detail=str(e)[:120])

        elapsed = time.monotonic() - start
        success = (
            "failed" not in result_text.lower()[:50]
            and len(errors_encountered) == 0
        )

        self._emit_step(
            f"coding: done ({elapsed:.1f}s)",
            detail=(
                f"{len(tool_names)} tool calls, "
                f"{len(self._edited_files)} files edited, "
                f"{verifications_passed} verifications passed"
            ),
        )

        logger.info(
            "coding_agent_done",
            result_length=len(result_text),
            tool_calls=len(tool_names),
            files_edited=len(self._edited_files),
            verifications_passed=verifications_passed,
            elapsed=elapsed,
        )

        return CodingResult(
            text=result_text,
            actions=[{"tools": tool_names, "files_edited": list(self._edited_files)}],
            success=success,
            iterations=iterations,
            tool_calls=tool_names,
            files_edited=list(self._edited_files),
            errors_encountered=errors_encountered,
            verifications_passed=verifications_passed,
            verifications_failed=verifications_failed,
        )

    def _format_tool_preview(self, name: str, args: dict[str, Any]) -> str:
        if name == "terminal":
            return args.get("command", "")[:80]
        elif name in ("write_file", "read_file", "patch"):
            return args.get("path", "")[:80]
        elif name == "search_files":
            return args.get("query", "")[:80]
        elif name == "glob":
            return args.get("pattern", "")[:80]
        elif name == "git_diff":
            return args.get("file_path", "unstaged")[:80]
        elif name == "git_status":
            return "checking status"
        elif name == "git_log":
            return f"last {args.get('count', 10)} commits"
        elif name == "git_commit":
            return args.get("message", "")[:80]
        elif name == "git_branch":
            return f"{args.get('action', 'list')} {args.get('name', '')}"[:80]
        elif name == "web_search":
            return args.get("query", "")[:80]
        elif name == "web_fetch":
            return args.get("url", "")[:80]
        elif name == "delegate_task":
            return f"{args.get('agent_type', 'browser')}: {args.get('task', '')[:60]}"
        elif name == "clarify":
            return args.get("question", "")[:80]
        elif name == "todo":
            return "updating task list"
        return ""

    def _analyze_tool_results(
        self,
        tool_names: list[str],
        errors_encountered: list[str],
    ) -> str:
        parts: list[str] = []

        if self._edited_files:
            parts.append(f"Files edited: {len(self._edited_files)}")
            for f in self._edited_files[:10]:
                parts.append(f"  - {f}")
            if len(self._edited_files) > 10:
                parts.append(f"  ... and {len(self._edited_files) - 10} more")

        tool_counts: dict[str, int] = {}
        for name in tool_names:
            tool_counts[name] = tool_counts.get(name, 0) + 1

        if tool_counts:
            parts.append(
                "Tool usage: "
                + ", ".join(
                    f"{name}({count})" for name, count in tool_counts.items()
                )
            )

        if errors_encountered:
            parts.append(f"Errors: {len(errors_encountered)}")
            for e in errors_encountered[:3]:
                parts.append(f"  - {e[:120]}")

        return "\n".join(parts) if parts else ""


def create_coding_agent(
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry | None = None,
    max_rounds: int = _MAX_ROUNDS,
    on_step: Callable[[str, str], None] | None = None,
    on_streaming_text: Callable[[str, str], None] | None = None,
    auto_discover_project: bool = True,
    verify_after_edits: bool = _VERIFY_AFTER_EDITS,
    enable_hooks: bool = True,
) -> CodingAgent:
    return CodingAgent(
        llm_provider=llm_provider,
        tool_registry=tool_registry,
        max_rounds=max_rounds,
        on_step=on_step,
        on_streaming_text=on_streaming_text,
        auto_discover_project=auto_discover_project,
        verify_after_edits=verify_after_edits,
        enable_hooks=enable_hooks,
    )
