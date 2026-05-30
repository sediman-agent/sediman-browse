"""Tests for AgentLoop reflection & recovery methods.

Covers:
  - _handle_reflection_result (decision tree)
  - _try_fallback (strategy fallback chain)
  - _try_lightweight_recovery (HTTP fallback for extraction tasks)
  - _build_observation (observation construction)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.loop import AgentLoop
from sediman.agent.state import AgentState, Observation, PlanStep, Reflection, Strategy


def _make_loop(**overrides):
    defaults = dict(llm_provider=MagicMock(), browser_session=MagicMock(), max_steps=5)
    defaults.update(overrides)
    loop = AgentLoop(**defaults)
    return loop


def _state(**kw):
    return AgentState(**kw)


def _step(**kw):
    defaults = dict(id=0, description="test step", strategy=Strategy.DIRECT)
    defaults.update(kw)
    return PlanStep(**defaults)


def _reflection(**kw):
    defaults = dict(
        task_complete=False, confidence=0.3, reasoning="test",
        should_retry=False, should_replan=False,
    )
    defaults.update(kw)
    return Reflection(**defaults)


# ── _handle_reflection_result ─────────────────────────────────────

class TestHandleReflectionResultTaskComplete:
    """task_complete + confidence >= 0.70 → mark completed, advance."""

    @pytest.mark.asyncio
    async def test_high_confidence_marks_completed(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=True, confidence=0.80)
        obs = Observation(source="s0", content="ok", success=True)

        await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "completed"
        assert state.current_step_index == 1

    @pytest.mark.asyncio
    async def test_exactly_070_confidence_completes(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=True, confidence=0.70)
        obs = Observation(source="s0", content="ok", success=True)

        await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "completed"

    @pytest.mark.asyncio
    async def test_high_conf_but_not_task_complete_does_not_complete(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=False, confidence=0.90, should_retry=False, should_replan=False)
        obs = Observation(source="s0", content="ok", success=True)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status != "completed"


class TestHandleReflectionResultRetry:
    """should_retry + retries left → increment retries, backoff, sleep."""

    @pytest.mark.asyncio
    async def test_retry_increments_retries(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step(max_retries=3)])
        step = state.plan_steps[0]
        refl = _reflection(should_retry=True, retry_context="timeout", confidence=0.2)
        obs = Observation(source="s0", content="fail", success=False)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.retries == 1
        assert step.status == "pending"
        assert "timeout" in step.failure_history

    @pytest.mark.asyncio
    async def test_retry_adds_failure_context_to_description(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step(max_retries=3)])
        step = state.plan_steps[0]
        refl = _reflection(should_retry=True, retry_context="Element not found", confidence=0.1)
        obs = Observation(source="s0", content="fail", success=False)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert "Previous attempt failed" in step.description
        assert "Element not found" in step.description

    @pytest.mark.asyncio
    async def test_no_retry_when_retries_exhausted(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step(max_retries=1, retries=1)])
        step = state.plan_steps[0]
        refl = _reflection(should_retry=True, confidence=0.1)
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.retries == 1


class TestHandleReflectionResultLightweightRecovery:
    """Branch: _try_lightweight_recovery succeeds → emit recovery."""

    @pytest.mark.asyncio
    async def test_lightweight_recovery_branch_taken(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(should_retry=False, should_replan=False, confidence=0.3)
        obs = Observation(source="s0", content="fail", success=False)

        async def _fake_recovery(s, st, o):
            st.status = "completed"
            st.result = "recovered content"
            return True

        with patch.object(loop, "_try_lightweight_recovery", side_effect=_fake_recovery):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "completed"


class TestHandleReflectionResultFallback:
    """_try_fallback branch: strategy is changed."""

    @pytest.mark.asyncio
    async def test_fallback_branch_taken(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step(strategy=Strategy.USE_SKILL)])
        step = state.plan_steps[0]
        refl = _reflection(should_retry=False, should_replan=False, confidence=0.3)
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.strategy == Strategy.DIRECT
        assert step.fallback_attempted is True


class TestHandleReflectionResultReplan:
    """should_replan + replans left → replan."""

    @pytest.mark.asyncio
    async def test_replan_increments_counter(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()], max_replans=3)
        step = state.plan_steps[0]
        refl = _reflection(should_replan=True, confidence=0.2, next_action="try different approach")
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False), \
             patch.object(loop, "_replan", new_callable=AsyncMock):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert state.replan_count == 1

    @pytest.mark.asyncio
    async def test_no_replan_when_max_exceeded(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()], max_replans=1, replan_count=1)
        step = state.plan_steps[0]
        refl = _reflection(should_replan=True, confidence=0.2)
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert state.replan_count == 1
        assert step.status == "failed"


class TestHandleReflectionResultLowConfAcceptAndFail:
    """Terminal branches: low-conf accept vs mark failed."""

    @pytest.mark.asyncio
    async def test_low_conf_accept_when_05_and_task_complete(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=True, confidence=0.50)
        obs = Observation(source="s0", content="partial", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "completed"
        assert state.current_step_index == 1

    @pytest.mark.asyncio
    async def test_below_05_conf_marks_failed(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=False, confidence=0.30)
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "failed"
        assert len(state.errors) == 1
        assert state.current_step_index == 1

    @pytest.mark.asyncio
    async def test_05_conf_but_not_task_complete_marks_failed(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        refl = _reflection(task_complete=False, confidence=0.55)
        obs = Observation(source="s0", content="fail", success=False)

        with patch.object(loop, "_try_lightweight_recovery", new_callable=AsyncMock, return_value=False), \
             patch.object(loop, "_try_fallback", return_value=False):
            await loop._handle_reflection_result(state, step, refl, obs)

        assert step.status == "failed"

    @pytest.mark.asyncio
    async def test_uses_observation_content_as_fallback_result(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="t", plan_steps=[_step()])
        step = state.plan_steps[0]
        step.result = None
        refl = _reflection(task_complete=True, confidence=0.80)
        obs = Observation(source="s0", content="the real output", success=True)

        await loop._handle_reflection_result(state, step, refl, obs)

        assert step.result == "the real output"


# ── _try_fallback ─────────────────────────────────────────────────

class TestTryFallback:
    def test_use_skill_falls_back_to_direct(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.USE_SKILL)

        result = loop._try_fallback(step)

        assert result is True
        assert step.strategy == Strategy.DIRECT
        assert step.original_strategy == Strategy.USE_SKILL
        assert step.fallback_attempted is True
        assert step.retries == 0
        assert step.status == "pending"

    def test_delegate_falls_back_to_direct(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.DELEGATE)

        result = loop._try_fallback(step)

        assert result is True
        assert step.strategy == Strategy.DIRECT

    def test_decompose_falls_back_to_delegate(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.DECOMPOSE)

        result = loop._try_fallback(step)

        assert result is True
        assert step.strategy == Strategy.DELEGATE

    def test_direct_has_no_fallback(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.DIRECT)

        result = loop._try_fallback(step)

        assert result is False

    def test_already_attempted_returns_false(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.USE_SKILL, fallback_attempted=True)

        result = loop._try_fallback(step)

        assert result is False

    def test_preserves_original_strategy_on_first_fallback(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.USE_SKILL)

        loop._try_fallback(step)

        assert step.original_strategy == Strategy.USE_SKILL

    def test_does_not_overwrite_original_strategy_on_double_call(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.USE_SKILL)

        loop._try_fallback(step)
        first_original = step.original_strategy

        step.strategy = Strategy.DELEGATE
        loop._try_fallback(step)

        assert step.original_strategy == first_original

    def test_resets_retries_to_zero(self):
        loop = _make_loop()
        step = _step(strategy=Strategy.USE_SKILL, retries=3)

        loop._try_fallback(step)

        assert step.retries == 0


# ── _try_lightweight_recovery ─────────────────────────────────────

class TestTryLightweightRecovery:
    @pytest.mark.asyncio
    async def test_returns_false_for_skill_strategy(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price")
        step = _step(strategy=Strategy.USE_SKILL)
        obs = Observation(source="s0", content="fail", success=False)

        result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_retries_exhausted(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price")
        step = _step(strategy=Strategy.DIRECT, max_retries=2, retries=2)
        obs = Observation(source="s0", content="fail", success=False)

        result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_non_extraction_task(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="click the button")
        step = _step(strategy=Strategy.DIRECT)
        obs = Observation(source="s0", content="fail", success=False)

        result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_observation_success(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price from https://example.com")
        step = _step(strategy=Strategy.DIRECT, description="extract from https://example.com")
        obs = Observation(source="s0", content="ok", success=True)

        result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_url_found(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract the price of milk")
        step = _step(strategy=Strategy.DIRECT, description="get price of milk")
        obs = Observation(source="s0", content="fail", success=False)

        result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_extraction_with_url_succeeds_via_http(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price from https://example.com/pricing")
        step = _step(strategy=Strategy.DIRECT, description="extract https://example.com/pricing")
        obs = Observation(source="s0", content="fail", success=False)

        long_markdown = "x" * 200
        mock_stats = MagicMock()
        with patch("sediman.web.extract.http_extract", new_callable=AsyncMock, return_value=(long_markdown, mock_stats)), \
             patch.object(loop, "_looks_like_error", return_value=False):
            result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is True
        assert step.status == "completed"
        assert step.result == long_markdown[:2000]
        assert any(a.get("action") == "http_fallback" for a in state.actions_taken)

    @pytest.mark.asyncio
    async def test_http_fallback_skips_short_content(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price from https://example.com")
        step = _step(strategy=Strategy.DIRECT, description="extract https://example.com")
        obs = Observation(source="s0", content="fail", success=False)

        short_content = "too short"
        mock_stats = MagicMock()
        with patch("sediman.web.extract.http_extract", new_callable=AsyncMock, return_value=(short_content, mock_stats)):
            result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_http_fallback_skips_error_content(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price from https://example.com")
        step = _step(strategy=Strategy.DIRECT, description="extract https://example.com")
        obs = Observation(source="s0", content="fail", success=False)

        error_content = "Error: 403 Forbidden. " * 20
        mock_stats = MagicMock()
        with patch("sediman.web.extract.http_extract", new_callable=AsyncMock, return_value=(error_content, mock_stats)), \
             patch.object(loop, "_looks_like_error", return_value=True):
            result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False

    @pytest.mark.asyncio
    async def test_http_fallback_exception_returns_false(self, tmp_sediman_dir):
        loop = _make_loop()
        state = _state(task="extract price from https://example.com")
        step = _step(strategy=Strategy.DIRECT, description="extract https://example.com")
        obs = Observation(source="s0", content="fail", success=False)

        with patch("sediman.web.extract.http_extract", new_callable=AsyncMock, side_effect=Exception("network error")):
            result = await loop._try_lightweight_recovery(state, step, obs)

        assert result is False


# ── _build_observation ────────────────────────────────────────────

class TestBuildObservation:
    def test_no_result_returns_failed_observation(self):
        loop = _make_loop()
        state = _state(task="t")
        step = _step(result=None)

        obs = loop._build_observation(step, state)

        assert obs.success is False
        assert obs.content == "No result produced"
        assert obs.source == "step_0"

    def test_empty_result_returns_failed_observation(self):
        loop = _make_loop()
        state = _state(task="t")
        step = _step(result="")

        obs = loop._build_observation(step, state)

        assert obs.success is False

    def test_error_result_is_not_success(self):
        loop = _make_loop()
        state = _state(task="t")
        step = _step(result="Error: something went wrong during execution")

        with patch.object(loop, "_looks_like_error", return_value=True):
            obs = loop._build_observation(step, state)

        assert obs.success is False

    def test_very_short_result_is_not_success(self):
        loop = _make_loop()
        state = _state(task="t")
        step = _step(result="ok")

        with patch.object(loop, "_looks_like_error", return_value=False):
            obs = loop._build_observation(step, state)

        assert obs.success is False

    def test_long_clean_result_is_success(self):
        loop = _make_loop()
        state = _state(task="t", actions_taken=[{"action": "done"}])
        step = _step(result="Successfully navigated to the page and extracted all the data from the table.")

        with patch.object(loop, "_looks_like_error", return_value=False):
            obs = loop._build_observation(step, state)

        assert obs.success is True

    def test_medium_result_without_done_action_is_failure(self):
        loop = _make_loop()
        state = _state(task="t", actions_taken=[])
        step = _step(result="A" * 40)

        with patch.object(loop, "_looks_like_error", return_value=False):
            obs = loop._build_observation(step, state)

        assert obs.success is False

    def test_metadata_includes_strategy_and_retries(self):
        loop = _make_loop()
        state = _state(task="t", actions_taken=[{"action": "done"}])
        step = _step(result="Good result with enough text to pass the checks.", strategy=Strategy.DELEGATE, retries=2)

        with patch.object(loop, "_looks_like_error", return_value=False):
            obs = loop._build_observation(step, state)

        assert obs.metadata["strategy"] == "delegate"
        assert obs.metadata["retries"] == 2

    def test_source_uses_step_id(self):
        loop = _make_loop()
        state = _state(task="t", actions_taken=[{"action": "done"}])
        step = _step(id=7, result="Good result with enough text to pass the checks.")

        with patch.object(loop, "_looks_like_error", return_value=False):
            obs = loop._build_observation(step, state)

        assert obs.source == "step_7"
