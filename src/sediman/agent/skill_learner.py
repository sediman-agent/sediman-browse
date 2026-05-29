from __future__ import annotations

import json
from typing import Any

import structlog

from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()

_MAX_REFINEMENT_CYCLES = 3


class SkillLearnerAgent:
    def __init__(self, llm: LLMProvider, engine: Any | None = None):
        self.llm = llm
        self._engine = engine

    async def review_and_learn(
        self,
        task: str,
        browser_actions: list[dict[str, Any]],
        result: str,
        success: bool,
        existing_skills: list[dict[str, str]],
        conversation: list[dict[str, str]] | None = None,
    ) -> str | None:
        if not browser_actions or not result:
            return None

        if self._engine and success:
            similar = self._engine.find_similar(task[:64], task)
            if similar:
                quick_steps = self._extract_steps_from_actions(browser_actions)
                if len(quick_steps) >= 2:
                    logger.info("skill_precheck_similar", name=similar["name"])
                    evaluation = {
                        "should_learn": True,
                        "should_patch": True,
                        "skill_name": similar["name"],
                        "description": similar.get("description", ""),
                        "steps": quick_steps,
                    }
                    refined = await self._refine_with_critique(
                        evaluation, task, browser_actions, result, success
                    )
                    return await self._apply_evaluation(refined or evaluation)

        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("skill_review.md")
        if not system_prompt:
            logger.debug("skill_review_template_missing")
            return None

        actions_text = self._format_actions(browser_actions)
        skills_text = self._format_skills(existing_skills)
        conversation_text = (
            self._format_conversation(conversation) if conversation else ""
        )

        user_content = (
            f"Task: {task}\n\n"
            f"Success: {'yes' if success else 'no'}\n\n"
            f"Browser actions taken:\n{actions_text}\n\n"
            f"Result:\n{result[:2000]}\n\n"
            f"Existing skills:\n{skills_text}"
        )
        if conversation_text:
            user_content += f"\n\nConversation history:\n{conversation_text}"

        failed_context = await self._load_failed_trajectories(
            skill_name=None, task=task
        )
        if failed_context:
            user_content += f"\n\n{failed_context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            if not response.text:
                return None

            evaluation = self._parse_response(response.text)
            if not evaluation:
                return None

            if not evaluation.get("should_learn"):
                logger.debug("skill_review_nothing_to_save", task=task[:60])
                return None

            refined = await self._refine_with_critique(
                evaluation, task, browser_actions, result, success
            )
            final = refined or evaluation
            return await self._apply_evaluation(final)

        except Exception as e:
            logger.warning("skill_learner_failed", error=str(e))
            return None

    async def _load_failed_trajectories(
        self, skill_name: str | None, task: str
    ) -> str:
        try:
            from sediman.memory.trajectories import TrajectoryDB

            db = TrajectoryDB()
            failed = await db.get_recent_failures(limit=5, skill_name=skill_name)
            if not failed and task:
                all_failed = await db.get_recent_failures(limit=5)
                failed = [t for t in all_failed if task[:30].lower() in t.task.lower()][:3]

            if not failed:
                return ""

            lines = ["Related past failures for context:"]
            for t in failed:
                lines.append(f"- Task: {t.task[:80]}")
                if t.error_type:
                    lines.append(f"  Error: {t.error_type}")
                if t.result:
                    lines.append(f"  Result: {t.result[:100]}")
                lines.append("")
            return "\n".join(lines)
        except Exception:
            return ""

    async def _refine_with_critique(
        self,
        evaluation: dict[str, Any],
        task: str,
        browser_actions: list[dict[str, Any]],
        result: str,
        success: bool,
    ) -> dict[str, Any] | None:
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("skill_review.md")
        if not system_prompt:
            return None

        refined = dict(evaluation)
        for cycle in range(_MAX_REFINEMENT_CYCLES):
            actions_text = self._format_actions(browser_actions)
            critique_prompt = (
                f"[CRITIQUE MODE]\n\n"
                f"Original task: {task}\n"
                f"Success: {'yes' if success else 'no'}\n\n"
                f"Browser actions:\n{actions_text}\n\n"
                f"Result:\n{result[:1000]}\n\n"
                f"Current skill draft:\n"
                f"Name: {refined.get('skill_name')}\n"
                f"Description: {refined.get('description')}\n"
                f"Steps: {json.dumps(refined.get('steps', []), indent=2)}\n"
                f"Pitfalls: {json.dumps(refined.get('pitfalls', []), indent=2)}\n"
                f"When to use: {refined.get('when_to_use', 'N/A')}\n"
                f"Verification: {refined.get('verification', 'N/A')}\n\n"
                "Critique the above skill and suggest refinements."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": critique_prompt},
            ]

            try:
                response = await self.llm.chat(messages=messages, tools=[])
                if not response.text:
                    break

                critique_data = self._parse_critique(response.text)
                if not critique_data or not critique_data.get("should_refine"):
                    break

                improvements = critique_data.get("improvements", {})
                if improvements.get("steps"):
                    refined["steps"] = improvements["steps"]
                if improvements.get("description"):
                    refined["description"] = improvements["description"]
                if improvements.get("pitfalls"):
                    refined["pitfalls"] = improvements["pitfalls"]
                if improvements.get("when_to_use"):
                    refined["when_to_use"] = improvements["when_to_use"]
                if improvements.get("verification"):
                    refined["verification"] = improvements["verification"]

            except Exception:
                break

        return refined

    def _parse_critique(self, text: str) -> dict[str, Any] | None:
        from sediman.utils import extract_json_from_text

        data = extract_json_from_text(text)
        if not isinstance(data, dict):
            return None
        return data

    def _format_actions(self, actions: list[dict[str, Any]]) -> str:
        lines = []
        for i, action in enumerate(actions, 1):
            action_type = action.get("action", action.get("type", "unknown"))
            detail = self._action_detail(action)
            lines.append(f"{i}. [{action_type}] {detail}")
        return "\n".join(lines) if lines else "No actions recorded"

    def _action_detail(self, action: dict[str, Any]) -> str:
        action_type = action.get("action", action.get("type", ""))
        args = action.get("arguments", action)

        if action_type == "navigate":
            url = args.get("url", "")
            return f"Navigate to {url}" if url else "Navigate"
        if action_type == "click":
            idx = args.get("index", "")
            text = args.get("text", args.get("label", ""))
            parts = []
            if idx:
                parts.append(f"element {idx}")
            if text:
                parts.append(f'"{text}"')
            return f"Click {' '.join(parts)}" if parts else "Click"
        if action_type == "input":
            text = args.get("text", "")
            field = args.get("selector", args.get("label", ""))
            parts = []
            if field:
                parts.append(f"in {field}")
            if text:
                parts.append(f'"{text[:50]}"')
            return f"Type {' '.join(parts)}" if parts else "Type text"
        if action_type == "extract":
            return "Extract data from page"
        if action_type == "scroll":
            direction = args.get("direction", "")
            return f"Scroll {direction}" if direction else "Scroll"
        if action_type == "search":
            query = args.get("query", "")
            return f"Search: {query}" if query else "Search"
        if action_type == "done":
            return "Task complete"
        return str(action)[:100]

    def _format_skills(self, skills: list[dict[str, str]]) -> str:
        if not skills:
            return "No existing skills."
        lines = [f"- {s['name']}: {s.get('description', '')}" for s in skills]
        return "\n".join(lines)

    def _extract_steps_from_actions(self, actions: list[dict[str, Any]]) -> list[str]:
        steps = []
        for action in actions:
            action_type = action.get("action", action.get("type", ""))
            if action_type == "done":
                continue
            detail = self._action_detail(action)
            if detail and detail != "Task complete":
                steps.append(detail)
        return steps

    def _format_conversation(self, conversation: list[dict[str, str]]) -> str:
        recent = conversation[-5:] if len(conversation) > 5 else conversation
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                lines.append(f"[{role}] {content[:150]}")
        return "\n".join(lines) if lines else "No conversation"

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        from sediman.utils import extract_json_from_text

        data = extract_json_from_text(text)
        if data is None:
            logger.debug("skill_learner_json_parse_failed", text=text[:200])
            return None
        if not isinstance(data, dict):
            return None
        if not data.get("should_learn"):
            return {"should_learn": False}
        required = ["skill_name", "description", "steps"]
        for field in required:
            if field not in data:
                logger.debug("skill_learner_missing_field", field=field)
                return None
        if not isinstance(data["steps"], list) or len(data["steps"]) < 2:
            return None
        return data

    async def _apply_evaluation(self, evaluation: dict[str, Any]) -> str | None:
        from sediman.skills.engine import SkillEngine
        from sediman.memory.security import scan_content

        engine = self._engine or SkillEngine()
        name = evaluation["skill_name"]
        description = evaluation["description"]
        steps = evaluation["steps"]
        category = evaluation.get("category", "auto-learned")
        when_to_use = evaluation.get("when_to_use")
        pitfalls = evaluation.get("pitfalls", [])
        verification = evaluation.get("verification")

        all_text = f"{name} {description} {' '.join(str(s) for s in steps)} {' '.join(str(p) for p in pitfalls)}"
        threats = scan_content(all_text)
        if threats:
            logger.warning("skill_rejected_security", name=name, threats=threats)
            return None

        if evaluation.get("should_patch"):
            existing = engine.read(name)
            if existing:
                updates: dict[str, Any] = {
                    "description": description,
                    "steps": steps,
                }
                if when_to_use:
                    updates["when_to_use"] = when_to_use
                if pitfalls:
                    updates["pitfalls"] = pitfalls
                if verification:
                    updates["verification"] = verification
                patched = engine.patch(name, updates)
                if patched:
                    logger.info("skill_learned_patch", name=name, steps=len(steps), new_version=patched.get("version"))
                    return name
        else:
            existing = engine.read(name)
            if existing:
                logger.debug("skill_already_exists", name=name)
                return None

            similar = engine.find_similar(name, description)
            if similar:
                logger.info("skill_similar_found", new_name=name, similar_to=similar.get("name"), action="merging_into_similar")
                updates = {"description": description, "steps": steps}
                if when_to_use:
                    updates["when_to_use"] = when_to_use
                if pitfalls:
                    updates["pitfalls"] = pitfalls
                if verification:
                    updates["verification"] = verification
                patched = engine.patch(similar["name"], updates)
                if patched:
                    return similar["name"]

            engine.create(
                name=name,
                description=description,
                steps=steps,
                category=category,
                when_to_use=when_to_use,
                pitfalls=pitfalls,
                verification=verification,
            )
            logger.info("skill_learned_create", name=name, steps=len(steps), category=category)
            return name
        return None
