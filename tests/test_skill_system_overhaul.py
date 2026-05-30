from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.manager import ManagerPlan
from sediman.agent.recorder import SkillRecorder
from sediman.agent.skill_auditor import SkillAuditor
from sediman.agent.skill_learner import SkillLearnerAgent
from sediman.skills.engine import SkillEngine
from sediman.skills.format import StepData, SkillData
from sediman.skills.healer import heal_skill


class TestStepData:
    def test_from_string(self):
        sd = StepData.from_json("Navigate to Google")
        assert sd.description == "Navigate to Google"
        assert sd.action_type == ""

    def test_from_dict(self):
        sd = StepData.from_json({
            "description": "Click button",
            "action_type": "click",
            "selector": "button.submit",
        })
        assert sd.description == "Click button"
        assert sd.action_type == "click"
        assert sd.selector == "button.submit"

    def test_to_json_roundtrip(self):
        sd = StepData(
            description="Navigate",
            action_type="navigate",
            url="https://example.com",
            expected_outcome="Page loads",
        )
        d = sd.to_json()
        sd2 = StepData.from_json(d)
        assert sd2.description == sd.description
        assert sd2.url == sd.url
        assert sd2.expected_outcome == sd.expected_outcome

    def test_to_string_with_url(self):
        sd = StepData(description="Navigate", url="https://example.com")
        s = sd.to_string()
        assert "https://example.com" in s

    def test_from_browser_action_navigate(self):
        action = {
            "action": "navigate",
            "arguments": {"url": "https://google.com"},
        }
        sd = StepData.from_browser_action(action)
        assert sd.action_type == "navigate"
        assert sd.url == "https://google.com"
        assert "google.com" in sd.description

    def test_from_browser_action_click(self):
        action = {
            "action": "click",
            "arguments": {"index": 5},
            "interacted_element": {"text": "Submit", "selector": "button"},
        }
        sd = StepData.from_browser_action(action)
        assert sd.action_type == "click"
        assert sd.selector == "button"
        assert "Submit" in sd.description

    def test_from_browser_action_input(self):
        action = {
            "action": "input",
            "arguments": {"text": "hello world"},
            "interacted_element": {"text": "Search", "selector": "input.q"},
        }
        sd = StepData.from_browser_action(action)
        assert sd.action_type == "input"
        assert sd.text == "hello world"
        assert sd.selector == "input.q"

    def test_from_browser_action_done(self):
        action = {"action": "done"}
        sd = StepData.from_browser_action(action)
        assert sd.action_type == "done"

    def test_from_browser_action_with_type_key(self):
        action = {"type": "scroll"}
        sd = StepData.from_browser_action(action)
        assert sd.action_type == "scroll"

    def test_to_json_omits_empty_fields(self):
        sd = StepData(description="Simple step")
        d = sd.to_json()
        assert "description" in d
        assert "url" not in d
        assert "selector" not in d


class TestSkillEngineCache:
    def test_list_skills_caches(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="test-skill", description="desc", steps=["s1"])
        result1 = engine.list_skills()
        result2 = engine.list_skills()
        assert result1 == result2
        assert engine._list_cache is not None

    def test_read_caches(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="cached-read", description="desc", steps=["s1"])
        r1 = engine.read("cached-read")
        assert "cached-read" in engine._read_cache
        r2 = engine.read("cached-read")
        assert r1 == r2

    def test_invalidate_cache_on_create(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="skill-a", description="a", steps=["s1"])
        engine.list_skills()
        assert engine._list_cache is not None
        engine.create(name="skill-b", description="b", steps=["s2"])
        assert engine._list_cache is None

    def test_invalidate_cache_on_patch(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="patch-test", description="orig", steps=["s1"])
        engine.read("patch-test")
        assert "patch-test" in engine._read_cache
        engine.patch("patch-test", {"description": "new"})
        assert "patch-test" in engine._read_cache
        assert engine._read_cache["patch-test"]["description"] == "new"

    def test_invalidate_cache_on_delete(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="del-test", description="desc", steps=["s1"])
        engine.read("del-test")
        assert "del-test" in engine._read_cache
        engine.delete("del-test")
        assert "del-test" not in engine._read_cache

    def test_cache_disabled(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=False)
        engine.create(name="no-cache", description="desc", steps=["s1"])
        r1 = engine.read("no-cache")
        assert engine._read_cache == {}
        assert engine._list_cache is None

    def test_list_skills_returns_full_data(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="full-1", description="d1", steps=["s1"], structured_steps=[{"description": "s1", "action_type": "navigate"}])
        engine.create(name="full-2", description="d2", steps=["s2"])
        full = engine.list_skills()
        assert len(full) == 2
        names = [s["name"] for s in full]
        assert "full-1" in names
        assert "full-2" in names
        full_1 = next(s for s in full if s["name"] == "full-1")
        assert full_1["structured_steps"] == [{"description": "s1", "action_type": "navigate"}]

    def test_list_skills_populates_read_cache(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="cache-pop", description="desc", steps=["s1"])
        engine.list_skills()
        assert "cache-pop" in engine._read_cache


class TestSkillEngineFindSimilarOptimized:
    @pytest.mark.asyncio
    async def test_find_similar_uses_cache(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="google-search", description="Search Google for information", steps=["s1"])
        engine.list_skills()
        assert engine._list_cache is not None
        results = await engine.find_similar("search Google for data")
        assert results is not None
        assert len(results) > 0
        assert results[0]["name"] == "google-search"


class TestRecorderEngineInjection:
    def test_recorder_uses_injected_engine(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="test task",
            skill_name="injected-engine-test",
            skill_description="Test with injected engine",
        )
        actions = [{"action": "navigate", "url": "https://example.com"}, {"action": "extract"}]

        name = recorder.record("test", plan, "done", actions, engine=engine)

        assert name == "injected-engine-test"
        skill = engine.read("injected-engine-test")
        assert skill is not None
        assert skill["name"] == "injected-engine-test"

    def test_recorder_produces_structured_steps(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        recorder = SkillRecorder()
        plan = ManagerPlan(
            browser_task="navigate and search",
            skill_name="structured-test",
            skill_description="Test structured steps",
        )
        actions = [
            {"action": "navigate", "arguments": {"url": "https://google.com"}},
            {"action": "input", "arguments": {"text": "test query"}, "interacted_element": {"text": "Search", "selector": "input[name=q]"}},
            {"action": "click", "arguments": {"index": 1}, "interacted_element": {"text": "Search button", "selector": "input[type=submit]"}},
        ]

        recorder.record("test", plan, "done", actions, engine=engine)

        skill = engine.read("structured-test")
        assert skill is not None
        assert len(skill["structured_steps"]) == 4
        nav_step = skill["structured_steps"][1]
        assert nav_step["action_type"] == "navigate"
        assert nav_step["url"] == "https://google.com"
        input_step = skill["structured_steps"][2]
        assert input_step["action_type"] == "input"
        assert input_step["text"] == "test query"
        assert input_step["selector"] == "input[name=q]"


class TestSkillLearnerEngineInjection:
    def test_learner_uses_injected_engine(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        llm = MagicMock()
        learner = SkillLearnerAgent(llm, engine=engine)
        assert learner._engine is engine

    def test_learner_falls_back_to_new_engine(self):
        llm = MagicMock()
        learner = SkillLearnerAgent(llm)
        assert learner._engine is None

    def test_conversation_trimmed_to_5(self):
        llm = MagicMock()
        learner = SkillLearnerAgent(llm)
        conv = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        result = learner._format_conversation(conv)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 5

    def test_conversation_content_trimmed_to_150(self):
        llm = MagicMock()
        learner = SkillLearnerAgent(llm)
        conv = [{"role": "user", "content": "x" * 300}]
        result = learner._format_conversation(conv)
        content_part = result.split("] ", 1)[1]
        assert len(content_part) <= 150

    def test_extract_steps_from_actions(self):
        llm = MagicMock()
        learner = SkillLearnerAgent(llm)
        actions = [
            {"action": "navigate", "arguments": {"url": "https://example.com"}},
            {"action": "click", "arguments": {"index": 1}},
            {"action": "done"},
        ]
        steps = learner._extract_steps_from_actions(actions)
        assert len(steps) == 2
        assert "example.com" in steps[0]


class TestSkillAuditorEngineInjection:
    def test_auditor_uses_injected_engine(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        llm = MagicMock()
        auditor = SkillAuditor(llm, engine=engine)
        assert auditor._engine is engine

    @pytest.mark.asyncio
    async def test_auditor_uses_list_skills_full(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="audit-test", description="desc", steps=["s1", "s2"])
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(text='{"actions": [], "summary": "ok"}'))
        auditor = SkillAuditor(llm, engine=engine)

        result = await auditor.audit()
        assert result["actions"] == []


class TestHealerEngineInjection:
    @pytest.mark.asyncio
    async def test_healer_accepts_engine_param(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(name="heal-test", description="desc", steps=["s1", "s2"])

        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            text=json.dumps({"steps": ["new1", "new2"], "confidence": "high", "reasoning": "test"})
        ))
        browser_session = MagicMock()
        browser_session.browser = None

        result = await heal_skill(
            skill={"name": "heal-test", "steps": ["s1", "s2"], "version": 1},
            error_context="test error",
            browser_session=browser_session,
            llm=llm,
            engine=engine,
        )
        assert result is not None
        assert result["version"] == 2
        assert "heal-test" in engine._read_cache


class TestSkillDataStructuredSteps:
    def test_structured_steps_serialized(self):
        skill = SkillData(
            name="test",
            description="desc",
            steps=["Navigate", "Click"],
            structured_steps=[
                {"description": "Navigate", "action_type": "navigate", "url": "https://example.com"},
                {"description": "Click", "action_type": "click"},
            ],
        )
        d = skill.to_json()
        assert "structured_steps" in d
        assert len(d["structured_steps"]) == 2
        assert d["structured_steps"][0]["url"] == "https://example.com"

    def test_structured_steps_omitted_when_empty(self):
        skill = SkillData(name="test", description="desc", steps=["s1"])
        d = skill.to_json()
        assert "structured_steps" not in d

    def test_parse_skill_json_with_structured_steps(self):
        data = {
            "name": "test",
            "description": "desc",
            "steps": ["s1"],
            "structured_steps": [{"description": "s1", "action_type": "navigate"}],
        }
        from sediman.skills.format import parse_skill_json
        skill = parse_skill_json(json.dumps(data))
        assert skill is not None
        assert len(skill.structured_steps) == 1
        assert skill.structured_steps[0]["action_type"] == "navigate"


class TestExecutorStructuredSteps:
    def test_format_steps_for_prompt_strings(self):
        from sediman.skills.executor import _format_steps_for_prompt
        result = _format_steps_for_prompt(["Navigate to Google", "Search for Python"])
        assert "1. Navigate to Google" in result
        assert "2. Search for Python" in result

    def test_format_steps_for_prompt_dicts(self):
        from sediman.skills.executor import _format_steps_for_prompt
        steps = [
            {"description": "Navigate", "action_type": "navigate", "url": "https://example.com", "expected_outcome": "Page loads"},
            {"description": "Click", "action_type": "click", "selector": "button"},
        ]
        result = _format_steps_for_prompt(steps)
        assert "URL: https://example.com" in result
        assert "Selector: button" in result
        assert "Expected: Page loads" in result


class TestPreCheckDedup:
    @pytest.mark.asyncio
    async def test_precheck_skips_llm_when_similar_exists(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(
            name="google-search",
            description="Search Google for information",
            steps=["Navigate to Google", "Type query", "Click search"],
        )

        similar_skill = {"name": "google-search", "description": "Search Google for information"}

        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            text=json.dumps({
                "should_learn": True,
                "should_patch": False,
                "skill_name": "google-search-web",
                "description": "Search Google for python async",
                "steps": ["Navigate to Google", "Type python async", "Click search"],
            })
        ))
        learner = SkillLearnerAgent(llm, engine=engine)

        actions = [
            {"action": "navigate", "arguments": {"url": "https://google.com"}},
            {"action": "input", "arguments": {"text": "python async"}},
            {"action": "click", "arguments": {"index": 1}},
        ]

        with patch("sediman.memory.security.scan_content", return_value=[]), \
             patch.object(SkillEngine, "find_similar", new_callable=AsyncMock, return_value=[similar_skill]):
            result = await learner.review_and_learn(
                task="search Google for python async info",
                browser_actions=actions,
                result="Found results",
                success=True,
                existing_skills=[{"name": "google-search", "description": "Search Google for information"}],
            )

        assert result == "google-search"

    @pytest.mark.asyncio
    async def test_precheck_falls_back_to_llm_when_no_similar(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)

        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            text=json.dumps({"should_learn": False})
        ))
        learner = SkillLearnerAgent(llm, engine=engine)

        actions = [
            {"action": "navigate", "arguments": {"url": "https://example.com"}},
            {"action": "extract"},
        ]

        with patch.object(SkillEngine, "find_similar", new_callable=AsyncMock, return_value=[]):
            result = await learner.review_and_learn(
                task="do something completely new",
                browser_actions=actions,
                result="done",
                success=True,
                existing_skills=[],
            )

        assert result is None
        llm.chat.assert_called_once()


class TestApplyEvaluationNoRedundantRead:
    @pytest.mark.asyncio
    async def test_patch_path_skips_second_read(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)
        engine.create(
            name="patch-test",
            description="original",
            steps=["s1", "s2"],
        )

        llm = MagicMock()
        learner = SkillLearnerAgent(llm, engine=engine)

        evaluation = {
            "should_learn": True,
            "should_patch": True,
            "skill_name": "patch-test",
            "description": "updated",
            "steps": ["new1", "new2", "new3"],
        }

        result = await learner._apply_evaluation(evaluation)
        assert result == "patch-test"

        skill = engine.read("patch-test")
        assert skill["description"] == "updated"
        assert len(skill["steps"]) == 3

    @pytest.mark.asyncio
    async def test_create_path_after_failed_patch(self, tmp_sediman_dir):
        skills_dir = tmp_sediman_dir / "skills"
        engine = SkillEngine(skills_dir=skills_dir, use_cache=True)

        llm = MagicMock()
        learner = SkillLearnerAgent(llm, engine=engine)

        evaluation = {
            "should_learn": True,
            "should_patch": False,
            "skill_name": "new-skill",
            "description": "a new skill",
            "steps": ["step1", "step2"],
        }

        with patch("sediman.memory.security.scan_content", return_value=[]), \
             patch.object(SkillEngine, "find_similar", return_value=[]):
            result = await learner._apply_evaluation(evaluation)
        assert result == "new-skill"
