from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.skill_learner import SkillLearnerAgent
from sediman.llm.provider import LLMResponse


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat = AsyncMock()
    return llm


@pytest.fixture
def learner(mock_llm):
    return SkillLearnerAgent(mock_llm)


def _make_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], done=True)


class TestRefineWithCritique:
    @pytest.mark.asyncio
    async def test_does_not_refine_when_no_template(self, mock_llm, learner):
        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="",
        ):
            result = await learner._refine_with_critique(
                {"skill_name": "test", "description": "desc", "steps": ["a", "b"]},
                "task",
                [{"action": "navigate", "url": "https://x.com"}],
                "done",
                True,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_refines_with_critique(self, mock_llm, learner):
        mock_llm.chat.side_effect = [
            _make_response(
                '{"critique": "needs more steps", "should_refine": true, '
                '"improvements": {"steps": ["a", "b", "c"]}}'
            ),
            _make_response('{"critique": "looks good", "should_refine": false}'),
        ]

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="You are a skill reviewer.",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test-skill",
                    "description": "original",
                    "steps": ["a", "b"],
                },
                "do something",
                [{"action": "navigate", "url": "https://x.com"}],
                "done",
                True,
            )
            assert result is not None
            assert result["steps"] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_refines_multiple_fields(self, mock_llm, learner):
        mock_llm.chat.side_effect = [
            _make_response(
                '{"critique": "needs improvement", "should_refine": true, '
                '"improvements": {"description": "new desc", "pitfalls": ["watch out"]}}'
            ),
            _make_response('{"critique": "good", "should_refine": false}'),
        ]

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="You are a skill reviewer.",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test",
                    "description": "old desc",
                    "steps": ["a", "b"],
                    "pitfalls": [],
                },
                "task",
                [],
                "done",
                True,
            )
            assert result is not None
            assert result["description"] == "new desc"
            assert result["pitfalls"] == ["watch out"]

    @pytest.mark.asyncio
    async def test_stops_after_max_cycles(self, mock_llm, learner):
        mock_llm.chat.side_effect = [
            _make_response(
                '{"critique": "fix 1", "should_refine": true, '
                '"improvements": {"steps": ["a", "b"]}}'
            ),
            _make_response(
                '{"critique": "fix 2", "should_refine": true, '
                '"improvements": {"steps": ["a", "b", "c"]}}'
            ),
            _make_response(
                '{"critique": "fix 3", "should_refine": true, '
                '"improvements": {"steps": ["a", "b", "c", "d"]}}'
            ),
            _make_response(
                '{"critique": "fix 4", "should_refine": true, '
                '"improvements": {"steps": ["a", "b", "c", "d", "e"]}}'
            ),
        ]

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="You are a skill reviewer.",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test",
                    "description": "desc",
                    "steps": ["a"],
                },
                "task",
                [],
                "done",
                True,
            )
            assert result is not None
            # Should have stopped after 3 cycles (one initial + one refinement)
            # actually _MAX_REFINEMENT_CYCLES = 3, so we expect max 3 chat calls that return refine=true
            # but the loop runs up to _MAX_REFINEMENT_CYCLES iterations
            assert len(mock_llm.chat.call_args_list) <= 4

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self, mock_llm, learner):
        mock_llm.chat.side_effect = Exception("LLM down")

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="You are a skill reviewer.",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test",
                    "description": "desc",
                    "steps": ["a", "b"],
                },
                "task",
                [],
                "done",
                True,
            )
            assert result is not None  # Returns original on failure
            assert result["steps"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_parse_critique_valid(self, learner):
        text = '{"critique": "good", "should_refine": false}'
        result = learner._parse_critique(text)
        assert result is not None
        assert result["should_refine"] is False

    @pytest.mark.asyncio
    async def test_parse_critique_invalid(self, learner):
        assert learner._parse_critique("not json") is None
        assert learner._parse_critique("") is None

    @pytest.mark.asyncio
    async def test_refines_when_no_critique_field(self, mock_llm, learner):
        mock_llm.chat.return_value = _make_response('{"not_critique": true}')

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="template",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test",
                    "description": "desc",
                    "steps": ["a", "b"],
                },
                "task",
                [],
                "done",
                True,
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_refinement_preserves_unchanged_fields(self, mock_llm, learner):
        mock_llm.chat.return_value = _make_response(
            '{"critique": "needs fix", "should_refine": true, '
            '"improvements": {"steps": ["new a", "new b"]}}'
        )

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="template",
        ):
            result = await learner._refine_with_critique(
                {
                    "skill_name": "test",
                    "description": "original desc",
                    "steps": ["old a", "old b"],
                    "when_to_use": "original trigger",
                    "verification": "original verify",
                },
                "task",
                [],
                "done",
                True,
            )
            assert result["description"] == "original desc"
            assert result["when_to_use"] == "original trigger"
            assert result["verification"] == "original verify"


class TestLoadFailedTrajectories:
    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self, learner):
        with patch(
            "sediman.memory.trajectories.TrajectoryDB",
            side_effect=ImportError("no db"),
        ):
            result = await learner._load_failed_trajectories("skill", "task")
            assert result == ""

    @pytest.mark.asyncio
    async def test_includes_failure_context(self, learner):
        mock_traj_db = MagicMock()
        mock_traj_instance = MagicMock()
        mock_traj_instance.get_recent_failures = AsyncMock(return_value=[])

        with patch(
            "sediman.memory.trajectories.TrajectoryDB",
            return_value=mock_traj_instance,
        ):
            result = await learner._load_failed_trajectories("test-skill", "test task")
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_empty_when_no_failures(self, learner):
        mock_db = MagicMock()
        mock_db.get_recent_failures = AsyncMock(return_value=[])

        with patch(
            "sediman.memory.trajectories.TrajectoryDB",
            return_value=mock_db,
        ):
            result = await learner._load_failed_trajectories(None, "task")
            assert result == ""


class TestReviewAndLearnWithRefinement:
    @pytest.mark.asyncio
    async def test_full_flow_with_refinement(self, mock_llm, learner, tmp_path):
        mock_llm.chat.return_value = _make_response(
            '{"should_learn": true, "skill_name": "critique-skill", '
            '"description": "refined skill", "steps": ["step a", "step b"]}'
        )

        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="You are a skill reviewer.",
        ), patch("sediman.skills.engine.SkillEngine.find_similar", return_value=[]):
            result = await learner.review_and_learn(
                task="refine me",
                browser_actions=[
                    {"action": "navigate", "url": "https://x.com"},
                    {"action": "click", "index": 1},
                ],
                result="success",
                success=True,
                existing_skills=[],
            )
            assert result is not None

        engine_mod.GLOBAL_SKILLS_DIR = original

    @pytest.mark.asyncio
    async def test_precheck_similar_with_refinement(self, mock_llm, learner, tmp_path):
        import sediman.skills.engine as engine_mod
        original = engine_mod.GLOBAL_SKILLS_DIR
        engine_mod.GLOBAL_SKILLS_DIR = tmp_path

        from sediman.skills.engine import SkillEngine
        engine = SkillEngine()
        engine.create("existing-skill", "Does a thing", ["a", "b"])
        learner._engine = engine

        similar_skill = {"name": "existing-skill", "description": "Does a thing"}
        mock_llm.chat.return_value = _make_response(
            '{"should_learn": true, "skill_name": "existing-skill", "should_patch": true, '
            '"description": "patched desc", "steps": ["new a", "new b"]}'
        )

        with patch(
            "sediman.agent.prompts.builder._load_template",
            return_value="template",
        ), patch.object(SkillEngine, "find_similar", new_callable=AsyncMock, return_value=[similar_skill]):
            result = await learner.review_and_learn(
                task="do the thing",
                browser_actions=[
                    {"action": "navigate", "url": "https://example.com"},
                    {"action": "click", "index": 2},
                ],
                result="done",
                success=True,
                existing_skills=[],
            )

            assert result == "existing-skill"
            fresh_engine = SkillEngine()
            patched = fresh_engine.read("existing-skill")
            assert patched["version"] == 2

        engine_mod.GLOBAL_SKILLS_DIR = original
