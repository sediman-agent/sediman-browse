from __future__ import annotations

import re
import subprocess
import tempfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import structlog

from sediman.agent.prompts.builder import PromptBuilder
from sediman.browser.session import BrowserSession, run_browser_task
from sediman.errors import looks_like_error
from sediman.llm.provider import LLMProvider
from sediman.skills.healer import heal_skill

logger = structlog.get_logger()

_SHELL_INJECT_RE = re.compile(r"!`(.+?)`")


def _looks_like_error(text: str) -> bool:
    return looks_like_error(text)


def _apply_shell_injection(text: str) -> str:
    def _replace(m: re.Match) -> str:
        cmd = m.group(1).strip()
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() or result.stderr.strip() or ""
        except Exception as e:
            logger.warning("shell_injection_failed", cmd=cmd, error=str(e))
            return ""
    return _SHELL_INJECT_RE.sub(_replace, text)


def _apply_argument_substitution(text: str, arguments: dict[str, str]) -> str:
    result = text
    result = result.replace("$ARGUMENTS", arguments.get("ARGUMENTS", ""))
    result = result.replace("$0", arguments.get("0", ""))
    for key, value in arguments.items():
        result = result.replace(f"${{{key}}}", value)
        result = result.replace(f"${key}", value)
    return result


def _matches_paths(skill: dict[str, Any], working_dir: str | None = None) -> bool:
    paths = skill.get("paths")
    if not paths:
        return True
    cwd = working_dir or str(Path.cwd())
    try:
        files = [str(f.relative_to(cwd)) for f in Path(cwd).rglob("*") if f.is_file()]
    except Exception:
        files = []
    for pattern in paths:
        if any(fnmatch(f, pattern) for f in files):
            return True
    return False


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


def _format_steps_for_prompt(steps: list[str | dict[str, Any]], args: dict[str, str] | None = None) -> str:
    args = args or {}
    lines = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, str):
            text = _apply_shell_injection(step)
            text = _apply_argument_substitution(text, args)
            lines.append(f"{i}. {text}")
        elif isinstance(step, dict):
            desc = step.get("description", "")
            desc = _apply_shell_injection(desc)
            desc = _apply_argument_substitution(desc, args)
            parts = [f"{i}. {desc}"]
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
    arguments: dict[str, str] | None = None,
    engine: Any = None,
) -> str:
    name = skill["name"]
    description = skill.get("description", "")
    steps = skill.get("steps", [])
    structured_steps = skill.get("structured_steps", [])
    verification = skill.get("verification")
    context = skill.get("context", "")
    timeout_seconds = skill.get("timeout_seconds")
    retry_policy = skill.get("retry_policy", "retry_on_error")
    args = arguments or {}

    description = _apply_shell_injection(description)
    description = _apply_argument_substitution(description, args)

    if context == "fork" and engine:
        return await _execute_in_fork(skill, browser_session, llm, engine, args)

    if structured_steps and _can_execute_programmatically(structured_steps):
        result = await _execute_structured_steps(
            structured_steps, browser_session, args, timeout_seconds,
        )
        if result and not _looks_like_error(result):
            if verification:
                v_result = await _verify_execution(
                    verification, browser_session, llm,
                )
                if not v_result.get("passed", False):
                    if max_retries > 0:
                        return await _execute_with_healing(
                            skill, browser_session, llm, builder=None,
                            flash_mode=flash_mode, max_retries=max_retries,
                            arguments=args, engine=engine,
                            error_context=v_result.get("fail_reason", "verification failed"),
                        )
                    return result
            _record_execution_metrics(engine, name, result)
            return result

    builder = PromptBuilder(flash_mode=flash_mode)
    task = builder.build_skill_executor_prompt(
        skill_name=name,
        description=description,
        steps=steps,
        verification=verification,
    )

    logger.info("skill_execution_start", skill=name, mode="prompt")

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
                _record_execution_metrics(engine, name, result_text)
                return result_text

            if attempt < max_retries:
                return await _execute_with_healing(
                    skill, browser_session, llm, builder=builder,
                    flash_mode=flash_mode, max_retries=1,
                    arguments=args, engine=engine,
                    error_context=result_text or "unknown error",
                    name=name, description=description,
                    verification=verification,
                )

            return result_text or "Skill execution completed with no output"

        except Exception as e:
            if attempt < max_retries:
                return await _execute_with_healing(
                    skill, browser_session, llm, builder=builder,
                    flash_mode=flash_mode, max_retries=1,
                    arguments=args, engine=engine,
                    error_context=str(e),
                    name=name, description=description,
                    verification=verification,
                )

            logger.error("skill_execution_failed", skill=name, error=str(e))
            return f"Skill '{name}' failed: {e}"


def _can_execute_programmatically(structured_steps: list[dict[str, Any]]) -> bool:
    if not structured_steps:
        return False
    supported = {"navigate", "click", "input", "scroll", "extract"}
    return all(s.get("action_type", "") in supported for s in structured_steps)


async def _execute_structured_steps(
    steps: list[dict[str, Any]],
    browser_session: BrowserSession,
    args: dict[str, str],
    timeout_seconds: int | None = None,
) -> str:
    import asyncio

    results = []
    page = browser_session.page

    for i, step in enumerate(steps):
        action = step.get("action_type", "")
        url = step.get("url", "")
        selector = step.get("selector", "")
        text = step.get("text", "")
        desc = step.get("description", f"Step {i+1}")
        wait_for = step.get("wait_for", "")
        condition = step.get("condition", "")
        on_error = step.get("on_error", "continue")

        if args:
            url = _apply_argument_substitution(url, args)
            text = _apply_argument_substitution(text, args)
            selector = _apply_argument_substitution(selector, args)

        try:
            if action == "navigate" and url:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds or 30000)
                results.append(f"Navigated to {url}")
            elif action == "click" and selector:
                await page.click(selector, timeout=10000)
                results.append(f"Clicked {selector}")
            elif action == "click" and text:
                elements = await page.query_selector_all(f"text={text}")
                if elements:
                    await elements[0].click()
                    results.append(f"Clicked '{text}'")
                else:
                    results.append(f"Could not find '{text}' to click")
                    if on_error == "abort":
                        break
            elif action == "input" and selector and text:
                await page.fill(selector, text, timeout=10000)
                results.append(f"Typed '{text[:30]}' in {selector}")
            elif action == "input" and text:
                await page.keyboard.type(text)
                results.append(f"Typed '{text[:30]}'")
            elif action == "scroll":
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                results.append("Scrolled down")
            elif action == "extract":
                body_text = await page.evaluate("() => document.body.innerText")
                results.append(body_text[:500] if body_text else "Page empty")
            else:
                results.append(f"Skipped unknown action: {action}")

            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=10000)
                except Exception:
                    pass

        except Exception as e:
            results.append(f"Error at step {i+1} ({action}): {str(e)[:100]}")
            if on_error == "abort":
                break

    return "\n".join(results)


async def _verify_execution(
    verification: str,
    browser_session: BrowserSession,
    llm: LLMProvider,
) -> dict[str, bool | str]:
    from sediman.skills.healer import verify_skill
    try:
        screenshot_path = await _capture_screenshot(browser_session)
        dom_snapshot = await _capture_dom(browser_session)
        return await verify_skill(
            skill_name="execution_check",
            skill={},
            verification_prompt=verification,
            llm=llm,
            screenshot_path=screenshot_path,
            dom_snapshot=dom_snapshot,
        )
    except Exception as e:
        return {"passed": False, "fail_reason": str(e)}


async def _execute_with_healing(
    skill: dict[str, Any],
    browser_session: BrowserSession,
    llm: LLMProvider,
    *,
    builder: Any = None,
    flash_mode: bool = True,
    max_retries: int = 1,
    arguments: dict[str, str] | None = None,
    engine: Any = None,
    error_context: str = "",
    name: str = "",
    description: str = "",
    verification: str | None = None,
) -> str:
    if not builder:
        builder = PromptBuilder(flash_mode=flash_mode)
    if not name:
        name = skill.get("name", "unknown")
    if not description:
        description = skill.get("description", "")
    if not verification:
        verification = skill.get("verification")
    steps = skill.get("steps", [])
    args = arguments or {}

    logger.info("skill_retry_with_healing", skill=name)
    screenshot_path = await _capture_screenshot(browser_session)
    dom_snapshot = await _capture_dom(browser_session)
    healed = await heal_skill(
        skill=skill,
        error_context=error_context,
        browser_session=browser_session,
        llm=llm,
        screenshot_path=screenshot_path,
        dom_snapshot=dom_snapshot,
    )
    if healed:
        skill = healed
        steps = skill.get("steps", [])
        verification = skill.get("verification", verification)
        task = builder.build_skill_executor_prompt(
            skill_name=name,
            description=description,
            steps=steps,
            verification=verification,
        )
        result_text, _actions = await run_browser_task(
            task=task,
            browser_session=browser_session,
            llm=llm.get_browser_use_llm(),
            flash_mode=flash_mode,
        )
        return result_text or f"Skill '{name}' completed after healing"

    return error_context or f"Skill '{name}' failed"


def _record_execution_metrics(engine: Any, name: str, result: str) -> None:
    if engine is None:
        return
    try:
        engine.record_usage(name)
    except Exception:
        pass


async def _execute_in_fork(
    skill: dict[str, Any],
    browser_session: BrowserSession,
    llm: LLMProvider,
    engine: Any,
    args: dict[str, str],
) -> str:
    name = skill["name"]
    description = skill.get("description", "")
    steps = skill.get("steps", [])
    verification = skill.get("verification")
    allowed_tools = skill.get("allowed_tools")

    logger.info("skill_fork_execution_start", skill=name)

    from sediman.agent.subagents.factory import SubagentFactory
    from sediman.agent.subagents.registry import SubagentRegistry

    registry = SubagentRegistry()
    factory = SubagentFactory(registry=registry)

    task = _format_steps_for_prompt(steps, args)
    if verification:
        task += f"\n\nVerification: {verification}"

    permission_overrides = {}
    if allowed_tools:
        permission_overrides = allowed_tools

    try:
        result = await factory.spawn(
            name=f"skill-{name[:20]}",
            task=task,
            max_iterations=15,
            permission_overrides=permission_overrides,
        )
        if result and result.text:
            return result.text
        return f"Skill '{name}' completed in subagent"
    except Exception as e:
        logger.warning("skill_fork_failed", skill=name, error=str(e))
        builder = PromptBuilder()
        task = builder.build_skill_executor_prompt(
            skill_name=name,
            description=description,
            steps=steps,
            verification=verification,
        )
        result_text, _ = await run_browser_task(
            task=task,
            browser_session=browser_session,
            llm=llm.get_browser_use_llm(),
        )
        return result_text or f"Skill '{name}' completed (fork fallback)"
