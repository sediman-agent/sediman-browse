from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop, StepEvent
from sediman.agent.state import AgentState, Observation, PlanStep, Reflection, Strategy
from sediman.agent.manager import ManagerPlan


class TestBuildPlanSteps:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    def test_direct_strategy_creates_single_step(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="go to google.com")
        plan = ManagerPlan(browser_task="go to google.com", strategy=Strategy.DIRECT)
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 1
        assert result.plan_steps[0].strategy == Strategy.DIRECT
        assert result.plan_steps[0].description == "go to google.com"
        assert result.plan_steps[0].id == 0

    def test_delegate_strategy_with_subtasks_creates_n_steps(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="multi-step task")
        plan = ManagerPlan(
            browser_task="multi-step task",
            strategy=Strategy.DELEGATE,
            subtasks=["subtask A", "subtask B", "subtask C"],
        )
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 3
        for i, step in enumerate(result.plan_steps):
            assert step.strategy == Strategy.DELEGATE
            assert step.id == i
        assert result.plan_steps[0].description == "subtask A"
        assert result.plan_steps[1].description == "subtask B"
        assert result.plan_steps[2].description == "subtask C"

    def test_delegate_strategy_with_empty_subtasks_falls_through(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        plan = ManagerPlan(
            browser_task="do task",
            strategy=Strategy.DELEGATE,
            subtasks=[],
        )
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 1
        assert result.plan_steps[0].strategy == Strategy.DIRECT

    def test_delegate_strategy_without_subtasks_field_falls_through(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        plan = ManagerPlan(
            browser_task="do task",
            strategy=Strategy.DELEGATE,
            subtasks=None,
        )
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 1
        assert result.plan_steps[0].strategy == Strategy.DIRECT

    def test_use_skill_strategy_creates_single_step_with_skill_name(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="check prices")
        plan = ManagerPlan(
            browser_task="check prices",
            strategy=Strategy.USE_SKILL,
            skill_to_use="price_checker",
        )
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 1
        assert result.plan_steps[0].strategy == Strategy.USE_SKILL
        assert "price_checker" in result.plan_steps[0].description
        assert "check prices" in result.plan_steps[0].description

    def test_delegate_subtasks_propagate_subagent_type(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        plan = ManagerPlan(
            browser_task="task",
            strategy=Strategy.DELEGATE,
            subtasks=["sub1", "sub2"],
            use_subagent="researcher",
        )
        result = loop._build_plan_steps(state, plan)
        for step in result.plan_steps:
            assert step.subagent_type == "researcher"

    def test_build_plan_steps_preserves_existing_steps(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        state.plan_steps.append(PlanStep(id=99, description="old step", strategy=Strategy.DIRECT))
        plan = ManagerPlan(browser_task="new task", strategy=Strategy.DIRECT)
        result = loop._build_plan_steps(state, plan)
        assert len(result.plan_steps) == 2
        assert result.plan_steps[0].description == "old step"
        assert result.plan_steps[1].description == "new task"


class TestTryToolLoopExecution:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_returns_none_when_browser_controller_fails(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, side_effect=Exception("no browser")):
            result = await loop._try_tool_loop_execution(state, step)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_registry_missing_browser_navigate(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = False
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop") as MockToolLoop:
            mock_register = MagicMock(side_effect=Exception("no browser tools"))
            with patch("sediman.browser.tools.register_browser_tools", mock_register):
                result = await loop._try_tool_loop_execution(state, step)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_short_result(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = True
        mock_response = MagicMock()
        mock_response.text = "short"
        mock_tool_loop_instance = MagicMock()
        mock_tool_loop_instance.run = AsyncMock(return_value=mock_response)
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop", return_value=mock_tool_loop_instance):
            result = await loop._try_tool_loop_execution(state, step)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_result(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = True
        mock_response = MagicMock()
        mock_response.text = ""
        mock_tool_loop_instance = MagicMock()
        mock_tool_loop_instance.run = AsyncMock(return_value=mock_response)
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop", return_value=mock_tool_loop_instance):
            result = await loop._try_tool_loop_execution(state, step)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = True
        long_text = "A" * 100
        mock_response = MagicMock()
        mock_response.text = long_text
        mock_tool_loop_instance = MagicMock()
        mock_tool_loop_instance.run = AsyncMock(return_value=mock_response)
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop", return_value=mock_tool_loop_instance):
            result = await loop._try_tool_loop_execution(state, step)
        assert result == long_text
        assert len(state.actions_taken) == 1
        assert state.actions_taken[0]["action"] == "tool_loop"

    @pytest.mark.asyncio
    async def test_returns_none_on_tool_loop_exception(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = True
        mock_tool_loop_instance = MagicMock()
        mock_tool_loop_instance.run = AsyncMock(side_effect=RuntimeError("LLM failure"))
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop", return_value=mock_tool_loop_instance):
            result = await loop._try_tool_loop_execution(state, step)
        assert result is None

    @pytest.mark.asyncio
    async def test_registers_browser_tools_when_missing(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="do something", strategy=Strategy.DIRECT)
        mock_registry = MagicMock()
        mock_registry.has_tool.return_value = False
        long_text = "B" * 80
        mock_response = MagicMock()
        mock_response.text = long_text
        mock_tool_loop_instance = MagicMock()
        mock_tool_loop_instance.run = AsyncMock(return_value=mock_response)
        with patch.object(loop, "_ensure_browser_controller", new_callable=AsyncMock, return_value=MagicMock()), \
             patch.object(loop, "_get_tool_registry", return_value=mock_registry), \
             patch("sediman.agent.loop.ToolLoop", return_value=mock_tool_loop_instance), \
             patch("sediman.browser.tools.register_browser_tools") as mock_register:
            result = await loop._try_tool_loop_execution(state, step)
        mock_register.assert_called_once_with(mock_registry)
        assert result == long_text


class TestExecuteDirectStep:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_uses_tool_loop_result_when_available(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="go to example.com", strategy=Strategy.DIRECT)
        plan = ManagerPlan(browser_task="go to example.com")
        tool_result = "X" * 80
        with patch.object(loop, "_try_tool_loop_execution", new_callable=AsyncMock, return_value=tool_result):
            await loop._execute_direct_step(state, step, plan)
        assert step.result == tool_result

    @pytest.mark.asyncio
    async def test_falls_back_to_browser_when_tool_loop_returns_none(self, tmp_sediman_dir):
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="go to example.com", strategy=Strategy.DIRECT)
        plan = ManagerPlan(browser_task="go to example.com")
        browser_result = BrowserResult(text="Navigated successfully to the page and found all the data requested.", actions=[{"action": "navigate", "url": "https://example.com"}])
        mock_ba = MagicMock()
        mock_ba.run = AsyncMock(return_value=browser_result)
        with patch.object(loop, "_try_tool_loop_execution", new_callable=AsyncMock, return_value=None), \
             patch.object(loop, "_get_browser_agent", return_value=mock_ba), \
             patch.object(loop, "_get_active_recording_name", return_value=None):
            await loop._execute_direct_step(state, step, plan)
        assert step.result == browser_result.text
        assert len(state.actions_taken) == 1

    @pytest.mark.asyncio
    async def test_does_not_call_browser_when_tool_loop_succeeds(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="go to example.com", strategy=Strategy.DIRECT)
        plan = ManagerPlan(browser_task="go to example.com")
        tool_result = "Y" * 100
        with patch.object(loop, "_try_tool_loop_execution", new_callable=AsyncMock, return_value=tool_result), \
             patch.object(loop, "_get_browser_agent") as mock_get_ba:
            await loop._execute_direct_step(state, step, plan)
        mock_get_ba.assert_not_called()

    @pytest.mark.asyncio
    async def test_browser_result_extends_actions_taken(self, tmp_sediman_dir):
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="task", strategy=Strategy.DIRECT)
        plan = ManagerPlan(browser_task="task")
        actions = [{"action": "click"}, {"action": "type"}, {"action": "done"}]
        browser_result = BrowserResult(text="Done with all three actions completed successfully on the page.", actions=actions)
        mock_ba = MagicMock()
        mock_ba.run = AsyncMock(return_value=browser_result)
        with patch.object(loop, "_try_tool_loop_execution", new_callable=AsyncMock, return_value=None), \
             patch.object(loop, "_get_browser_agent", return_value=mock_ba), \
             patch.object(loop, "_get_active_recording_name", return_value=None):
            await loop._execute_direct_step(state, step, plan)
        assert len(state.actions_taken) == 3


class TestExecuteDelegateStep:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_uses_subagent_factory_when_subagent_type_set(self, tmp_sediman_dir):
        from sediman.agent.subagents.result import SubagentResult

        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="research topic", strategy=Strategy.DELEGATE, subagent_type="researcher")
        subagent_result = SubagentResult(success=True, summary="Research completed", actions_taken=[{"action": "read"}])
        mock_factory = MagicMock()
        mock_factory.spawn = AsyncMock(return_value=subagent_result)
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_delegate_step(state, step)
        assert step.result == "Research completed"
        assert len(state.actions_taken) == 1

    @pytest.mark.asyncio
    async def test_subagent_factory_receives_parent_context(self, tmp_sediman_dir):
        from sediman.agent.subagents.result import SubagentResult

        loop = self._make_loop()
        state = AgentState(task="main task")
        state.errors.append("prev error")
        state.observations.append(Observation(source="step_0", content="obs content"))
        step = PlanStep(id=0, description="sub task", strategy=Strategy.DELEGATE, subagent_type="browser")
        subagent_result = SubagentResult(success=True, summary="done")
        mock_factory = MagicMock()
        mock_factory.spawn = AsyncMock(return_value=subagent_result)
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_delegate_step(state, step)
        call_kwargs = mock_factory.spawn.call_args
        ctx = call_kwargs.kwargs.get("parent_context") or call_kwargs[1].get("parent_context") if len(call_kwargs) > 1 else call_kwargs.kwargs.get("parent_context")
        assert ctx is not None
        assert ctx["task"] == "main task"

    @pytest.mark.asyncio
    async def test_uses_delegate_parallel_when_no_subagent_type(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="simple task", strategy=Strategy.DELEGATE)
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=["parallel result"]) as mock_dp:
            await loop._execute_delegate_step(state, step)
        assert step.result == "parallel result"
        assert state.delegate_results == ["parallel result"]

    @pytest.mark.asyncio
    async def test_delegate_parallel_single_task(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE)
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=["result A"]) as mock_dp:
            await loop._execute_delegate_step(state, step)
        mock_dp.assert_called_once_with(
            tasks=["task A"],
            browser_session=loop.browser,
            llm_provider=loop.llm,
            max_concurrent=1,
        )

    @pytest.mark.asyncio
    async def test_exception_sets_error_result(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="failing task", strategy=Strategy.DELEGATE)
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            await loop._execute_delegate_step(state, step)
        assert "Delegation failed" in step.result
        assert "boom" in step.result

    @pytest.mark.asyncio
    async def test_subagent_with_artifacts(self, tmp_sediman_dir):
        from sediman.agent.subagents.result import SubagentResult, Artifact

        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="task", strategy=Strategy.DELEGATE, subagent_type="coder")
        subagent_result = SubagentResult(
            success=True, summary="done",
            artifacts=[Artifact(kind="file", name="output.txt", content="hello")],
        )
        mock_factory = MagicMock()
        mock_factory.spawn = AsyncMock(return_value=subagent_result)
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_delegate_step(state, step)
        assert step.result == "done"

    @pytest.mark.asyncio
    async def test_empty_delegate_parallel_result(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="task", strategy=Strategy.DELEGATE)
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=[]):
            await loop._execute_delegate_step(state, step)
        assert step.result == "No result from delegate"


class TestExecuteParallelDelegates:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_all_subagent_types_uses_factory_spawn_parallel(self, tmp_sediman_dir):
        from sediman.agent.subagents.result import SubagentResult

        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE, subagent_type="browser"),
            PlanStep(id=1, description="task B", strategy=Strategy.DELEGATE, subagent_type="browser"),
        ]
        results = [
            SubagentResult(success=True, summary="result A"),
            SubagentResult(success=True, summary="result B"),
        ]
        mock_factory = MagicMock()
        mock_factory.spawn_parallel = AsyncMock(return_value=results)
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_parallel_delegates(state, steps)
        assert steps[0].result == "result A"
        assert steps[1].result == "result B"
        assert steps[0].status == "completed"
        assert steps[1].status == "completed"

    @pytest.mark.asyncio
    async def test_mixed_types_falls_back_to_delegate_parallel(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE, subagent_type="browser"),
            PlanStep(id=1, description="task B", strategy=Strategy.DELEGATE),
        ]
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=["result A", "result B"]) as mock_dp:
            await loop._execute_parallel_delegates(state, steps)
        mock_dp.assert_called_once()
        assert steps[0].result == "result A"
        assert steps[1].result == "result B"
        assert steps[0].status == "completed"

    @pytest.mark.asyncio
    async def test_no_subagent_types_uses_delegate_parallel(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE),
            PlanStep(id=1, description="task B", strategy=Strategy.DELEGATE),
            PlanStep(id=2, description="task C", strategy=Strategy.DELEGATE),
        ]
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=["r1", "r2", "r3"]):
            await loop._execute_parallel_delegates(state, steps)
        assert state.delegate_results == ["r1", "r2", "r3"]

    @pytest.mark.asyncio
    async def test_factory_spawn_parallel_failure_marks_all_failed(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE, subagent_type="browser"),
            PlanStep(id=1, description="task B", strategy=Strategy.DELEGATE, subagent_type="browser"),
        ]
        mock_factory = MagicMock()
        mock_factory.spawn_parallel = AsyncMock(side_effect=RuntimeError("spawn failed"))
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_parallel_delegates(state, steps)
        for step in steps:
            assert step.status == "failed"
            assert "Subagent delegation failed" in step.result
        assert len(state.errors) == 2

    @pytest.mark.asyncio
    async def test_delegate_parallel_failure_marks_all_failed(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE),
        ]
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, side_effect=RuntimeError("delegate failed")):
            await loop._execute_parallel_delegates(state, steps)
        assert steps[0].status == "failed"
        assert "Delegation failed" in steps[0].result
        assert len(state.errors) == 1

    @pytest.mark.asyncio
    async def test_sets_phase_to_delegating(self, tmp_sediman_dir):
        from sediman.agent.state import AgentPhase

        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE)]
        with patch("sediman.agent.loop.delegate_parallel", new_callable=AsyncMock, return_value=["r1"]):
            await loop._execute_parallel_delegates(state, steps)
        assert state.phase == AgentPhase.DELEGATING

    @pytest.mark.asyncio
    async def test_factory_spawn_parallel_with_failed_result(self, tmp_sediman_dir):
        from sediman.agent.subagents.result import SubagentResult

        loop = self._make_loop()
        state = AgentState(task="task")
        steps = [
            PlanStep(id=0, description="task A", strategy=Strategy.DELEGATE, subagent_type="browser"),
            PlanStep(id=1, description="task B", strategy=Strategy.DELEGATE, subagent_type="browser"),
        ]
        results = [
            SubagentResult(success=True, summary="ok"),
            SubagentResult(success=False, summary="failed subagent"),
        ]
        mock_factory = MagicMock()
        mock_factory.spawn_parallel = AsyncMock(return_value=results)
        with patch.object(loop, "_get_subagent_factory", return_value=mock_factory):
            await loop._execute_parallel_delegates(state, steps)
        assert steps[0].status == "completed"
        assert steps[1].status == "failed"


class TestExecuteSkillStep:
    def _make_loop(self):
        llm = MagicMock()
        browser = MagicMock()
        return AgentLoop(llm_provider=llm, browser_session=browser, max_steps=5)

    @pytest.mark.asyncio
    async def test_executes_skill_when_found_in_engine(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="check prices")
        state.current_task = "check prices"
        step = PlanStep(id=0, description="Execute skill 'price_check': check prices", strategy=Strategy.USE_SKILL)
        plan = ManagerPlan(browser_task="check prices", strategy=Strategy.USE_SKILL, skill_to_use="price_check")
        mock_engine = MagicMock()
        skill_data = {"name": "price_check", "steps": [{"action": "navigate", "url": "https://example.com"}]}
        mock_engine.read.return_value = skill_data
        mock_engine.record_usage = MagicMock()
        with patch.object(loop, "_get_engine", return_value=mock_engine), \
             patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, return_value="Price is $42.00") as mock_exec:
            await loop._execute_skill_step(state, step, plan)
        mock_exec.assert_called_once()
        assert step.result == "Price is $42.00"
        mock_engine.record_usage.assert_called_once_with("price_check")

    @pytest.mark.asyncio
    async def test_falls_back_to_browser_when_skill_not_found(self, tmp_sediman_dir):
        from sediman.agent.browser_agent import BrowserResult

        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="Execute skill 'missing': task", strategy=Strategy.USE_SKILL)
        plan = ManagerPlan(browser_task="task", strategy=Strategy.USE_SKILL, skill_to_use="missing_skill")
        mock_engine = MagicMock()
        mock_engine.read.return_value = None
        browser_result = BrowserResult(text="Browser completed the task successfully with detailed output.", actions=[{"action": "done"}])
        mock_ba = MagicMock()
        mock_ba.run = AsyncMock(return_value=browser_result)
        with patch.object(loop, "_get_engine", return_value=mock_engine), \
             patch.object(loop, "_get_browser_agent", return_value=mock_ba), \
             patch.object(loop, "_get_active_recording_name", return_value=None):
            await loop._execute_skill_step(state, step, plan)
        assert step.result == browser_result.text
        assert len(state.actions_taken) == 1

    @pytest.mark.asyncio
    async def test_skill_execution_failure_sets_error_message(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        state.current_task = "task"
        step = PlanStep(id=0, description="Execute skill 'broken': task", strategy=Strategy.USE_SKILL)
        plan = ManagerPlan(browser_task="task", strategy=Strategy.USE_SKILL, skill_to_use="broken_skill")
        mock_engine = MagicMock()
        skill_data = {"name": "broken_skill", "steps": []}
        mock_engine.read.return_value = skill_data
        mock_engine.record_usage = MagicMock()
        with patch.object(loop, "_get_engine", return_value=mock_engine), \
             patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, side_effect=RuntimeError("skill crash")):
            await loop._execute_skill_step(state, step, plan)
        assert "Skill execution failed" in step.result
        assert "skill crash" in step.result

    @pytest.mark.asyncio
    async def test_uses_skill_to_use_from_plan(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        state.current_task = "task"
        step = PlanStep(id=0, description="task", strategy=Strategy.USE_SKILL)
        plan = ManagerPlan(browser_task="task", strategy=Strategy.USE_SKILL, skill_to_use="my_skill")
        mock_engine = MagicMock()
        mock_engine.read.return_value = {"name": "my_skill"}
        mock_engine.record_usage = MagicMock()
        with patch.object(loop, "_get_engine", return_value=mock_engine), \
             patch("sediman.skills.executor.execute_skill", new_callable=AsyncMock, return_value="ok"):
            await loop._execute_skill_step(state, step, plan)
        mock_engine.read.assert_called_once_with("my_skill")

    @pytest.mark.asyncio
    async def test_skill_to_use_defaults_to_empty_string(self, tmp_sediman_dir):
        loop = self._make_loop()
        state = AgentState(task="task")
        step = PlanStep(id=0, description="task", strategy=Strategy.USE_SKILL)
        plan = ManagerPlan(browser_task="task", strategy=Strategy.USE_SKILL, skill_to_use=None)
        mock_engine = MagicMock()
        mock_engine.read.return_value = None
        browser_result = MagicMock()
        browser_result.text = "fallback"
        browser_result.actions = []
        mock_ba = MagicMock()
        mock_ba.run = AsyncMock(return_value=browser_result)
        with patch.object(loop, "_get_engine", return_value=mock_engine), \
             patch.object(loop, "_get_browser_agent", return_value=mock_ba), \
             patch.object(loop, "_get_active_recording_name", return_value=None):
            await loop._execute_skill_step(state, step, plan)
        mock_engine.read.assert_called_once_with("")
