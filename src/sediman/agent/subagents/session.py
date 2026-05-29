from __future__ import annotations

from typing import Any
from collections.abc import Callable

import structlog

from sediman.agent.browser_agent import BrowserSubagent, BrowserResult
from sediman.agent.state import AgentPhase, AgentState
from sediman.agent.subagents.permissions import PermissionRules
from sediman.agent.subagents.result import Artifact, SubagentResult
from sediman.agent.subagents.template import AgentTemplate
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.browser.session import BrowserSession
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()


class SubagentSession:
    """Isolated execution context for a subagent.

    Similar to AgentLoop but stripped of post-task orchestration
    (no skill learning, auditing, or scheduling).
    """

    def __init__(
        self,
        template: AgentTemplate,
        task: str,
        parent_context: dict[str, Any],
        tool_registry: ToolRegistry,
        llm_provider: LLMProvider,
        browser_session: BrowserSession | None = None,
        on_step: Callable[[str, str], None] | None = None,
        flash_mode: bool = True,
    ):
        self.template = template
        self.task = task
        self.parent_context = parent_context
        self.tool_registry = tool_registry
        self.llm = llm_provider
        self.browser = browser_session
        self.on_step = on_step
        self.flash_mode = flash_mode
        self._conversation: list[dict[str, str]] = []
        self._iterations = 0

    async def run(self) -> SubagentResult:
        logger.info(
            "subagent_session_start",
            agent=self.template.name,
            task=self.task[:80],
        )

        system_prompt = self._build_system_prompt()
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.task},
        ]

        # Simple single-step execution for most subagents,
        # but we support iterative tool use if needed.
        state = AgentState(task=self.task, max_iterations=self.template.max_iterations)
        state.phase = AgentPhase.EXECUTING

        try:
            # Try direct browser execution first if we have a browser
            if self.browser and self._is_browser_task(self.task):
                result = await self._run_browser_step(self.task)
                state.result = result.text
                state.actions_taken = result.actions
                state.phase = AgentPhase.DONE
                return self._assemble_result(state)

            # Otherwise, use LLM chat with tools
            for attempt in range(self.template.max_iterations):
                self._iterations = attempt + 1
                response = await self.llm.chat(
                    messages=messages,
                    tools=self.tool_registry.get_definitions(),
                )

                if response.tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": response.text or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                },
                            }
                            for tc in response.tool_calls
                        ],
                    })
                    for tc in response.tool_calls:
                        # Permission check
                        perms = PermissionRules(self.template.permissions)
                        if perms.is_denied(tc.name):
                            result_text = f"Tool '{tc.name}' is not allowed for this subagent."
                            state.errors.append(result_text)
                        else:
                            tool_result = await self.tool_registry.dispatch(
                                tc.name, tc.arguments
                            )
                            result_text = tool_result.output
                            if not tool_result.success:
                                state.errors.append(f"Tool {tc.name} failed: {result_text[:200]}")
                            if tool_result.data and tc.name in ("write_file", "patch"):
                                state.actions_taken.append(
                                    {
                                        "tool": tc.name,
                                        "args": tc.arguments,
                                        "data": tool_result.data,
                                    }
                                )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_text,
                        })
                else:
                    # No tool calls — we have a text answer
                    state.result = response.text or ""
                    state.phase = AgentPhase.DONE
                    break

            if state.phase != AgentPhase.DONE:
                state.phase = AgentPhase.DONE
                if not state.result:
                    state.result = "Subagent completed without a final result."

        except Exception as e:
            logger.error("subagent_session_error", agent=self.template.name, error=str(e))
            state.phase = AgentPhase.FAILED
            state.errors.append(str(e))
            state.result = f"Subagent '{self.template.name}' failed: {e}"

        return self._assemble_result(state)

    def _build_system_prompt(self) -> str:
        sections: list[str] = []

        if self.template.system_prompt:
            sections.append(self.template.system_prompt)

        # Inject parent context selectively
        parent_task = self.parent_context.get("task", "")
        parent_errors = self.parent_context.get("errors", [])
        parent_obs = self.parent_context.get("observations", [])

        if parent_task:
            sections.append(f"<parent_task>\n{parent_task}\n</parent_task>")
        if parent_errors:
            sections.append(
                "<parent_errors>\n" + "\n".join(f"- {e}" for e in parent_errors[-3:]) + "\n</parent_errors>"
            )
        if parent_obs:
            sections.append(
                "<parent_observations>\n"
                + "\n".join(f"- {o}" for o in parent_obs[-3:])
                + "\n</parent_observations>"
            )

        return "\n\n".join(sections)

    def _is_browser_task(self, task: str) -> bool:
        """Heuristic: if we have a browser and no non-browser tools, treat as browser task."""
        if not self.browser:
            return False
        # If the template denies browser-related tools, don't use browser
        perms = PermissionRules(self.template.permissions)
        if perms.is_denied("browser") or perms.is_denied("web_search"):
            return False
        return True

    async def _run_browser_step(self, task: str) -> BrowserResult:
        browser_agent = BrowserSubagent(
            browser_session=self.browser,
            llm_provider=self.llm,
            max_steps=30,
            flash_mode=self.flash_mode,
            on_browser_step=self.on_step,
        )
        return await browser_agent.run(task)

    def _assemble_result(self, state: AgentState) -> SubagentResult:
        success = state.phase != AgentPhase.FAILED and not state.errors
        summary = state.result or "No result."

        artifacts: list[Artifact] = []
        for action in state.actions_taken:
            data = action.get("data", {})
            if action.get("tool") == "write_file" and data.get("path"):
                artifacts.append(
                    Artifact(
                        kind="file",
                        name=data.get("path", "").split("/")[-1],
                        path=data.get("path"),
                    )
                )
            if action.get("tool") == "skill_manage" and data.get("name"):
                artifacts.append(
                    Artifact(
                        kind="skill",
                        name=data.get("name"),
                        metadata={"steps": data.get("steps", 0)},
                    )
                )

        return SubagentResult(
            success=success,
            summary=summary[:2000],
            detail=state.result,
            actions_taken=state.actions_taken,
            artifacts=artifacts,
            iterations=self._iterations,
            strategy_used="direct",
            errors=state.errors,
        )
