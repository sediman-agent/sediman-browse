from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

from pathlib import Path as _Path

from sediman.agent.browser_agent import BrowserSubagent, BrowserResult
from sediman.agent.compressor import ContextCompressor
from sediman.agent.delegate import delegate_parallel
from sediman.agent.manager import ManagerAgent, ManagerPlan
from sediman.agent.planner import TaskPlanner
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
from sediman.agent.subagents.factory import SubagentFactory
from sediman.agent.subagents.registry import SubagentRegistry
from sediman.agent.tool_dispatch import ToolRegistry, ToolLoop
from sediman.agent.tools import create_agent_tool_registry
from sediman.agent.guardrails import (
    AuditLog,
    Budget,
    TraceCollector,
    Trace,
    assess_risk,
    GLOBAL_APPROVAL,
    SharedScratchpad,
)
from sediman.agent.progress import (
    ProgressTracker,
    generate_milestones_prompt,
    parse_milestones,
)
from sediman.browser.session import BrowserSession
from sediman.llm.provider import LLMProvider
from sediman.memory.manager import MemoryManager

logger = structlog.get_logger()

import re as _re

_AGENT_STATE_FILE = Path.home() / ".sediman" / "agent_state.json"

_SIMPLE_URL_RE = _re.compile(
    r'^(?:go\s+to|open|visit|browse|navigate\s+to)\s+https?://\S+$', _re.IGNORECASE
)


def _load_agent_state() -> dict[str, Any]:
    try:
        if _AGENT_STATE_FILE.exists():
            return json.loads(_AGENT_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_agent_state(data: dict[str, Any]) -> None:
    pass


@dataclass
class StepEvent:
    step: int
    action: str
    observation: str
    phase: str = ""
    detail: str = ""
    url: str | None = None
    tool_name: str | None = None


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
        max_steps: int = 25,
        on_step: Callable[[StepEvent], None] | None = None,
        on_streaming_text: Callable[[str, str], None] | None = None,
        flash_mode: bool = True,
        max_conversation: int = 40,
        context_window: int = 10,
        max_iterations: int = 50,
        memory_manager: MemoryManager | None = None,
        skip_reflection_on_success: bool = True,
        turbo_mode: bool = False,
    ):
        self._budget = Budget()
        self.llm = llm_provider
        self.llm.set_token_callback(self._budget.add_tokens)
        self.browser = browser_session
        self.max_steps = max_steps
        self.on_step = on_step
        self.on_streaming_text = on_streaming_text
        self.flash_mode = flash_mode
        self.turbo_mode = turbo_mode
        self.max_conversation = max_conversation
        self.context_window = context_window
        self._conversation: list[dict[str, str]] = []
        self._compressor = ContextCompressor(llm_provider)
        self._manager = ManagerAgent(llm_provider, memory_manager=memory_manager)
        self._regex_planner = TaskPlanner()
        self._recorder = SkillRecorder()
        self._tool_registry: ToolRegistry | None = None
        self._max_iterations = max_iterations
        self._memory = memory_manager or MemoryManager(llm_provider)
        self._memory_initialized = False
        self._pending_review = False
        self._skill_engine: Any | None = None
        self._skill_learner = SkillLearnerAgent(llm_provider, trajectory_db=self._get_trajectory_db())
        self._skill_auditor = SkillAuditor(llm_provider)
        self._subagent_registry = SubagentRegistry()
        self._subagent_factory: SubagentFactory | None = None
        self._skip_reflection_on_success = skip_reflection_on_success

        # Cached state to avoid redundant disk reads / LLM calls
        self._cached_skill_summaries: str | None = None  # deprecated, kept for compat
        self._cached_browser_use_llm: Any | None = None
        self._cached_memory_context: str | None = None
        self._recording_manager: Any | None = None

        saved = _load_agent_state()
        self._iters_since_skill = saved.get("iters_since_skill", 0)
        self._skill_review_threshold = saved.get("skill_review_threshold", 10)
        self._trace_collector = TraceCollector.get()
        self._audit = AuditLog.get()
        self._scratchpad = SharedScratchpad()
        self._progress: ProgressTracker | None = None

    def _get_tool_registry(self) -> ToolRegistry:
        if self._tool_registry is None:
            self._tool_registry = create_agent_tool_registry()
            from sediman.agent.checkpoint import CheckpointManager
            cp = CheckpointManager(enabled=True)
            self._tool_registry.set_checkpoint_manager(cp)
        return self._tool_registry

    def _get_engine(self) -> Any:
        if self._skill_engine is None:
            from sediman.skills.engine import SkillEngine
            self._skill_engine = SkillEngine()
            self._skill_learner._engine = self._skill_engine
            self._skill_auditor._engine = self._skill_engine
        return self._skill_engine

    def _get_subagent_factory(self) -> SubagentFactory:
        if self._subagent_factory is None:
            self._subagent_factory = SubagentFactory(
                registry=self._subagent_registry,
                llm_provider=self.llm,
                browser_session=self.browser,
                tool_registry=self._get_tool_registry(),
                on_step=self.on_step,
                flash_mode=self.flash_mode,
                on_streaming_text=self.on_streaming_text,
            )
            from sediman.agent.tools import set_subagent_factory
            set_subagent_factory(self._subagent_factory)
        return self._subagent_factory

    def _get_browser_agent(self, recording_name: str | None = None, task: str = "") -> BrowserSubagent:
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
                    url=url if url.startswith("http") else None,
                ))
        if self._cached_memory_context is None:
            try:
                from sediman.memory.store import MemoryStore
                memory_store = MemoryStore()
                self._cached_memory_context = memory_store.format_for_system_prompt_filtered(
                    task or "browser task", max_chars=800
                )
            except Exception:
                self._cached_memory_context = ""
        return BrowserSubagent(
            browser_session=self.browser,
            llm_provider=self.llm,
            max_steps=self.max_steps,
            flash_mode=self.flash_mode,
            turbo_mode=self.turbo_mode,
            on_browser_step=on_browser_step,
            conversation=self._conversation,
            recording_name=recording_name,
            memory_context=self._cached_memory_context,
            browser_use_llm=self._cached_browser_use_llm,
        )

    async def run(self, task: str) -> AgentResult:
        session_id = str(uuid.uuid4())[:8]
        state = AgentState(task=task, max_iterations=self._max_iterations)
        self._budget = Budget()
        self._budget.start()
        self.llm.set_token_callback(self._budget.add_tokens)
        trace = self._trace_collector.start_trace("agent.run", task=task[:100])
        root_span = trace.spans[0] if trace.spans else None

        if not self._memory_initialized:
            await self._memory.initialize()
            self._memory_initialized = True

        logger.info("agent_task_start", session_id=session_id, task=task)
        self._audit.record("agent", "task_start", task[:100], session_id=session_id)

        if self._compressor.should_compress(self._conversation):
            self._conversation = await self._compressor.compress(self._conversation)

        # ── Turbo Path: zero-overhead for simple browser tasks ────
        if self.turbo_mode and self._is_turbo_eligible(task):
            return await self._run_turbo(task, session_id, state)

        # ── Fast Path: URL-only tasks skip LLM planning ────────
        if _SIMPLE_URL_RE.match(task.strip()) and not self._conversation:
            self._emit(state, "Direct navigation (URL fast path)", detail=task[:100])
            url = task.strip().split()[-1]
            step = PlanStep(id=0, description=task, strategy=Strategy.DIRECT)
            step.status = "in_progress"
            recording_name = self._get_active_recording_name()
            browser_agent = self._get_browser_agent(recording_name=recording_name, task=task)
            browser_result: BrowserResult = await browser_agent.run(task=task)
            if browser_agent._browser_use_llm is not None:
                self._cached_browser_use_llm = browser_agent._browser_use_llm
            step.result = browser_result.text
            step.status = "completed"
            state.actions_taken.extend(browser_result.actions)
            state.result = browser_result.text
            self._conversation.append({"role": "user", "content": task})
            self._conversation.append({"role": "assistant", "content": state.result})
            if len(self._conversation) > self.max_conversation:
                self._conversation = self._conversation[-self.max_conversation:]
            plan = ManagerPlan(browser_task=task, strategy=Strategy.DIRECT)
            asyncio.create_task(self._run_background_post_task(state, plan, task))
            return AgentResult(
                task=task, result=state.result,
                steps=[StepEvent(step=0, action=f"navigate: {url}", observation=browser_result.text[:200])],
                actions_taken=state.actions_taken, iterations=1, strategy_used="direct",
            )

        # ── Fast Path: regex planner already resolved scheduling ──
        regex_plan = self._regex_planner.plan(task)
        if regex_plan.schedule and not self._conversation:
            self._emit(state, "Scheduling task (regex)", detail=f"Cron: {regex_plan.schedule.cron}")
            result_text = f"Scheduled: {regex_plan.schedule.cron} → {regex_plan.schedule.task}"
            job_id = None
            try:
                from sediman.scheduler.cron import CronManager, validate_cron_expr
                if validate_cron_expr(regex_plan.schedule.cron):
                    cron = CronManager()
                    job_id = cron.add_job(
                        cron_expr=regex_plan.schedule.cron,
                        task=regex_plan.schedule.task,
                        model=getattr(self.llm, "model", None),
                        base_url=getattr(self.llm, "base_url", None),
                    )
            except Exception as e:
                logger.debug("regex_schedule_failed", error=str(e))
            self._conversation.append({"role": "user", "content": task})
            self._conversation.append({"role": "assistant", "content": result_text})
            if len(self._conversation) > self.max_conversation:
                self._conversation = self._conversation[-self.max_conversation:]
            return AgentResult(
                task=task, result=result_text,
                scheduled_job_id=job_id, schedule_cron=regex_plan.schedule.cron,
                strategy_used="schedule",
            )

        # ── Phase 1: Planning ─────────────────────────────────
        state.phase = AgentPhase.PLANNING
        self._emit(state, "Planning task...", detail=task[:100])

        previous_failure = None
        if state.errors:
            previous_failure = state.errors[-1]

        # Emit streaming plan reasoning if on_step is wired
        def on_plan_token(token: str) -> None:
            self._stream_text(token, phase="planning")

        plan = await self._manager.plan(
            task, self._conversation, previous_failure, on_streaming_token=on_plan_token,
            regex_plan=regex_plan,
        )
        state = self._build_plan_steps(state, plan)

        # ── Progress Tracking: milestones + loop detection ────
        milestones = plan.milestones
        if not milestones and plan.strategy not in (Strategy.CONVERSATIONAL,) and not plan.schedule:
            try:
                milestones = await self._manager.generate_milestones(task)
            except Exception:
                milestones = []
        self._progress = ProgressTracker(milestones=milestones)
        if milestones:
            self._emit(state, f"Milestones: {len(milestones)}", detail=" | ".join(milestones[:4]))

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
            response_text = plan.response or ""
            if not response_text:
                response_text = "I'm Sediman. How can I help you?"
            else:
                await self._stream_text_async(response_text, phase="responding")
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

        if len(delegate_steps) > 1:
            await self._execute_parallel_delegates(state, delegate_steps)
            for step in delegate_steps:
                observation = self._build_observation(step, state)
                state.observations.append(observation)
            state.current_step_index = len(delegate_steps)

        while state.should_continue() and state.iteration < state.max_iterations:
            exhausted, reason = self._budget.is_exhausted()
            if exhausted:
                self._audit.record("agent", "budget_exhausted", reason)
                logger.warning("budget_exhausted", reason=reason)
                break

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
                f"Step {state.iteration}: {step.description[:80]}",
                detail=f"Strategy: {step.strategy.value} | Retry: {step.retries}/{step.max_retries}",
            )

            if step.strategy == Strategy.DELEGATE:
                exec_span = trace.new_span("execute.delegate", root_span, step=step.id)
                await self._execute_delegate_step(state, step)
                trace.finish_span(exec_span, status="ok" if step.result and not self._looks_like_error(step.result) else "error")
            elif step.strategy == Strategy.USE_SKILL:
                exec_span = trace.new_span("execute.skill", root_span, step=step.id)
                await self._execute_skill_step(state, step, plan)
                trace.finish_span(exec_span, status="ok" if step.result and not self._looks_like_error(step.result) else "error")
            else:
                exec_span = trace.new_span("execute.direct", root_span, step=step.id)
                await self._execute_direct_step(state, step, plan)
                trace.finish_span(exec_span, status="ok" if step.result and not self._looks_like_error(step.result) else "error")
            self._budget.add_action()

            # ── Phase 3: Observe ──────────────────────────────
            state.phase = AgentPhase.OBSERVING
            observation = self._build_observation(step, state)
            state.observations.append(observation)
            self._emit(
                state,
                f"Observed: {'success' if observation.success else 'failure'}",
                detail=observation.content[:100],
            )

            # ── Progress Check (loop detection + milestones) ──
            if self._progress is not None:
                page_url = ""
                page_text = ""
                try:
                    ctrl = await self._ensure_browser_controller()
                    if ctrl and ctrl.is_started:
                        snap = await ctrl.snapshot()
                        page_url = snap.url
                        page_text = snap.text_preview or ""
                except Exception:
                    pass

                report = self._progress.check_heuristics(
                    action=step.description,
                    page_url=page_url,
                    page_text=page_text,
                )

                if report.loop_detected:
                    self._emit(state, "LOOP DETECTED", detail=report.reason)
                    logger.warning("loop_detected", step=step.id, reason=report.reason)

                if report.should_replan:
                    self._audit.record("agent", "progress_replan", report.reason)

                if self._progress.should_check_milestone():
                    next_m = self._progress.milestones.next_unachieved()
                    if next_m:
                        m_report = await self._progress.check_milestone(
                            llm=self.llm,
                            milestone=next_m,
                            page_snapshot=page_text,
                            page_url=page_url,
                        )
                        if m_report.milestone_achieved:
                            self._emit(state, f"MILESTONE: {m_report.milestone_achieved}")
                        if m_report.should_replan:
                            self._emit(state, "MILESTONE STUCK", detail=m_report.reason)

            # ── Phase 4: Reflect (conditional) ──────────────
            # Skip reflection if the step succeeded and produced substantial output,
            # unless it's a complex multi-step task or previous errors exist.
            reflection = await self._reflect_on_step(state, step, observation)
            if reflection is not None:
                state.reflections.append(reflection)
                self._emit(
                    state,
                    f"Reflection: confidence={reflection.confidence:.1f}, complete={reflection.task_complete}",
                    detail=reflection.reasoning[:100] if reflection.reasoning else "",
                )
                await self._handle_reflection_result(state, step, reflection, observation)
            else:
                # Fast-path: mark complete without LLM reflection
                step.status = "completed"
                state.advance_step()

        # ── Phase 5: Final Assembly ─────────────────────────────
        state = await self._assemble_result(state, plan)
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

    def _is_turbo_eligible(self, task: str) -> bool:
        from sediman.agent.locales import (
            SCHEDULE_KEYWORDS,
            CHAT_KEYWORDS,
            AMBIGUOUS_KEYWORDS,
            ACTION_VERBS,
        )

        if self._conversation:
            return False
        if len(task) > 500:
            return False
        task_lower = task.lower()
        if any(kw in task_lower for kw in SCHEDULE_KEYWORDS):
            return False
        if any(kw in task_lower for kw in CHAT_KEYWORDS):
            return False
        if any(kw in task_lower for kw in AMBIGUOUS_KEYWORDS):
            return False
        if not any(kw in task_lower for kw in ACTION_VERBS):
            return False
        return True

    async def _run_turbo(
        self, task: str, session_id: str, state: AgentState
    ) -> AgentResult:
        self._emit(state, "Executing (turbo)...", detail=task[:100])
        state.phase = AgentPhase.EXECUTING

        step = PlanStep(id=0, description=task, strategy=Strategy.DIRECT)
        step.status = "in_progress"

        recording_name = self._get_active_recording_name()
        browser_agent = self._get_browser_agent(recording_name=recording_name, task=task)

        browser_result: BrowserResult = await browser_agent.run(
            task=task,
        )

        if browser_agent._browser_use_llm is not None:
            self._cached_browser_use_llm = browser_agent._browser_use_llm

        step.result = browser_result.text
        step.status = "completed"
        state.actions_taken.extend(browser_result.actions)
        state.result = browser_result.text

        self._conversation.append({"role": "user", "content": task})
        self._conversation.append({"role": "assistant", "content": state.result})
        if len(self._conversation) > self.max_conversation:
            self._conversation = self._conversation[-self.max_conversation:]

        self._emit(state, f"Turbo complete: {len(browser_result.actions)} actions")

        logger.info(
            "turbo_task_done",
            session_id=session_id,
            result_length=len(state.result),
            actions=len(browser_result.actions),
        )

        plan = ManagerPlan(browser_task=task, strategy=Strategy.DIRECT)

        asyncio.create_task(self._run_background_post_task(state, plan, task))

        return AgentResult(
            task=task,
            result=state.result,
            steps=[StepEvent(step=0, action=f"direct: {task[:80]}", observation=browser_result.text[:200])],
            actions_taken=state.actions_taken,
            iterations=1,
            strategy_used="direct",
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

    def _get_tool_loop(self) -> ToolLoop:
        registry = self._get_tool_registry()
        return ToolLoop(llm=self.llm, registry=registry, max_rounds=self.max_steps)

    async def _ensure_browser_controller(self) -> Any:
        from sediman.browser.tools import get_default_browser_controller, set_default_browser_controller
        ctrl = get_default_browser_controller()
        if ctrl is not None:
            return ctrl
        from sediman.browser.controller import BrowserController
        ctrl = BrowserController(headless=self.browser.headless)
        try:
            browser_obj = self.browser.browser
            if browser_obj is not None:
                try:
                    page = await browser_obj.get_current_page()
                    if page:
                        ctrl._own_page = page
                except Exception:
                    pass
        except Exception:
            pass
        set_default_browser_controller(ctrl)
        return ctrl

    async def _execute_direct_step(
        self, state: AgentState, step: PlanStep, plan: ManagerPlan
    ) -> None:
        tool_result = await self._try_tool_loop_execution(state, step)
        if tool_result is not None:
            step.result = tool_result
            self._emit(state, f"Completed via tool loop")
            return

        recording_name = self._get_active_recording_name()
        browser_agent = self._get_browser_agent(recording_name=recording_name, task=step.description)

        browser_result: BrowserResult = await browser_agent.run(
            task=step.description,
        )

        step.result = browser_result.text
        state.actions_taken.extend(browser_result.actions)
        self._emit(state, f"Completed {len(browser_result.actions)} browser actions")
        if browser_result.text:
            await self._stream_text_async(browser_result.text[:500], phase="executing")

    async def _try_tool_loop_execution(
        self, state: AgentState, step: PlanStep,
    ) -> str | None:
        try:
            await self._ensure_browser_controller()
        except Exception as e:
            logger.debug("tool_loop_browser_ctrl_failed", error=str(e))
            return None

        registry = self._get_tool_registry()
        if not registry.has_tool("browser_navigate"):
            try:
                from sediman.browser.tools import register_browser_tools
                register_browser_tools(registry)
            except Exception as e:
                logger.debug("tool_loop_register_browser_failed", error=str(e))
                return None

        tool_loop = ToolLoop(llm=self.llm, registry=registry, max_rounds=min(25, self.max_steps), budget=self._budget)

        try:
            from sediman.agent.prompts.builder import PromptBuilder
            prompt_builder = PromptBuilder(flash_mode=self.flash_mode)
            system_prompt = prompt_builder.build_system_prompt(
                task=step.description,
                memory_context=self._cached_memory_context,
            )
        except Exception:
            system_parts = [
                "You are Sediman, an autonomous browser automation agent.",
                "Use browser tools to complete the task step by step.",
                "Always start with browser_navigate, then browser_snapshot to see the page.",
                "Use browser_click/browser_type to interact with elements by their ref_id.",
                "After completing the task, respond with a summary of what you did and found.",
            ]
            system_prompt = "\n".join(system_parts)

        context_parts = []
        if self._conversation:
            for msg in self._conversation[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:200]
                context_parts.append(f"{role}: {content}")
        if state.observations:
            for obs in state.observations[-3:]:
                context_parts.append(f"Previous observation: {obs.content[:200]}")

        user_content = step.description
        if context_parts:
            user_content = (
                f"Context:\n" + "\n".join(context_parts)
                + f"\n\nCurrent task: {step.description}"
            )

        messages = [
            {"role": "user", "content": user_content},
        ]

        def _on_tool_call(name: str, args: dict[str, Any]) -> None:
            self._emit(state, f"Tool: {name}", detail=str(args)[:100], tool_name=name)

        try:
            response = await tool_loop.run(messages=messages, system=system_prompt, on_tool_call=_on_tool_call)
            result = response.text or ""
            if not result or len(result.strip()) < 50:
                return None
            state.actions_taken.append({"action": "tool_loop", "task": step.description[:100]})
            return result
        except Exception as e:
            logger.warning("tool_loop_execution_failed", error=str(e))
            return None

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

        engine = self._get_engine()
        skill_name = plan.skill_to_use or ""
        skill_data = engine.read(skill_name)

        if skill_data:
            try:
                skill_args = self._extract_skill_arguments(skill_data, state.current_task or "")
                result = await execute_skill(
                    skill_data, self.browser, self.llm,
                    engine=engine, arguments=skill_args,
                )
                step.result = result
                engine.record_usage(skill_name)
            except Exception as e:
                step.result = f"Skill execution failed: {e}"
        else:
            recording_name = self._get_active_recording_name()
            browser_agent = self._get_browser_agent(recording_name=recording_name, task=step.description)
            browser_result = await browser_agent.run(task=step.description)
            step.result = browser_result.text
            state.actions_taken.extend(browser_result.actions)

    def _build_observation(self, step: PlanStep, state: AgentState) -> Observation:
        content = step.result or ""
        if not content:
            return Observation(
                source=f"step_{step.id}",
                content="No result produced",
                success=False,
                metadata={"strategy": step.strategy.value, "retries": step.retries},
            )

        has_error = self._looks_like_error(content)
        is_very_short = len(content.strip()) < 20
        has_done_action = any(
            a.get("action") == "done" or a.get("type") == "done"
            for a in state.actions_taken[-5:]
        )
        success = not has_error and not is_very_short
        if success and not has_done_action and len(content) < 50:
            success = False

        return Observation(
            source=f"step_{step.id}",
            content=content,
            success=success,
            metadata={"strategy": step.strategy.value, "retries": step.retries},
        )

    async def _reflect_on_step(
        self, state: AgentState, step: PlanStep, observation: Observation
    ) -> Reflection | None:
        from sediman.agent.guardrails import AuditLog

        content = observation.content or ""

        def _has_data_values(text: str) -> bool:
            import re as _re
            if _re.search(r'\d+\.?\d*', text):
                return True
            if _re.search(r'https?://\S+', text):
                return True
            if _re.search(r'[\w.-]+@[\w.-]+', text):
                return True
            return False

        has_done_action = any(
            a.get("action") == "done" or a.get("type") == "done"
            for a in state.actions_taken[-5:]
        )
        has_error_indicators = self._looks_like_error(content)

        if len(state.plan_steps) == 1 and observation.success and not state.errors:
            if _has_data_values(content) and len(content) > 80:
                AuditLog.get().record("reflection", "single_step_fast_path", "single-step success with data", step=step.id)
                return Reflection(
                    task_complete=True,
                    confidence=0.75,
                    reasoning="Single-step plan completed with grounded data.",
                    should_retry=False,
                    should_replan=False,
                )
            elif has_done_action and not has_error_indicators and len(content) > 40:
                AuditLog.get().record("reflection", "single_step_done", "single-step with done action", step=step.id)
                return Reflection(
                    task_complete=True,
                    confidence=0.70,
                    reasoning="Single-step plan completed, browser reported done, no errors.",
                    should_retry=False,
                    should_replan=False,
                )
            elif not state.errors and step.retries == 0:
                AuditLog.get().record("reflection", "single_step_verify", "single-step but no grounded data, verifying", step=step.id)

        if self._skip_reflection_on_success:
            if (
                observation.success
                and has_done_action
                and len(content) > 80
                and not state.errors
                and not has_error_indicators
                and step.retries == 0
                and _has_data_values(content)
            ):
                AuditLog.get().record("reflection", "fast_path_success", "done_action_with_data", step=step.id)
                return Reflection(
                    task_complete=True,
                    confidence=0.70,
                    reasoning="Fast-path: browser reported done with grounded data, no errors.",
                    should_retry=False,
                    should_replan=False,
                )

        if not observation.success and self._looks_like_error(content):
            from sediman.agent.guardrails import AuditLog
            AuditLog.get().record("reflection", "fast_path_error", "error_indicators_detected", step=step.id)
            should_retry = step.retries < step.max_retries
            return Reflection(
                task_complete=False,
                confidence=0.15,
                reasoning=f"Error fast-path: result contains error indicators.",
                should_retry=should_retry,
                should_replan=not should_retry and state.iteration < state.max_iterations,
                retry_context=f"Error detected: {content[:200]}",
            )

        if not observation.success:
            should_retry = step.retries < step.max_retries
            return Reflection(
                task_complete=False,
                confidence=0.3,
                reasoning="Observation reports failure without specific error pattern.",
                should_retry=should_retry,
                should_replan=not should_retry and state.iteration < state.max_iterations,
                retry_context=f"Observation marked as failed: {content[:200]}",
            )

        if len(content) < 80:
            return Reflection(
                task_complete=False,
                confidence=0.25,
                reasoning=f"Result too short ({len(content)} chars) to contain meaningful data.",
                should_retry=step.retries < step.max_retries,
                retry_context="Previous attempt produced insufficient output.",
            )

        task_lower = state.task.lower()
        task_words = [w for w in task_lower.split() if len(w) > 3 and w not in (
            "check", "find", "search", "look", "what", "show", "tell", "please",
            "could", "would", "about", "from", "with", "that", "this",
        )]
        has_err = self._looks_like_error(content)
        if task_words and observation.success and not has_err and len(content) > 150 and _has_data_values(content):
            content_lower = content.lower()
            matched = sum(1 for w in task_words if w in content_lower)
            threshold = max(3, len(task_words) * 3 // 4)
            if matched >= threshold:
                AuditLog.get().record("reflection", "data_match", f"{matched}/{len(task_words)} keywords", step=step.id)
                return Reflection(
                    task_complete=True,
                    confidence=0.7,
                    reasoning=f"Data-match: {matched}/{len(task_words)} task keywords found with grounded values.",
                    should_retry=False,
                    should_replan=False,
                )

        if len(content) > 80 and observation.success and step.retries == 0 and not state.errors and not has_err:
            AuditLog.get().record("reflection", "llm_reflect", "falling_through_to_llm", step=step.id, content_len=len(content))

        try:
            result = await self._manager.reflect(
                task=state.task,
                result=observation.content,
                observations=[o.content[:300] for o in state.observations[-5:]],
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

            tc = result.get("task_complete", False)
            if not isinstance(tc, bool):
                tc = str(tc).lower() in ("true", "yes", "1")
            conf = float(result.get("confidence", 0.3))
            conf = max(0.0, min(1.0, conf))
            reasoning_text = result.get("reasoning", "")
            retry_ctx = reasoning_text if not tc else None
            return Reflection(
                task_complete=tc,
                confidence=conf,
                reasoning=reasoning_text,
                issues=issues,
                next_action=suggested_fix,
                should_retry=should_retry,
                should_replan=should_replan,
                retry_context=retry_ctx,
            )
        except Exception as e:
            logger.warning("reflection_failed", error=str(e))
            from sediman.agent.guardrails import AuditLog
            AuditLog.get().record("reflection", "failed", str(e), step_id=step.id)
            return Reflection(
                task_complete=False,
                confidence=0.2,
                reasoning=f"Reflection LLM call failed: {e}. Defaulting to incomplete for safety.",
                should_retry=not observation.success and step.retries < step.max_retries,
                retry_context=f"Previous attempt produced: {observation.content[:200] if observation.content else 'no output'}",
            )

    async def _handle_reflection_result(
        self,
        state: AgentState,
        step: PlanStep,
        reflection: Reflection,
        observation: Observation,
    ) -> None:
        from sediman.agent.guardrails import AuditLog

        if reflection.task_complete and reflection.confidence >= 0.70:
            AuditLog.get().record("reflection_result", "completed", f"conf={reflection.confidence:.2f}", step=step.id)
            step.status = "completed"
            step.result = step.result or observation.content[:2000]
            state.advance_step()
        elif reflection.should_retry and step.retries < step.max_retries:
            step.retries += 1
            step.status = "pending"
            if reflection.retry_context:
                step.add_failure(reflection.retry_context[:200])
            enhanced_desc = step.description
            if step.failure_history:
                last_err = step.failure_history[-1]
                enhanced_desc = f"{step.description}\n[Previous attempt failed: {last_err}]"
            step.description = enhanced_desc
            import random
            backoff = min(2 ** step.retries + random.uniform(0, 1), 10)
            AuditLog.get().record("reflection_result", "retry", f"attempt={step.retries}, backoff={backoff:.1f}s", step=step.id)
            await asyncio.sleep(backoff)
            self._emit(state, f"Retrying step (attempt {step.retries + 1}/{step.max_retries})", detail=step.description[:80])
        elif await self._try_lightweight_recovery(state, step, observation):
            self._emit(state, "Recovered via lightweight retry", detail=step.description[:80])
        elif self._try_fallback(step, state):
            self._emit(
                state,
                f"Falling back to {step.strategy.value}",
                detail=f"Previous strategy {step.original_strategy.value if step.original_strategy else 'unknown'} failed",
            )
        elif reflection.should_replan and state.replan_count < state.max_replans:
            state.replan_count += 1
            AuditLog.get().record("reflection_result", "replan", f"replan#{state.replan_count}", step=step.id)
            self._emit(state, "Replanning based on reflection...", detail=reflection.reasoning[:100] if reflection.reasoning else "")
            await self._replan(state, reflection)
        else:
            if reflection.confidence >= 0.5 and reflection.task_complete:
                AuditLog.get().record("reflection_result", "low_conf_accept", f"conf={reflection.confidence:.2f}", step=step.id)
                step.status = "completed"
                step.result = step.result or observation.content[:2000]
            else:
                AuditLog.get().record("reflection_result", "failed", f"conf={reflection.confidence:.2f}", step=step.id)
                step.status = "failed"
                state.errors.append(f"Step failed: {step.description[:80]}")
            state.advance_step()

    async def _try_lightweight_recovery(
        self, state: AgentState, step: PlanStep, observation: Observation
    ) -> bool:
        if step.strategy == Strategy.USE_SKILL:
            return False
        if step.retries >= step.max_retries:
            return False

        task_lower = state.task.lower()
        extraction_kw = ("extract", "get the", "price", "scrape", "read the", "pull")
        is_extraction = any(kw in task_lower for kw in extraction_kw)

        if is_extraction and not observation.success:
            try:
                import re
                from sediman.web.extract import http_extract
                url_match = re.search(r"https?://[^\s<>\"]+", step.description or state.task)
                if url_match:
                    url = url_match.group(0).rstrip(".,;:)")
                    markdown, stats = await http_extract(url)
                    if markdown and len(markdown.strip()) > 100 and not self._looks_like_error(markdown):
                        step.result = markdown[:2000]
                        step.status = "completed"
                        state.actions_taken.append({"action": "http_fallback", "url": url})
                        logger.info("recovered_via_http_fallback", url=url)
                        return True
            except Exception as e:
                logger.debug("http_fallback_failed", error=str(e))

        return False

    async def _replan(self, state: AgentState, reflection: Reflection) -> None:
        from sediman.agent.guardrails import AuditLog, plan_hash

        failed_step = state.current_step
        if failed_step:
            failed_step.status = "failed"

        new_task = reflection.next_action or state.task
        failure_ctx = ""
        if reflection.reasoning:
            failure_ctx = f" (Previous approach failed: {reflection.reasoning[:200]})"
        if failed_step and failed_step.failure_history:
            failure_ctx += f" [Attempt history: {'; '.join(failed_step.failure_history[-2:])}]"
        if failure_ctx:
            new_task = f"{new_task}{failure_ctx}"

        plan = await self._manager.plan(new_task, self._conversation)

        sig = plan_hash(plan.browser_task or new_task, plan.strategy.value)
        if sig in state.plan_signatures:
            AuditLog.get().record("replan", "duplicate_detected", sig, task=new_task[:80])
            logger.warning("replan_duplicate", signature=sig, task=new_task[:80])
            for step in state.pending_steps:
                step.status = "failed"
                state.errors.append(f"Replan produced duplicate plan: {step.description[:80]}")
            return

        state.plan_signatures.append(sig)

        new_steps_state = self._build_plan_steps(AgentState(task=new_task), plan)

        dead_steps = [s for s in state.plan_steps if s.status in ("failed",)]
        if len(dead_steps) > 10:
            state.plan_steps = [s for s in state.plan_steps if s.status not in ("failed",)]

        remaining_index = len(state.plan_steps)
        for step in new_steps_state.plan_steps:
            step.id = remaining_index
            state.plan_steps.append(step)
            remaining_index += 1

        AuditLog.get().record("replan", "new_plan", f"strategy={plan.strategy.value}", steps=len(new_steps_state.plan_steps))

    async def _assemble_result(self, state: AgentState, plan: ManagerPlan) -> AgentState:
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

        await self._stream_text_async(state.result, phase="result")

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

    def _get_active_recording_name(self) -> str | None:
        if self._recording_manager is None:
            try:
                from sediman.agent.recording_manager import RecordingManager
                self._recording_manager = RecordingManager.get_instance()
            except Exception:
                return None
        try:
            if self._recording_manager.is_recording():
                recorder = self._recording_manager.get_active_recorder()
                if recorder and recorder.session:
                    return recorder.session.name
        except Exception:
            pass
        return None

    async def _verify_skill(self, skill_name: str) -> bool:
        try:
            from sediman.skills.executor import execute_skill
            engine = self._get_engine()
            skill_data = engine.read(skill_name)
            if not skill_data:
                return False
            result = await execute_skill(skill_data, self.browser, self.llm, max_retries=0)
            from sediman.errors import looks_like_error
            if looks_like_error(result):
                logger.info("skill_verification_failed", name=skill_name, result=result[:100])
                return False
            logger.info("skill_verification_passed", name=skill_name)
            return True
        except Exception as e:
            logger.debug("skill_verification_error", name=skill_name, error=str(e))
            return False

    def _verify_skill_later(self, skill_name: str) -> None:
        """Fire-and-forget verification that does not block the background task."""
        async def _run() -> None:
            try:
                await self._verify_skill(skill_name)
            except Exception as e:
                logger.debug("lazy_verification_failed", name=skill_name, error=str(e))
        asyncio.create_task(_run())

    async def _post_task(self, state: AgentState, plan: ManagerPlan, task: str) -> None:
        if getattr(plan, "create_subagent", None):
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

        if plan.schedule:
            job_id = self._create_scheduled_job(plan)
            if job_id:
                state.scheduled_job_id = job_id
                state.schedule_cron = plan.schedule.cron
                schedule_tag = f"[Scheduled: {plan.schedule.cron} → {plan.schedule.task}]"
                if schedule_tag not in state.result and f"Schedule configured: {plan.schedule.cron}" not in state.result:
                    state.result += f"\n\n{schedule_tag}"

        recorded = self._recorder.record(
            task=task,
            plan=plan,
            browser_result=state.result,
            browser_actions=state.actions_taken,
            engine=self._get_engine(),
        )
        if recorded:
            state.skill_created = recorded
            self._cached_skill_summaries = None

        asyncio.create_task(self._run_background_post_task(state, plan, task))

    async def _run_background_post_task(self, state: AgentState, plan: ManagerPlan, task: str) -> None:
        try:
            async def _save_session_and_trajectory() -> None:
                await self._save_session(task, state.result, state.actions_taken)
                await self._save_trajectory(state, task)

            async def _drain_recording() -> None:
                try:
                    from sediman.agent.recording_manager import RecordingManager
                    mgr = RecordingManager.get_instance()
                    if mgr.is_recording():
                        await mgr.drain_active_events()
                except Exception:
                    pass

            await asyncio.gather(_save_session_and_trajectory(), _drain_recording())

            all_actions = state.actions_taken

            if state.skill_created:
                # Run verification truly async so the background task doesn't block
                self._verify_skill_later(state.skill_created)

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
                        self._cached_skill_summaries = None
                        self._iters_since_skill = 0
                        self._persist_skill_counter()
                finally:
                    self._pending_review = False

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
            self._cached_memory_context = None
        except Exception as e:
            logger.warning("background_post_task_failed", error=str(e))

    async def _run_skill_review(
        self,
        task: str,
        actions: list[dict[str, Any]],
        result: str,
    ) -> str | None:
        try:
            engine = self._get_engine()
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

    def _try_fallback(self, step: PlanStep, state: AgentState | None = None) -> bool:
        if step.fallback_attempted:
            return False

        fallback_map = {
            Strategy.USE_SKILL: Strategy.DIRECT,
            Strategy.DELEGATE: Strategy.DIRECT,
            Strategy.DECOMPOSE: Strategy.DELEGATE,
            Strategy.DIRECT: None,
        }

        new_strategy = fallback_map.get(step.strategy)
        if new_strategy is None:
            if state and state.errors:
                from sediman.agent.guardrails import AuditLog
                AuditLog.get().record("fallback", "direct_exhausted", "no_fallback_from_direct", step=step.id)
            return False

        step.original_strategy = step.original_strategy or step.strategy
        step.strategy = new_strategy
        step.fallback_attempted = True
        step.status = "pending"
        step.retries = 0
        if step.failure_history:
            step.description = f"{step.description}\n[Fallback from {step.original_strategy.value}: {'; '.join(step.failure_history[-1:])}]"
        return True

    def _emit(self, state: AgentState, message: str, detail: str = "", url: str | None = None, tool_name: str | None = None) -> None:
        if self.on_step:
            self.on_step(StepEvent(
                step=state.iteration,
                action=message,
                observation="",
                phase=state.phase.value,
                detail=detail,
                url=url,
                tool_name=tool_name,
            ))

    def _stream_text(self, token: str, phase: str = "responding") -> None:
        if not self.on_streaming_text:
            return
        if not token:
            return
        try:
            if len(token) <= 4:
                self.on_streaming_text(token, phase)
            else:
                for i in range(0, len(token), 3):
                    self.on_streaming_text(token[i:i + 3], phase)
        except Exception:
            pass

    async def _stream_text_async(self, text: str, phase: str = "responding") -> None:
        """Stream text token-by-token for smooth TUI rendering."""
        import asyncio

        if not self.on_streaming_text or not text:
            return
        chunk_size = 3
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            try:
                self.on_streaming_text(chunk, phase)
            except Exception:
                pass
            if i > 0 and i % 60 == 0:
                await asyncio.sleep(0)

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

    @staticmethod
    def _extract_skill_arguments(skill: dict[str, Any], task: str) -> dict[str, str]:
        args: dict[str, str] = {}
        skill_name = skill.get("name", "")
        task_lower = task.lower()
        if skill_name.lower() in task_lower:
            prefix = task_lower.split(skill_name.lower())[-1].strip()
            args["ARGUMENTS"] = prefix
            args["0"] = prefix
        else:
            args["ARGUMENTS"] = task
            args["0"] = task
        return args

    async def _install_suggested_skill(self, skill_name: str, source: str) -> str | None:
        try:
            from sediman.skills.hub import LocalSkillInstaller, GitHubInstaller
            engine = self._get_engine()
            installer = LocalSkillInstaller()
            ok, msg = installer.install(skill_name, source, engine, force=False)
            if not ok:
                gh = GitHubInstaller()
                ref = f"{source}@{skill_name}"
                ok, msg = gh.install(ref, engine, force=False)
            if ok:
                self._cached_skill_summaries = None
                logger.info("suggested_skill_installed", name=skill_name, source=source)
                return msg
            logger.warning("suggested_skill_install_failed", name=skill_name, msg=msg)
            return None
        except Exception as e:
            logger.warning("suggested_skill_install_error", name=skill_name, error=str(e))
            return None

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

    def _get_trajectory_db(self) -> Any:
        try:
            from sediman.memory.trajectories import TrajectoryDB
            return TrajectoryDB()
        except Exception:
            return None

    async def _save_trajectory(self, state: AgentState, task: str) -> None:
        db = self._get_trajectory_db()
        if db is None:
            return
        try:
            from sediman.memory.trajectories import Trajectory, TrajectoryStep
            import time as _time

            steps = []
            for a in state.actions_taken:
                steps.append(TrajectoryStep(
                    action=json.dumps(a, default=str)[:500],
                ))

            traj = Trajectory(
                task=task,
                steps=steps,
                result=state.result[:4000] if state.result else None,
                success=not self._looks_like_error(state.result) if state.result else False,
                skill_name=state.skill_created,
                metadata={"iterations": state.iteration, "errors": len(state.errors)},
            )
            await db.save(traj)
            logger.debug("trajectory_saved", id=traj.id, steps=len(steps))
        except Exception as e:
            logger.debug("trajectory_save_inner_failed", error=str(e))
