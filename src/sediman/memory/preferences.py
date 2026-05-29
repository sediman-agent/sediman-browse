from __future__ import annotations

from typing import Any

import structlog

from sediman.memory.trajectories import TrajectoryDB
from sediman.skills.engine import SkillEngine

logger = structlog.get_logger()

_MIN_TRAJECTORIES_FOR_REVIEW = 3
_MIN_PREFERENCE_SCORE = -0.5
_PRUNE_THRESHOLD = -1.0


class PreferenceLearner:
    """Aggregates user ratings, tunes skill ranking, and prunes low-rated skills.

    DPO-inspired approach:
    - Track which skills get positive vs negative ratings
    - Use rating distribution to adjust skill selection priority
    - Periodically prune skills with consistently poor ratings
    """

    def __init__(self, traj_db: TrajectoryDB | None = None, engine: SkillEngine | None = None):
        self._db = traj_db or TrajectoryDB()
        self._engine = engine or SkillEngine()

    async def aggregate_preferences(self) -> dict[str, Any]:
        scores = await self._db.get_top_skills_by_preference(
            min_trajectories=_MIN_TRAJECTORIES_FOR_REVIEW
        )
        return {
            "total_skills_rated": len(scores),
            "skill_scores": scores,
        }

    async def get_skill_ranking(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._db.get_top_skills_by_preference(
            min_trajectories=_MIN_TRAJECTORIES_FOR_REVIEW,
            limit=limit,
        )

    async def get_skills_needing_review(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:
        unrated = await self._db.get_unrated_trajectories(limit=limit)
        return [
            {
                "trajectory_id": t.id,
                "task": t.task,
                "success": t.success,
                "skill_name": t.skill_name,
                "created_at": t.created_at,
            }
            for t in unrated
        ]

    async def prune_low_rated_skills(
        self, dry_run: bool = True
    ) -> list[dict[str, Any]]:
        scores = await self._db.get_top_skills_by_preference(
            min_trajectories=2
        )
        to_prune = []
        for score in scores:
            avg_pref = score.get("avg_preference", 0)
            if avg_pref is not None and avg_pref <= _PRUNE_THRESHOLD:
                skill_name = score["skill_name"]
                to_prune.append({
                    "skill_name": skill_name,
                    "avg_preference": avg_pref,
                    "trajectory_count": score.get("traj_count", 0),
                    "success_rate": score.get("success_rate", 0),
                })
                if not dry_run:
                    try:
                        self._engine.delete(skill_name)
                        logger.info(
                            "skill_pruned",
                            name=skill_name,
                            avg_preference=avg_pref,
                        )
                    except Exception as e:
                        logger.warning(
                            "skill_prune_failed",
                            name=skill_name,
                            error=str(e),
                        )

        if dry_run:
            logger.info(
                "prune_dry_run",
                candidates=len(to_prune),
                would_remove=[t["skill_name"] for t in to_prune],
            )
        else:
            logger.info("prune_executed", removed=len(to_prune))

        return to_prune

    async def record_feedback(
        self,
        trajectory_id: str,
        rating: int,
        feedback: str | None = None,
    ) -> None:
        await self._db.rate_trajectory(trajectory_id, rating, feedback)

    async def tune_preferences(
        self,
        skill_scores: list[dict[str, Any]] | None = None,
    ) -> None:
        if skill_scores is None:
            skill_scores = await self._db.get_top_skills_by_preference(
                min_trajectories=_MIN_TRAJECTORIES_FOR_REVIEW
            )

        for s in skill_scores:
            skill_name = s["skill_name"]
            avg_pref = s.get("avg_preference", 0)
            success_rate = s.get("success_rate", 0)

            if avg_pref is None:
                continue

            skill = self._engine.read(skill_name)
            if not skill:
                continue

            if avg_pref < _MIN_PREFERENCE_SCORE:
                logger.warning(
                    "skill_low_preference",
                    name=skill_name,
                    avg_preference=avg_pref,
                    success_rate=success_rate,
                )

            if avg_pref > 0.5:
                logger.info(
                    "skill_high_preference",
                    name=skill_name,
                    avg_preference=avg_pref,
                    success_rate=success_rate,
                )

    async def get_preference_summary(self) -> dict[str, Any]:
        scores = await self._db.get_top_skills_by_preference(
            min_trajectories=1
        )
        total_preferences = sum(
            1 for s in scores if s.get("avg_preference") is not None
        )

        return {
            "total_skills_with_preferences": total_preferences,
            "total_tracked_skills": len(scores),
            "highly_rated": [
                s
                for s in scores
                if s.get("avg_preference") is not None and s["avg_preference"] > 0.5
            ],
            "low_rated": [
                s
                for s in scores
                if s.get("avg_preference") is not None and s["avg_preference"] < _MIN_PREFERENCE_SCORE
            ],
            "pending_review": await self.get_skills_needing_review(limit=5),
        }
