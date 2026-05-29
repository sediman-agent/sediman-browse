from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()

_STALE_THRESHOLD_DAYS = 30


class SkillAuditor:
    def __init__(self, llm: LLMProvider, engine: Any | None = None):
        self.llm = llm
        self._engine = engine

    async def audit(self) -> dict[str, Any]:
        from sediman.skills.engine import SkillEngine

        engine = self._engine or SkillEngine()
        if hasattr(engine, 'list_skills_full'):
            skills = engine.list_skills_full()
        else:
            skills = engine.list_skills()
        if not skills:
            return {"actions": [], "summary": "No skills to audit."}

        skill_details = []
        for s in skills:
            full = engine.read(s["name"])
            if full:
                detail = {
                    "name": full["name"],
                    "description": full.get("description", ""),
                    "steps_count": len(full.get("steps", [])),
                    "version": full.get("version", 1),
                    "updated_at": full.get("updated_at"),
                    "use_count": full.get("use_count", 0),
                    "last_used_at": full.get("last_used_at"),
                }
                skill_details.append(detail)

        stale_names = self._identify_stale(skill_details)

        system_prompt = self._build_prompt(skill_details, stale_names)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please audit the skills listed above and recommend actions."},
        ]

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            if not response.text:
                return {"actions": [], "summary": "Audit produced no response."}

            result = self._parse_response(response.text)
            if result:
                await self._apply_actions(result, engine)
            return result or {"actions": [], "summary": "Audit could not parse response."}

        except Exception as e:
            logger.warning("skill_audit_failed", error=str(e))
            return {"actions": [], "summary": f"Audit failed: {e}"}

    def _identify_stale(self, skills: list[dict[str, Any]]) -> list[str]:
        now = datetime.now(timezone.utc)
        stale = []
        for s in skills:
            updated = s.get("updated_at")
            last_used = s.get("last_used_at")

            if not updated and not last_used:
                stale.append(s["name"])
                continue

            ref_str = last_used or updated
            try:
                ref_dt = datetime.fromisoformat(ref_str)
                if ref_dt.tzinfo is None:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                age_days = (now - ref_dt).days
                if age_days > _STALE_THRESHOLD_DAYS:
                    stale.append(s["name"])
            except (ValueError, TypeError):
                pass

        return stale

    def _build_prompt(
        self, skills: list[dict[str, Any]], stale_names: list[str]
    ) -> str:
        from sediman.agent.prompts.builder import _load_template

        template = _load_template("skill_audit.md")

        lines = ["<current_skills>"]
        for s in skills:
            stale_tag = " [STALE]" if s["name"] in stale_names else ""
            lines.append(
                f"- {s['name']}{stale_tag}: {s['description']} "
                f"(v{s['version']}, steps={s['steps_count']}, "
                f"used={s['use_count']}x, last={s.get('last_used_at', 'never')}, "
                f"updated={s.get('updated_at', 'unknown')})"
            )
        lines.append("</current_skills>")

        return f"{template}\n\n{chr(10).join(lines)}"

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        text = text.strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
            else:
                return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug("skill_audit_json_parse_failed", text=text[:200])
            return None

    async def _apply_actions(self, result: dict[str, Any], engine: Any) -> None:
        actions = result.get("actions", [])
        for action_item in actions:
            name = action_item.get("skill_name", "")
            action = action_item.get("action", "keep")
            reason = action_item.get("reason", "")

            if action == "delete":
                deleted = engine.delete(name)
                if deleted:
                    logger.info("skill_audit_deleted", name=name, reason=reason)
            elif action == "archive":
                patched = engine.patch(name, {"category": "archived"})
                if patched:
                    logger.info("skill_audit_archived", name=name, reason=reason)
