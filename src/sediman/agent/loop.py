from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

from sediman.agent.browser_agent import BrowserSubagent, BrowserResult
from sediman.agent.compressor import ContextCompressor
from sediman.agent.delegate import delegate_parallel
from sediman.agent.manager import ManagerAgent, ManagerPlan
from sediman.agent.recorder import SkillRecorder
from sediman.agent.skill_learner import SkillLearnerAgent
from sediman.agent.skill_auditor import SkillAuditor
from sediman.agent.state import (
    AgentPhase,
    AgentState,
    Observation,
    PlanStep,
    Reflection,
    Strategy,
)
from sediman.agent.tool_dispatch import ToolRegistry
from sediman.agent.tools import create_agent_tool_registry
from sediman.browser.session import BrowserSession
from sediman.llm.provider import LLMProvider
from sediman.memory.manager import MemoryManager

logger = structlog.get_logger()

_AGENT_STATE_FILE = Path.home() / ".sediman" / "agent_state.json"


def _load_agent_state() -> dict[str, Any]:
    try:
        if _AGENT_STATE_FILE.exists():
            return json.loads(_AGENT_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_agent_state(data: dict[str, Any]) -> None:
    try:
        _AGENT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AGENT_STATE_FILE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


@dataclass
class StepEvent:
    step: int
    action: str
    observation: str
    phase: str = ""
    detail: str = ""


@dataclass
class AgentResult:
    task: str
    result: str
    steps: list[StepEvent] = field(default_factory=list)
    skill_created: str | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    scheduled_job_id: str | None = None
    schedule_cron: str | None = None
    iterations: int = 0
    strategy_used: str = "direct"


class AgentLoop:
    def __init__(
        self,
        llm_provider: LLMProvider,
        browser_session: BrowserSession,
        max_steps: int = 50,
        on_step: Callable[[StepEvent], None] | None = None,
        flash_mode: bool = True,
        max_conversation: int = 40,
        context_window: int = 10,
        max_iterations: int = 5,
        memory_manager: MemoryManager | None = None,
    ):
        self.llm = llm_provider
        self.browser = browser_session
        self.max_steps = max_steps
        self.on_step = on_step
        self.flash_mode = flash_mode
        self.max_conversation = max_conversation
        self.context_window = context_window
        self._conversation: list[dict[str, str]] = []
        self._compressor = ContextCompressor(llm_provider)
        self._manager = ManagerAgent(llm_provider)
        self._recorder = SkillRecorder()
        self._tool_registry: ToolRegistry | None = None
        self._max_iterations = max_iterations
        self._memory = memory_manager or MemoryManager(llm_provider)
        self._memory_initialized = False
        self._pending_review = False
        self._skill_learner = SkillLearnerAgent(llm_provider)
        self._skill_auditor = SkillAuditor(llm_provider)

        saved = _load_agent_state()
        self._iters_since_skill = saved.get("iters_since_skill", 0)
        self._skill_review_threshold = saved.get("skill_review_threshold", 10)

    def _get_tool_registry(self) -> ToolRegistry:
        if self._tool_registry is None:
            self._tool_registry = create_agent_tool_registry()
        return self._tool_registry

    def _get_browser_agent(self) -> BrowserSubagent:
        on_browser_step = None
        if self.on_step:
            browser_step_counter = [0]
            def on_browser_step(action: str, url: str) -> None:
                browser_step_counter[0] += 1
                self.on_step(StepEvent(
                    step=browser_step_counter[0],
                    action=action,
                    observation=url,
                    phase="executing",
                ))
        return BrowserSubagent(
            browser_session=self.browser,
            llm_provider=self.llm,
            max_steps=self.max_steps,
            flash_mode=self.flash_mode,
            on_browser_step=on_browser_step,
            conversation=self._conversation,
        )

    async def run(self, task: str) -> AgentResult:
        session_id = str(uuid.uuid4())[:8]
        state = AgentState(task=task, max_iterations=self._max_iterations)

        if not self._memory_initialized:
            await self._memory.initialize()
            self._memory_initialized = True

        logger.info("agent_task_start", session_id=session_id, task=task)

        if self._compressor.should_compress(self._conversation):
            self._conversation = await self._compressor.compress(self._conversation)

        # ── Phase 1: Planning ─────────────────────────────────
        state.phase = AgentPhase.PLANNING
        self._emit(state, "Planning task...", detail=task[:100])

        previous_failure = None
        if state.errors:
            previous_failure = state.errors[-1]

        episodic_context = None

        plan = await self._manager.plan(task, self._conversation, previous_failure)
        state = self._build_plan_steps(state, plan)

        logger.info(
            "manager_plan",
            session_id=session_id,
            strategy=plan.strategy.value,
            browser_task=plan.browser_task[:80] if plan.browser_task else "",
            schedule=plan.schedule.cron if plan.schedule else None,
            subtasks=len(plan.subtasks) if plan.subtasks else 0,
        )

        self._emit(
            state,
            f"Plan: {plan.strategy.value}",
            detail=f"Strategy: {plan.strategy.value}"
            + (f" | Subtasks: {len(plan.subtasks)}" if plan.subtasks else "")
            + (f" | Cron: {plan.schedule.cron}" if plan.schedule else ""),
        )

        # ── Fast Path: Conversational (no browser) ──────────────
        if plan.strategy == Strategy.CONVERSATIONAL:
            self._emit(state, "Responding directly...", detail="No browser needed")
            response_text = plan.response or "I'm Sediman. How can I help you?"
            self._conversation.append({"role": "user", "content": task})
            self._conversation.append({"role": "assistant", "content": response_text})
            if len(self._conversation) > self.max_conversation:
                self._conversation = self._conversation[-self.max_conversation:]
            return AgentResult(
                task=task,
                result=response_text,
                strategy_used="conversational",
            )

        # ── Fast Path: Schedule-only (no browser) ─────────────
        if plan.schedule and not plan.browser_task:
            self._emit(state, "Scheduling task...", detail=f"Cron: {plan.schedule.cron}")
            result_text = f"Scheduled: {plan.schedule.cron} → {plan.schedule.task}"
            job_id = self._create_scheduled_job(plan)
            self._conversation.append({"role": "user", "content": task})
            self._conversation.append({"role": "assistant", "content": result_text})
            if len(self._conversation) > self.max_conversation:
                self._conversation = self._conversation[-self.max_conversation:]
            return AgentResult(
                task=task,
                result=result_text,
                scheduled_job_id=job_id,
                schedule_cron=plan.schedule.cron,
                strategy_used="schedule",
            )

        # ── Phase 2: Iterative Execution Loop ──────────────────
        delegate_steps = [s for s in state.plan_steps if s.strategy == Strategy.DELEGATE]
        non_delegate_steps = [s for s in state.plan_steps if s.strategy != Strategy.DELEGATE]

        if len(delegate_steps) > 1:
            await self._execute_parallel_delegates(state, delegate_steps)
            for step in delegate_steps:
                observation = self._build_observation(step, state)
                state.observations.append(observation)
            state.current_step_index = len(delegate_steps)

        while state.should_continue() and state.iteration < state.max_iterations:
            state.iteration += 1

            step = state.current_step
            if step is None:
                break

            if step.status in ("completed", "failed"):
                state.advance_step()
                continue

            state.phase = AgentPhase.EXECUTING
            step.status = "in_progress"
            self._emit(
                state,
                f"Iteration {state.iteration}: {step.description[:60]}",
                detail=f"Strategy: {step.strategy.value} | Retry: {step.retries}/{step.max_retries}",
            )

            if step.strategy == Strategy.DELEGATE:
                await self._execute_delegate_step(state, step)
            elif step.strategy == Strategy.USE_SKILL:
                await self._execute_skill_step(state, step, plan)
            else:
                await self._execute_direct_step(state, step, plan)

            # ── Phase 3: Observe ──────────────────────────────
            state.phase = AgentPhase.OBSERVING
            observation = self._build_observation(step, state)
            state.observations.append(observation)
            self._emit(
                state,
                f"Observed: {'success' if observation.success else 'failure'}",
                detail=observation.content[:100],
            )

            # ── Phase 4: Reflect ──────────────────────────────
            state.phase = AgentPhase.REFLECTING
            reflection = await self._reflect_on_step(state, step, observation)
            state.reflections.append(reflection)
            self._emit(
                state,
                f"Reflection: confidence={reflection.confidence:.1f}, complete={reflection.task_complete}",
                detail=reflection.reasoning[:100] if reflection.reasoning else "",
            )

            if reflection.task_complete and reflection.confidence >= 0.6:
                step.status = "completed"
                step.result = step.result or observation.content[:500]
                state.advance_step()
            elif reflection.should_retry and step.retries < step.max_retries:
                step.retries += 1
                step.status = "pending"
                self._emit(state, f"Retrying step (attempt {step.retries + 1})", detail=step.description[:80])
            elif self._try_fallback(step):
                self._emit(
                    state,
                    f"Falling back to {step.strategy.value}",
                    detail=f"Previous strategy {step.original_strategy.value if step.original_strategy else 'unknown'} failed",
                )
            elif reflection.should_replan and state.iteration < state.max_iterations:
                self._emit(state, "Replanning based on reflection...", detail=reflection.reasoning[:100] if reflection.reasoning else "")
                await self._replan(state, reflection)
            else:
                if reflection.confidence >= 0.3:
                    step.status = "completed"
                    step.result = step.result or observation.content[:500]
                else:
                    step.status = "failed"
                    state.errors.append(f"Step failed: {step.description[:80]}")
                state.advance_step()

        # ── Phase 5: Final Assembly ─────────────────────────────
        state = self._assemble_result(state, plan)
        state.phase = AgentPhase.DONE

        # ── Phase 6: Post-task orchestration ────────────────────
        await self._post_task(state, plan, task)

        logger.info(
            "agent_task_done",
            session_id=session_id,
            result_length=len(state.result),
            iterations=state.iteration,
            actions=len(state.actions_taken),
            scheduled=plan.schedule.cron if plan.schedule else None,
        )

        return AgentResult(
            task=task,
            result=state.result,
            steps=self._build_step_events(state),
            skill_created=state.skill_created,
            actions_taken=state.actions_taken,
            scheduled_job_id=state.scheduled_job_id,
            schedule_cron=state.schedule_cron,
            iterations=state.iteration,
            strategy_used=plan.strategy.value,
        )

    def _build_plan_steps(self, state: AgentState, plan: ManagerPlan) -> AgentState:
        if plan.strategy == Strategy.DELEGATE and plan.subtasks:
            for i, subtask in enumerate(plan.subtasks):
                state.plan_steps.append(
                    PlanStep(
                        id=i,
                        description=subtask,
                        strategy=Strategy.DELEGATE,
                        subagent_type=plan.use_subagent,
                    )
                )
        elif plan.strategy == Strategy.USE_SKILL:
            state.plan_steps.append(
                PlanStep(
                    id=0,
                    description=f"Execute skill '{plan.skill_to_use}': {plan.browser_task}",
                    strategy=Strategy.USE_SKILL,
                )
            )
        else:
            state.plan_steps.append(
                PlanStep(
                    id=0,
                    description=plan.browser_task,
                    strategy=Strategy.DIRECT,
                )
            )
        return state

    async def _execute_direct_step(
        self, state: AgentState, step: PlanStep, plan: ManagerPlan
    ) -> None:
        skill_context = self._find_relevant_skills(step.description)
        browser_agent = self._get_browser_agent()

        browser_result: BrowserResult = await browser_agent.run(
            task=step.description,
            skill_summaries=skill_context,
        )

        step.result = browser_result.text
        state.actions_taken.extend(browser_result.actions)
        self._emit(state, f"Completed {len(browser_result.actions)} browser actions")

    async def _execute_delegate_step(self, state: AgentState, step: PlanStep) -> None:
        try:
            if step.subagent_type:
                factory = self._get_subagent_factory()
                parent_context = {
                    "task": state.task,
                    "errors": [e for e in state.errors],
                    "observations": [o.content[:200] for o in state.observations[-3:]],
                }
                result = await factory.spawn(
                    agent_type=step.subagent_type,
                    task=step.description,
                    parent_context=parent_context,
                )
                step.result = result.summary
                state.actions_taken.extend(result.actions_taken)
                if result.artifacts:
                    for art in result.artifacts:
                        logger.info("subagent_artifact", kind=art.kind, name=art.name)
            else:
                result = await delegate_parallel(
                    tasks=[step.description],
                    browser_session=self.browser,
                    llm_provider=self.llm,
                    max_concurrent=1,
                )
                step.result = result[0] if result else "No result from delegate"
                state.delegate_results.extend(result)
        except Exception as e:
            step.result = f"Delegation failed: {e}"
            logger.warning("delegate_step_failed", error=str(e))

    async def _execute_parallel_delegates(
        self, state: AgentState, steps: list[PlanStep]
    ) -> None:
        state.phase = AgentPhase.DELEGATING
        self._emit(
            state,
            f"Delegating {len(steps)} subtasks in parallel",
            detail="; ".join(s.description[:40] for s in steps),
        )

        # If all steps have subagent_type, use factory parallel spawn
        if all(s.subagent_type for s in steps):
            factory = self._get_subagent_factory()
            parent_context = {
                "task": state.task,
                "errors": [e for e in state.errors],
                "observations": [o.content[:200] for o in state.observations[-3:]],
            }
            specs = [(s.subagent_type or "browser", s.description) for s in steps]
            try:
                results = await factory.spawn_parallel(
                    specs=specs,
                    parent_context=parent_context,
                    max_concurrent=min(3, len(steps)),
                )
                for step, result in zip(steps, results):
                    step.result = result.summary
                    step.status = "completed" if result.success else "failed"
                    state.actions_taken.extend(result.actions_taken)
                self._emit(
                    state,
                    f"Parallel subagents complete: {len(results)} results",
                    detail="; ".join(r.summary[:40] for r in results),
                )
            except Exception as e:
                logger.warning("parallel_subagent_delegation_failed", error=str(e))
                for step in steps:
                    step.result = f"Subagent delegation failed: {e}"
                    step.status = "failed"
                    state.errors.append(f"Parallel subagent delegation failed: {str(e)[:80]}")
            return

        # Fallback to legacy delegate_parallel
        tasks = [s.description for s in steps]
        try:
            results = await delegate_parallel(
                tasks=tasks,
                browser_session=self.browser,
                llm_provider=self.llm,
                max_concurrent=min(3, len(tasks)),
            )
            for step, result in zip(steps, results):
                step.result = result
                step.status = "completed"
            state.delegate_results.extend(results)
            self._emit(
                state,
                f"Parallel delegation complete: {len(results)} results",
                detail="; ".join(r[:40] for r in results),
            )
        except Exception as e:
            logger.warning("parallel_delegation_failed", error=str(e))
            for step in steps:
                step.result = f"Delegation failed: {e}"
                step.status = "failed"
                state.errors.append(f"Parallel delegation failed: {str(e)[:80]}")

    async def _execute_skill_step(
        self, state: AgentState, step: PlanStep, plan: ManagerPlan
    ) -> None:
        from sediman.skills.executor import execute_skill
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine()
        skill_name = plan.skill_to_use or ""
        skill_data = engine.read(skill_name)

        if skill_data:
            try:
                result = await execute_skill(skill_data, self.browser, self.llm)
                step.result = result
                engine.record_usage(skill_name)
            except Exception as e:
                step.result = f"Skill execution failed: {e}"
        else:
            browser_agent = self._get_browser_agent()
            browser_result = await browser_agent.run(task=step.description)
            step.result = browser_result.text
            state.actions_taken.extend(browser_result.actions)

    def _build_observation(self, step: PlanStep, state: AgentState) -> Observation:
        if step.result:
            success = not self._looks_like_error(step.result)
        else:
            success = False
        return Observation(
            source=f"step_{step.id}",
            content=step.result or "No result",
            success=success,
            metadata={"strategy": step.strategy.value, "retries": step.retries},
        )

    async def _reflect_on_step(
        self, state: AgentState, step: PlanStep, observation: Observation
    ) -> Reflection:
        try:
            result = await self._manager.reflect(
                task=state.task,
                result=observation.content,
                observations=[o.content[:200] for o in state.observations[-5:]],
            )

            issues = result.get("issues", [])
            suggested_fix = result.get("suggested_fix")

            should_retry = not observation.success and step.retries < step.max_retries
            should_replan = (
                not observation.success
                and step.retries >= step.max_retries
                and suggested_fix
                and state.iteration < state.max_iterations
            )

            return Reflection(
                task_complete=result.get("task_complete", True),
                confidence=float(result.get("confidence", 0.5)),
                reasoning=result.get("reasoning", ""),
                issues=issues,
                next_action=suggested_fix,
                should_retry=should_retry,
                should_replan=should_replan,
            )
        except Exception as e:
            logger.debug("reflection_failed", error=str(e))
            return Reflection(
                task_complete=observation.success,
                confidence=0.5 if observation.success else 0.2,
                reasoning=f"Reflection failed: {e}. Defaulting to observation success.",
                should_retry=not observation.success and step.retries < step.max_retries,
            )

    async def _replan(self, state: AgentState, reflection: Reflection) -> None:
        failed_step = state.current_step
        if failed_step:
            failed_step.status = "failed"

        new_task = reflection.next_action or state.task
        if reflection.reasoning:
            new_task = f"{new_task} (Previous approach failed: {reflection.reasoning[:200]})"

        plan = await self._manager.plan(new_task, self._conversation)
        new_steps = self._build_plan_steps(AgentState(task=new_task), plan)

        remaining_index = len(state.plan_steps)
        for step in new_steps.plan_steps:
            step.id = remaining_index
            state.plan_steps.append(step)
            remaining_index += 1

    def _assemble_result(self, state: AgentState, plan: ManagerPlan) -> AgentState:
        completed = state.completed_steps
        if completed:
            results = []
            for step in completed:
                if step.result:
                    results.append(step.result)
            state.result = "\n\n".join(results)
        elif state.delegate_results:
            state.result = "\n\n".join(state.delegate_results)
        elif plan.schedule:
            state.result = f"Schedule configured: {plan.schedule.cron} → {plan.schedule.task}"
        else:
            state.result = "Task could not be completed."

        if state.errors:
            state.result += f"\n\n[Encountered {len(state.errors)} error(s) during execution]"

        self._conversation.append({"role": "user", "content": state.task})
        self._conversation.append({"role": "assistant", "content": state.result})

        if len(self._conversation) > self.max_conversation:
            self._conversation = self._conversation[-self.max_conversation:]

        return state

    def _persist_skill_counter(self) -> None:
        _save_agent_state({
            "iters_since_skill": self._iters_since_skill,
            "skill_review_threshold": self._skill_review_threshold,
        })

    async def _post_task(self, state: AgentState, plan: ManagerPlan, task: str) -> None:
        # Save auto-created subagent if ManagerAgent designed one
        if plan.create_subagent:
            try:
                from sediman.agent.subagents.template import AgentTemplate

                subagent_template = AgentTemplate(
                    name=plan.create_subagent.get("name", "auto-agent"),
                    description=plan.create_subagent.get("description", ""),
                    mode="subagent",
                    model=plan.create_subagent.get("model"),
                    permissions=plan.create_subagent.get("permissions", {}),
                    system_prompt=plan.create_subagent.get("system_prompt", ""),
                    max_iterations=int(plan.create_subagent.get("max_iterations", 5)),
                )
                self._subagent_registry.save(subagent_template)
                state.result += f"\n\n[Created new subagent: {subagent_template.name}]"
            except Exception as e:
                logger.warning("auto_subagent_save_failed", error=str(e))

        await self._save_session(task, state.result, state.actions_taken)

        all_actions = state.actions_taken
        recorded = self._recorder.record(
            task=task,
            plan=plan,
            browser_result=state.result,
            browser_actions=all_actions,
        )
        if recorded:
            state.skill_created = recorded

        if not state.skill_created:
            self._iters_since_skill += len(all_actions)
            self._persist_skill_counter()
        else:
            self._iters_since_skill = 0
            self._persist_skill_counter()

        if (
            not state.skill_created
            and not self._pending_review
            and self._iters_since_skill >= self._skill_review_threshold
        ):
            self._pending_review = True
            try:
                learned = await self._run_skill_review(
                    task=task,
                    actions=all_actions,
                    result=state.result,
                )
                if learned:
                    state.skill_created = learned
                    self._iters_since_skill = 0
                    self._persist_skill_counter()
            finally:
                self._pending_review = False

        if plan.schedule:
            job_id = self._create_scheduled_job(plan)
            if job_id:
                state.scheduled_job_id = job_id
                state.schedule_cron = plan.schedule.cron
                schedule_tag = f"[Scheduled: {plan.schedule.cron} → {plan.schedule.task}]"
                if schedule_tag not in state.result and f"Schedule configured: {plan.schedule.cron}" not in state.result:
                    state.result += f"\n\n{schedule_tag}"

        if plan.memory:
            await self._memory.handle_tool_call("memory", {
                "action": "add",
                "target": "memory",
                "content": plan.memory,
            })

        await self._memory.on_turn_start()
        if self._memory.should_review():
            await self._memory.run_background_review(self._conversation)
            audit_result = await self._skill_auditor.audit()
            if audit_result.get("actions"):
                logger.info(
                    "skill_audit_completed",
                    actions=len(audit_result["actions"]),
                    summary=audit_result.get("summary", "")[:100],
                )

        await self._memory.on_session_end()

    async def _run_skill_review(
        self,
        task: str,
        actions: list[dict[str, Any]],
        result: str,
    ) -> str | None:
        try:
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine()
            existing_skills = engine.list_skills()

            learned = await self._skill_learner.review_and_learn(
                task=task,
                browser_actions=actions,
                result=result,
                success=not self._looks_like_error(result),
                existing_skills=existing_skills,
                conversation=self._conversation,
            )
            if learned:
                logger.info("skill_auto_learned", name=learned, source="review_agent")
            return learned
        except Exception as e:
            logger.debug("skill_review_failed", error=str(e))
            return None

    def _looks_like_error(self, text: str) -> bool:
        from sediman.errors import looks_like_error
        return looks_like_error(text)

    def _try_fallback(self, step: PlanStep) -> bool:
        if step.fallback_attempted:
            return False

        fallback_map = {
            Strategy.USE_SKILL: Strategy.DIRECT,
            Strategy.DELEGATE: Strategy.DIRECT,
            Strategy.DECOMPOSE: Strategy.DELEGATE,
        }

        new_strategy = fallback_map.get(step.strategy)
        if new_strategy is None:
            return False

        step.original_strategy = step.original_strategy or step.strategy
        step.strategy = new_strategy
        step.fallback_attempted = True
        step.status = "pending"
        step.retries = 0
        return True

    def _emit(self, state: AgentState, message: str, detail: str = "") -> None:
        if self.on_step:
            self.on_step(StepEvent(
                step=state.iteration,
                action=message,
                observation="",
                phase=state.phase.value,
                detail=detail,
            ))

    def _build_step_events(self, state: AgentState) -> list[StepEvent]:
        events = []
        for i, step in enumerate(state.plan_steps):
            events.append(StepEvent(
                step=i,
                action=f"{step.strategy.value}: {step.description[:80]}",
                observation=step.result[:200] if step.result else "",
            ))
        return events

    def get_conversation(self) -> list[dict[str, str]]:
        return list(self._conversation)

    def set_conversation(self, messages: list[dict[str, str]]) -> None:
        self._conversation = list(messages)

    def clear_conversation(self) -> None:
        self._conversation = []

    async def compress_context(self) -> int:
        if not self._compressor.should_compress(self._conversation):
            return 0
        await self._memory.on_pre_compress()
        before = len(self._conversation)
        self._conversation = await self._compressor.compress(self._conversation)
        return before - len(self._conversation)

    def _build_task_with_context(self, task: str) -> str:
        if not self._conversation:
            return task

        from sediman.utils import format_conversation_context
        context = format_conversation_context(self._conversation, limit=self.context_window)

        return f"""Previous conversation context:
{context}

Current task: {task}

Note: Continue from where we left off. Remember what was discussed above."""

    def _find_relevant_skills(self, task: str) -> str | None:
        from sediman.skills.engine import SkillEngine
        engine = SkillEngine()
        return engine.get_skill_summaries() or None

    async def _save_session(self, task: str, result: str, actions: list[dict[str, Any]]) -> None:
        try:
            from sediman.memory.sessions import save_session
            steps = []
            for a in actions:
                steps.append({
                    "action": json.dumps(a, default=str)[:200],
                    "observation": "",
                })
            await save_session(task=task, steps=steps, result=result)
        except Exception as e:
            logger.debug("session_save_failed", error=str(e))

    def _create_scheduled_job(self, plan: ManagerPlan) -> str | None:
        if not plan.schedule:
            return None
        try:
            from sediman.scheduler.cron import CronManager, validate_cron_expr
            if not validate_cron_expr(plan.schedule.cron):
                logger.warning("invalid_cron_expr", expr=plan.schedule.cron)
                return None
            cron = CronManager()
            job_id = cron.add_job(
                cron_expr=plan.schedule.cron,
                task=plan.schedule.task,
                model=getattr(self.llm, "model", None),
                base_url=getattr(self.llm, "base_url", None),
            )
            logger.info("task_scheduled", job_id=job_id, cron=plan.schedule.cron, task=plan.schedule.task)
            return job_id
        except Exception as e:
            logger.warning("schedule_creation_failed", error=str(e))
            return None

    def get_memory_manager(self) -> MemoryManager:
        return self._memory
