from __future__ import annotations

from unittest.mock import patch


from sediman.agent.recorder import SkillRecorder
from sediman.agent.manager import ManagerPlan
from sediman.agent.planner import ScheduleIntent


class TestSkillRecorderShouldRecordAutoLearn:
    def test_auto_learn_with_three_distinct_types(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="search google for python")
        actions = [
            {"action": "navigate", "url": "https://google.com"},
            {"action": "click", "index": 1},
            {"action": "input", "text": "python"},
        ]
        assert recorder.should_record("search google", plan, actions) is True

    def test_auto_learn_with_navigate_click_extract(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="get price")
        actions = [
            {"action": "navigate"},
            {"action": "click"},
            {"action": "extract"},
        ]
        assert recorder.should_record("get price", plan, actions) is True

    def test_no_auto_learn_with_two_actions(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="simple")
        actions = [
            {"action": "navigate"},
            {"action": "click"},
        ]
        assert recorder.should_record("simple", plan, actions) is False

    def test_no_auto_learn_with_all_same_type(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="browse")
        actions = [
            {"action": "navigate"},
            {"action": "navigate"},
            {"action": "navigate"},
        ]
        assert recorder.should_record("browse", plan, actions) is False

    def test_auto_learn_ignores_done_actions_for_distinct(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="task")
        actions = [
            {"action": "navigate"},
            {"action": "done"},
            {"action": "done"},
        ]
        assert recorder.should_record("task", plan, actions) is False

    def test_skill_name_overrides_auto_learn_threshold(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="task",
            skill_name="named-skill",
        )
        actions = [
            {"action": "navigate"},
            {"action": "click"},
        ]
        assert recorder.should_record("task", plan, actions) is True


class TestSkillRecorderInferSkillName:
    def test_basic_task_name(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("Search Google for Python tutorials")
        assert result is not None
        assert "search" in result
        assert "google" in result
        assert "python" in result

    def test_short_task_name(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("Go")
        assert result is None

    def test_task_with_special_chars(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("Check price of NVDA @ Yahoo! Finance")
        assert result is not None
        assert "@" not in result
        assert "!" not in result

    def test_task_with_numbers(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("Book flight 123 on airline website")
        assert result is not None
        assert "123" in result

    def test_empty_task(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("")
        assert result is None

    def test_task_with_only_special_chars(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name("@#$%^&*()")
        assert result is None

    def test_long_task_truncated_to_5_words(self):
        recorder = SkillRecorder()
        result = recorder._infer_skill_name(
            "Search for the best python tutorial on the internet today"
        )
        assert result is not None
        parts = result.split("-")
        assert len(parts) <= 5


class TestSkillRecorderExtractVariables:
    def test_extracts_input_variables(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "navigate", "url": "https://google.com"},
            {"action": "input", "text": "python async await"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 1
        assert "input_value" in variables[0]

    def test_extracts_search_query(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "search", "query": "python tutorials"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert "search_query" in variables

    def test_deduplicates_urls(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "navigate", "url": "https://a.com"},
            {"action": "navigate", "url": "https://a.com"},
            {"action": "navigate", "url": "https://b.com"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 0

    def test_deduplicates_input_texts(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "input", "text": "hello"},
            {"action": "input", "text": "hello"},
            {"action": "input", "text": "world"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 2

    def test_short_input_skipped(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "input", "text": "ab"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 0

    def test_max_10_variables(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "input", "text": f"value_{i}"} for i in range(15)
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 10

    def test_empty_actions(self):
        recorder = SkillRecorder()
        variables = recorder._extract_variables_from_actions([])
        assert variables == []

    def test_actions_with_arguments_key(self):
        recorder = SkillRecorder()
        actions = [
            {"action": "input", "arguments": {"text": "search term"}},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 1

    def test_navigate_with_type_key(self):
        recorder = SkillRecorder()
        actions = [
            {"type": "navigate", "url": "https://x.com"},
        ]
        variables = recorder._extract_variables_from_actions(actions)
        assert len(variables) == 0


class TestSkillRecorderRecordAutoLearn:
    def test_auto_records_without_skill_name(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="search for python")
        actions = [
            {"action": "navigate", "url": "https://google.com"},
            {"action": "input", "text": "python"},
            {"action": "click", "index": 1},
        ]

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            name = recorder.record("search for python", plan, "done", actions, engine=engine)

        assert name is not None
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            skill = engine.read(name)
        assert skill is not None
        assert len(skill["steps"]) >= 3

    def test_auto_record_includes_variables(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="search google")
        actions = [
            {"action": "navigate", "url": "https://google.com"},
            {"action": "input", "text": "python async"},
            {"action": "click", "index": 1},
        ]

        skills_dir = tmp_sediman_dir / "skills"
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            name = recorder.record("search google", plan, "done", actions, engine=engine)

        assert name is not None
        with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", skills_dir):
            from sediman.skills.engine import SkillEngine
            engine = SkillEngine(skills_dir=skills_dir)
            skill = engine.read(name)
        assert "variables" in skill
        assert len(skill["variables"]) >= 1

    def test_auto_record_skips_when_no_name_inferred(self, tmp_sediman_dir):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="x")
        actions = [
            {"action": "navigate"},
            {"action": "click"},
            {"action": "input"},
        ]
        result = recorder.record("", plan, "done", actions)
        assert result is None


class TestSkillRecorderBuildSteps:
    def test_includes_browser_task_when_different(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="specific browser task")
        string_steps, structured_steps = recorder._build_steps(
            "original task", plan,
            [
                {"action": "navigate", "url": "https://x.com"},
                {"action": "click", "index": 1},
            ],
        )
        assert any("specific browser task" in s for s in string_steps)
        assert len(structured_steps) == len(string_steps)

    def test_skips_done_actions(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="task")
        string_steps, _ = recorder._build_steps(
            "task", plan,
            [
                {"action": "navigate", "url": "https://x.com"},
                {"action": "done"},
            ],
        )
        assert len(string_steps) == 1

    def test_fallback_to_task_description(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(browser_task="task")
        string_steps, _ = recorder._build_steps(
            "task", plan, [{"action": "done"}]
        )
        assert len(string_steps) == 1
        assert "task" in string_steps[0]

    def test_includes_schedule(self):
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="task",
            schedule=ScheduleIntent(cron="*/5 * * * *", task="check server"),
        )
        string_steps, _ = recorder._build_steps(
            "task", plan, [{"action": "navigate"}, {"action": "click"}]
        )
        assert any("Schedule" in s for s in string_steps)
