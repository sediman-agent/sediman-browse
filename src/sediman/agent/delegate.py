from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


async def delegate_task(
    task: str,
    browser_session: Any,
    llm: Any,
    max_steps: int = 30,
    browser_context: Any | None = None,
) -> str:
    """Spawn an isolated subagent to run a task in parallel.

    The subagent gets its own browser context and LLM session.
    Only the final result is returned — no intermediate state leaks.
    If *browser_context* is provided it is used instead of the default
    session, enabling true isolation between parallel delegations.
    """
    from sediman.browser.session import run_browser_task

    logger.info("subagent_delegated", task=task[:80])

    try:
        session = browser_session
        if browser_context is not None:
            session = browser_context

        result_text, _actions = await run_browser_task(
            task=task,
            browser_session=session,
            llm=llm,
            max_steps=max_steps,
        )
        return result_text
    except Exception as e:
        logger.error("subagent_failed", error=str(e))
        return f"Subagent failed: {e}"


async def delegate_parallel(
    tasks: list[str],
    browser_session: Any,
    llm_provider: Any,
    max_concurrent: int = 3,
) -> list[str]:
    """Run multiple tasks in parallel, each in its own browser context/tab.

    Max 3 concurrent to avoid overwhelming the browser/LLM.
    Returns results in the same order as input tasks.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[str | None] = [None] * len(tasks)

    async def _run_with_semaphore(index: int, task: str) -> None:
        async with semaphore:
            context = None
            try:
                if browser_session and hasattr(browser_session, "browser") and browser_session.browser:
                    context = await browser_session.browser.create_session()
            except Exception:
                context = None

            try:
                llm = llm_provider.get_browser_use_llm()
                results[index] = await delegate_task(
                    task, browser_session, llm,
                    browser_context=context,
                )
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    coros = [_run_with_semaphore(i, t) for i, t in enumerate(tasks)]
    await asyncio.gather(*coros)

    logger.info("parallel_delegation_done", tasks=len(tasks))
    return [r or "No result" for r in results]
