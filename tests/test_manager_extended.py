from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.manager import ManagerAgent, ManagerPlan
from sediman.agent.state import PlanStep, Strategy
from sediman.llm.provider import LLMResponse


def _make_manager() -> ManagerAgent:
    llm = MagicMock()
    llm.chat = AsyncMock()
    return ManagerAgent(llm=llm)


# ---------------------------------------------------------------------------
# _parse_plan_data
# ---------------------------------------------------------------------------


class TestParsePlanData:
    def _parse(self, data: dict) -> ManagerPlan | None:
        return _make_manager()._parse_plan_data(data)

    def test_conversational_strategy(self):
        plan = self._parse({"browser_task": "", "strategy": "conversational", "response": "Hi!"})
        assert plan is not None
        assert plan.strategy == Strategy.CONVERSATIONAL
        assert plan.browser_task == ""
        assert plan.response == "Hi!"

    def test_conversational_default_response(self):
        plan = self._parse({"browser_task": "", "strategy": "conversational"})
        assert plan is not None
        assert "Sediman" in plan.response

    def test_direct_strategy(self):
        plan = self._parse({"browser_task": "go to google.com", "strategy": "direct"})
        assert plan is not None
        assert plan.strategy == Strategy.DIRECT
        assert plan.browser_task == "go to google.com"

    def test_use_skill_strategy(self):
        plan = self._parse({
            "browser_task": "scrape prices",
            "strategy": "use_skill",
            "skill_to_use": "price_scraper",
        })
        assert plan is not None
        assert plan.strategy == Strategy.USE_SKILL
        assert "price_scraper" in plan.browser_task

    def test_delegate_strategy(self):
        plan = self._parse({"browser_task": "sub job", "strategy": "delegate"})
        assert plan is not None
        assert plan.strategy == Strategy.DELEGATE

    def test_decompose_strategy(self):
        plan = self._parse({"browser_task": "complex thing", "strategy": "decompose"})
        assert plan is not None
        assert plan.strategy == Strategy.DECOMPOSE

    def test_schedule_with_valid_cron(self):
        plan = self._parse({
            "browser_task": "check prices",
            "schedule": {"cron": "0 9 * * *", "task": "check prices daily"},
        })
        assert plan is not None
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 9 * * *"
        assert plan.schedule.task == "check prices daily"

    def test_schedule_invalid_cron_ignored(self):
        plan = self._parse({
            "browser_task": "check prices",
            "schedule": {"cron": "not-a-cron", "task": "check"},
        })
        assert plan is not None
        assert plan.schedule is None

    def test_subtasks(self):
        plan = self._parse({
            "browser_task": "big task",
            "strategy": "decompose",
            "subtasks": ["step one", "step two"],
        })
        assert plan is not None
        assert plan.subtasks == ["step one", "step two"]

    def test_subtasks_non_list_ignored(self):
        plan = self._parse({
            "browser_task": "x",
            "subtasks": "not a list",
        })
        assert plan is not None
        assert plan.subtasks is None

    def test_milestones(self):
        plan = self._parse({
            "browser_task": "x",
            "milestones": ["m1", "m2", "m3"],
        })
        assert plan is not None
        assert plan.milestones == ["m1", "m2", "m3"]

    def test_milestones_non_list_ignored(self):
        plan = self._parse({"browser_task": "x", "milestones": "bad"})
        assert plan is not None
        assert plan.milestones is None

    def test_empty_browser_task_falls_back_to_task_field(self):
        plan = self._parse({"task": "fallback task", "strategy": "direct"})
        assert plan is not None
        assert plan.browser_task == "fallback task"

    def test_empty_browser_task_with_schedule_only(self):
        plan = self._parse({
            "schedule": {"cron": "*/5 * * * *", "task": "monitor"},
        })
        assert plan is not None
        assert plan.browser_task == ""
        assert plan.schedule is not None

    def test_invalid_strategy_falls_back_to_direct(self):
        plan = self._parse({"browser_task": "do it", "strategy": "unknown_strategy"})
        assert plan is not None
        assert plan.strategy == Strategy.DIRECT

    def test_memory_and_skill_fields(self):
        plan = self._parse({
            "browser_task": "search",
            "memory": "user prefers dark mode",
            "skill_name": "search_skill",
            "skill_description": "A search skill",
            "use_subagent": "researcher",
        })
        assert plan is not None
        assert plan.memory == "user prefers dark mode"
        assert plan.skill_name == "search_skill"
        assert plan.skill_description == "A search skill"
        assert plan.use_subagent == "researcher"


# ---------------------------------------------------------------------------
# decompose
# ---------------------------------------------------------------------------


class TestDecompose:
    @pytest.mark.asyncio
    async def test_successful_decomposition(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text='{"subtasks": ["search for laptops", "compare prices", "read reviews"]}',
        )
        steps = await manager.decompose("find the best laptop")
        assert len(steps) == 3
        assert all(s.strategy == Strategy.DELEGATE for s in steps)
        assert steps[0].description == "search for laptops"
        assert steps[1].id == 1
        assert steps[2].id == 2

    @pytest.mark.asyncio
    async def test_empty_llm_response_returns_direct(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(text="")
        steps = await manager.decompose("do something")
        assert len(steps) == 1
        assert steps[0].strategy == Strategy.DIRECT
        assert steps[0].description == "do something"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_direct(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(text="not json at all")
        steps = await manager.decompose("do something")
        assert len(steps) == 1
        assert steps[0].strategy == Strategy.DIRECT

    @pytest.mark.asyncio
    async def test_llm_exception_returns_direct(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.side_effect = RuntimeError("LLM down")
        steps = await manager.decompose("do something")
        assert len(steps) == 1
        assert steps[0].strategy == Strategy.DIRECT

    @pytest.mark.asyncio
    async def test_beam_scoring_picks_best(self, tmp_sediman_dir):
        manager = _make_manager()
        call_count = 0

        async def _chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return LLMResponse(text='{"subtasks": ["a"]}')
            return LLMResponse(text='{"subtasks": ["step one", "step two", "step three"]}')

        manager.llm.chat = AsyncMock(side_effect=_chat)
        steps = await manager.decompose("complex task", max_subtasks=5, beam_width=2)
        assert len(steps) >= 1
        for s in steps:
            assert s.strategy == Strategy.DELEGATE

    @pytest.mark.asyncio
    async def test_respects_max_subtasks(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text='{"subtasks": ["a", "b", "c", "d", "e", "f", "g"]}',
        )
        steps = await manager.decompose("task", max_subtasks=3)
        assert len(steps) == 3


# ---------------------------------------------------------------------------
# reflect
# ---------------------------------------------------------------------------


class TestReflect:
    @pytest.mark.asyncio
    async def test_successful_reflection(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": True,
                "confidence": 0.9,
                "reasoning": "All elements found",
                "issues": [],
                "suggested_fix": None,
            }),
        )
        result = await manager.reflect("find prices", "done", ["page loaded", "prices found"])
        assert result["task_complete"] is True
        assert result["confidence"] == 0.9
        assert result["reasoning"] == "All elements found"

    @pytest.mark.asyncio
    async def test_json_parse_failure_returns_defaults(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(text="not json")
        result = await manager.reflect("task", "result", ["obs"])
        assert result["task_complete"] is False
        assert result["confidence"] == 0.2
        assert "reflection_llm_failure" in result["issues"]

    @pytest.mark.asyncio
    async def test_non_boolean_task_complete_coerced(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": "true",
                "confidence": 0.5,
                "reasoning": "",
                "issues": [],
            }),
        )
        result = await manager.reflect("task", "result", [])
        assert result["task_complete"] is True

    @pytest.mark.asyncio
    async def test_non_boolean_task_complete_false_coerced(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": "nope",
                "confidence": 0.5,
                "reasoning": "",
                "issues": [],
            }),
        )
        result = await manager.reflect("task", "result", [])
        assert result["task_complete"] is False

    @pytest.mark.asyncio
    async def test_confidence_clamped_high(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": True,
                "confidence": 2.5,
                "reasoning": "",
                "issues": [],
            }),
        )
        result = await manager.reflect("task", "result", [])
        assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_confidence_clamped_low(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": False,
                "confidence": -0.5,
                "reasoning": "",
                "issues": [],
            }),
        )
        result = await manager.reflect("task", "result", [])
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_llm_exception_returns_defaults(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.side_effect = RuntimeError("fail")
        result = await manager.reflect("task", "result", [])
        assert result["task_complete"] is False
        assert result["suggested_fix"] is None

    @pytest.mark.asyncio
    async def test_reflect_with_suggested_fix(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text=json.dumps({
                "task_complete": False,
                "confidence": 0.4,
                "reasoning": "Page not loaded",
                "issues": ["timeout"],
                "suggested_fix": "Wait longer for the page to load",
            }),
        )
        result = await manager.reflect("task", "result", [])
        assert result["suggested_fix"] == "Wait longer for the page to load"
        assert "timeout" in result["issues"]


# ---------------------------------------------------------------------------
# generate_milestones
# ---------------------------------------------------------------------------


class TestGenerateMilestones:
    @pytest.mark.asyncio
    async def test_successful_milestone_generation(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(
            text='{"milestones": ["navigate to page", "fill form", "submit", "verify"]}',
        )
        result = await manager.generate_milestones("fill out a form")
        assert len(result) == 4
        assert result[0] == "navigate to page"

    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(text="")
        result = await manager.generate_milestones("task")
        assert result == []

    @pytest.mark.asyncio
    async def test_parse_failure(self, tmp_sediman_dir):
        manager = _make_manager()
        manager.llm.chat.return_value = LLMResponse(text="not valid json here")
        result = await manager.generate_milestones("task")
        assert result == []


# ---------------------------------------------------------------------------
# _contextualize_browser_task
# ---------------------------------------------------------------------------


class TestContextualizeBrowserTask:
    def test_no_conversation_returns_task_as_is(self):
        manager = _make_manager()
        result = manager._contextualize_browser_task("open google.com", None)
        assert result == "open google.com"

    def test_empty_conversation_returns_task_as_is(self):
        manager = _make_manager()
        result = manager._contextualize_browser_task("open google.com", [])
        assert result == "open google.com"

    def test_with_conversation_prepends_context(self):
        manager = _make_manager()
        conversation = [
            {"role": "user", "content": "I need to buy a laptop"},
            {"role": "assistant", "content": "Sure, let me search for laptops"},
        ]
        result = manager._contextualize_browser_task("compare prices", conversation)
        assert "Previous conversation:" in result
        assert "Current task: compare prices" in result
        assert "Continue from where we left off" in result
        assert "I need to buy a laptop" in result

    def test_limits_to_last_six_messages(self):
        manager = _make_manager()
        conversation = [
            {"role": "user", "content": f"msg {i}"} for i in range(10)
        ]
        result = manager._contextualize_browser_task("task", conversation)
        assert "msg 4" in result
        assert "msg 9" in result


# ---------------------------------------------------------------------------
# _score_decomposition
# ---------------------------------------------------------------------------


class TestScoreDecomposition:
    def _score(self, steps, task="complex task"):
        return _make_manager()._score_decomposition(steps, task)

    def _make_step(self, desc):
        return PlanStep(id=0, description=desc, strategy=Strategy.DELEGATE)

    def test_empty_steps_returns_zero(self):
        assert self._score([]) == 0.0

    def test_2_subtasks_gets_bonus(self):
        steps = [self._make_step("do part one of complex task"), self._make_step("do part two of complex task")]
        score = self._score(steps)
        assert score >= 1.0

    def test_3_subtasks_gets_bonus(self):
        steps = [self._make_step(f"subtask number {i} of the complex task") for i in range(3)]
        score = self._score(steps)
        assert score >= 1.0

    def test_1_subtask_low_score(self):
        steps = [self._make_step("a short one")]
        score = self._score(steps, "complex task with many steps")
        assert score < 1.0
        assert score >= 0.3

    def test_keyword_overlap_adds_bonus(self):
        steps = [self._make_step("research the complex task for pricing info")]
        score_with_overlap = self._score(steps, "complex task")
        steps_no_overlap = [self._make_step("xyz abc def")]
        score_no_overlap = self._score(steps_no_overlap, "complex task")
        assert score_with_overlap > score_no_overlap

    def test_many_subtasks_reduced_bonus(self):
        steps = [self._make_step(f"step {i} with a moderate description length here") for i in range(8)]
        score = self._score(steps)
        assert score < 1.5

    def test_avg_description_length_bonus(self):
        steps = [
            PlanStep(id=0, description="a" * 50, strategy=Strategy.DELEGATE),
            PlanStep(id=1, description="b" * 50, strategy=Strategy.DELEGATE),
        ]
        score = self._score(steps)
        assert score >= 1.5  # 1.0 for 2 subtasks + 0.5 for avg len in [20,120]
