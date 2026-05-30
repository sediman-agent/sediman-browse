from __future__ import annotations

import asyncio
import aiosqlite
import structlog
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

logger = structlog.get_logger()

DEFAULT_DATA_DIR = Path.home() / ".sediman"
DB_NAME = "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    steps_json TEXT NOT NULL DEFAULT '[]',
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    action TEXT NOT NULL,
    observation TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trajectories (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    steps_json TEXT NOT NULL DEFAULT '[]',
    result TEXT,
    success INTEGER NOT NULL DEFAULT 0,
    skill_name TEXT,
    error_type TEXT,
    duration_ms INTEGER,
    screenshot_dir TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trajectory_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trajectory_id TEXT NOT NULL REFERENCES trajectories(id),
    rating INTEGER NOT NULL CHECK(rating >= -1 AND rating <= 1),
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trajectories_success ON trajectories(success);
CREATE INDEX IF NOT EXISTS idx_trajectories_skill ON trajectories(skill_name);
CREATE INDEX IF NOT EXISTS idx_trajectories_task ON trajectories(task);
CREATE INDEX IF NOT EXISTS idx_trajectories_created ON trajectories(created_at);
CREATE INDEX IF NOT EXISTS idx_traj_prefs_traj ON trajectory_preferences(trajectory_id);

CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    id, task, result,
    content=sessions,
    content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, id, task, result)
    VALUES (new.rowid, new.id, new.task, new.result);
END;

CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, id, task, result)
    VALUES ('delete', old.rowid, old.id, old.task, old.result);
END;

CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, id, task, result)
    VALUES ('delete', old.rowid, old.id, old.task, old.result);
    INSERT INTO sessions_fts(rowid, id, task, result)
    VALUES (new.rowid, new.id, new.task, new.result);
END;
"""

_PERF_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-32000",
    "PRAGMA busy_timeout=5000",
    "PRAGMA foreign_keys=ON",
]

_POOL_SIZE = 3
_pool: list[aiosqlite.Connection] = []
_pool_lock = asyncio.Lock()
_pool_initialized = False


async def _init_pool() -> None:
    global _pool_initialized
    if _pool_initialized:
        return
    _pool_initialized = True


async def _create_conn() -> aiosqlite.Connection:
    db_path = get_db_path()
    conn = await aiosqlite.connect(db_path, timeout=10)
    conn.row_factory = aiosqlite.Row
    for pragma in _PERF_PRAGMAS:
        try:
            await conn.execute(pragma)
        except Exception:
            pass
    return conn


async def acquire() -> aiosqlite.Connection:
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    await _init_pool()
    async with _pool_lock:
        while _pool:
            conn = _pool.pop()
            try:
                await conn.execute("SELECT 1")
            except Exception:
                try:
                    await conn.close()
                except Exception:
                    pass
                continue
            return conn

        return await _create_conn()


async def release(conn: aiosqlite.Connection) -> None:
    async with _pool_lock:
        if len(_pool) < _POOL_SIZE:
            _pool.append(conn)
        else:
            try:
                await conn.close()
            except Exception:
                pass


@asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    conn = await acquire()
    try:
        yield conn
    finally:
        await release(conn)


async def init_db() -> None:
    await _init_pool()
    async with get_connection() as conn:
        await conn.executescript(_SCHEMA)


def get_db_path() -> Path:
    return DEFAULT_DATA_DIR / DB_NAME
