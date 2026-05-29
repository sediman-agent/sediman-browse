from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest

from sediman.store.db import init_db, get_connection


class TestTrajectoryTables:
    @pytest.mark.asyncio
    async def test_trajectories_table_exists(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='trajectories'"
                )
                row = await cursor.fetchone()
                assert row is not None

    @pytest.mark.asyncio
    async def test_trajectory_preferences_table_exists(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='trajectory_preferences'"
                )
                row = await cursor.fetchone()
                assert row is not None

    @pytest.mark.asyncio
    async def test_trajectories_schema(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                cursor = await conn.execute("PRAGMA table_info(trajectories)")
                columns = {row[1]: row[2] for row in await cursor.fetchall()}
                assert "id" in columns
                assert "task" in columns
                assert "steps_json" in columns
                assert "success" in columns
                assert "skill_name" in columns
                assert "created_at" in columns

    @pytest.mark.asyncio
    async def test_trajectory_preferences_schema(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                cursor = await conn.execute("PRAGMA table_info(trajectory_preferences)")
                columns = {row[1]: row[2] for row in await cursor.fetchall()}
                assert "trajectory_id" in columns
                assert "rating" in columns
                assert "feedback" in columns
                assert "created_at" in columns

    @pytest.mark.asyncio
    async def test_trajectories_indexes(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='trajectories'"
                )
                indexes = [row[0] for row in await cursor.fetchall()]
                assert "idx_trajectories_success" in indexes
                assert "idx_trajectories_skill" in indexes
                assert "idx_trajectories_task" in indexes

    @pytest.mark.asyncio
    async def test_rating_constraint(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                await conn.execute(
                    "INSERT INTO trajectories (id, task, steps_json, success) VALUES ('t1', 'test', '[]', 1)"
                )
                await conn.execute(
                    "INSERT INTO trajectory_preferences (trajectory_id, rating) VALUES ('t1', 1)"
                )
                await conn.commit()

                with pytest.raises(aiosqlite.IntegrityError):
                    await conn.execute(
                        "INSERT INTO trajectory_preferences (trajectory_id, rating) VALUES ('t1', 99)"
                    )
                    await conn.commit()

    @pytest.mark.asyncio
    async def test_insert_and_select_trajectory(self, tmp_sediman_dir):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
            await init_db()
            async with get_connection() as conn:
                await conn.execute(
                    "INSERT INTO trajectories (id, task, steps_json, success, skill_name) VALUES (?, ?, ?, ?, ?)",
                    ("t1", "test task", '[]', 1, "test-skill"),
                )
                await conn.commit()

                cursor = await conn.execute("SELECT * FROM trajectories WHERE id = 't1'")
                row = await cursor.fetchone()
                assert row["task"] == "test task"
                assert row["success"] == 1
                assert row["skill_name"] == "test-skill"
