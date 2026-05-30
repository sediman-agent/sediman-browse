from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from sediman.agent.loop import StepEvent
from sediman.browser.session import BrowserSession
from sediman.llm.provider import create_provider, LLMProvider

logger = structlog.get_logger()

_sentry_initialized = False


def _init_sentry() -> None:
    global _sentry_initialized
    if _sentry_initialized:
        return
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        )
        _sentry_initialized = True
        logger.info("sentry_initialized")
    except ImportError:
        pass
    except Exception as e:
        logger.warning("sentry_init_failed", error=str(e))


def _capture_exception(exc: Exception) -> None:
    if not _sentry_initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


MAX_TASK_LENGTH = 10000
MAX_NAME_LENGTH = 64
MAX_CRON_FIELDS = 5
_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_CRON_FIELD_RE = re.compile(r"^[\d*/,-]+$")

_scheduler: Any = None
_task_store: dict[str, dict[str, Any]] = {}
_task_queue: asyncio.Queue | None = None
_queue_worker_started = False


class ErrorResponse(BaseModel):
    error: dict[str, Any]


def _make_error(code: str, message: str, suggestion: str | None = None, status: int = 500) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if suggestion:
        detail["suggestion"] = suggestion
    return HTTPException(status_code=status, detail=detail)


def _classify_error(exc: Exception) -> tuple[str, str, str | None]:
    from sediman.errors import classify_error
    info = classify_error(exc)
    return info.code, info.message, info.suggestion


def _setup_scheduler() -> Any:
    from sediman.scheduler.cron import CronScheduler

    sched = CronScheduler()
    sched.start()
    return sched


async def _run_scheduled_task(job: dict[str, Any]) -> None:
    from sediman.scheduler.cron import execute_cron_job
    try:
        await execute_cron_job(job)
        logger.info("scheduled_task_complete", job_id=job["id"])
    except Exception as e:
        logger.error("scheduled_task_failed", job_id=job["id"], error=str(e))


def reload_scheduler_jobs() -> None:
    global _scheduler
    if not isinstance(_scheduler, object) or not hasattr(_scheduler, "reload"):
        return
    _scheduler.reload()


async def _start_queue_worker() -> None:
    global _task_queue, _queue_worker_started
    if _queue_worker_started:
        return
    _task_queue = asyncio.Queue()
    _queue_worker_started = True
    asyncio.create_task(_queue_worker())


async def _queue_worker() -> None:
    global _task_queue
    while True:
        task_id = await _task_queue.get()
        entry = _task_store.get(task_id)
        if not entry:
            continue
        try:
            entry["status"] = "running"
            entry["started_at"] = time.time()
            agent = await _get_agent_loop()
            result = await agent.run(entry["task"])
            entry["status"] = "completed"
            entry["completed_at"] = time.time()
            entry["result"] = {
                "result": result.result,
                "skill_created": result.skill_created,
                "actions_count": len(result.actions_taken),
                "iterations": result.iterations,
                "strategy": result.strategy_used,
                "steps": [
                    {"step": e.step, "action": e.action, "observation": e.observation}
                    for e in result.steps
                ],
            }
        except Exception as e:
            code, message, suggestion = _classify_error(e)
            entry["status"] = "failed"
            entry["completed_at"] = time.time()
            entry["error"] = {"code": code, "message": message, "suggestion": suggestion}
        finally:
            _task_queue.task_done()


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _scheduler, _browser
    _init_sentry()
    try:
        _scheduler = _setup_scheduler()
    except Exception as e:
        logger.warning("scheduler_setup_failed", error=str(e))
    await _start_queue_worker()
    from sediman.integrations import setup_integrations
    setup_integrations()
    yield
    if _browser:
        try:
            await _browser.stop()
        except Exception as e:
            logger.warning("browser_shutdown_failed", error=str(e))
        _browser = None
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


app = FastAPI(title="Sediman Browse", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_browser: BrowserSession | None = None
_llm: LLMProvider | None = None
_agent_loop: Any = None
_llm_config: dict[str, Any] = {}


def init_state(provider: str = "openai", model: str | None = None, base_url: str | None = None, terminal: bool = False) -> None:
    global _llm_config
    _llm_config = {"provider": provider, "model": model, "base_url": base_url, "terminal": terminal}


def _get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = create_provider(
            provider=_llm_config["provider"],
            model=_llm_config.get("model"),
            base_url=_llm_config.get("base_url"),
        )
    return _llm


async def _get_browser() -> BrowserSession:
    global _browser
    if _browser is None:
        from sediman.config import STEALTH_ENABLED, STEALTH_PROXY

        _browser = BrowserSession(
            headless=False, stealth=STEALTH_ENABLED, proxy=STEALTH_PROXY or None
        )
        await _browser.start()
    return _browser


async def _get_agent_loop() -> Any:
    global _agent_loop
    if _agent_loop is None:
        from sediman.agent.loop import AgentLoop
        from sediman.agent.tools import set_terminal_allowed

        browser = await _get_browser()
        llm = _get_llm()
        _agent_loop = AgentLoop(llm_provider=llm, browser_session=browser)
        if _llm_config.get("terminal"):
            set_terminal_allowed(True)
    return _agent_loop


def _validate_skill_name(name: str) -> str:
    if not name or not _SAFE_NAME_RE.match(name) or len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": f"Invalid skill name: {name!r}"})
    return name


def _validate_cron(cron: str) -> str:
    parts = cron.strip().split()
    if len(parts) != MAX_CRON_FIELDS:
        raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": f"Cron must have {MAX_CRON_FIELDS} fields, got {len(parts)}"})
    for part in parts:
        if not _CRON_FIELD_RE.match(part):
            raise HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": f"Invalid cron field: {part!r}"})
    return cron


class TaskRequest(BaseModel):
    task: str

    @field_validator("task")
    @classmethod
    def validate_task(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task is required")
        if len(v) > MAX_TASK_LENGTH:
            raise ValueError(f"task must be {MAX_TASK_LENGTH} characters or less")
        return v


class SkillRequest(BaseModel):
    name: str


class ScheduleRequest(BaseModel):
    cron: str
    task: str
    skill: str | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != MAX_CRON_FIELDS:
            raise ValueError(f"Cron must have {MAX_CRON_FIELDS} fields")
        return v

    @field_validator("task")
    @classmethod
    def validate_task(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("task is required")
        if len(v) > MAX_TASK_LENGTH:
            raise ValueError(f"task must be {MAX_TASK_LENGTH} characters or less")
        return v


class HubInstallRequest(BaseModel):
    name: str
    force: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not _SAFE_NAME_RE.match(v) or len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Invalid skill name: {v!r}")
        return v


class MemoryAddRequest(BaseModel):
    target: str
    content: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if v not in ("memory", "user"):
            raise ValueError("target must be 'memory' or 'user'")
        return v


class MemoryReplaceRequest(BaseModel):
    target: str
    old_entry: str
    new_entry: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if v not in ("memory", "user"):
            raise ValueError("target must be 'memory' or 'user'")
        return v


class MemoryRemoveRequest(BaseModel):
    target: str
    entry: str

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        if v not in ("memory", "user"):
            raise ValueError("target must be 'memory' or 'user'")
        return v


class RecordStartRequest(BaseModel):
    name: str
    description: str | None = None
    fps: int = 3
    max_duration: int = 300

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not _SAFE_NAME_RE.match(v) or len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Invalid skill name: {v!r}")
        return v

    @field_validator("fps")
    @classmethod
    def validate_fps(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("fps must be between 1 and 10")
        return v

    @field_validator("max_duration")
    @classmethod
    def validate_max_duration(cls, v: int) -> int:
        if v < 10 or v > 3600:
            raise ValueError("max_duration must be between 10 and 3600 seconds")
        return v


@app.post("/api/task", response_model=None)
async def run_task(req: TaskRequest):
    from sediman.store.db import init_db
    await init_db()

    task_id = str(uuid.uuid4())
    _task_store[task_id] = {
        "task_id": task_id,
        "task": req.task,
        "status": "queued",
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }

    if _task_queue is None:
        await _start_queue_worker()

    await _task_queue.put(task_id)

    return {"task_id": task_id, "status": "queued"}


@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    entry = _task_store.get(task_id)
    if not entry:
        raise _make_error("NOT_FOUND", f"Task '{task_id}' not found.", "Check the task ID.", status=404)
    response: dict[str, Any] = {
        "task_id": entry["task_id"],
        "task": entry["task"],
        "status": entry["status"],
        "created_at": entry["created_at"],
    }
    if entry["started_at"]:
        response["started_at"] = entry["started_at"]
    if entry["completed_at"]:
        response["completed_at"] = entry["completed_at"]
        response["duration"] = entry["completed_at"] - (entry["started_at"] or entry["created_at"])
    if entry["result"]:
        response["result"] = entry["result"]
    if entry["error"]:
        response["error"] = entry["error"]
    return response


@app.get("/api/skills")
async def list_skills():
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    return {"skills": engine.list_skills()}


@app.get("/api/skills/{name}")
async def get_skill(name: str):
    _validate_skill_name(name)
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    skill = engine.read(name)
    if not skill:
        raise _make_error("NOT_FOUND", f"Skill '{name}' not found", status=404)
    return skill


@app.post("/api/skills/{name}/run", response_model=None)
async def run_skill(name: str, req: SkillRequest):
    _validate_skill_name(name)
    from sediman.skills.engine import SkillEngine
    from sediman.skills.executor import execute_skill
    from sediman.store.db import init_db
    await init_db()

    engine = SkillEngine()
    skill = engine.read(name)
    if not skill:
        raise _make_error("NOT_FOUND", f"Skill '{name}' not found", status=404)

    browser = await _get_browser()
    llm = _get_llm()

    try:
        result = await execute_skill(skill, browser, llm)
        return {"result": result}
    except Exception as e:
        code, message, suggestion = _classify_error(e)
        logger.error("skill_run_failed", error=str(e), exc_info=True)
        raise _make_error(code, message, suggestion)


@app.delete("/api/skills/{name}")
async def delete_skill(name: str):
    _validate_skill_name(name)
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    if engine.delete(name):
        return {"deleted": name}
    raise _make_error("NOT_FOUND", f"Skill '{name}' not found", status=404)


@app.get("/api/hub/browse")
async def hub_browse(category: str | None = None):
    from sediman.skills.hub import HubClient
    client = HubClient()
    skills = client.browse(category=category)
    return {"skills": [{"name": s.name, "description": s.description, "category": s.category, "trust": s.trust, "variables": s.variables} for s in skills]}


@app.get("/api/hub/search")
async def hub_search(q: str):
    from sediman.skills.hub import HubClient
    client = HubClient()
    skills = client.search(q)
    return {"skills": [{"name": s.name, "description": s.description, "category": s.category, "trust": s.trust} for s in skills]}


@app.get("/api/hub/{name}")
async def hub_info(name: str):
    from sediman.skills.hub import HubClient
    client = HubClient()
    info = client.info(name)
    if not info:
        raise _make_error("NOT_FOUND", f"Skill '{name}' not found in hub", status=404)
    return info


@app.post("/api/hub/install")
async def hub_install(req: HubInstallRequest):
    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import HubClient
    client = HubClient()
    engine = SkillEngine()
    ok, msg = client.install(req.name, engine, force=req.force)
    if ok:
        return {"installed": req.name, "message": msg}
    raise HTTPException(status_code=400, detail={"code": "INSTALL_ERROR", "message": msg})


@app.post("/api/skills/record/start")
async def start_recording(req: RecordStartRequest):
    from sediman.agent.recording_manager import RecordingManager

    browser = await _get_browser()
    manager = RecordingManager.get_instance()

    if manager.is_recording(req.name):
        raise _make_error("ALREADY_RECORDING", f"Already recording '{req.name}'.", "Stop the current recording first.", status=409)

    try:
        session = await manager.start_recording(
            name=req.name,
            browser=browser,
            description=req.description,
            fps=req.fps,
            max_duration=req.max_duration,
        )
        return {
            "session_id": session.id,
            "name": session.name,
            "status": "recording",
            "fps": req.fps,
            "max_duration": req.max_duration,
        }
    except Exception as e:
        raise _make_error("RECORD_START_FAILED", str(e))


@app.post("/api/skills/record/{session_id}/stop")
async def stop_recording(session_id: str):
    from sediman.agent.recording_manager import RecordingManager
    from sediman.agent.trace_to_skill import TraceToSkill
    from sediman.skills.engine import SkillEngine

    manager = RecordingManager.get_instance()
    session = manager.get_session(session_id)
    if not session:
        raise _make_error("NOT_FOUND", f"Recording session '{session_id}' not found.", status=404)

    try:
        recording = await manager.stop_by_session_id(session_id)
    except ValueError as e:
        raise _make_error("NOT_RECORDING", str(e), status=409)

    try:
        llm = _get_llm()
        converter = TraceToSkill(llm)
        skill_data = await converter.convert(recording)
    except Exception as e:
        manager.cleanup(recording.name)
        raise _make_error("ANALYSIS_FAILED", f"Failed to analyze recording: {e}")

    if not skill_data:
        manager.cleanup(recording.name)
        return {
            "status": "analyzed",
            "frames": recording.frame_count,
            "duration": recording.duration_seconds,
            "actions": len(recording.actions),
            "skill": None,
            "message": "Could not extract a skill from this recording. It may be too short or the task too simple.",
        }

    engine = SkillEngine()
    existing = engine.read(skill_data["skill_name"])
    if existing:
        engine.patch(skill_data["skill_name"], {
            "description": skill_data["description"],
            "steps": skill_data["steps"],
            "when_to_use": skill_data.get("when_to_use"),
            "pitfalls": skill_data.get("pitfalls", []),
            "verification": skill_data.get("verification"),
        })
    else:
        engine.create(
            name=skill_data["skill_name"],
            description=skill_data["description"],
            steps=skill_data["steps"],
            category=skill_data.get("category", "recorded"),
            when_to_use=skill_data.get("when_to_use"),
            pitfalls=skill_data.get("pitfalls", []),
            verification=skill_data.get("verification"),
        )

    manager.cleanup(recording.name)

    return {
        "status": "skill_created",
        "frames": recording.frame_count,
        "duration": recording.duration_seconds,
        "actions": len(recording.actions),
        "skill": skill_data,
        "message": f"Skill '{skill_data['skill_name']}' created with {len(skill_data['steps'])} steps.",
    }


@app.get("/api/skills/record/active")
async def get_active_recordings():
    from sediman.agent.recording_manager import RecordingManager

    manager = RecordingManager.get_instance()
    active = manager.get_active_sessions()
    return {
        "recordings": [
            {
                "session_id": s.id,
                "name": s.name,
                "started_at": s.started_at,
                "frame_count": s.frame_count,
                "duration_seconds": s.duration_seconds,
                "action_count": len(s.actions),
            }
            for s in active
        ],
    }


@app.websocket("/ws/record/{session_id}")
async def ws_record(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info("ws_record_connected", session_id=session_id)

    from sediman.agent.recording_manager import RecordingManager

    manager = RecordingManager.get_instance()
    session = manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "error", "error": {"code": "NOT_FOUND", "message": f"Session '{session_id}' not found."}})
        await websocket.close()
        return

    recorder = manager.get_recorder(session.name)
    if not recorder or not recorder.is_recording:
        await websocket.send_json({"type": "error", "error": {"code": "NOT_RECORDING", "message": "Session is not actively recording."}})
        await websocket.close()
        return

    last_frame_count = 0

    try:
        while True:
            current = manager.get_session(session_id)
            if not current:
                break

            if current.frame_count > last_frame_count:
                new_frames = current.frames[last_frame_count:]
                for frame in new_frames:
                    await websocket.send_json({
                        "type": "frame",
                        "timestamp": frame.timestamp,
                        "url": frame.url,
                        "cursor_x": frame.cursor_x,
                        "cursor_y": frame.cursor_y,
                        "action": frame.action,
                        "action_detail": frame.action_detail,
                        "screenshot": frame.screenshot_b64,
                        "frame_number": last_frame_count,
                    })
                last_frame_count = current.frame_count

            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if msg == "stop":
                    break
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.info("ws_record_disconnected", session_id=session_id)
    except Exception as e:
        logger.debug("ws_record_error", error=str(e))


@app.get("/api/schedule")
async def list_schedule():
    from sediman.scheduler.cron import CronManager
    cron = CronManager()
    return {"jobs": cron.list_jobs()}


@app.post("/api/schedule")
async def add_schedule(req: ScheduleRequest):
    _validate_cron(req.cron)
    from sediman.scheduler.cron import CronManager
    cron = CronManager()
    job_id = cron.add_job(
        cron_expr=req.cron,
        task=req.task,
        skill_name=req.skill,
        provider=_llm_config.get("provider", "openai"),
        model=_llm_config.get("model"),
        base_url=_llm_config.get("base_url"),
    )
    reload_scheduler_jobs()
    return {"job_id": job_id, "cron": req.cron, "task": req.task}


@app.delete("/api/schedule/{job_id}")
async def remove_schedule(job_id: str):
    from sediman.scheduler.cron import CronManager
    cron = CronManager()
    if cron.remove_job(job_id):
        reload_scheduler_jobs()
        return {"removed": job_id}
    raise _make_error("NOT_FOUND", f"Job '{job_id}' not found", status=404)


@app.get("/api/memory")
async def get_memory():
    from sediman.memory.store import MemoryStore
    store = MemoryStore()
    all_entries = store.get_all_entries()
    mem_usage = store.get_usage("memory")
    user_usage = store.get_usage("user")
    return {
        "entries": all_entries,
        "usage": {
            "memory": {"chars": mem_usage.chars, "limit": mem_usage.limit, "pct": mem_usage.pct},
            "user": {"chars": user_usage.chars, "limit": user_usage.limit, "pct": user_usage.pct},
        },
    }


@app.post("/api/memory/add")
async def add_memory(req: MemoryAddRequest):
    from sediman.memory.store import MemoryStore
    store = MemoryStore()
    result = store.add_or_consolidate(req.target, req.content)
    if not result.success:
        raise _make_error("MEMORY_ERROR", result.message)
    return {
        "success": True,
        "message": result.message,
        "entries": result.entries,
        "usage": (
            {"chars": result.usage.chars, "limit": result.usage.limit, "pct": result.usage.pct}
            if result.usage else None
        ),
    }


@app.post("/api/memory/replace")
async def replace_memory(req: MemoryReplaceRequest):
    from sediman.memory.store import MemoryStore
    store = MemoryStore()
    result = store.replace(req.target, req.old_entry, req.new_entry)
    if not result.success:
        raise _make_error("MEMORY_ERROR", result.message)
    return {
        "success": True,
        "message": result.message,
        "entries": result.entries,
        "usage": (
            {"chars": result.usage.chars, "limit": result.usage.limit, "pct": result.usage.pct}
            if result.usage else None
        ),
    }


@app.post("/api/memory/remove")
async def remove_memory(req: MemoryRemoveRequest):
    from sediman.memory.store import MemoryStore
    store = MemoryStore()
    result = store.remove(req.target, req.entry)
    if not result.success:
        raise _make_error("MEMORY_ERROR", result.message)
    return {
        "success": True,
        "message": result.message,
        "entries": result.entries,
        "usage": (
            {"chars": result.usage.chars, "limit": result.usage.limit, "pct": result.usage.pct}
            if result.usage else None
        ),
    }


@app.get("/api/sessions")
async def list_sessions():
    from sediman.memory.sessions import get_recent_sessions
    from sediman.store.db import init_db
    await init_db()
    sessions = await get_recent_sessions()
    return {"sessions": sessions}


@app.get("/api/screenshot")
async def get_screenshot():
    browser = await _get_browser()
    b64 = await browser.take_screenshot()
    if b64:
        return {"screenshot": b64}
    raise _make_error("NO_BROWSER", "No browser page available", "Start a task first.", status=503)


@app.get("/api/status")
async def get_status():
    from sediman.scheduler.cron import CronManager

    current_task = None
    for entry in _task_store.values():
        if entry["status"] in ("queued", "running"):
            current_task = {
                "task_id": entry["task_id"],
                "task": entry["task"],
                "status": entry["status"],
            }
            break

    cron = CronManager()
    jobs = cron.list_jobs()
    active_jobs = [j for j in jobs if j.get("enabled", True)]

    agent = _agent_loop
    conv_len = len(agent._conversation) if agent else 0

    last_result = None
    for entry in reversed(list(_task_store.values())):
        if entry["status"] == "completed" and entry.get("result"):
            last_result = {
                "task_id": entry["task_id"],
                "task": entry["task"],
                "result": entry["result"]["result"][:200] if entry["result"].get("result") else None,
            }
            break

    return {
        "browser_open": _browser is not None and _browser.is_started,
        "model": _llm_config.get("model"),
        "provider": _llm_config.get("provider"),
        "conversation_messages": conv_len,
        "current_task": current_task,
        "scheduler": {
            "active_jobs": len(active_jobs),
            "total_jobs": len(jobs),
        },
        "last_result": last_result,
        "queue_size": _task_queue.qsize() if _task_queue else 0,
    }


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("ws_chat_connected")

    from sediman.store.db import init_db
    await init_db()

    agent = await _get_agent_loop()

    try:
        history = []
        for msg in agent._conversation:
            history.append(msg)
        if history:
            await websocket.send_json({"type": "history", "messages": history})

        while True:
            data = await websocket.receive_text()
            import json
            msg = json.loads(data)
            task = msg.get("task", "")

            if not task:
                await websocket.send_json({"type": "error", "error": {"code": "VALIDATION", "message": "No task provided"}})
                continue

            await websocket.send_json({
                "type": "status",
                "message": "Planning...",
                "phase": "planning",
                "timestamp": time.time(),
            })

            start_time = time.time()

            def on_step_streaming(event: StepEvent) -> None:
                try:
                    asyncio.get_event_loop().create_task(
                        websocket.send_json({
                            "type": "progress",
                            "step": event.step,
                            "action": event.action,
                            "observation": event.observation,
                            "phase": "executing",
                            "elapsed": round(time.time() - start_time, 1),
                            "timestamp": time.time(),
                        })
                    )
                except Exception:
                    pass

            original_on_step = agent.on_step
            agent.on_step = on_step_streaming

            try:
                result = await agent.run(task)
                agent.on_step = original_on_step

                await websocket.send_json({
                    "type": "result",
                    "result": result.result,
                    "skill_created": result.skill_created,
                    "actions_count": len(result.actions_taken),
                    "iterations": result.iterations,
                    "strategy": result.strategy_used,
                    "elapsed": round(time.time() - start_time, 1),
                    "timestamp": time.time(),
                    "steps": [
                        {"step": e.step, "action": e.action, "observation": e.observation}
                        for e in result.steps
                    ],
                })
            except Exception as e:
                agent.on_step = original_on_step
                code, message, suggestion = _classify_error(e)
                await websocket.send_json({
                    "type": "error",
                    "error": {"code": code, "message": message, "suggestion": suggestion},
                })

    except WebSocketDisconnect:
        logger.info("ws_chat_disconnected")


@app.websocket("/ws/viewport")
async def ws_viewport(websocket: WebSocket):
    await websocket.accept()
    logger.info("ws_viewport_connected")

    last_screenshot = None

    try:
        while True:
            browser = await _get_browser()
            b64 = await browser.take_screenshot()
            if b64 and b64 != last_screenshot:
                await websocket.send_json({"type": "screenshot", "data": b64, "timestamp": time.time()})
                last_screenshot = b64

            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if msg == "stop":
                    break
            except asyncio.TimeoutError:
                continue

    except WebSocketDisconnect:
        logger.info("ws_viewport_disconnected")


# ── Integration Endpoints ──────────────────────────────────────────


@app.get("/api/integrations")
async def list_integrations():
    from sediman.integrations import list_integrations
    return {"integrations": list_integrations()}


@app.post("/api/integrations/{name}/configure")
async def configure_integration(name: str, req: dict):
    from sediman.integrations import update_config
    try:
        result = update_config(name, req)
        return {"integration": name, "config": result}
    except ValueError as e:
        raise _make_error("INVALID_CONFIG", str(e), status=400)


@app.post("/api/integrations/{name}/send")
async def send_integration_message(name: str, req: dict):
    target = req.get("target", "")
    content = req.get("content", "")
    if not target or not content:
        raise _make_error("VALIDATION", "target and content are required", status=400)
    from sediman.integrations import send_message
    try:
        result = await send_message(name, target, content)
        return {"result": result}
    except ValueError as e:
        raise _make_error("INTEGRATION_ERROR", str(e), status=400)


@app.get("/api/integrations/{name}/status")
async def integration_status(name: str):
    from sediman.integrations import get_integration, get_config
    config = get_config().get(name, {})
    inst = get_integration(name)
    return {
        "name": name,
        "enabled": config.get("enabled", False),
        "configured": bool(config.get("token")),
        "connected": inst is not None and inst.enabled,
    }
