from __future__ import annotations


from sediman.agent.state import (
    AgentPhase,
    AgentState,
    Observation,
    PlanStep,
    Reflection,
    Strategy,
)


class TestAgentPhase:
    def test_values(self):
        assert AgentPhase.PLANNING.value == "planning"
        assert AgentPhase.EXECUTING.value == "executing"
        assert AgentPhase.DONE.value == "done"
        assert AgentPhase.FAILED.value == "failed"
        assert AgentPhase.REFLECTING.value == "reflecting"
        assert AgentPhase.OBSERVING.value == "observing"
        assert AgentPhase.DELEGATING.value == "delegating"

    def test_enum_membership(self):
        assert AgentPhase("planning") == AgentPhase.PLANNING
        assert AgentPhase("done") == AgentPhase.DONE


class TestStrategy:
    def test_values(self):
        assert Strategy.DIRECT.value == "direct"
        assert Strategy.USE_SKILL.value == "use_skill"
        assert Strategy.DELEGATE.value == "delegate"
        assert Strategy.DECOMPOSE.value == "decompose"
        assert Strategy.CONVERSATIONAL.value == "conversational"

    def test_all_strategies_defined(self):
        strategies = {s.value for s in Strategy}
        assert "direct" in strategies
        assert "use_skill" in strategies
        assert "delegate" in strategies
        assert "decompose" in strategies
        assert "conversational" in strategies


class TestObservation:
    def test_defaults(self):
        obs = Observation(source="browser", content="page loaded")
        assert obs.success is True
        assert obs.url is None
        assert obs.screenshot is None
        assert obs.metadata == {}

    def test_with_all_fields(self):
        obs = Observation(
            source="browser",
            content="error occurred",
            success=False,
            url="https://example.com",
            screenshot="base64...",
            metadata={"retry": True},
        )
        assert obs.source == "browser"
        assert obs.content == "error occurred"
        assert obs.success is False
        assert obs.url == "https://example.com"
        assert obs.screenshot == "base64..."
        assert obs.metadata == {"retry": True}

    def test_default_factory_not_shared(self):
        obs1 = Observation(source="s1", content="c1")
        obs1.metadata["key"] = "val"
        obs2 = Observation(source="s2", content="c2")
        assert obs2.metadata == {}


class TestReflection:
    def test_defaults(self):
        ref = Reflection(task_complete=True, confidence=0.9, reasoning="done")
        assert ref.issues == []
        assert ref.next_action is None
        assert ref.should_retry is False
        assert ref.should_replan is False

    def test_with_all_fields(self):
        ref = Reflection(
            task_complete=False,
            confidence=0.3,
            reasoning="stuck",
            issues=["element not found", "timeout"],
            next_action="retry with different selector",
            should_retry=True,
            should_replan=True,
        )
        assert ref.task_complete is False
        assert ref.confidence == 0.3
        assert len(ref.issues) == 2
        assert ref.should_retry is True

    def test_default_factory_not_shared(self):
        ref1 = Reflection(task_complete=True, confidence=1.0, reasoning="ok")
        ref1.issues.append("minor")
        ref2 = Reflection(task_complete=True, confidence=1.0, reasoning="ok")
        assert ref2.issues == []


class TestPlanStep:
    def test_defaults(self):
        step = PlanStep(id=1, description="do something", strategy=Strategy.DIRECT)
        assert step.status == "pending"
        assert step.result is None
        assert step.observations == []
        assert step.retries == 0
        assert step.max_retries == 2
        assert step.original_strategy is None
        assert step.fallback_attempted is False

    def test_with_all_fields(self):
        step = PlanStep(
            id=1,
            description="navigate",
            strategy=Strategy.USE_SKILL,
            status="completed",
            result="success",
            observations=[Observation(source="browser", content="done")],
            retries=1,
            max_retries=3,
            original_strategy=Strategy.DIRECT,
            fallback_attempted=True,
        )
        assert step.status == "completed"
        assert step.result == "success"
        assert len(step.observations) == 1
        assert step.retries == 1
        assert step.fallback_attempted is True

    def test_default_factory_not_shared(self):
        step1 = PlanStep(id=1, description="d1", strategy=Strategy.DIRECT)
        step1.observations.append(Observation(source="browser", content="oops"))
        step2 = PlanStep(id=2, description="d2", strategy=Strategy.DIRECT)
        assert step2.observations == []


class TestAgentState:
    def test_defaults(self):
        state = AgentState(task="test task")
        assert state.task == "test task"
        assert state.phase == AgentPhase.PLANNING
        assert state.plan_steps == []
        assert state.current_step_index == 0
        assert state.observations == []
        assert state.reflections == []
        assert state.iteration == 0
        assert state.max_iterations == 5
        assert state.result == ""
        assert state.skill_created is None
        assert state.actions_taken == []
        assert state.scheduled_job_id is None
        assert state.schedule_cron is None
        assert state.delegate_results == []
        assert state.errors == []

    def test_current_step_returns_none_when_empty(self):
        state = AgentState(task="t")
        assert state.current_step is None

    def test_current_step_returns_first_step(self):
        state = AgentState(task="t")
        step = PlanStep(id=1, description="s1", strategy=Strategy.DIRECT)
        state.plan_steps.append(step)
        assert state.current_step == step

    def test_current_step_advances_with_index(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT),
        ]
        assert state.current_step.id == 1
        state.advance_step()
        assert state.current_step.id == 2

    def test_current_step_none_when_index_out_of_range(self):
        state = AgentState(task="t")
        state.plan_steps = [PlanStep(id=1, description="s1", strategy=Strategy.DIRECT)]
        state.current_step_index = 5
        assert state.current_step is None

    def test_completed_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT, status="completed"),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT, status="pending"),
            PlanStep(id=3, description="s3", strategy=Strategy.DIRECT, status="completed"),
        ]
        assert len(state.completed_steps) == 2
        assert state.completed_steps[0].id == 1
        assert state.completed_steps[1].id == 3

    def test_pending_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT, status="completed"),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT, status="pending"),
            PlanStep(id=3, description="s3", strategy=Strategy.DIRECT, status="in_progress"),
        ]
        assert len(state.pending_steps) == 1
        assert state.pending_steps[0].id == 2

    def test_failed_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT, status="failed"),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT, status="completed"),
        ]
        assert len(state.failed_steps) == 1
        assert state.failed_steps[0].id == 1

    def test_total_retries(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT, retries=2),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT, retries=3),
        ]
        assert state.total_retries == 5

    def test_advance_step_increments_index(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="s1", strategy=Strategy.DIRECT),
            PlanStep(id=2, description="s2", strategy=Strategy.DIRECT),
        ]
        state.advance_step()
        assert state.current_step_index == 1

    def test_advance_step_beyond_last(self):
        state = AgentState(task="t")
        state.plan_steps = [PlanStep(id=1, description="s1", strategy=Strategy.DIRECT)]
        state.advance_step()
        assert state.current_step_index == 1
        assert state.current_step is None

    def test_should_continue_false_when_done(self):
        state = AgentState(task="t", phase=AgentPhase.DONE)
        assert state.should_continue() is False

    def test_should_continue_false_when_failed(self):
        state = AgentState(task="t", phase=AgentPhase.FAILED)
        assert state.should_continue() is False

    def test_should_continue_false_when_max_iterations_exceeded(self):
        state = AgentState(task="t", iteration=5, max_iterations=5)
        assert state.should_continue() is False

    def test_should_continue_true_when_pending_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [PlanStep(id=1, description="s1", strategy=Strategy.DIRECT)]
        assert state.should_continue() is True

    def test_should_continue_false_when_no_plan_steps(self):
        state = AgentState(task="t")
        assert state.should_continue() is False

    def test_should_continue_false_when_no_pending_and_no_current(self):
        state = AgentState(task="t")
        state.plan_steps = [PlanStep(id=1, description="s1", strategy=Strategy.DIRECT, status="completed")]
        state.advance_step()
        assert state.should_continue() is False

    def test_to_summary_includes_task(self):
        state = AgentState(task="my task")
        summary = state.to_summary()
        assert "Task: my task" in summary

    def test_to_summary_includes_phase(self):
        state = AgentState(task="t", phase=AgentPhase.EXECUTING)
        summary = state.to_summary()
        assert "Phase: executing" in summary

    def test_to_summary_includes_iteration(self):
        state = AgentState(task="t", iteration=3, max_iterations=5)
        summary = state.to_summary()
        assert "3/5" in summary

    def test_to_summary_includes_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="first", strategy=Strategy.DIRECT, status="completed"),
            PlanStep(id=2, description="second", strategy=Strategy.DIRECT, status="pending"),
        ]
        summary = state.to_summary()
        assert "first" in summary
        assert "second" in summary
        assert "completed" in summary or "●" in summary
        assert "pending" in summary or "○" in summary

    def test_to_summary_includes_errors(self):
        state = AgentState(task="t")
        state.errors = ["error1", "error2", "error3"]
        summary = state.to_summary()
        assert "Errors:" in summary

    def test_to_summary_includes_observations_count(self):
        state = AgentState(task="t")
        state.observations = [Observation(source="browser", content="x")]
        summary = state.to_summary()
        assert "Observations: 1" in summary

    def test_to_summary_includes_result_in_steps(self):
        state = AgentState(task="t")
        state.plan_steps = [
            PlanStep(id=1, description="step1", strategy=Strategy.DIRECT, status="completed", result="success!"),
        ]
        summary = state.to_summary()
        assert "success!" in summary

    def test_default_factory_not_shared(self):
        state1 = AgentState(task="t1")
        state1.actions_taken.append({"type": "click"})
        state2 = AgentState(task="t2")
        assert state2.actions_taken == []

    def test_default_factory_not_shared_for_reflections(self):
        state1 = AgentState(task="t1")
        state1.reflections.append(Reflection(task_complete=False, confidence=0.0, reasoning="fail"))
        state2 = AgentState(task="t2")
        assert state2.reflections == []

    def test_default_factory_not_shared_for_errors(self):
        state1 = AgentState(task="t1")
        state1.errors.append("err")
        state2 = AgentState(task="t2")
        assert state2.errors == []

    def test_max_iterations_configurable(self):
        state = AgentState(task="t", max_iterations=10)
        assert state.max_iterations == 10

    def test_phase_set_via_constructor(self):
        state = AgentState(task="t", phase=AgentPhase.REFLECTING)
        assert state.phase == AgentPhase.REFLECTING
