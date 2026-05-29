from __future__ import annotations

from typing import Any

import structlog

from sediman.agent.prompts.builder import PromptBuilder
from sediman.browser.session import BrowserSession
from sediman.llm.provider import LLMProvider
from sediman.skills.engine import SkillEngine

logger = structlog.get_logger()


def _safe_read_screenshot(path: str | None) -> str | None:
    if not path:
        return None
    try:
        from pathlib import Path
        from base64 import b64encode

        p = Path(path)
        if p.exists() and p.stat().st_size < 5 * 1024 * 1024:
            return b64encode(p.read_bytes()).decode("utf-8")
    except Exception as e:
        logger.debug("screenshot_read_failed", path=path, error=str(e))
    return None


def _truncate_dom(dom: str | None, max_chars: int = 3000) -> str | None:
    if dom is None:
        return None
    return dom[:max_chars]


async def heal_skill(
    skill: dict[str, Any],
    error_context: str,
    browser_session: BrowserSession,
    llm: LLMProvider,
    engine: SkillEngine | None = None,
    screenshot_path: str | None = None,
    dom_snapshot: str | None = None,
) -> dict[str, Any] | None:
    name = skill["name"]
    steps = skill.get("steps", [])

    logger.info("skill_healing_start", skill=name, has_screenshot=screenshot_path is not None)

    healer_system = PromptBuilder.get_healer_prompt()

    steps_text = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))

    user_text = f"""Skill name: "{name}"

Original steps:
{steps_text}

Error context:
{error_context}

Please analyze the failure and provide updated steps."""

    dom_text = _truncate_dom(dom_snapshot)
    if dom_text:
        user_text += f"\n\nDOM snapshot (at failure point):\n{dom_text}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": healer_system},
    ]

    screenshot_b64 = _safe_read_screenshot(screenshot_path)
    if screenshot_b64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                        "detail": "low",
                    },
                },
            ],
        })
    else:
        messages.append({"role": "user", "content": user_text})

    try:
        response = await llm.chat(messages=messages, tools=[])
        if not response.text:
            logger.warning("heal_no_response", skill=name)
            return None


        from sediman.utils import extract_json_from_text

        data = extract_json_from_text(response.text)
        if data is None:
            logger.warning("heal_parse_failed", skill=name)
            return None

        if "error" in data:
            logger.warning(
                "heal_unfixable",
                skill=name,
                reason=data.get("error", data.get("reasoning", "unknown")),
            )
            return None

        new_steps = data.get("steps", [])
        if not new_steps:
            logger.warning("heal_empty_steps", skill=name)
            return None

        confidence = data.get("confidence", "medium")
        reasoning = data.get("reasoning", "unknown")

        engine = engine or SkillEngine()
        patched = engine.patch(name, {"steps": new_steps})

        if patched:
            logger.info(
                "skill_healed",
                skill=name,
                old_version=skill.get("version", 1),
                new_version=patched["version"],
                confidence=confidence,
                reason=reasoning,
                screenshot_used=screenshot_path is not None,
            )

        return patched

    except Exception as e:
        logger.warning("heal_failed", skill=name, error=str(e))
        return None


def verify_skill(
    skill_name: str,
    skill: dict[str, Any],
    verification_prompt: str,
    screenshot_path: str | None = None,
    dom_snapshot: str | None = None,
) -> dict[str, bool | str]:
    prompt = (
        f"You are verifying whether a browser automation skill executed correctly.\n\n"
        f"Skill name: {skill_name}\n"
        f"Skill description: {skill.get('description', '')}\n"
        f"Verification criteria: {verification_prompt}\n"
    )

    if dom_snapshot:
        dom_trimmed = _truncate_dom(dom_snapshot)
        if dom_trimmed:
            prompt += f"\nDOM snapshot:\n{dom_trimmed}\n"

    prompt += "\nDoes the result satisfy the verification criteria? Respond with JSON: {\"passed\": true/false, \"fail_reason\": \"...\"}"

    messages = [{"role": "user", "content": prompt}]

    screenshot_b64 = _safe_read_screenshot(screenshot_path)
    if screenshot_b64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                        "detail": "low",
                    },
                },
            ],
        })

    return {
        "passed": True,
        "fail_reason": "",
    }
