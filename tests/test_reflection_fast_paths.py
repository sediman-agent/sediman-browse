"""Tests for Rule-Based Reflection Skip — error fast-path and data-match fast-path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop
from sediman.agent.state import AgentState, Observation, PlanStep, Reflection, Strategy


class TestReflectOnStepErrorFastPath:
    def _make_loop(self):
        loop = AgentLoop(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)
        loop._skip_reflection_on_success = False
        return loop

    @pytest.mark.asyncio
    async def test_error_fast_path_returns_low_confidence(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=True):
            state = AgentState(task="extract prices")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT, max_retries=2)
            obs = Observation(source="s", content="Error: timeout exceeded", success=False)

            result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.task_complete is False
        assert result.confidence <= 0.2
        assert result.should_retry is True
        assert "Error fast-path" in result.reasoning

    @pytest.mark.asyncio
    async def test_error_fast_path_should_replan_when_retries_exhausted(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=True):
            state = AgentState(task="extract prices")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT, max_retries=2, retries=2)
            obs = Observation(source="s", content="Error: crashed", success=False)

            result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.should_retry is False
        assert result.should_replan is True

    @pytest.mark.asyncio
    async def test_no_error_fast_path_when_success(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="do stuff")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            obs = Observation(source="s", content="All done successfully. The task was completed and all results are present right here.", success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.9, "reasoning": "ok",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.task_complete is True
        assert result.confidence == 0.9


class TestReflectOnStepDataMatchFastPath:
    def _make_loop(self):
        loop = AgentLoop(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)
        loop._skip_reflection_on_success = False
        return loop

    @pytest.mark.asyncio
    async def test_data_match_fast_path_triggers(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="extract nvidia stock price")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            content = "The nvidia stock price is $131.00 as of today. " * 5
            obs = Observation(source="s", content=content, success=True)

            result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.task_complete is True
        assert result.confidence >= 0.7
        assert "Data-match" in result.reasoning

    @pytest.mark.asyncio
    async def test_data_match_does_not_trigger_with_error(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", side_effect=[False, True]):
            state = AgentState(task="extract prices")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            obs = Observation(source="s", content="some prices here " * 10, success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.5, "reasoning": "ok",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_data_match_does_not_trigger_short_content(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="extract nvidia prices")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            content = "nvidia price data " * 10
            obs = Observation(source="s", content=content, success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.5, "reasoning": "ok",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result.confidence == 0.5


class TestReflectOnStepSuccessFastPath:
    def _make_loop(self):
        loop = AgentLoop(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)
        loop._skip_reflection_on_success = True
        return loop

    @pytest.mark.asyncio
    async def test_success_fast_path_with_done_action(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="go to google", actions_taken=[{"action": "done"}])
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            obs = Observation(source="s", content="x" * 90 + " data: 42", success=True)

            result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.task_complete is True
        assert result.confidence == 0.70

    @pytest.mark.asyncio
    async def test_success_fast_path_without_done_action(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="go to google")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            obs = Observation(source="s", content="x" * 100, success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.7, "reasoning": "LLM confirmed",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result is not None
        assert result.task_complete is True
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_success_fast_path_skipped_when_errors(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="go to google", errors=["prev error"])
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT)
            obs = Observation(source="s", content="x" * 100, success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.7, "reasoning": "ok",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_success_fast_path_skipped_with_retries(self, tmp_sediman_dir):
        loop = self._make_loop()
        with patch.object(loop, "_looks_like_error", return_value=False):
            state = AgentState(task="go to google")
            step = PlanStep(id=0, description="do it", strategy=Strategy.DIRECT, retries=1)
            obs = Observation(source="s", content="x" * 100, success=True)

            with patch.object(loop._manager, "reflect", new_callable=AsyncMock, return_value={
                "task_complete": True, "confidence": 0.7, "reasoning": "ok",
            }):
                result = await loop._reflect_on_step(state, step, obs)

        assert result.confidence == 0.7
