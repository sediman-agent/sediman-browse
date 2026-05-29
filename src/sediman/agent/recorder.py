from __future__ import annotations

from typing import Any

import structlog

from sediman.agent.manager import ManagerPlan
from sediman.skills.format import StepData

logger = structlog.get_logger()


class SkillRecorder:
    def should_record(
        self,
        task: str,
        plan: ManagerPlan,
        browser_actions: list[dict[str, Any]],
    ) -> bool:
        if plan.skill_name:
            return len(browser_actions) >= 2
        if len(browser_actions) < 3:
            return False
        distinct_types = set()
        for action in browser_actions:
            action_type = action.get("action", action.get("type", ""))
            if action_type and action_type != "done":
                distinct_types.add(action_type)
        if len(distinct_types) < 2:
            return False
        return True

    def record(
        self,
        task: str,
        plan: ManagerPlan,
        browser_result: str,
        browser_actions: list[dict[str, Any]],
        engine: Any | None = None,
    ) -> str | None:
        if not self.should_record(task, plan, browser_actions):
            return None

        from sediman.skills.engine import SkillEngine

        engine = engine or SkillEngine()

        skill_name = plan.skill_name or self._infer_skill_name(task)
        if not skill_name:
            return None

        existing = engine.read(skill_name)
        if existing:
            logger.debug("skill_already_exists", name=skill_name)
            return None

        string_steps, structured_steps = self._build_steps(task, plan, browser_actions)

        description = plan.skill_description or task[:100]
        variables = self._extract_variables_from_actions(browser_actions)
        engine.create(
            name=skill_name,
            description=description,
            steps=string_steps,
            category="auto-recorded",
            structured_steps=structured_steps,
            variables=variables,
        )

        logger.info(
            "skill_recorded",
            name=skill_name,
            steps=len(string_steps),
            variables=len(variables),
            source="recorder",
        )
        return skill_name

    def _infer_skill_name(self, task: str) -> str | None:
        import re

        cleaned = re.sub(r"[^a-z0-9\s]", "", task.lower())
        words = cleaned.split()[:5]
        if not words:
            return None
        name = "-".join(words)
        name = re.sub(r"-+", "-", name).strip("-")
        if len(name) < 3:
            return None
        if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", name):
            return None
        return name

    def _build_steps(
        self,
        task: str,
        plan: ManagerPlan,
        browser_actions: list[dict[str, Any]],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        step_objs: list[StepData] = []

        if plan.browser_task and plan.browser_task != task:
            step_objs.append(StepData(description=f"Task: {plan.browser_task}"))

        for action in browser_actions:
            sd = StepData.from_browser_action(action)
            if sd.description and sd.action_type != "done":
                step_objs.append(sd)

        if plan.schedule:
            step_objs.append(
                StepData(description=f"Schedule: {plan.schedule.cron} — {plan.schedule.task}")
            )

        if not step_objs:
            step_objs.append(StepData(description=task[:200]))

        string_steps = [s.to_string() for s in step_objs]
        structured_steps = [s.to_json() for s in step_objs]
        return string_steps, structured_steps

    def _extract_variables_from_actions(
        self, actions: list[dict[str, Any]]
    ) -> list[str]:
        variables = []
        seen_urls = set()
        seen_texts = set()

        for action in actions:
            action_type = action.get("action", action.get("type", ""))
            args = action.get("arguments", action)

            if action_type == "navigate":
                url = args.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
            elif action_type == "input":
                text = args.get("text", "")
                if text and len(text) > 2 and text not in seen_texts:
                    seen_texts.add(text)
                    variables.append(f"input_value_{len(variables) + 1}")
            elif action_type == "search":
                query = args.get("query", "")
                if query:
                    variables.append("search_query")

        return variables[:10]

    def _summarize_action(self, action: dict[str, Any]) -> str | None:
        action_type = action.get("action", action.get("type", ""))
        if action_type == "done":
            return None

        args = action.get("arguments", action)
        if action_type == "click":
            idx = args.get("index", "")
            text = args.get("text", args.get("label", ""))
            parts = []
            if idx:
                parts.append(f"element {idx}")
            if text:
                parts.append(f'"{text}"')
            return "Click " + " ".join(parts) if parts else None

        if action_type == "input":
            text = args.get("text", "")
            field = args.get("selector", args.get("label", ""))
            parts = []
            if field:
                parts.append(f"in {field}")
            if text:
                parts.append(f'"{text[:50]}"')
            return "Type " + " ".join(parts) if parts else None

        if action_type == "navigate":
            url = args.get("url", "")
            return f"Navigate to {url}" if url else None

        if action_type == "extract":
            return "Extract data from page"

        if action_type == "scroll":
            return "Scroll page"

        if action_type == "search":
            query = args.get("query", "")
            return f"Search: {query}" if query else None

        detail = str(action)[:100]
        return detail if detail else None
