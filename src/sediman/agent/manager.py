from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from sediman.agent.planner import TaskPlanner, ScheduleIntent
from sediman.agent.state import PlanStep, Strategy
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()


@dataclass
class ManagerPlan:
    browser_task: str
    schedule: ScheduleIntent | None = None
    memory: str | None = None
    skill_name: str | None = None
    skill_description: str | None = None
    strategy: Strategy = Strategy.DIRECT
    subtasks: list[str] | None = None
    skill_to_use: str | None = None
    response: str | None = None


class ManagerAgent:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        self._regex_planner = TaskPlanner()

    async def plan(
        self,
        task: str,
        conversation: list[dict[str, str]] | None = None,
        previous_failure: str | None = None,
        on_streaming_token: Callable[[str], None] | None = None,
    ) -> ManagerPlan:
        regex_plan = self._regex_planner.plan(task)

        if regex_plan.schedule and not conversation:
            return ManagerPlan(
                browser_task="",
                schedule=regex_plan.schedule,
            )

        if self._is_simple_browser_task(task) and not conversation and not previous_failure:
            return ManagerPlan(browser_task=task)

        try:
            if on_streaming_token:
                manager_plan = await self._llm_plan_stream(
                    task, conversation, previous_failure, on_streaming_token
                )
            else:
                manager_plan = await self._llm_plan(task, conversation, previous_failure)
            if manager_plan:
                if regex_plan.schedule and not manager_plan.schedule:
                    manager_plan.schedule = regex_plan.schedule
                    if manager_plan.strategy != Strategy.CONVERSATIONAL:
                        manager_plan.browser_task = ""
                return manager_plan
        except Exception as e:
            logger.debug("manager_llm_plan_failed", error=str(e))

        if regex_plan.schedule:
            browser_task = self._contextualize_browser_task(
                regex_plan.browser_task, conversation
            )
            return ManagerPlan(
                browser_task=browser_task,
                schedule=regex_plan.schedule,
            )

        return ManagerPlan(browser_task=task)

    async def decompose(
        self,
        task: str,
        max_subtasks: int = 5,
    ) -> list[PlanStep]:
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("manager_system.md")

        decompose_prompt = (
            system_prompt
            + "\n\n## Task Decomposition\n\n"
            "Break this task into independent subtasks that can run in parallel.\n"
            "Each subtask should be a complete, self-contained browser task.\n"
            f"Maximum {max_subtasks} subtasks.\n\n"
            'Respond with JSON: {"subtasks": ["task1", "task2", ...]}'
        )

        messages = [
            {"role": "system", "content": decompose_prompt},
            {"role": "user", "content": task},
        ]

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            text = response.text or ""
            text = self._extract_json(text)
            if text:
                data = json.loads(text)
                subtasks = data.get("subtasks", [])
                steps = []
                for i, subtask in enumerate(subtasks[:max_subtasks]):
                    steps.append(PlanStep(
                        id=i,
                        description=subtask,
                        strategy=Strategy.DELEGATE,
                    ))
                return steps
        except Exception as e:
            logger.debug("decompose_failed", error=str(e))

        return [PlanStep(id=0, description=task, strategy=Strategy.DIRECT)]

    async def reflect(
        self,
        task: str,
        result: str,
        observations: list[str],
    ) -> dict[str, Any]:
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("reflection.md")

        obs_text = "\n".join(f"- {o}" for o in observations[-10:]) if observations else "None"

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Original task: {task}\n\n"
                    f"Result obtained:\n{result[:2000]}\n\n"
                    f"Observations during execution:\n{obs_text}\n\n"
                    "Evaluate whether the task was completed successfully."
                ),
            },
        ]

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            text = response.text or ""
            text = self._extract_json(text)
            if text:
                return json.loads(text)
        except Exception as e:
            logger.debug("reflect_failed", error=str(e))

        return {
            "task_complete": True,
            "confidence": 0.5,
            "reasoning": "Defaulting to complete due to reflection failure.",
            "issues": [],
        }

    async def _llm_plan_stream(
        self,
        task: str,
        conversation: list[dict[str, str]] | None,
        previous_failure: str | None,
        on_token: Callable[[str], None],
    ) -> ManagerPlan | None:
        """Streaming version of _llm_plan — yields reasoning tokens as they arrive."""
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("manager_system.md")

        if conversation:
            from sediman.utils import format_conversation_context
            context = format_conversation_context(conversation, limit=10)
            system_prompt += (
                "\n\n<conversation_history>\n"
                "The user has had previous interactions. Use this context to "
                "understand follow-up messages, corrections, and references "
                "to earlier tasks.\n\n"
                f"{context}\n"
                "</conversation_history>"
            )

        if previous_failure:
            system_prompt += (
                f"\n\n<previous_failure>\n"
                f"The previous attempt failed with this error:\n{previous_failure}\n"
                f"Adjust the plan to avoid the same failure.\n"
                f"</previous_failure>"
            )

        episodic = self._get_episodic_context(task)
        if episodic:
            system_prompt += (
                f"\n\n<episodic_memory>\n"
                f"Relevant past experiences:\n{episodic}\n"
                f"</episodic_memory>"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        # Collect streaming response
        chunks: list[str] = []
        try:
            async for token in self.llm.chat_stream(messages=messages, tools=[]):
                if token:
                    chunks.append(token)
                    on_token(token)
        except Exception as e:
            logger.debug("plan_stream_failed", error=str(e))
            return None

        text = "".join(chunks)
        if not text.strip():
            return None

        text = self._extract_json(text)
        if not text:
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("manager_plan_json_parse_failed", text=text[:200])
            return None

        return self._parse_plan_data(data)

    def _parse_plan_data(self, data: dict[str, Any]) -> ManagerPlan | None:
        """Parse the JSON dict into a ManagerPlan."""
        browser_task = data.get("browser_task", "")

        strategy = Strategy.DIRECT
        strat_str = data.get("strategy", "direct")
        try:
            strategy = Strategy(strat_str)
        except ValueError:
            pass

        response_text = data.get("response")

        if strategy == Strategy.CONVERSATIONAL:
            return ManagerPlan(
                browser_task="",
                strategy=Strategy.CONVERSATIONAL,
                response=response_text or "I'm Sediman, your browser automation agent. How can I help you?",
            )

        subtasks = data.get("subtasks")
        if subtasks and not isinstance(subtasks, list):
            subtasks = None

        skill_to_use = data.get("skill_to_use")
        if skill_to_use and strategy == Strategy.USE_SKILL:
            browser_task = f"Execute skill '{skill_to_use}' for: {browser_task}"

        schedule = None
        sched_data = data.get("schedule")
        if sched_data and isinstance(sched_data, dict):
            from sediman.scheduler.cron import validate_cron_expr
            cron = sched_data.get("cron", "")
            if validate_cron_expr(cron):
                schedule = ScheduleIntent(
                    cron=cron,
                    task=sched_data.get("task", browser_task or data.get("task", "")),
                )

        if not browser_task and schedule:
            return ManagerPlan(
                browser_task="",
                schedule=schedule,
            )

        if not browser_task:
            browser_task = data.get("task", "")

        return ManagerPlan(
            browser_task=browser_task,
            schedule=schedule,
            memory=data.get("memory"),
            skill_name=data.get("skill_name"),
            skill_description=data.get("skill_description"),
            strategy=strategy,
            subtasks=subtasks,
            skill_to_use=skill_to_use,
        )

    async def _llm_plan(
        self,
        task: str,
        conversation: list[dict[str, str]] | None = None,
        previous_failure: str | None = None,
    ) -> ManagerPlan | None:
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("manager_system.md")

        if conversation:
            from sediman.utils import format_conversation_context
            context = format_conversation_context(conversation, limit=10)
            system_prompt += (

                "\n\n<conversation_history>\n"
                "The user has had previous interactions. Use this context to "
                "understand follow-up messages, corrections, and references "
                "to earlier tasks.\n\n"
                f"{context}\n"
                "</conversation_history>"
            )

        if previous_failure:
            system_prompt += (
                f"\n\n<previous_failure>\n"
                f"The previous attempt failed with this error:\n{previous_failure}\n"
                f"Adjust the plan to avoid the same failure.\n"
                f"</previous_failure>"
            )

        episodic = self._get_episodic_context(task)
        if episodic:
            system_prompt += (
                f"\n\n<episodic_memory>\n"
                f"Relevant past experiences:\n{episodic}\n"
                f"</episodic_memory>"
            )

        schedule_ctx = self._get_schedule_context(task)
        if schedule_ctx:
            system_prompt += (
                f"\n\n<recent_schedule_results>\n"
                f"The user has scheduled tasks that have recently run. "
                f"If they ask about past results, use this data in your response.\n\n"
                f"{schedule_ctx}\n"
                f"</recent_schedule_results>"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        response = await self.llm.chat(messages=messages, tools=[])

        text = response.text or ""
        if not text.strip():
            return None

        text = self._extract_json(text)
        if not text:
            return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("manager_plan_json_parse_failed", text=text[:200])
            return None

        browser_task = data.get("browser_task", "")

        strategy = Strategy.DIRECT
        strat_str = data.get("strategy", "direct")
        try:
            strategy = Strategy(strat_str)
        except ValueError:
            pass

        response_text = data.get("response")

        if strategy == Strategy.CONVERSATIONAL:
            return ManagerPlan(
                browser_task="",
                strategy=Strategy.CONVERSATIONAL,
                response=response_text or "I'm Sediman, your browser automation agent. How can I help you?",
            )

        subtasks = data.get("subtasks")
        if subtasks and not isinstance(subtasks, list):
            subtasks = None

        skill_to_use = data.get("skill_to_use")
        if skill_to_use and strategy == Strategy.USE_SKILL:
            browser_task = f"Execute skill '{skill_to_use}' for: {browser_task}"

        schedule = None
        sched_data = data.get("schedule")
        if sched_data and isinstance(sched_data, dict):
            from sediman.scheduler.cron import validate_cron_expr
            cron = sched_data.get("cron", "")
            if validate_cron_expr(cron):
                schedule = ScheduleIntent(
                    cron=cron,
                    task=sched_data.get("task", browser_task or task),
                )

        if not browser_task and schedule:
            return ManagerPlan(
                browser_task="",
                schedule=schedule,
            )

        if not browser_task:
            browser_task = task

        return ManagerPlan(
            browser_task=browser_task,
            schedule=schedule,
            memory=data.get("memory"),
            skill_name=data.get("skill_name"),
            skill_description=data.get("skill_description"),
            strategy=strategy,
            subtasks=subtasks,
            skill_to_use=skill_to_use,
        )

    def _contextualize_browser_task(
        self,
        browser_task: str,
        conversation: list[dict[str, str]] | None,
    ) -> str:
        if not conversation:
            return browser_task
        context_lines = []
        for msg in conversation[-6:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_lines.append(f"{role}: {msg['content'][:200]}")
        context = "\n".join(context_lines)
        return (
            f"Previous conversation:\n{context}\n\n"
            f"Current task: {browser_task}\n\n"
            f"Note: Continue from where we left off."
        )

    def _extract_json(self, text: str) -> str | None:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        if text.startswith("{"):
            return text

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]

        return None

    def _get_episodic_context(self, task: str) -> str | None:
        try:
            from sediman.memory.prompt import get_relevant_context
            context = get_relevant_context(task, limit=3)
            if context:
                return "\n".join(f"- {c}" for c in context)[:400]
        except Exception:
            pass
        return None

    def _is_simple_browser_task(self, task: str) -> bool:
        if len(task) >= 200:
            return False
        task_lower = task.lower()
        if any(kw in task_lower for kw in ("chat", "converse", "discuss")):
            return False
        if any(kw in task_lower for kw in ("schedule", "cron", "remind", "recurring", "interval", "periodically")):
            return False
        # Vague/ambiguous tasks need LLM interpretation
        if any(kw in task_lower for kw in ("sorry", "actually", "wait", "never mind", "no i meant", "i meant")):
            return False
        # Must contain a clear action verb for fast-path
        action_verbs = ("go to", "open", "visit", "browse", "navigate", "search", "find", "check", "get", "buy", "book", "fill", "download", "upload", "log in", "sign in", "click", "scrape", "monitor", "track", "watch", "extract", "take screenshot")
        if not any(kw in task_lower for kw in action_verbs):
            return False
        return True

    def _get_schedule_context(self, task: str) -> str | None:
        try:
            from sediman.scheduler.cron import CronManager
            cron = CronManager()
            jobs = cron.list_jobs()
            if not jobs:
                return None
            task_lower = task.lower()
            schedule_keywords = (
                "result", "last", "past", "previous", "found", "got",
                "price", "stock", "data", "value", "check", "report",
                "schedule", "scheduled", "job", "run", "ran",
            )
            is_asking_about_schedule = any(
                kw in task_lower for kw in schedule_keywords
            )
            if not is_asking_about_schedule:
                return None
            lines = []
            for job in jobs:
                job_task = job.get("task", "").lower()
                matches_topic = any(
                    kw in job_task or kw in task_lower
                    for kw in task_lower.split()
                    if len(kw) > 2
                )
                if not matches_topic:
                    continue
                has_result = bool(job.get("last_result"))
                lines.append(
                    f"- Job {job['id']} (cron: {job.get('cron', 'N/A')}): "
                    f"Task: {job.get('task', 'N/A')}\n"
                    f"  Status: {'Has run' if has_result else 'NOT YET RUN — scheduled but never executed'}\n"
                    f"  Last run: {job.get('last_run', 'never')}\n"
                    f"  Result: {job.get('last_result', 'No result yet — the cron job has not executed')}"
                )
            if not lines:
                return None
            header = (
                "IMPORTANT: The user is asking about scheduled task results. "
                "Include the actual data in your response. "
                "If no results exist yet, tell them the job hasn't run yet.\n\n"
            )
            return (header + "\n".join(lines))[:1500]
        except Exception:
            return None
