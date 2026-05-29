from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import structlog

from sediman.agent.prompts.builder import PromptBuilder
from sediman.browser.session import BrowserSession, run_browser_task
from sediman.errors import looks_like_error
from sediman.llm.provider import LLMProvider
from sediman.skills.healer import heal_skill

logger = structlog.get_logger()


def _looks_like_error(text: str) -> bool:
    return looks_like_error(text)


async def _capture_screenshot(browser_session) -> str | None:
    try:
        page = browser_session.page
        data = await page.screenshot()
        path = Path(tempfile.mktemp(suffix=".png"))
        path.write_bytes(data)
        return str(path)
    except Exception as e:
        logger.warning("screenshot_capture_failed", error=str(e))
        return None


async def _capture_dom(browser_session) -> str | None:
    try:
        page = browser_session.page
        content = await page.content()
        if not content:
            return None
        if len(content) > 3000:
            content = content[:3000]
        return content
    except Exception as e:
        logger.warning("dom_capture_failed", error=str(e))
        return None


def _format_steps_for_prompt(steps: list[str | dict[str, Any]]) -> str:
    lines = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, str):
            lines.append(f"{i}. {step}")
        elif isinstance(step, dict):
            parts = [f"{i}. {step.get('description', '')}"]
            if step.get("url"):
                parts.append(f"URL: {step['url']}")
            if step.get("selector"):
                parts.append(f"Selector: {step['selector']}")
            if step.get("expected_outcome"):
                parts.append(f"Expected: {step['expected_outcome']}")
            lines.append(" | ".join(parts))
    return "\n".join(lines)


async def execute_skill(
    skill: dict[str, Any],
    browser_session: BrowserSession,
    llm: LLMProvider,
    max_retries: int = 1,
    flash_mode: bool = True,
) -> str:
    name = skill["name"]
    description = skill.get("description", "")
    steps = skill.get("steps", [])
    verification = skill.get("verification")

    builder = PromptBuilder(flash_mode=flash_mode)
    task = builder.build_skill_executor_prompt(
        skill_name=name,
        description=description,
        steps=steps,
        verification=verification,
    )

    logger.info("skill_execution_start", skill=name)

    for attempt in range(max_retries + 1):
        try:
            result_text, _actions = await run_browser_task(
                task=task,
                browser_session=browser_session,
                llm=llm.get_browser_use_llm(),
                flash_mode=flash_mode,
            )

            if result_text and not _looks_like_error(result_text):
                logger.info("skill_execution_done", skill=name, attempt=attempt)
                return result_text

            if attempt < max_retries:
                logger.info("skill_retry_with_healing", skill=name, attempt=attempt)
                healed = await heal_skill(
                    skill=skill,
                    error_context=result_text or "unknown error",
                    browser_session=browser_session,
                    llm=llm,
                )
                if healed:
                    skill = healed
                    steps = skill.get("steps", [])
                    task = builder.build_skill_executor_prompt(
                        skill_name=name,
                        description=description,
                        steps=steps,
                    )
                    continue

            return result_text or "Skill execution completed with no output"

        except Exception as e:
            if attempt < max_retries:
                logger.info("skill_error_retry", skill=name, error=str(e))
                healed = await heal_skill(
                    skill=skill,
                    error_context=str(e),
                    browser_session=browser_session,
                    llm=llm,
                )
                if healed:
                    skill = healed
                    continue

            logger.error("skill_execution_failed", skill=name, error=str(e))
            return f"Skill '{name}' failed: {e}"
