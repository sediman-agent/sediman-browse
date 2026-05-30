import { homedir } from "os"
import { join } from "path"

export function getDataDir(): string {
  return process.env.SEDIMAN_DATA_DIR || join(homedir(), ".sediman")
}

export const SKILLS_DIR = () => join(getDataDir(), "skills")
export const MEMORY_DIR = () => join(getDataDir(), "memories")
export const SESSIONS_DIR = () => join(getDataDir(), "sessions")
export const CRON_DIR = () => join(getDataDir(), "cron")
export const RECORDINGS_DIR = () => join(getDataDir(), "recordings")
export const AGENTS_DIR = () => join(getDataDir(), "agents")
export const BROWSER_PROFILE_DIR = () => join(getDataDir(), "browser-profile-cron")

export const SOUL_FILE = () => join(getDataDir(), "SOUL.md")
export const CONTEXT_FILE = () => join(getDataDir(), "CONTEXT.md")
export const AGENT_STATE_FILE = () => join(getDataDir(), "agent_state.json")
export const HISTORY_FILE = () => join(getDataDir(), "history")
export const SCREENSHOT_FILE = () => join(getDataDir(), "last_screenshot.png")
export const TRAJECTORIES_DIR = () => join(getDataDir(), "trajectories")

export const MEMORY_LIMIT = Number(process.env.SEDIMAN_MEMORY_LIMIT) || 2200
export const USER_LIMIT = Number(process.env.SEDIMAN_USER_LIMIT) || 1375
export const MAX_STRUCTURED_BYTES = Number(process.env.SEDIMAN_MAX_STRUCTURED_BYTES) || 50000
export const MAX_ENTRIES_PER_TYPE = Number(process.env.SEDIMAN_MAX_ENTRIES_PER_TYPE) || 50

export const MAX_TASK_LENGTH = 10000
export const MAX_NAME_LENGTH = 64
export const MAX_CRON_FIELDS = 5
export const MAX_RESULT_CHARS = Number(process.env.SEDIMAN_MAX_RESULT_CHARS) || 2000
export const MAX_RESULTS_PER_JOB = Number(process.env.SEDIMAN_MAX_RESULTS_PER_JOB) || 100
export const MAX_RECORDING_SECONDS = Number(process.env.SEDIMAN_MAX_RECORDING_SECONDS) || 300

export const COMPRESS_THRESHOLD = Number(process.env.SEDIMAN_COMPRESS_THRESHOLD) || 20
export const SKILL_STALE_DAYS = Number(process.env.SEDIMAN_SKILL_STALE_DAYS) || 30
export const MAX_NESTED_DEPTH = Number(process.env.SEDIMAN_MAX_NESTED_DEPTH) || 2

export const DEFAULT_HTTP_TIMEOUT = Number(process.env.SEDIMAN_HTTP_TIMEOUT) || 15.0
export const DEFAULT_WEB_MAX_CHARS = Number(process.env.SEDIMAN_WEB_MAX_CHARS) || 5000

export const CORS_ORIGINS = (
  process.env.SEDIMAN_CORS_ORIGINS || "http://localhost:3000,http://localhost:5173"
).split(",").map(s => s.trim()).filter(Boolean)

export const OPENBROWSER_HOST = process.env.SEDIMAN_OPENBROWSER_HOST || "127.0.0.1"
export const OPENBROWSER_PORT = Number(process.env.SEDIMAN_OPENBROWSER_PORT) || 7788
export const OPENBROWSER_JS = ["true", "1", "yes"].includes(
  (process.env.SEDIMAN_OPENBROWSER_JS || "true").toLowerCase()
)

export const PYTHON_SOCKET = process.env.SEDIMAN_PYTHON_SOCKET || "/tmp/sediman-python.sock"
export const MAIN_SOCKET = process.env.SEDIMAN_MAIN_SOCKET || "/tmp/sediman.sock"
