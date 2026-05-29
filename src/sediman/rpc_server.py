"""Unix socket JSON-RPC 2.0 server for the Python backend.

Called by the TS RPC server via callPython() in proxy.ts.
Provides agent.run, system.*, skills.run, model.*, terminal.*, record.* handlers.

Usage:
    python -m sediman.rpc_server
    SEDIMAN_PYTHON_SOCKET=/tmp/my-python.sock python -m sediman.rpc_server
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import traceback
from typing import Any, Callable

import structlog

from sediman.agent.interrupt import InterruptSignal

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
            profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
        )
        _sentry_initialized = True
        logger.info("sentry_initialized", environment=os.environ.get("SENTRY_ENVIRONMENT", "production"))
    except ImportError:
        logger.debug("sentry_sdk_not_installed")
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
from sediman.agent.loop import AgentLoop, AgentResult, StepEvent
from sediman.browser.session import BrowserSession
from sediman.llm.provider import create_provider, LLMProvider, PROVIDERS

logger = structlog.get_logger()

# Global cron scheduler — started in serve(), used by schedule.add/remove for hot-reload
_cron_scheduler: Any = None
SOCKET = os.environ.get("SEDIMAN_PYTHON_SOCKET", "/tmp/sediman-python.sock")
MAX_TASK_LENGTH = 10000

# Lazy-initialized shared state (mirrors api/app.py pattern)
_browser: BrowserSession | None = None
_llm: LLMProvider | None = None
_agent_loop: AgentLoop | None = None
_llm_config: dict[str, Any] = {}
_agent_loop_lock = asyncio.Lock()
_browser_lock = asyncio.Lock()


# ── Initialization ─────────────────────────────────────────────────

def init_state(
    provider: str = "openai",
    model: str | None = None,
    base_url: str | None = None,
    terminal: bool = False,
) -> None:
    global _llm_config
    _llm_config = {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "terminal": terminal,
    }


def _get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        cfg = {k: v for k, v in _llm_config.items() if k != "terminal"}
        _llm = create_provider(**cfg)
    return _llm


async def _get_browser() -> BrowserSession:
    global _browser
    if _browser is None:
        async with _browser_lock:
            if _browser is None:
                from sediman.config import STEALTH_ENABLED, STEALTH_PROXY

                _browser = BrowserSession(
                    headless=True,
                    stealth=STEALTH_ENABLED,
                    proxy=STEALTH_PROXY or None,
                )
                await _browser.start()
    return _browser


async def _get_agent_loop() -> AgentLoop:
    global _agent_loop
    if _agent_loop is None:
        async with _agent_loop_lock:
            if _agent_loop is None:
                from sediman.agent.tools import set_terminal_allowed

                browser = await _get_browser()
                llm = _get_llm()
                _agent_loop = AgentLoop(llm_provider=llm, browser_session=browser)
                if _llm_config.get("terminal"):
                    set_terminal_allowed(True)
    return _agent_loop


def _reset_state() -> None:
    global _browser, _llm, _agent_loop
    _browser = None
    _llm = None
    _agent_loop = None


async def _shutdown() -> None:
    global _browser, _agent_loop
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    _agent_loop = None


# ── Handlers ───────────────────────────────────────────────────────

async def handle_system_status(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    browser = _browser
    llm = _llm
    agent = _agent_loop
    return {
        "browser_open": browser is not None and browser.is_running,
        "model": os.environ.get("SEDIMAN_MODEL") if not llm else getattr(llm, "model", None),
        "provider": _llm_config.get("provider", os.environ.get("SEDIMAN_PROVIDER", "openai")),
        "conversation_messages": len(getattr(agent, "_conversation", [])),
        "current_task": None,
        "scheduler": {"active_jobs": 0, "total_jobs": 0},
        "last_result": None,
        "queue_size": 0,
    }


async def handle_system_screenshot(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    browser = await _get_browser()
    screenshot = await browser.take_screenshot()
    if not screenshot:
        raise RuntimeError("No browser screenshot available")
    return {"screenshot": screenshot}


async def handle_system_btw(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    question = params.get("question", "")
    if not question:
        raise ValueError("question is required")
    from sediman.llm.provider import create_provider

    llm = create_provider(**{k: v for k, v in _llm_config.items() if k != "terminal"})
    system_msg = {"role": "system", "content": "You are a helpful assistant. Answer concisely."}
    msg = {"role": "user", "content": question}
    response = await llm.chat(messages=[system_msg, msg], tools=[])
    return {"answer": response.text}


async def handle_system_doctor(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    checks = {}
    for binary in ["google-chrome", "chromium", "python3"]:
        checks[binary] = shutil.which(binary) is not None
    checks["cloakbrowser"] = bool(os.environ.get("CLOAKBROWSER_BINARY"))
    checks["browser_running"] = _browser is not None and getattr(_browser, "is_running", False)
    checks["llm_configured"] = _llm is not None or bool(_llm_config)
    return {"checks": checks}


async def handle_agent_run(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    task = (params.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")
    if len(task) > MAX_TASK_LENGTH:
        raise ValueError(f"Task exceeds max length of {MAX_TASK_LENGTH}")

    agent = await _get_agent_loop()

    if notify:
        original_on_step = agent.on_step

        def stepping(event: StepEvent) -> None:
            try:
                notify("chat.progress", {
                    "phase": event.phase or "executing",
                    "action": event.action or "",
                    "url": event.observation or "",
                    "step": event.step,
                })
            except Exception:
                pass
            if original_on_step:
                original_on_step(event)

        agent.on_step = stepping

    InterruptSignal.get().clear()

    try:
        result: AgentResult = await agent.run(task)
    except InterruptedError:
        return {
            "task": task,
            "result": "Task cancelled by user.",
            "success": False,
            "steps": [],
            "skill_created": None,
            "elapsed_secs": 0,
            "strategy_used": "cancelled",
        }
    finally:
        if notify:
            agent.on_step = original_on_step if notify else agent.on_step

    return {
        "task": task,
        "result": result.result or "",
        "success": True,
        "steps": [{"action": s.action, "observation": s.observation, "phase": s.phase} for s in (result.steps or [])],
        "skill_created": result.skill_created,
        "actions_taken": result.actions_taken or [],
        "scheduled_job_id": result.scheduled_job_id,
        "schedule_cron": result.schedule_cron,
        "iterations": result.iterations or 0,
        "strategy_used": result.strategy_used or "direct",
        "elapsed_secs": 0,
    }


async def handle_agent_cancel(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    InterruptSignal.get().trigger("Cancelled by user via RPC")
    return {"cancelled": True}


async def handle_skills_run(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("skill name is required")

    from sediman.skills.engine import SkillEngine

    engine = SkillEngine()
    skill = engine.get_skill(name)
    if not skill:
        raise ValueError(f"Skill '{name}' not found")

    browser = await _get_browser()
    llm = _get_llm()
    from sediman.skills.executor import execute_skill

    result_text = await execute_skill(skill=skill, browser_session=browser, llm=llm)
    return {"result": result_text}


async def handle_model_switch(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    provider = (params.get("provider") or "").strip()
    model = (params.get("model") or "").strip() or None
    if not provider:
        raise ValueError("provider is required")
    _llm_config["provider"] = provider
    if model:
        _llm_config["model"] = model
    _reset_state()
    return {"provider": provider, "model": model}


async def handle_model_list_providers(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    providers = []
    for name, cfg in PROVIDERS.items():
        providers.append({"name": name, "default_model": cfg.get("model"), "default_base_url": cfg.get("base_url")})
    return {"providers": providers}


async def handle_terminal_set(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.agent.tools import set_terminal_allowed
    allowed = bool(params.get("allowed", False))
    set_terminal_allowed(allowed)
    return {"allowed": allowed}


async def handle_terminal_status(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.agent.tools import is_terminal_allowed
    return {"allowed": is_terminal_allowed()}


async def handle_record_start(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("recording name is required")
    browser = await _get_browser()
    from sediman.agent.recording_manager import RecordingManager

    mgr = RecordingManager.get_instance()
    session = await mgr.start_recording(name=name, browser=browser)
    return {"session_id": session.id, "name": session.name, "started_at": str(session.started_at)}


async def handle_record_stop(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    session_id = (params.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    from sediman.agent.recording_manager import RecordingManager

    mgr = RecordingManager.get_instance()
    session = await mgr.stop_by_session_id(session_id)
    if not session:
        raise ValueError(f"Recording session '{session_id}' not found")

    from sediman.skills.trace_to_skill import TraceToSkill
    from sediman.skills.engine import SkillEngine

    skill_engine = SkillEngine()
    llm = _get_llm()
    converter = TraceToSkill(llm)
    try:
        result = await converter.convert(recording=session)
        skill_name = result.get("name", session.name)
        skill_data = result.get("skill", {})
        skill_engine.ensure_skill(skill_name, skill_data)
        return {"session_id": session_id, "skill_created": skill_name, "message": f"Skill '{skill_name}' created"}
    except Exception as e:
        return {"session_id": session_id, "skill_created": None, "message": f"Recording stopped but skill creation failed: {e}"}


async def handle_record_active(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.agent.recording_manager import RecordingManager

    mgr = RecordingManager.get_instance()
    sessions = mgr.get_active_sessions()
    recordings = []
    for s in sessions:
        recordings.append({
            "session_id": s.id,
            "name": s.name,
            "started_at": str(s.started_at),
            "frame_count": len(getattr(s, "frames", [])),
            "duration_seconds": 0,
            "action_count": len(getattr(s, "actions", [])),
        })
    return {"recordings": recordings}


async def handle_integration_list(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.integrations import list_integrations
    return {"integrations": list_integrations()}


async def handle_integration_configure(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("integration name is required")
    from sediman.integrations import update_config
    updates = {k: v for k, v in params.items() if k != "name" and v is not None}
    result = update_config(name, updates)
    return {"integration": name, "config": result}


async def handle_integration_send(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    integration = (params.get("integration") or "").strip()
    target = (params.get("target") or "").strip()
    content = (params.get("content") or "").strip()
    if not integration or not target or not content:
        raise ValueError("integration, target, and content are required")
    from sediman.integrations import send_message
    result = await send_message(integration, target, content)
    return {"result": result}


async def handle_integration_status(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.integrations import get_integration, get_config
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("integration name is required")
    inst = get_integration(name)
    config = get_config().get(name, {})
    return {
        "name": name,
        "enabled": config.get("enabled", False),
        "configured": bool(config.get("token")),
        "connected": inst is not None and inst.enabled,
    }


# ── Hub ─────────────────────────────────────────────────────────────

async def handle_hub_browse(params: dict[str, Any], notify: NotifyFn | None = None) -> list[dict[str, Any]]:
    from sediman.skills.hub import HubClient
    hub = HubClient()
    category = params.get("category")
    results = hub.browse(category=category if category else None)
    return [
        {
            "name": s.name, "description": s.description,
            "category": s.category, "author": s.author,
            "version": s.version, "trust": s.trust,
        }
        for s in results
    ]


async def handle_hub_search(params: dict[str, Any], notify: NotifyFn | None = None) -> list[dict[str, Any]]:
    from sediman.skills.hub import HubClient
    hub = HubClient()
    query = (params.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    results = hub.search(query)
    return [
        {
            "name": s.name, "description": s.description,
            "category": s.category, "author": s.author,
            "version": s.version, "trust": s.trust,
        }
        for s in results
    ]


async def handle_hub_info(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import HubClient
    hub = HubClient()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    info = hub.info(name)
    if not info:
        raise ValueError(f"Skill '{name}' not found in hub")
    return info


async def handle_hub_install(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import HubClient
    from sediman.skills.engine import SkillEngine
    hub = HubClient()
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    force = bool(params.get("force", False))
    success, message = hub.install(name, engine, force=force)
    if not success:
        raise ValueError(message)
    return {"installed": name, "message": message}


async def handle_hub_install_github(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import GitHubInstaller
    from sediman.skills.engine import SkillEngine
    installer = GitHubInstaller()
    engine = SkillEngine()
    ref = (params.get("ref") or "").strip()
    if not ref:
        raise ValueError("ref is required")
    force = bool(params.get("force", False))
    success, message = installer.install(ref, engine, force=force)
    if not success:
        raise ValueError(message)
    return {"installed": ref, "message": message}


async def handle_hub_check_update(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import GitHubInstaller
    from sediman.skills.engine import SkillEngine
    installer = GitHubInstaller()
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    has_update, message = installer.check_update(name, engine)
    return {"hasUpdate": has_update, "message": message}


async def handle_hub_update_skill(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import GitHubInstaller
    from sediman.skills.engine import SkillEngine
    installer = GitHubInstaller()
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    updated, message = installer.update_skill(name, engine)
    return {"updated": updated, "message": message}


async def handle_hub_remove(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.engine import SkillEngine
    from sediman.skills.hub import SkillLockFile
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    engine = SkillEngine()
    engine.delete(name)
    lock = SkillLockFile()
    lock.remove(name)
    return {"removed": name}


async def handle_hub_get_lock_info(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.hub import SkillLockFile
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    lock = SkillLockFile()
    entry = lock.get(name)
    if not entry:
        raise ValueError(f"No lock info for {name}")
    return entry.to_json()


# ── Memory ──────────────────────────────────────────────────────────

async def handle_memory_get(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.store import MemoryStore
    store = MemoryStore()
    all_entries = store.get_all_entries()
    mem_entries = all_entries.get("memory", [])
    user_entries = all_entries.get("user", [])
    return {
        "entries": {
            "memory": [{"content": e, "created_at": None} for e in mem_entries],
            "user": [{"content": e, "created_at": None} for e in user_entries],
        },
        "memory": "\n".join(mem_entries),
        "user": "\n".join(user_entries),
        "memory_entries": len(mem_entries),
        "user_entries": len(user_entries),
    }


async def handle_memory_add(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.manager import MemoryManager
    mgr = MemoryManager()
    await mgr.initialize()
    target = (params.get("target") or "memory").strip()
    content = (params.get("content") or "").strip()
    if not content:
        raise ValueError("content is required")
    result = mgr._handle_memory_tool({"action": "add", "target": target, "content": content})
    return {"success": True, "message": result}


async def handle_memory_replace(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.manager import MemoryManager
    mgr = MemoryManager()
    await mgr.initialize()
    target = (params.get("target") or "memory").strip()
    content = (params.get("content") or "").strip()
    old_entry = (params.get("old_entry") or "").strip()
    if not content or not old_entry:
        raise ValueError("content and old_entry are required")
    result = mgr._handle_memory_tool({
        "action": "replace", "target": target, "content": content, "old_entry": old_entry,
    })
    return {"success": True, "message": result}


async def handle_memory_remove(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.manager import MemoryManager
    mgr = MemoryManager()
    await mgr.initialize()
    target = (params.get("target") or "memory").strip()
    content = (params.get("content") or "").strip()
    if not content:
        raise ValueError("content is required")
    result = mgr._handle_memory_tool({
        "action": "remove", "target": target, "old_entry": content,
    })
    return {"success": True, "message": result}


async def handle_memory_search(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.manager import MemoryManager
    mgr = MemoryManager()
    await mgr.initialize()
    query = (params.get("query") or "").strip()
    limit = int(params.get("limit", 5))
    if not query:
        raise ValueError("query is required")
    results = mgr.get_relevant_context(query, limit=limit)
    return {"results": results}


async def handle_memory_changelog(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.changelog import get_recent_changes
    target = params.get("target")
    limit = int(params.get("limit", 20))
    changes = get_recent_changes(target=target, limit=limit)
    return {
        "changes": [
            {
                "action": c.action, "target": c.target,
                "content": c.content, "reason": c.reason,
                "timestamp": c.timestamp,
            }
            for c in changes
        ],
    }


# ── Sessions ────────────────────────────────────────────────────────

async def handle_sessions_list(params: dict[str, Any], notify: NotifyFn | None = None) -> list[dict[str, Any]]:
    from sediman.memory.sessions import get_recent_sessions
    sessions = get_recent_sessions(limit=50)
    return [
        {"id": s["id"], "task": s["task"],
         "result": s.get("result", ""), "created_at": s.get("created_at", "")}
        for s in sessions
    ]


async def handle_sessions_search(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.sessions import search_sessions
    query = (params.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    limit = int(params.get("limit", 20))
    results = search_sessions(query, limit=limit)
    return {"sessions": results}


async def handle_sessions_save(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.sessions import save_session
    task = (params.get("task") or "").strip()
    if not task:
        raise ValueError("task is required")
    steps = params.get("steps", [])
    result = params.get("result", "")
    session_id = save_session(task, steps_json=json.dumps(steps), result=result)
    return {"session_id": session_id}


async def handle_sessions_get(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.memory.sessions import get_session_by_id
    session_id = (params.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_id is required")
    session = get_session_by_id(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    return session


# ── Schedule ────────────────────────────────────────────────────────

async def handle_schedule_list(params: dict[str, Any], notify: NotifyFn | None = None) -> list[dict[str, Any]]:
    from sediman.scheduler.cron import CronManager
    mgr = CronManager()
    jobs = mgr.list_jobs()
    return [
        {
            "id": j.get("id", ""), "task": j.get("task", ""),
            "cron_expr": j.get("cron", ""),
            "skill_name": j.get("skill_name"),
            "enabled": j.get("enabled", True),
            "last_run": j.get("last_run"),
            "next_run": j.get("next_run"),
        }
        for j in jobs
    ]


async def handle_schedule_add(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.scheduler.cron import CronManager
    mgr = CronManager()
    cron = (params.get("cron") or "").strip()
    task = (params.get("task") or "").strip()
    if not cron or not task:
        raise ValueError("cron and task are required")
    skill = params.get("skill")
    job_id = mgr.add_job(
        cron=cron,
        task=task,
        skill_name=skill if skill else None,
        enabled=True,
    )

    # Hot-reload scheduler so the new job starts immediately
    if _cron_scheduler is not None:
        _cron_scheduler.reload()

    return {"job_id": job_id}


async def handle_schedule_remove(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.scheduler.cron import CronManager
    mgr = CronManager()
    job_id = (params.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id is required")
    mgr.remove_job(job_id)

    # Hot-reload scheduler so the removed job stops
    if _cron_scheduler is not None:
        _cron_scheduler.reload()

    return {"removed": job_id}


# ── Skills CRUD ─────────────────────────────────────────────────────

async def handle_skills_list(params: dict[str, Any], notify: NotifyFn | None = None) -> list[dict[str, Any]]:
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    skills = engine.list_skills()
    return [
        {
            "name": s.get("name", ""), "description": s.get("description", ""),
            "category": s.get("category"), "version": s.get("version", 1),
        }
        for s in skills
    ]


async def handle_skills_get(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    skill = engine.read(name)
    if not skill:
        raise ValueError(f"Skill '{name}' not found")
    if hasattr(skill, "to_dict"):
        return skill.to_dict()
    return skill if isinstance(skill, dict) else {"name": name}


async def handle_skills_create(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.engine import SkillEngine
    from sediman.skills.format import SkillData
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    description = (params.get("description") or "").strip()
    steps = params.get("steps", [])
    if not name or not description:
        raise ValueError("name and description are required")
    if not isinstance(steps, list):
        steps = []
    skill_data = SkillData(
        name=name,
        description=description,
        steps=steps,
        category=params.get("category", "general"),
        when_to_use=params.get("when_to_use"),
        pitfalls=params.get("pitfalls", []),
        verification=params.get("verification"),
    )
    engine.ensure_skill(name, skill_data)
    if hasattr(skill_data, "to_dict"):
        return skill_data.to_dict()
    return {"name": name, "description": description}


async def handle_skills_delete(params: dict[str, Any], notify: NotifyFn | None = None) -> dict[str, Any]:
    from sediman.skills.engine import SkillEngine
    engine = SkillEngine()
    name = (params.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    engine.delete(name)
    return {"deleted": name}


# ── Dispatching ────────────────────────────────────────────────────

NotifyFn = Callable[[str, dict[str, Any]], None]

HANDLERS: dict[str, Callable] = {
    "system.status": handle_system_status,
    "system.screenshot": handle_system_screenshot,
    "system.btw": handle_system_btw,
    "system.doctor": handle_system_doctor,
    "agent.run": handle_agent_run,
    "agent.cancel": handle_agent_cancel,
    "skills.run": handle_skills_run,
    "skills.list": handle_skills_list,
    "skills.get": handle_skills_get,
    "skills.create": handle_skills_create,
    "skills.delete": handle_skills_delete,
    "hub.browse": handle_hub_browse,
    "hub.search": handle_hub_search,
    "hub.info": handle_hub_info,
    "hub.install": handle_hub_install,
    "hub.install_github": handle_hub_install_github,
    "hub.check_update": handle_hub_check_update,
    "hub.update_skill": handle_hub_update_skill,
    "hub.remove": handle_hub_remove,
    "hub.get_lock_info": handle_hub_get_lock_info,
    "memory.get": handle_memory_get,
    "memory.add": handle_memory_add,
    "memory.replace": handle_memory_replace,
    "memory.remove": handle_memory_remove,
    "memory.search": handle_memory_search,
    "memory.changelog": handle_memory_changelog,
    "sessions.list": handle_sessions_list,
    "sessions.search": handle_sessions_search,
    "sessions.save": handle_sessions_save,
    "sessions.get": handle_sessions_get,
    "schedule.list": handle_schedule_list,
    "schedule.add": handle_schedule_add,
    "schedule.remove": handle_schedule_remove,
    "model.switch": handle_model_switch,
    "model.list_providers": handle_model_list_providers,
    "terminal.set": handle_terminal_set,
    "terminal.status": handle_terminal_status,
    "record.start": handle_record_start,
    "record.stop": handle_record_stop,
    "record.active": handle_record_active,
    "integration.list": handle_integration_list,
    "integration.configure": handle_integration_configure,
    "integration.send": handle_integration_send,
    "integration.status": handle_integration_status,
}


async def dispatch_request(
    method: str,
    params: dict[str, Any],
    req_id: int | str | None,
    notify: NotifyFn | None = None,
) -> dict[str, Any]:
    handler = HANDLERS.get(method)
    if not handler:
        return _error(req_id, -32601, f"Method not found: {method}")
    try:
        result = await handler(params, notify)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except InterruptedError:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "result": "Task cancelled by user.",
                "steps": [],
                "skill_created": None,
                "elapsed_secs": 0,
                "strategy_used": "cancelled",
            },
        }
    except Exception as e:
        _capture_exception(e)
        logger.exception("handler_error", method=method)
        return _error(req_id, -32000, str(e))


def _error(req_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ── Connection Handler ─────────────────────────────────────────────

async def handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single client connection (one or more JSON-RPC requests)."""
    notify: NotifyFn | None = None

    async def _notify(method: str, params: dict[str, Any]) -> None:
        try:
            msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
            writer.write(msg.encode())
            await writer.drain()
        except Exception:
            pass

    async def read_cancel() -> None:
        """Background task: read additional lines for cancel while agent.run is active."""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode())
                    if msg.get("method") == "agent.cancel":
                        InterruptSignal.get().trigger("Cancelled by user")
                        break
                except json.JSONDecodeError:
                    pass
                except Exception:
                    pass
        except Exception:
            pass

    try:
        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                req = json.loads(line.decode())
            except json.JSONDecodeError:
                response = _error(None, -32700, "Parse error")
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
                continue

            method = req.get("method", "")
            params = req.get("params", {})
            req_id = req.get("id")

            if method == "agent.run":
                cancel_task = asyncio.create_task(read_cancel())
                try:
                    response = await dispatch_request(method, params, req_id, _notify)
                finally:
                    cancel_task.cancel()
                    try:
                        await cancel_task
                    except asyncio.CancelledError:
                        pass
            else:
                response = await dispatch_request(method, params, req_id, None)

            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()

    except Exception:
        logger.exception("connection_error")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ── Server ─────────────────────────────────────────────────────────

async def serve() -> None:
    """Start the Unix socket JSON-RPC server with cron scheduler."""
    global _cron_scheduler

    if os.path.exists(SOCKET):
        os.unlink(SOCKET)

    # Start the cron scheduler alongside the RPC server
    from sediman.scheduler.cron import CronScheduler
    _cron_scheduler = CronScheduler()
    _cron_scheduler.start()
    logger.info("cron_scheduler_started")

    server = await asyncio.start_unix_server(handle_connection, path=SOCKET)
    logger.info("rpc_server_started", socket=SOCKET)

    try:
        async with server:
            await server.serve_forever()
    finally:
        _cron_scheduler.stop()
        _cron_scheduler = None


def main() -> None:
    """Entry point: python -m sediman.rpc_server."""
    import sys

    provider = os.environ.get("SEDIMAN_PROVIDER", "openai")
    model = os.environ.get("SEDIMAN_MODEL")
    base_url = os.environ.get("SEDIMAN_BASE_URL") or os.environ.get("OLLAMA_BASE_URL")
    terminal = os.environ.get("SEDIMAN_TERMINAL", "").lower() in ("true", "1", "yes")

    init_state(provider=provider, model=model, base_url=base_url, terminal=terminal)
    _init_sentry()

    from sediman.integrations import setup_integrations, start_listeners
    setup_integrations()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("rpc_server_shutdown")
        asyncio.run(_shutdown())


if __name__ == "__main__":
    main()
