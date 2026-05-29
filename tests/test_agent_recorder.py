from __future__ import annotations

from unittest.mock import patch


from sediman.agent.recorder import SkillRecorder
from sediman.agent.manager import ManagerPlan
from sediman.agent.planner import ScheduleIntent


class TestSkillRecorderShouldRecord:
    def test_records_when_skill_name_present_and_enough_actions(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="check stock price",
            skill_name="stock-checker",
            skill_description="Check stock price",
        )
        actions = [{"action": "navigate"}, {"action": "extract"}]

        assert recorder.should_record("check stock price", plan, actions) is True

    def test_auto_records_when_no_skill_name_but_complex_actions(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="check stock price")
        actions = [
            {"action": "navigate"},
            {"action": "click"},
            {"action": "input"},
        ]

        assert recorder.should_record("check stock price", plan, actions) is True

    def test_skips_when_too_few_actions_and_no_skill_name(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="check stock price")
        actions = [{"action": "navigate"}, {"action": "extract"}]

        assert recorder.should_record("check stock price", plan, actions) is False

    def test_skips_when_single_action_type_and_no_skill_name(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="check stock price")
        actions = [{"action": "navigate"}, {"action": "navigate"}, {"action": "navigate"}]

        assert recorder.should_record("check stock price", plan, actions) is False

    def test_skips_when_too_few_actions(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="check stock price",
            skill_name="stock-checker",
            skill_description="Check stock price",
        )
        actions = [{"action": "navigate"}]

        assert recorder.should_record("check stock price", plan, actions) is False


class TestSkillRecorderRecord:
    def test_creates_skill_from_plan(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="navigate to Yahoo Finance and get NVDA price",
            skill_name="nvda-price",
            skill_description="Get NVIDIA stock price from Yahoo Finance",
        )
        actions = [
            {"action": "navigate", "url": "https://finance.yahoo.com/quote/NVDA"},
            {"action": "extract"},
        ]

        with patch("sediman.skills.engine.SKILLS_DIR", tmp_sediman_dir / "skills"):
            name = recorder.record("get nvidia price", plan, "NVDA: $131", actions)

        assert name == "nvda-price"

        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        skill = engine.read("nvda-price")
        assert skill is not None
        assert skill["description"] == "Get NVIDIA stock price from Yahoo Finance"
        assert len(skill["steps"]) >= 2

    def test_includes_schedule_in_steps(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="check server",
            schedule=ScheduleIntent(cron="*/5 * * * *", task="check server"),
            skill_name="server-check",
            skill_description="Check server status",
        )
        actions = [{"action": "navigate"}, {"action": "extract"}]

        with patch("sediman.skills.engine.SKILLS_DIR", tmp_sediman_dir / "skills"):
            name = recorder.record("check server", plan, "OK", actions)

        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        skill = engine.read("server-check")
        steps_text = " ".join(skill["steps"])
        assert "Schedule" in steps_text

    def test_does_not_overwrite_existing(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="do something",
            skill_name="existing-skill",
            skill_description="Already exists",
        )
        actions = [{"action": "navigate"}, {"action": "click"}]

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine

            engine = SkillEngine(skills_dir=skills_dir)
            engine.create(name="existing-skill", description="original", steps=["s1"])

            name = recorder.record("do something", plan, "done", actions)

        assert name is None

    def test_returns_none_when_should_not_record(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="simple task")
        result = recorder.record("simple task", plan, "done", [{"action": "click"}])
        assert result is None


class TestSkillRecorderActionSummarization:
    def test_navigate_action(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action(
            {"action": "navigate", "url": "https://example.com"}
        )
        assert "example.com" in result

    def test_click_action(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action({"action": "click", "index": 5})
        assert "5" in result

    def test_input_action(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action({"action": "input", "text": "hello world"})
        assert "hello world" in result

    def test_extract_action(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action({"action": "extract"})
        assert "Extract" in result

    def test_done_action_returns_none(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action({"action": "done"})
        assert result is None

    def test_empty_action_returns_none_or_string(self):
        recorder = SkillRecorder()
        result = recorder._summarize_action({"action": ""})
        assert result is None or isinstance(result, str)
