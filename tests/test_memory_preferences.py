from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sediman.memory.preferences import PreferenceLearner
from sediman.memory.trajectories import Trajectory


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_top_skills_by_preference = AsyncMock(return_value=[])
    db.get_unrated_trajectories = AsyncMock(return_value=[])
    db.rate_trajectory = AsyncMock()
    return db


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.read = MagicMock(return_value={"name": "test-skill", "version": 1})
    engine.delete = MagicMock(return_value=True)
    return engine


@pytest.fixture
def learner(mock_db, mock_engine):
    return PreferenceLearner(traj_db=mock_db, engine=mock_engine)


class TestPreferenceLearner:
    @pytest.mark.asyncio
    async def test_aggregate_preferences_empty(self, learner):
        result = await learner.aggregate_preferences()
        assert "total_skills_rated" in result
        assert result["skill_scores"] == []

    @pytest.mark.asyncio
    async def test_aggregate_returns_scores(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = [
            {"skill_name": "s1", "avg_preference": 0.8, "traj_count": 5, "success_rate": 1.0}
        ]
        result = await learner.aggregate_preferences()
        assert result["total_skills_rated"] == 1
        assert result["skill_scores"][0]["skill_name"] == "s1"

    @pytest.mark.asyncio
    async def test_get_skill_ranking(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = [
            {"skill_name": "top", "avg_preference": 0.9},
            {"skill_name": "mid", "avg_preference": 0.5},
        ]
        ranking = await learner.get_skill_ranking(limit=10)
        assert len(ranking) == 2
        assert ranking[0]["skill_name"] == "top"

    @pytest.mark.asyncio
    async def test_get_skills_needing_review(self, learner, mock_db):
        mock_db.get_unrated_trajectories.return_value = [
            Trajectory(id="1", task="task a", success=True, skill_name="s1"),
        ]
        needs_review = await learner.get_skills_needing_review()
        assert len(needs_review) == 1
        assert needs_review[0]["trajectory_id"] == "1"

    @pytest.mark.asyncio
    async def test_record_feedback(self, learner, mock_db):
        await learner.record_feedback("traj-1", 1, feedback="great")
        mock_db.rate_trajectory.assert_called_once_with("traj-1", 1, "great")

    @pytest.mark.asyncio
    async def test_prune_dry_run_no_candidates(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = []
        to_prune = await learner.prune_low_rated_skills(dry_run=True)
        assert to_prune == []

    @pytest.mark.asyncio
    async def test_prune_dry_run_identifies_candidates(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = [
            {
                "skill_name": "bad-skill",
                "avg_preference": -1.5,
                "traj_count": 3,
                "success_rate": 0.0,
            }
        ]
        to_prune = await learner.prune_low_rated_skills(dry_run=True)
        assert len(to_prune) == 1
        assert to_prune[0]["skill_name"] == "bad-skill"

    @pytest.mark.asyncio
    async def test_prune_execution(self, learner, mock_db, mock_engine):
        mock_db.get_top_skills_by_preference.return_value = [
            {
                "skill_name": "bad-skill",
                "avg_preference": -1.5,
                "traj_count": 3,
                "success_rate": 0.0,
            }
        ]
        to_prune = await learner.prune_low_rated_skills(dry_run=False)
        assert len(to_prune) == 1
        mock_engine.delete.assert_called_once_with("bad-skill")

    @pytest.mark.asyncio
    async def test_tune_preferences(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = [
            {
                "skill_name": "good-skill",
                "avg_preference": 0.8,
                "traj_count": 5,
                "success_rate": 1.0,
            },
            {
                "skill_name": "bad-skill",
                "avg_preference": -0.7,
                "traj_count": 3,
                "success_rate": 0.2,
            },
        ]

        await learner.tune_preferences()
        # Should not raise

    @pytest.mark.asyncio
    async def test_get_preference_summary(self, learner, mock_db):
        mock_db.get_top_skills_by_preference.return_value = [
            {
                "skill_name": "good",
                "avg_preference": 0.9,
                "traj_count": 5,
                "success_rate": 1.0,
            },
            {
                "skill_name": "bad",
                "avg_preference": -0.7,
                "traj_count": 2,
                "success_rate": 0.0,
            },
        ]
        mock_db.get_unrated_trajectories.return_value = []
        summary = await learner.get_preference_summary()
        assert summary["total_skills_with_preferences"] == 2
        assert len(summary["highly_rated"]) == 1
