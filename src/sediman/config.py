from __future__ import annotations

import os
from pathlib import Path


def _get_data_dir() -> Path:
    env = os.environ.get("SEDIMAN_DATA_DIR")
    if env:
        return Path(env)
    return Path.home() / ".sediman"


DATA_DIR = _get_data_dir()

SKILLS_DIR = DATA_DIR / "skills"
MEMORY_DIR = DATA_DIR / "memories"
SESSIONS_DIR = DATA_DIR / "sessions"
CRON_DIR = DATA_DIR / "cron"
RECORDINGS_DIR = DATA_DIR / "recordings"
AGENTS_DIR = DATA_DIR / "agents"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile-cron"

SOUL_FILE = DATA_DIR / "SOUL.md"
CONTEXT_FILE = DATA_DIR / "CONTEXT.md"
AGENT_STATE_FILE = DATA_DIR / "agent_state.json"
HISTORY_FILE = DATA_DIR / "history"
SCREENSHOT_FILE = DATA_DIR / "last_screenshot.png"
TRAJECTORIES_DIR = DATA_DIR / "trajectories"

OLD_MEMORY_FILE = DATA_DIR / "MEMORY.md"
OLD_USER_FILE = DATA_DIR / "USER.md"
OLD_MEMORY_DB = DATA_DIR / "memory.json"

MEMORY_LIMIT = int(os.environ.get("SEDIMAN_MEMORY_LIMIT", "2200"))
USER_LIMIT = int(os.environ.get("SEDIMAN_USER_LIMIT", "1375"))
MAX_STRUCTURED_BYTES = int(os.environ.get("SEDIMAN_MAX_STRUCTURED_BYTES", "50000"))
MAX_ENTRIES_PER_TYPE = int(os.environ.get("SEDIMAN_MAX_ENTRIES_PER_TYPE", "50"))

MAX_TASK_LENGTH = 10000
MAX_NAME_LENGTH = 64
MAX_CRON_FIELDS = 5
MAX_RESULT_CHARS = int(os.environ.get("SEDIMAN_MAX_RESULT_CHARS", "2000"))
MAX_RESULTS_PER_JOB = int(os.environ.get("SEDIMAN_MAX_RESULTS_PER_JOB", "100"))
MAX_RECORDING_SECONDS = int(os.environ.get("SEDIMAN_MAX_RECORDING_SECONDS", "300"))

COMPRESS_THRESHOLD = int(os.environ.get("SEDIMAN_COMPRESS_THRESHOLD", "20"))
SKILL_STALE_DAYS = int(os.environ.get("SEDIMAN_SKILL_STALE_DAYS", "30"))
MAX_NESTED_DEPTH = int(os.environ.get("SEDIMAN_MAX_NESTED_DEPTH", "2"))

DEFAULT_HTTP_TIMEOUT = float(os.environ.get("SEDIMAN_HTTP_TIMEOUT", "15.0"))
DEFAULT_WEB_MAX_CHARS = int(os.environ.get("SEDIMAN_WEB_MAX_CHARS", "5000"))

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "SEDIMAN_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if o.strip()
]

OPENBROWSER_HOST = os.environ.get("SEDIMAN_OPENBROWSER_HOST", "127.0.0.1")
OPENBROWSER_PORT = int(os.environ.get("SEDIMAN_OPENBROWSER_PORT", "7788"))
OPENBROWSER_JS = os.environ.get("SEDIMAN_OPENBROWSER_JS", "true").lower() in ("true", "1", "yes")
