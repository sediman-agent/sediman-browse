from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from sediman.store.db import get_connection as _get_conn

logger = structlog.get_logger()


async def save_session(
    task: str,
    steps: list[dict[str, Any]],
    result: str | None = None,
) -> str:
    session_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    async with _get_conn() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, task, steps_json, result, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, task, json.dumps(steps), result, now),
        )
        for step in steps:
            await conn.execute(
                "INSERT INTO session_steps (session_id, action, observation, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, step.get("action", ""), step.get("observation", ""), now),
            )
        await conn.commit()
    logger.info("session_saved", session_id=session_id)
    return session_id


async def search_sessions(query: str, limit: int = 5) -> list[dict[str, Any]]:
    async with _get_conn() as conn:
        cursor = await conn.execute(
            """
            SELECT s.id, s.task, s.result, s.created_at
            FROM sessions s
            JOIN sessions_fts f ON s.id = f.id
            WHERE sessions_fts MATCH ?
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (query, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_recent_sessions(limit: int = 10) -> list[dict[str, Any]]:
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT id, task, result, created_at FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT id, task, steps_json, result, created_at FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        steps_json = data.pop("steps_json", "[]")
        try:
            data["steps"] = json.loads(steps_json)
        except (json.JSONDecodeError, TypeError):
            data["steps"] = []
        return data
