from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

from sediman.memory.trajectories import (
    Trajectory,
    TrajectoryDB,
    TrajectoryStep,
    make_trajectory,
)


@pytest_asyncio.fixture
async def db(tmp_sediman_dir: Path):
    db_path = tmp_sediman_dir / "state.db"
    with patch("sediman.memory.trajectories.TRAJECTORIES_DIR", tmp_sediman_dir / "trajs"):
        from sediman.store.db import init_db
        await init_db()
        yield TrajectoryDB(db_path=db_path)


class TestTrajectoryStep:
    def test_default_timestamp(self):
        step = TrajectoryStep(action="navigate")
        assert step.action == "navigate"
        assert step.timestamp is not None

    def test_full_construction(self):
        step = TrajectoryStep(
            action="click",
            observation="button found",
            screenshot_path="/tmp/screen.png",
            duration_ms=150,
            error=None,
            timestamp="2024-01-01T00:00:00",
        )
        assert step.action == "click"
        assert step.screenshot_path == "/tmp/screen.png"


class TestTrajectory:
    def test_default_id(self):
        t = Trajectory(task="test task")
        assert t.id is not None
        assert len(t.id) > 0

    def test_empty_steps(self):
        t = Trajectory(task="test")
        assert t.steps == []

    def test_metadata_default(self):
        t = Trajectory(task="test")
        assert t.metadata == {}


class TestMakeTrajectory:
    def test_from_actions(self):
        actions = [
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "index": 1},
        ]
        traj = make_trajectory(
            task="test task",
            actions=actions,
            result="success",
            success=True,
            skill_name="test-skill",
        )
        assert traj.task == "test task"
        assert traj.result == "success"
        assert traj.success is True
        assert traj.skill_name == "test-skill"
        assert len(traj.steps) == 2

    def test_with_screenshots(self):
        actions = [{"action": "navigate", "url": "https://example.com"}]
        traj = make_trajectory(
            task="test",
            actions=actions,
            screenshots=["/tmp/screen1.png"],
        )
        assert traj.steps[0].screenshot_path == "/tmp/screen1.png"

    def test_preserves_action_observation(self):
        actions = [
            {"action": "click", "observation": "button clicked", "duration_ms": 100}
        ]
        traj = make_trajectory(task="test", actions=actions)
        assert traj.steps[0].observation == "button clicked"
        assert traj.steps[0].duration_ms == 100

    def test_empty_actions(self):
        traj = make_trajectory(task="empty", actions=[])
        assert traj.steps == []


class TestTrajectoryDBSave:
    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, db):
        steps = [TrajectoryStep(action="navigate", observation="ok")]
        traj = Trajectory(
            id="test-1",
            task="test task",
            steps=steps,
            result="done",
            success=True,
            skill_name="skill-1",
        )

        await db.save(traj)
        retrieved = await db.get("test-1")

        assert retrieved is not None
        assert retrieved.task == "test task"
        assert retrieved.result == "done"
        assert retrieved.success is True
        assert retrieved.skill_name == "skill-1"
        assert len(retrieved.steps) == 1
        assert retrieved.steps[0].action == "navigate"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await db.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_overwrites(self, db):
        traj1 = Trajectory(id="same-id", task="v1", steps=[])
        await db.save(traj1)

        traj2 = Trajectory(id="same-id", task="v2", steps=[])
        await db.save(traj2)

        retrieved = await db.get("same-id")
        assert retrieved is not None
        assert retrieved.task == "v2"

    @pytest.mark.asyncio
    async def test_save_with_metadata(self, db):
        traj = Trajectory(
            id="meta-test",
            task="test",
            steps=[],
            metadata={"source": "test", "priority": 1},
        )
        await db.save(traj)
        retrieved = await db.get("meta-test")
        assert retrieved is not None
        assert retrieved.metadata["source"] == "test"
        assert retrieved.metadata["priority"] == 1


class TestTrajectoryDBQueries:
    @pytest.mark.asyncio
    async def test_query_similar_tasks(self, db):
        await db.save(Trajectory(id="1", task="search google", steps=[], success=True))
        await db.save(Trajectory(id="2", task="search bing", steps=[], success=True))
        await db.save(Trajectory(id="3", task="check email", steps=[], success=True))

        results = await db.query_similar_tasks("search", limit=10)
        assert len(results) >= 2
        task_names = [r.task for r in results]
        assert "search google" in task_names
        assert "search bing" in task_names

    @pytest.mark.asyncio
    async def test_get_recent_failures(self, db):
        await db.save(
            Trajectory(id="1", task="task a", steps=[], success=True)
        )
        await db.save(
            Trajectory(id="2", task="task b", steps=[], success=False)
        )
        await db.save(
            Trajectory(id="3", task="task c", steps=[], success=False, skill_name="bad-skill")
        )

        failures = await db.get_recent_failures(limit=10)
        assert len(failures) == 2

        skill_failures = await db.get_recent_failures(limit=10, skill_name="bad-skill")
        assert len(skill_failures) == 1
        assert skill_failures[0].id == "3"

    @pytest.mark.asyncio
    async def test_get_related_trajectories(self, db):
        await db.save(
            Trajectory(id="1", task="task a", steps=[], skill_name="my-skill")
        )
        await db.save(
            Trajectory(id="2", task="task b", steps=[], skill_name="my-skill")
        )
        await db.save(
            Trajectory(id="3", task="task c", steps=[], skill_name="other-skill")
        )

        related = await db.get_related_trajectories("my-skill")
        assert len(related) == 2

    @pytest.mark.asyncio
    async def test_get_related_empty(self, db):
        related = await db.get_related_trajectories("nonexistent")
        assert related == []


class TestTrajectoryDBRatings:
    @pytest.mark.asyncio
    async def test_rate_trajectory(self, db):
        await db.save(Trajectory(id="rate-1", task="test", steps=[], success=True))
        await db.rate_trajectory("rate-1", 1, feedback="good job")

    @pytest.mark.asyncio
    async def test_rate_invalid_value(self, db):
        with pytest.raises(ValueError, match="Rating must be"):
            await db.rate_trajectory("bad", 99)

    @pytest.mark.asyncio
    async def test_get_skill_success_rate(self, db):
        await db.save(
            Trajectory(id="1", task="a", steps=[], success=True, skill_name="s")
        )
        await db.save(
            Trajectory(id="2", task="b", steps=[], success=False, skill_name="s")
        )
        await db.save(
            Trajectory(id="3", task="c", steps=[], success=True, skill_name="s")
        )

        rate = await db.get_skill_success_rate("s")
        assert rate == 2 / 3

    @pytest.mark.asyncio
    async def test_get_skill_success_rate_no_trajs(self, db):
        rate = await db.get_skill_success_rate("nonexistent")
        assert rate == 0.0

    @pytest.mark.asyncio
    async def test_get_unrated_trajectories(self, db):
        await db.save(Trajectory(id="1", task="a", steps=[], success=True))
        await db.save(Trajectory(id="2", task="b", steps=[], success=True))
        await db.rate_trajectory("1", 1)

        unrated = await db.get_unrated_trajectories(limit=10)
        assert len(unrated) == 1
        assert unrated[0].id == "2"


class TestTrajectoryDBScreenshots:
    @pytest.mark.asyncio
    async def test_save_screenshot(self, db):

        path = await db.save_screenshot("test-traj", 0, b"fake-png-data")
        assert path is not None
        assert path.endswith("step_0.png")

        saved_file = Path(path)
        assert saved_file.read_bytes() == b"fake-png-data"


class TestTrajectoryDBTopSkills:
    @pytest.mark.asyncio
    async def test_get_top_skills_by_preference(self, db):
        await db.save(
            Trajectory(id="1", task="a", steps=[], success=True, skill_name="good")
        )
        await db.save(
            Trajectory(id="2", task="b", steps=[], success=True, skill_name="good")
        )
        await db.save(
            Trajectory(id="3", task="c", steps=[], success=False, skill_name="bad")
        )
        await db.save(
            Trajectory(id="4", task="d", steps=[], success=False, skill_name="bad")
        )
        await db.save(
            Trajectory(id="5", task="e", steps=[], success=True, skill_name="good")
        )
        await db.rate_trajectory("1", 1)
        await db.rate_trajectory("2", 1)
        await db.rate_trajectory("3", -1)
        await db.rate_trajectory("4", -1)

        top = await db.get_top_skills_by_preference(min_trajectories=2)
        top_names = [s["skill_name"] for s in top]
        assert "good" in top_names
        assert len(top) >= 1
