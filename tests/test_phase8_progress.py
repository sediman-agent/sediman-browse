from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.progress import (
    LoopDetector,
    Milestone,
    MilestoneTracker,
    ProgressReport,
    ProgressTracker,
    generate_milestones_prompt,
    parse_milestones,
    _hash_state,
    _hash_text,
)


class TestLoopDetector:
    def test_no_loop_single_action(self):
        ld = LoopDetector(max_repeats=2, window=10)
        assert ld.record("click", "http://example.com", "abc") is False

    def test_loop_detected_same_action(self):
        ld = LoopDetector(max_repeats=2, window=10)
        assert ld.record("click", "http://example.com", "abc") is False
        assert ld.record("click", "http://example.com", "abc") is True

    def test_no_loop_different_actions(self):
        ld = LoopDetector(max_repeats=2, window=10)
        assert ld.record("click", "http://example.com", "abc") is False
        assert ld.record("type", "http://example.com", "abc") is False

    def test_loop_window_respects_size(self):
        ld = LoopDetector(max_repeats=3, window=5)
        ld.record("click", "url", "h")
        ld.record("type", "url", "h")
        ld.record("click", "url", "h")
        ld.record("click", "url", "h")
        assert ld.record("click", "url", "h") is True

    def test_reset_clears_history(self):
        ld = LoopDetector(max_repeats=2, window=10)
        ld.record("click", "url", "h")
        ld.reset()
        assert ld.record("click", "url", "h") is False

    def test_different_urls_no_loop(self):
        ld = LoopDetector(max_repeats=2, window=10)
        assert ld.record("click", "http://a.com", "h") is False
        assert ld.record("click", "http://b.com", "h") is False


class TestMilestoneTracker:
    def test_empty_tracker(self):
        mt = MilestoneTracker()
        assert mt.next_unachieved() is None
        assert mt.progress_fraction() == 0.0

    def test_milestones_creation(self):
        mt = MilestoneTracker(["step1", "step2", "step3"])
        assert len(mt.milestones) == 3
        assert mt.progress_fraction() == 0.0

    def test_next_unachieved(self):
        mt = MilestoneTracker(["a", "b", "c"])
        m = mt.next_unachieved()
        assert m is not None
        assert m.description == "a"

    def test_mark_achieved(self):
        mt = MilestoneTracker(["a", "b"])
        mt.mark_achieved(0)
        assert mt.milestones[0].achieved is True
        assert mt.milestones[1].achieved is False
        assert mt.progress_fraction() == 0.5

    def test_mark_failed(self):
        mt = MilestoneTracker(["a"])
        mt.mark_failed(0)
        assert mt.milestones[0].failed_count == 1

    def test_all_achieved(self):
        mt = MilestoneTracker(["a", "b"])
        mt.mark_achieved(0)
        mt.mark_achieved(1)
        assert mt.next_unachieved() is None
        assert mt.progress_fraction() == 1.0

    def test_summaries(self):
        mt = MilestoneTracker(["a", "b"])
        mt.mark_achieved(0)
        summaries = mt.summaries()
        assert summaries == ["✓ a", "○ b"]


class TestProgressTracker:
    def test_heuristics_url_progress(self):
        pt = ProgressTracker()
        pt._last_url = "http://old.com"
        report = pt.check_heuristics("click", page_url="http://new.com")
        assert report.url_progress is True
        assert report.score > 0.5

    def test_heuristics_loop_detected(self):
        pt = ProgressTracker()
        pt.check_heuristics("click", page_url="http://a.com", page_text="hello")
        report = pt.check_heuristics("click", page_url="http://a.com", page_text="hello")
        assert report.loop_detected is True
        assert report.should_replan is True
        assert report.score < 0.5

    def test_heuristics_element_present(self):
        pt = ProgressTracker()
        report = pt.check_heuristics(
            "click",
            page_url="http://a.com",
            page_text="Welcome to the checkout page",
            expected_elements=["checkout"],
        )
        assert report.element_present is True

    def test_should_check_milestone(self):
        pt = ProgressTracker(milestones=["a", "b"], check_interval=3)
        pt.check_heuristics("s1")
        pt.check_heuristics("s2")
        pt.check_heuristics("s3")
        assert pt.should_check_milestone() is True

    def test_should_not_check_no_milestones(self):
        pt = ProgressTracker(milestones=None, check_interval=3)
        pt.check_heuristics("s1")
        pt.check_heuristics("s2")
        pt.check_heuristics("s3")
        assert pt.should_check_milestone() is False

    def test_reset(self):
        pt = ProgressTracker()
        pt.check_heuristics("s1")
        pt.reset()
        assert pt._step_count == 0

    @pytest.mark.asyncio
    async def test_check_milestone_achieved(self):
        pt = ProgressTracker(milestones=["Navigate to Google"])
        milestone = pt.milestones.next_unachieved()
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(
            text='{"achieved": true, "confidence": 0.9, "reasoning": "page shows google"}'
        )
        report = await pt.check_milestone(llm, milestone, "Google Search", "https://google.com")
        assert report.milestone_achieved is not None
        assert report.score > 0.8

    @pytest.mark.asyncio
    async def test_check_milestone_not_achieved(self):
        pt = ProgressTracker(milestones=["Add to cart"])
        milestone = pt.milestones.next_unachieved()
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(
            text='{"achieved": false, "confidence": 0.3, "reasoning": "cart is empty"}'
        )
        report = await pt.check_milestone(llm, milestone, "Homepage", "https://shop.com")
        assert report.milestone_failed is not None
        assert report.score < 0.3

    @pytest.mark.asyncio
    async def test_check_milestone_llm_error(self):
        pt = ProgressTracker(milestones=["Do something"])
        milestone = pt.milestones.next_unachieved()
        llm = AsyncMock()
        llm.chat.side_effect = Exception("LLM down")
        report = await pt.check_milestone(llm, milestone, "page", "url")
        assert report.score == 0.3
        assert "error" in report.reason.lower()

    @pytest.mark.asyncio
    async def test_evaluate_promise(self):
        pt = ProgressTracker()
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(text="4 - Making good progress")
        score = await pt.evaluate_promise(llm, "Buy shoes", "clicking add to cart", "cart page")
        assert score == 0.8

    @pytest.mark.asyncio
    async def test_evaluate_promise_fallback(self):
        pt = ProgressTracker()
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(text="no score here")
        score = await pt.evaluate_promise(llm, "task", "step")
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_evaluate_promise_error(self):
        pt = ProgressTracker()
        llm = AsyncMock()
        llm.chat.side_effect = Exception("timeout")
        score = await pt.evaluate_promise(llm, "task", "step")
        assert score == 0.5


class TestMilestoneGeneration:
    def test_generate_prompt(self):
        prompt = generate_milestones_prompt("Buy running shoes on Amazon")
        assert "milestones" in prompt.lower()
        assert "Buy running shoes" in prompt

    def test_parse_milestones_valid(self):
        text = '{"milestones": ["Go to Amazon", "Search for shoes", "Add to cart", "Checkout"]}'
        result = parse_milestones(text)
        assert len(result) == 4
        assert result[0] == "Go to Amazon"

    def test_parse_milestones_empty(self):
        text = '{"milestones": []}'
        result = parse_milestones(text)
        assert result == []

    def test_parse_milestones_invalid_json(self):
        result = parse_milestones("not json at all")
        assert result == []

    def test_parse_milestones_filters_empty(self):
        text = '{"milestones": ["step1", "", "step3"]}'
        result = parse_milestones(text)
        assert len(result) == 2


class TestHashing:
    def test_hash_state_deterministic(self):
        h1 = _hash_state("click", "url", "hash")
        h2 = _hash_state("click", "url", "hash")
        assert h1 == h2

    def test_hash_state_different_inputs(self):
        h1 = _hash_state("click", "url1", "hash")
        h2 = _hash_state("type", "url1", "hash")
        assert h1 != h2

    def test_hash_text_empty(self):
        assert _hash_text("") == ""

    def test_hash_text_deterministic(self):
        h1 = _hash_text("hello world")
        h2 = _hash_text("hello world")
        assert h1 == h2


class TestManagerMilestones:
    def test_manager_plan_has_milestones_field(self):
        from sediman.agent.manager import ManagerPlan
        plan = ManagerPlan(browser_task="test", milestones=["a", "b"])
        assert plan.milestones == ["a", "b"]

    def test_manager_plan_milestones_default_none(self):
        from sediman.agent.manager import ManagerPlan
        plan = ManagerPlan(browser_task="test")
        assert plan.milestones is None

    def test_parse_plan_data_extracts_milestones(self):
        from sediman.agent.manager import ManagerAgent
        agent = ManagerAgent(llm=MagicMock())
        data = {
            "browser_task": "test",
            "strategy": "direct",
            "milestones": ["step1", "step2"],
        }
        plan = agent._parse_plan_data(data)
        assert plan is not None
        assert plan.milestones == ["step1", "step2"]

    def test_parse_plan_data_ignores_bad_milestones(self):
        from sediman.agent.manager import ManagerAgent
        agent = ManagerAgent(llm=MagicMock())
        data = {
            "browser_task": "test",
            "strategy": "direct",
            "milestones": "not a list",
        }
        plan = agent._parse_plan_data(data)
        assert plan is not None
        assert plan.milestones is None

    @pytest.mark.asyncio
    async def test_generate_milestones_success(self):
        from sediman.agent.manager import ManagerAgent
        llm = AsyncMock()
        llm.chat.return_value = MagicMock(
            text='{"milestones": ["Navigate to site", "Search", "Buy"]}'
        )
        agent = ManagerAgent(llm=llm)
        milestones = await agent.generate_milestones("Buy a laptop")
        assert len(milestones) == 3

    @pytest.mark.asyncio
    async def test_generate_milestones_failure(self):
        from sediman.agent.manager import ManagerAgent
        llm = AsyncMock()
        llm.chat.side_effect = Exception("fail")
        agent = ManagerAgent(llm=llm)
        milestones = await agent.generate_milestones("Buy a laptop")
        assert milestones == []


class TestDecomposeBeamSearch:
    @pytest.mark.asyncio
    async def test_beam_search_returns_best(self):
        from sediman.agent.manager import ManagerAgent
        from sediman.agent.state import PlanStep, Strategy

        llm = AsyncMock()
        responses = [
            MagicMock(text='{"subtasks": ["short"]}')
            for _ in range(2)
        ]
        responses[0] = MagicMock(text='{"subtasks": ["Find product on Amazon", "Compare prices", "Add to cart"]}')
        responses[1] = MagicMock(text='{"subtasks": ["Search for the specific product we want to buy on the Amazon website and locate it"]}')
        llm.chat.side_effect = responses

        agent = ManagerAgent(llm=llm)
        steps = await agent.decompose("Buy headphones", beam_width=2)
        assert len(steps) >= 1
        assert all(isinstance(s, PlanStep) for s in steps)

    @pytest.mark.asyncio
    async def test_decompose_fallback_on_failure(self):
        from sediman.agent.manager import ManagerAgent

        llm = AsyncMock()
        llm.chat.side_effect = Exception("LLM error")
        agent = ManagerAgent(llm=llm)
        steps = await agent.decompose("Buy headphones", beam_width=2)
        assert len(steps) == 1
        assert steps[0].strategy.value == "direct"

    def test_score_decomposition(self):
        from sediman.agent.manager import ManagerAgent
        from sediman.agent.state import PlanStep, Strategy

        agent = ManagerAgent(llm=MagicMock())

        good = [
            PlanStep(id=0, description="Search Amazon for headphones", strategy=Strategy.DELEGATE),
            PlanStep(id=1, description="Compare top 3 results", strategy=Strategy.DELEGATE),
            PlanStep(id=2, description="Add best option to cart", strategy=Strategy.DELEGATE),
        ]
        bad = [PlanStep(id=0, description="Do it", strategy=Strategy.DELEGATE)]

        score_good = agent._score_decomposition(good, "Buy headphones on Amazon")
        score_bad = agent._score_decomposition(bad, "Buy headphones on Amazon")
        assert score_good > score_bad


class TestBrowserState:
    def test_browser_state_dataclass(self):
        from sediman.browser.controller import BrowserState
        state = BrowserState(url="http://example.com", scroll_x=0, scroll_y=100)
        assert state.url == "http://example.com"
        assert state.scroll_y == 100

    def test_browser_controller_has_methods(self):
        from sediman.browser.controller import BrowserController
        ctrl = BrowserController(headless=True)
        assert hasattr(ctrl, "save_checkpoint")
        assert hasattr(ctrl, "restore_checkpoint")
        assert hasattr(ctrl, "clear_checkpoints")
        assert hasattr(ctrl, "_saved_states")

    @pytest.mark.asyncio
    async def test_save_checkpoint_no_page(self):
        from sediman.browser.controller import BrowserController
        ctrl = BrowserController(headless=True)
        idx = await ctrl.save_checkpoint()
        assert idx == -1

    @pytest.mark.asyncio
    async def test_restore_checkpoint_empty(self):
        from sediman.browser.controller import BrowserController
        ctrl = BrowserController(headless=True)
        result = await ctrl.restore_checkpoint()
        assert result is False

    def test_clear_checkpoints(self):
        from sediman.browser.controller import BrowserController, BrowserState
        ctrl = BrowserController(headless=True)
        ctrl._saved_states.append(BrowserState(url="http://a.com", scroll_x=0, scroll_y=0))
        ctrl.clear_checkpoints()
        assert len(ctrl._saved_states) == 0
