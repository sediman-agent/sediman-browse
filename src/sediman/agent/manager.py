from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from sediman.agent.planner import TaskPlanner, ScheduleIntent
from sediman.agent.state import PlanStep, Strategy
from sediman.llm.provider import LLMProvider
from sediman.memory.manager import MemoryManager

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
    use_subagent: str | None = None
    milestones: list[str] | None = None


class ManagerAgent:
    def __init__(self, llm: LLMProvider, memory_manager: MemoryManager | None = None):
        self.llm = llm
        self._regex_planner = TaskPlanner()
        self._memory = memory_manager

    async def plan(
        self,
        task: str,
        conversation: list[dict[str, str]] | None = None,
        previous_failure: str | None = None,
        on_streaming_token: Callable[[str], None] | None = None,
        regex_plan: Any | None = None,
    ) -> ManagerPlan:
        if regex_plan is None:
            regex_plan = self._regex_planner.plan(task)

        has_conversation = bool(conversation)
        is_fresh_session = conversation is not None and len(conversation) == 0

        if regex_plan.schedule and not has_conversation:
            return ManagerPlan(
                browser_task="",
                schedule=regex_plan.schedule,
            )

        # Fast-path: explicit URL navigation
        if self._is_explicit_url_task(task) and is_fresh_session and not previous_failure:
            return ManagerPlan(browser_task=task)

        # Fast-path: strongly-matching coding keywords (optimization for common patterns)
        if self._is_strong_coding_task(task) and is_fresh_session and not previous_failure:
            return ManagerPlan(
                browser_task=task,
                strategy=Strategy.DELEGATE,
                subtasks=[task],
                use_subagent="code",
            )

        # LLM classification: ask the model once to decide browser/code/conversational
        # Only activate for fresh sessions (empty conversation list explicitly passed)
        if is_fresh_session and not previous_failure and len(task) < 1000:
            classification = await self._classify_task(task)
            if classification == "code":
                return ManagerPlan(
                    browser_task=task,
                    strategy=Strategy.DELEGATE,
                    subtasks=[task],
                    use_subagent="code",
                )
            elif classification == "browser":
                return ManagerPlan(browser_task=task)
            elif classification == "conversational":
                pass  # Fall through to LLM plan for actual conversational response

        try:
            if on_streaming_token:
                manager_plan = await self._llm_plan_stream(
                    task, conversation, previous_failure, on_streaming_token
                )
                if manager_plan is None:
                    manager_plan = await self._llm_plan(task, conversation, previous_failure)
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

        # Fallback: if no action verbs detected, treat as conversational
        from sediman.agent.locales import ACTION_VERBS
        task_lower = task.lower()
        if not any(kw in task_lower for kw in ACTION_VERBS):
            return ManagerPlan(
                browser_task="",
                strategy=Strategy.CONVERSATIONAL,
                response=None,
            )

        return ManagerPlan(browser_task=task)

    async def decompose(
        self,
        task: str,
        max_subtasks: int = 5,
        beam_width: int = 2,
    ) -> list[PlanStep]:
        import asyncio

        candidates = await asyncio.gather(
            *[self._single_decompose(task, max_subtasks, seed=i) for i in range(beam_width)],
            return_exceptions=True,
        )

        valid = []
        for c in candidates:
            if isinstance(c, list) and c:
                valid.append(c)

        if not valid:
            return [PlanStep(id=0, description=task, strategy=Strategy.DIRECT)]

        if len(valid) == 1:
            return valid[0]

        scored = []
        for steps in valid:
            score = self._score_decomposition(steps, task)
            scored.append((score, steps))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    async def _single_decompose(
        self, task: str, max_subtasks: int, seed: int = 0,
    ) -> list[PlanStep]:
        from sediman.agent.prompts.builder import _load_template

        system_prompt = _load_template("manager_system.md")

        seed_hint = ""
        if seed > 0:
            seed_hint = " Provide an alternative decomposition approach.\n"

        decompose_prompt = (
            system_prompt
            + "\n\n## Task Decomposition\n\n"
            "Break this task into independent subtasks that can run in parallel.\n"
            "Each subtask should be a complete, self-contained browser task.\n"
            f"{seed_hint}"
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

        return []

    def _score_decomposition(self, steps: list[PlanStep], task: str) -> float:
        if not steps:
            return 0.0
        score = 0.0
        n = len(steps)
        if 2 <= n <= 4:
            score += 1.0
        elif n == 1:
            score += 0.3
        elif n > 4:
            score += 0.5
        total_desc_len = sum(len(s.description) for s in steps)
        avg_len = total_desc_len / n if n else 0
        if 20 <= avg_len <= 120:
            score += 0.5
        task_words = set(task.lower().split())
        for s in steps:
            desc_words = set(s.description.lower().split())
            overlap = len(task_words & desc_words)
            if overlap > 0:
                score += 0.3
                break
        return score

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
                data = json.loads(text)
                task_complete = data.get("task_complete", False)
                if not isinstance(task_complete, bool):
                    task_complete = str(task_complete).lower() in ("true", "yes", "1")
                confidence = float(data.get("confidence", 0.3))
                confidence = max(0.0, min(1.0, confidence))
                return {
                    "task_complete": task_complete,
                    "confidence": confidence,
                    "reasoning": data.get("reasoning", ""),
                    "issues": data.get("issues", []),
                    "suggested_fix": data.get("suggested_fix"),
                }
        except Exception as e:
            logger.warning("reflect_failed", error=str(e))

        return {
            "task_complete": False,
            "confidence": 0.2,
            "reasoning": "Reflection failed — defaulting to incomplete for safety.",
            "issues": ["reflection_llm_failure"],
            "suggested_fix": None,
        }

    async def generate_milestones(self, task: str) -> list[str]:
        from sediman.agent.progress import generate_milestones_prompt, parse_milestones

        prompt = generate_milestones_prompt(task)
        messages = [
            {"role": "system", "content": "You are a task planning assistant. Generate milestones as requested."},
            {"role": "user", "content": prompt},
        ]
        try:
            response = await self.llm.chat(messages=messages, tools=[])
            text = response.text or ""
            milestones = parse_milestones(text)
            if milestones:
                return milestones
        except Exception as e:
            logger.debug("generate_milestones_failed", error=str(e))
        return []

    async def _build_prompt(
        self,
        task: str,
        conversation: list[dict[str, str]] | None,
        previous_failure: str | None,
    ) -> str:
        from sediman.agent.prompts.builder import _load_template
        from sediman.utils import format_conversation_context

        system_prompt = _load_template("manager_system.md")

        if conversation:
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

        import asyncio

        async def _empty() -> str | None:
            return None

        results = await asyncio.gather(
            self._get_episodic_context_async(task),
            self._memory.get_preference_context() if self._memory else _empty(),
            self._memory.get_trajectory_context(task) if self._memory else _empty(),
            return_exceptions=True,
        )
        episodic = results[0] if not isinstance(results[0], Exception) else None
        preference_ctx = results[1] if not isinstance(results[1], Exception) else None
        trajectory_ctx = results[2] if not isinstance(results[2], Exception) else None

        if episodic:
            system_prompt += (
                f"\n\n<episodic_memory>\n"
                f"Relevant past experiences:\n{episodic}\n"
                f"</episodic_memory>"
            )

        if preference_ctx:
            system_prompt += (
                f"\n\n<skill_preferences>\n"
                f"{preference_ctx}\n"
                f"</skill_preferences>"
            )

        if trajectory_ctx:
            system_prompt += (
                f"\n\n<similar_past_tasks>\n"
                f"{trajectory_ctx}\n"
                f"</similar_past_tasks>"
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

        return system_prompt

    async def _llm_plan_stream(
        self,
        task: str,
        conversation: list[dict[str, str]] | None,
        previous_failure: str | None,
        on_token: Callable[[str], None],
    ) -> ManagerPlan | None:
        system_prompt = await self._build_prompt(task, conversation, previous_failure)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        text = await self._collect_llm_response(messages, on_token)
        if text:
            json_text = self._extract_json(text)
            if json_text:
                try:
                    data = json.loads(json_text)
                    plan = self._parse_plan_data(data)
                    if plan:
                        return plan
                except json.JSONDecodeError:
                    logger.debug("manager_plan_json_parse_failed", text=json_text[:200])

            return ManagerPlan(
                browser_task="",
                strategy=Strategy.CONVERSATIONAL,
                response=text.strip(),
            )

        return None

    async def _collect_llm_response(
        self,
        messages: list[dict[str, Any]],
        on_token: Callable[[str], None] | None = None,
    ) -> str | None:
        """Call the LLM and collect the full response. Tries non-streaming first
        (most reliable), then falls back to streaming, then tries without system message."""
        last_error: str | None = None

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            response_text = response.text or ""
            if response_text.strip():
                if on_token:
                    for chunk in self._chunk_text(response_text, size=3):
                        on_token(chunk)
                return response_text
        except Exception as e:
            last_error = str(e)
            logger.warning("plan_chat_failed, falling back to streaming", error=last_error)

        chunks: list[str] = []
        try:
            async for token in self.llm.chat_stream(messages=messages, tools=[]):
                if token:
                    chunks.append(token)
                    if on_token:
                        on_token(token)
        except Exception as e:
            last_error = last_error or str(e)
            logger.warning("plan_stream_failed", error=str(e))

        text = "".join(chunks)
        if text.strip():
            return text

        user_content = ""
        for m in messages:
            if m.get("role") == "user":
                user_content = m.get("content", "")
        if user_content:
            try:
                simple_messages = [
                    {"role": "user", "content": f"Respond conversationally: {user_content}"}
                ]
                response = await self.llm.chat(messages=simple_messages, tools=[])
                response_text = response.text or ""
                if response_text.strip():
                    if on_token:
                        for chunk in self._chunk_text(response_text, size=3):
                            on_token(chunk)
                    return response_text
            except Exception as e:
                last_error = last_error or str(e)
                logger.warning("plan_simple_chat_failed", error=str(e))

        return None

    @staticmethod
    def _chunk_text(text: str, size: int = 3) -> list[str]:
        return [text[i:i + size] for i in range(0, len(text), size)]

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

        milestones = data.get("milestones")
        if milestones and not isinstance(milestones, list):
            milestones = None

        return ManagerPlan(
            browser_task=browser_task,
            schedule=schedule,
            memory=data.get("memory"),
            skill_name=data.get("skill_name"),
            skill_description=data.get("skill_description"),
            strategy=strategy,
            subtasks=subtasks,
            skill_to_use=skill_to_use,
            use_subagent=data.get("use_subagent"),
            milestones=[str(m) for m in milestones] if milestones else None,
        )

    async def _llm_plan(
        self,
        task: str,
        conversation: list[dict[str, str]] | None = None,
        previous_failure: str | None = None,
    ) -> ManagerPlan | None:
        system_prompt = await self._build_prompt(task, conversation, previous_failure)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        text = await self._collect_llm_response(messages)
        if text:
            if text.startswith("[LLM error:"):
                return None
            json_text = self._extract_json(text)
            if json_text:
                try:
                    data = json.loads(json_text)
                    plan = self._parse_plan_data(data)
                    if plan:
                        return plan
                except json.JSONDecodeError:
                    logger.debug("manager_plan_json_parse_failed", text=json_text[:200])

            return None

        return None

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

    async def _get_episodic_context_async(self, task: str) -> str | None:
        try:
            if self._memory:
                context = await self._memory._async_get_relevant_context(task, limit=3)
            else:
                from sediman.memory.prompt import get_relevant_context
                context = get_relevant_context(task, limit=3)
            if context:
                return "\n".join(f"- {c}" for c in context)[:400]
        except Exception:
            pass
        return None

    def _get_episodic_context(self, task: str) -> str | None:
        try:
            if self._memory:
                context = self._memory.get_relevant_context(task, limit=3)
            else:
                from sediman.memory.prompt import get_relevant_context
                context = get_relevant_context(task, limit=3)
            if context:
                return "\n".join(f"- {c}" for c in context)[:400]
        except Exception:
            pass
        return None

    def _is_explicit_url_task(self, task: str) -> bool:
        import re

        if len(task) >= 300:
            return False
        task_stripped = task.strip()
        url_patterns = (
            r'^(?:go\s+to|open|visit|browse|navigate\s+to)\s+https?://\S+$',
            r'^https?://\S+$',
            r'^check\s+https?://\S+',
        )
        for pattern in url_patterns:
            if re.search(pattern, task_stripped, re.IGNORECASE):
                return True
        if "http://" in task_stripped or "https://" in task_stripped:
            from sediman.agent.locales import CHAT_KEYWORDS, SCHEDULE_KEYWORDS
            task_lower = task_stripped.lower()
            if not any(kw in task_lower for kw in CHAT_KEYWORDS):
                if not any(kw in task_lower for kw in SCHEDULE_KEYWORDS):
                    return True
        return False

    _STRONG_CODING_KEYWORDS = (
        "npm install", "pip install", "cargo build", "cargo run",
        "yarn add", "pnpm add", "bun add", "bun install",
        "uv pip install", "uv add",
        "pytest", "jest", "vitest", "mocha",
        "run the tests", "run tests", "run test suite",
        "git commit", "git push", "git clone",
        "create a new project", "initialize a project",
        "docker build", "docker compose",
        "run the build", "build the project",
        "deploy to", "set up ci/cd",
    )

    def _is_strong_coding_task(self, task: str) -> bool:
        if len(task) >= 500:
            return False
        task_lower = task.lower()
        return any(kw in task_lower for kw in self._STRONG_CODING_KEYWORDS)

    async def _classify_task(self, task: str) -> str | None:
        try:
            from sediman.agent.coding_agent.prompts import build_classification_prompt

            prompt = build_classification_prompt(task)
            messages = [
                {"role": "user", "content": prompt},
            ]
            response = await self.llm.chat(messages=messages, tools=[])
            text = (response.text or "").strip().lower()

            if "code" in text:
                return "code"
            elif "browser" in text:
                return "browser"
            elif "conversational" in text:
                return "conversational"
            else:
                logger.debug("classify_task_unclear", response=text[:80])
                return None
        except Exception as e:
            logger.debug("classify_task_failed", error=str(e))
            return None

    _CODING_KEYWORDS = (
        "install", "pip install", "npm install", "cargo", "yarn add",
        "run test", "run the test", "run tests", "pytest", "jest",
        "build", "compile", "make", "cargo build",
        "write a script", "create a file", "edit the file",
        "fix the code", "fix the bug", "debug",
        "git commit", "git push", "git pull",
        "start the server", "run the server", "run the app",
        "create a project", "initialize", "init a",
        "set up", "setup", "configure",
        "execute", "run the command", "run this",
        "install dep", "update dep", "upgrade dep",
    )

    def _is_simple_coding_task(self, task: str) -> bool:
        if len(task) >= 500:
            return False
        task_lower = task.lower()
        return any(kw in task_lower for kw in self._CODING_KEYWORDS)

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
