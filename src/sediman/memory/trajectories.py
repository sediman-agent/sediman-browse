from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

from sediman.config import TRAJECTORIES_DIR
from sediman.memory.vector import VectorStore
from sediman.store.db import get_connection, get_db_path

logger = structlog.get_logger()


@dataclass
class TrajectoryStep:
    action: str
    observation: str | None = None
    screenshot_path: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class Trajectory:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: str = ""
    steps: list[TrajectoryStep] = field(default_factory=list)
    result: str | None = None
    success: bool = False
    skill_name: str | None = None
    error_type: str | None = None
    duration_ms: int | None = None
    screenshot_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TrajectoryDB:
    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or get_db_path()
        self._vector_store: VectorStore | None = None

    def _get_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = VectorStore()
        return self._vector_store

    async def save(self, traj: Trajectory) -> str:
        TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)
        async with get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO trajectories
                   (id, task, steps_json, result, success, skill_name,
                    error_type, duration_ms, screenshot_dir, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    traj.id,
                    traj.task,
                    json.dumps([asdict(s) for s in traj.steps], default=str),
                    traj.result,
                    1 if traj.success else 0,
                    traj.skill_name,
                    traj.error_type,
                    traj.duration_ms,
                    traj.screenshot_dir,
                    json.dumps(traj.metadata, default=str),
                ),
            )
            await db.commit()
        await self._async_index_trajectory(traj)
        logger.debug("trajectory_saved", id=traj.id, task=traj.task[:60])
        return traj.id

    def _index_trajectory(self, traj: Trajectory) -> None:
        try:
            vs = self._get_vector_store()
            summary = traj.result or traj.task
            if len(summary) > 300:
                summary = summary[:300]
            text = f"{traj.task}\n{summary}"
            vs.add(text, metadata={
                "trajectory_id": traj.id,
                "task": traj.task[:120],
                "success": traj.success,
                "skill_name": traj.skill_name,
            })
        except Exception as e:
            logger.debug("trajectory_index_failed", id=traj.id, error=str(e))

    async def _async_index_trajectory(self, traj: Trajectory) -> None:
        try:
            vs = self._get_vector_store()
            summary = traj.result or traj.task
            if len(summary) > 300:
                summary = summary[:300]
            text = f"{traj.task}\n{summary}"
            await vs.async_add(text, metadata={
                "trajectory_id": traj.id,
                "task": traj.task[:120],
                "success": traj.success,
                "skill_name": traj.skill_name,
            })
        except Exception as e:
            logger.debug("trajectory_index_failed", id=traj.id, error=str(e))

    async def get(self, traj_id: str) -> Trajectory | None:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM trajectories WHERE id = ?", (traj_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_traj(row)

    async def query_similar_tasks(
        self,
        task_query: str,
        limit: int = 10,
        min_success_rate: float = 0.0,
    ) -> list[Trajectory]:
        trajectory_ids = await self._semantic_search_tasks(task_query, limit * 2)
        if trajectory_ids:
            return await self._fetch_trajectories_by_ids(
                trajectory_ids, limit, min_success_rate,
            )
        return await self._sql_search_tasks(task_query, limit, min_success_rate)

    async def _semantic_search_tasks(
        self, query: str, max_results: int,
    ) -> list[str]:
        try:
            vs = self._get_vector_store()
            results = await vs.async_search(query, k=max_results, threshold=0.25)
            return [
                r["metadata"]["trajectory_id"]
                for r in results
                if r.get("metadata", {}).get("trajectory_id")
            ]
        except Exception as e:
            logger.debug("semantic_trajectory_search_failed", error=str(e))
            return []

    async def _fetch_trajectories_by_ids(
        self,
        ids: list[str],
        limit: int,
        min_success_rate: float,
    ) -> list[Trajectory]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                f"""SELECT * FROM trajectories
                WHERE id IN ({placeholders})
                AND (success = 1 OR success = ?)
                ORDER BY created_at DESC
                LIMIT ?""",
                (*ids, 1 if min_success_rate > 0 else 0, limit),
            )
            return [self._row_to_traj(r) for r in rows]

    async def _sql_search_tasks(
        self,
        task_query: str,
        limit: int,
        min_success_rate: float,
    ) -> list[Trajectory]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                """SELECT *, (SELECT AVG(rating) FROM trajectory_preferences
                    WHERE trajectory_id = t.id) as avg_rating
                FROM trajectories t
                WHERE t.task LIKE ? AND (t.success = 1 OR t.success = ?)
                ORDER BY t.created_at DESC
                LIMIT ?""",
                (f"%{task_query}%", 1 if min_success_rate > 0 else 0, limit),
            )
            return [self._row_to_traj(r) for r in rows]

    async def get_recent_failures(
        self,
        limit: int = 10,
        skill_name: str | None = None,
    ) -> list[Trajectory]:
        async with get_connection() as db:
            if skill_name:
                rows = await db.execute_fetchall(
                    """SELECT * FROM trajectories
                    WHERE success = 0 AND skill_name = ?
                    ORDER BY created_at DESC LIMIT ?""",
                    (skill_name, limit),
                )
            else:
                rows = await db.execute_fetchall(
                    """SELECT * FROM trajectories
                    WHERE success = 0
                    ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                )
            return [self._row_to_traj(r) for r in rows]

    async def get_related_trajectories(
        self,
        skill_name: str,
        limit: int = 20,
    ) -> list[Trajectory]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                """SELECT * FROM trajectories
                WHERE skill_name = ?
                ORDER BY created_at DESC LIMIT ?""",
                (skill_name, limit),
            )
            return [self._row_to_traj(r) for r in rows]

    async def rate_trajectory(
        self,
        traj_id: str,
        rating: int,
        feedback: str | None = None,
    ) -> None:
        if rating not in (-1, 0, 1):
            raise ValueError("Rating must be -1, 0, or 1")
        async with get_connection() as db:
            await db.execute(
                """INSERT INTO trajectory_preferences (trajectory_id, rating, feedback)
                   VALUES (?, ?, ?)""",
                (traj_id, rating, feedback),
            )
            await db.commit()
        logger.info("trajectory_rated", id=traj_id, rating=rating)

    async def get_skill_success_rate(self, skill_name: str) -> float:
        async with get_connection() as db:
            cursor = await db.execute(
                """SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as passed
                FROM trajectories WHERE skill_name = ?""",
                (skill_name,),
            )
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                return 0.0
            return row[1] / row[0]

    async def get_top_skills_by_preference(
        self,
        min_trajectories: int = 3,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                """SELECT
                    t.skill_name,
                    COUNT(*) as traj_count,
                    AVG(CASE WHEN t.success THEN 1.0 ELSE 0.0 END) as success_rate,
                    AVG(p.rating) as avg_preference
                FROM trajectories t
                LEFT JOIN trajectory_preferences p ON p.trajectory_id = t.id
                WHERE t.skill_name IS NOT NULL
                GROUP BY t.skill_name
                HAVING traj_count >= ?
                ORDER BY avg_preference DESC, success_rate DESC
                LIMIT ?""",
                (min_trajectories, limit),
            )
            return [dict(r) for r in rows]

    async def get_unrated_trajectories(
        self,
        limit: int = 10,
    ) -> list[Trajectory]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                """SELECT * FROM trajectories t
                WHERE NOT EXISTS (
                    SELECT 1 FROM trajectory_preferences p
                    WHERE p.trajectory_id = t.id
                )
                ORDER BY t.created_at DESC LIMIT ?""",
                (limit,),
            )
            return [self._row_to_traj(r) for r in rows]

    async def _ensure_trajectory_dir(self, traj_id: str) -> Path:
        path = TRAJECTORIES_DIR / traj_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_screenshot(
        self, traj_id: str, step_index: int, screenshot_data: bytes
    ) -> str:
        directory = await self._ensure_trajectory_dir(traj_id)
        path = directory / f"step_{step_index}.png"
        path.write_bytes(screenshot_data)
        return str(path)

    @staticmethod
    def _row_to_traj(row: Any) -> Trajectory:
        if hasattr(row, "keys"):
            row = {k: row[k] for k in row.keys()}
        steps_raw = row["steps_json"]
        steps = []
        if steps_raw:
            try:
                step_dicts = json.loads(steps_raw) if isinstance(steps_raw, str) else steps_raw
                for s in step_dicts:
                    if isinstance(s, dict):
                        steps.append(TrajectoryStep(**s))
            except (json.JSONDecodeError, TypeError):
                pass

        meta = {}
        meta_raw = row.get("metadata_json")
        if meta_raw:
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            except (json.JSONDecodeError, TypeError):
                pass

        return Trajectory(
            id=row["id"],
            task=row["task"],
            steps=steps,
            result=row.get("result"),
            success=bool(row["success"]),
            skill_name=row.get("skill_name"),
            error_type=row.get("error_type"),
            duration_ms=row.get("duration_ms"),
            screenshot_dir=row.get("screenshot_dir"),
            metadata=meta if isinstance(meta, dict) else {},
            created_at=row.get("created_at", ""),
        )


def make_trajectory(
    task: str,
    actions: list[dict[str, Any]],
    result: str | None = None,
    success: bool = True,
    skill_name: str | None = None,
    error_type: str | None = None,
    duration_ms: int | None = None,
    screenshots: list[str | None] | None = None,
) -> Trajectory:
    steps: list[TrajectoryStep] = []
    for i, action in enumerate(actions):
        screenshot_path = None
        if screenshots and i < len(screenshots):
            screenshot_path = screenshots[i]
        steps.append(TrajectoryStep(
            action=action.get("action", str(action)),
            observation=action.get("observation", action.get("result")),
            screenshot_path=screenshot_path,
            duration_ms=action.get("duration_ms"),
            error=action.get("error"),
        ))

    return Trajectory(
        task=task,
        steps=steps,
        result=result,
        success=success,
        skill_name=skill_name,
        error_type=error_type,
        duration_ms=duration_ms,
    )
