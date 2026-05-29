from __future__ import annotations

from typing import Any
from collections.abc import Callable

import structlog

from sediman.config import MAX_NESTED_DEPTH
from sediman.agent.subagents.permissions import PermissionRules
from sediman.agent.subagents.registry import SubagentRegistry
from sediman.agent.subagents.result import SubagentResult
from sediman.agent.subagents.session import SubagentSession
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.agent.tools import create_agent_tool_registry
from sediman.browser.session import BrowserSession
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()


class SubagentFactory:
    """Factory for spawning isolated subagent sessions."""

    def __init__(
        self,
        registry: SubagentRegistry,
        llm_provider: LLMProvider,
        browser_session: BrowserSession | None = None,
        tool_registry: ToolRegistry | None = None,
        on_step: Callable[[str, str], None] | None = None,
        flash_mode: bool = True,
        max_nested_depth: int = MAX_NESTED_DEPTH,
    ):
        self.registry = registry
        self.llm = llm_provider
        self.browser = browser_session
        self.tool_registry = tool_registry or create_agent_tool_registry()
        self.on_step = on_step
        self.flash_mode = flash_mode
        self.max_nested_depth = max_nested_depth

    async def spawn(
        self,
        agent_type: str,
        task: str,
        parent_context: dict[str, Any] | None = None,
        browser_isolation: bool = False,
        depth: int = 0,
    ) -> SubagentResult:
        """Spawn a subagent of the given type to execute a task.

        Args:
            agent_type: Name of the registered agent template.
            task: The task description.
            parent_context: Selective context to inject from the parent.
            browser_isolation: If True, create a new browser context/page.
            depth: Current nesting depth (to prevent infinite recursion).
        """
        if depth > self.max_nested_depth:
            return SubagentResult(
                success=False,
                summary=f"Max subagent nesting depth ({self.max_nested_depth}) exceeded.",
                errors=["nesting_depth_exceeded"],
            )

        template = self.registry.get(agent_type)
        if not template:
            return SubagentResult(
                success=False,
                summary=f"Unknown subagent type: '{agent_type}'.",
                errors=[f"unknown_agent_type: {agent_type}"],
            )

        logger.info(
            "subagent_spawn",
            agent=agent_type,
            task=task[:80],
            isolation=browser_isolation,
            depth=depth,
        )

        # Build permission-filtered tool registry
        perms = PermissionRules(template.permissions)
        filtered_tools = perms.filter_tools(self.tool_registry)

        # Browser handling
        browser = self.browser
        isolated_browser: BrowserSession | None = None
        if browser_isolation and self.browser:
            import tempfile

            temp_dir = tempfile.mkdtemp(prefix="sediman-isolated-")
            isolated_browser = BrowserSession(
                headless=True,
                user_data_dir=temp_dir,
            )
            try:
                await isolated_browser.start()
                browser = isolated_browser
                logger.info("browser_isolation_started", temp_dir=temp_dir)
            except Exception as e:
                logger.warning("browser_isolation_failed", error=str(e))
                isolated_browser = None

        session = SubagentSession(
            template=template,
            task=task,
            parent_context=parent_context or {},
            tool_registry=filtered_tools,
            llm_provider=self.llm,
            browser_session=browser,
            on_step=self.on_step,
            flash_mode=self.flash_mode,
        )

        try:
            result = await session.run()
        finally:
            if isolated_browser is not None:
                try:
                    await isolated_browser.stop()
                except Exception as e:
                    logger.warning("isolated_browser_stop_failed", error=str(e))

        logger.info(
            "subagent_done",
            agent=agent_type,
            success=result.success,
            iterations=result.iterations,
            actions=len(result.actions_taken),
        )
        return result

    async def spawn_parallel(
        self,
        specs: list[tuple[str, str]],
        parent_context: dict[str, Any] | None = None,
        browser_isolation: bool = False,
        max_concurrent: int = 3,
        depth: int = 0,
    ) -> list[SubagentResult]:
        """Spawn multiple subagents in parallel.

        Args:
            specs: List of (agent_type, task) tuples.
            parent_context: Shared parent context for all.
            browser_isolation: Whether to isolate browsers.
            max_concurrent: Max parallel subagents.
            depth: Nesting depth.

        Returns:
            SubagentResult list in the same order as specs.
        """
        import asyncio

        if depth > self.max_nested_depth:
            return [
                SubagentResult(
                    success=False,
                    summary="Max nesting depth exceeded for parallel spawn.",
                    errors=["nesting_depth_exceeded"],
                )
                for _ in specs
            ]

        semaphore = asyncio.Semaphore(max_concurrent)
        results: list[SubagentResult | None] = [None] * len(specs)

        async def _run_with_semaphore(index: int, agent_type: str, task: str) -> None:
            async with semaphore:
                results[index] = await self.spawn(
                    agent_type=agent_type,
                    task=task,
                    parent_context=parent_context,
                    browser_isolation=browser_isolation,
                    depth=depth + 1,
                )

        coros = [
            _run_with_semaphore(i, at, t) for i, (at, t) in enumerate(specs)
        ]
        await asyncio.gather(*coros)

        return [r or SubagentResult(success=False, summary="No result") for r in results]

    def list_available(self) -> list[dict[str, Any]]:
        """Return metadata for all available subagent types."""
        return [t.to_dict() for t in self.registry.list()]
