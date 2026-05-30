from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import structlog

logger = structlog.get_logger()

JOBS_DIR = Path.home() / ".sediman" / "cron"
RESULTS_FILE = JOBS_DIR / "results.jsonl"
MAX_RESULT_CHARS = 2000
MAX_RESULTS_PER_JOB = 100

_CRON_FIELD_RE = re.compile(r"^[\d*/,\-]+$")
_JOB_ID_RE = re.compile(r"^[a-f0-9]{1,12}$")
_list_jobs_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL = 30.0

_SUPRESSED_LOGGERS = (
    "browser_use", "Agent", "service", "httpx", "httpcore",
    "openai", "browser_use.agent", "browser_use.browser",
    "browser_use.tools", "browser_use.controller", "bubus",
    "sediman", "sediman.agent.loop", "sediman.browser.session",
    "sediman.scheduler.cron", "sediman.memory.sessions",
)


@contextmanager
def _suppress_logging() -> Generator[None, None, None]:
    """Temporarily suppress noisy loggers without mutating global config.

    Uses per-logger level overrides so we never touch the root logger
    or structlog's global configuration.
    """
    saved: dict[str, int] = {}
    for _name in _SUPRESSED_LOGGERS:
        lg = logging.getLogger(_name)
        saved[_name] = lg.level
        lg.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for _name, level in saved.items():
            logging.getLogger(_name).setLevel(level)


def validate_cron_expr(expr: str) -> bool:
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    return all(_CRON_FIELD_RE.match(p) for p in parts)


class CronManager:
    def __init__(self) -> None:
        self.jobs_dir = JOBS_DIR
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.jobs_dir / "results.jsonl"

    @property
    def _results_file(self) -> Path:
        return RESULTS_FILE

    def _job_path(self, job_id: str) -> Path:
        if not _JOB_ID_RE.match(job_id):
            raise ValueError(f"Invalid job ID: {job_id!r}")
        return self.jobs_dir / f"{job_id}.json"

    def add_job(
        self,
        cron_expr: str,
        task: str,
        skill_name: str | None = None,
        provider: str = "openai",
        model: str | None = None,
        base_url: str | None = None,
        notify: str | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "cron": cron_expr,
            "task": task,
            "skill_name": skill_name,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
            "last_result": None,
            "enabled": True,
            "notify": notify,
        }
        self._job_path(job_id).write_text(json.dumps(job, indent=2))
        _list_jobs_cache.pop(str(self.jobs_dir), None)
        logger.info("cron_job_added", job_id=job_id, cron=cron_expr, task=task)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            path = self._job_path(job_id)
        except ValueError:
            return None
        if not path.exists():
            for p in self.jobs_dir.glob("*.json"):
                if _JOB_ID_RE.match(p.stem) and p.stem.startswith(job_id):
                    return json.loads(p.read_text())
            return None
        return json.loads(path.read_text())

    def list_jobs(self) -> list[dict[str, Any]]:
        cache_key = str(self.jobs_dir)
        now = time.time()
        if cache_key in _list_jobs_cache:
            ts, cached = _list_jobs_cache[cache_key]
            if now - ts < _CACHE_TTL:
                return cached
        if not self.jobs_dir.exists():
            return []
        jobs = []
        for p in sorted(self.jobs_dir.glob("*.json")):
            data = json.loads(p.read_text())
            if "id" not in data:
                data["id"] = p.stem
            jobs.append(data)
        _list_jobs_cache[cache_key] = (now, jobs)
        return jobs

    def remove_job(self, job_id: str) -> bool:
        try:
            path = self._job_path(job_id)
        except ValueError:
            return False
        if path.exists():
            path.unlink()
            _list_jobs_cache.pop(str(self.jobs_dir), None)
            logger.info("cron_job_removed", job_id=job_id)
            return True

        for p in self.jobs_dir.glob("*.json"):
            if _JOB_ID_RE.match(p.stem) and p.stem.startswith(job_id):
                p.unlink()
                _list_jobs_cache.pop(str(self.jobs_dir), None)
                logger.info("cron_job_removed", job_id=p.stem)
                return True

        return False

    def update_job_result(self, job_id: str, result: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        job["last_run"] = datetime.now(timezone.utc).isoformat()
        job["last_result"] = result[:500]
        self._job_path(job["id"]).write_text(json.dumps(job, indent=2))
        _list_jobs_cache.pop(str(self.jobs_dir), None)
        self._append_result_history(job_id, job.get("task", ""), result)

    def _append_result_history(self, job_id: str, task: str, result: str) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "job_id": job_id,
            "task": task,
            "result": result[:MAX_RESULT_CHARS],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.results_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._trim_result_history(job_id)

    def _trim_result_history(self, job_id: str) -> None:
        if not self.results_file.exists():
            return
        entries = self._read_all_results()
        job_entries = [e for e in entries if e["job_id"] == job_id]
        if len(job_entries) <= MAX_RESULTS_PER_JOB:
            return
        keep_ids = {e["timestamp"] for e in job_entries[-MAX_RESULTS_PER_JOB:]}
        other_entries = [e for e in entries if e["job_id"] != job_id]
        kept = [e for e in job_entries if e["timestamp"] in keep_ids]
        all_kept = other_entries + kept
        all_kept.sort(key=lambda e: e["timestamp"])
        with open(self.results_file, "w") as f:
            for e in all_kept:
                f.write(json.dumps(e) + "\n")

    def _read_all_results(self) -> list[dict[str, Any]]:
        if not self.results_file.exists():
            return []
        entries = []
        with open(self.results_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def get_results(
        self,
        job_id: str | None = None,
        task_filter: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        entries = self._read_all_results()
        if job_id:
            entries = [e for e in entries if e["job_id"] == job_id]
        if task_filter:
            keyword = task_filter.lower()
            entries = [e for e in entries if keyword in e.get("task", "").lower() or keyword in e.get("result", "").lower()]
        entries.sort(key=lambda e: e["timestamp"], reverse=True)
        return entries[:limit]


class _CronResources:
    """Shared resources reused across cron job executions in a single process."""

    def __init__(self) -> None:
        self.llm: Any = None
        self.browser: Any = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def ensure_initialized(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            from sediman.browser.session import BrowserSession
            from sediman.llm.provider import create_provider
            from sediman.store.db import init_db

            await init_db()
            self.llm = create_provider(provider="openai")
            self.browser = BrowserSession(
                headless=True,
                stealth=True,
                user_data_dir=str(Path.home() / ".sediman" / "browser-profile-cron"),
            )
            await self.browser.start()
            self._initialized = True

    async def shutdown(self) -> None:
        if self.browser:
            await self.browser.stop()
            self.browser = None
        self._initialized = False


_shared_resources: _CronResources | None = None


def _get_shared_resources() -> _CronResources:
    global _shared_resources
    if _shared_resources is None:
        _shared_resources = _CronResources()
    return _shared_resources


async def execute_cron_job(job: dict[str, Any]) -> str:
    """Execute a scheduled cron job."""
    with _suppress_logging():
        try:
            return await _execute_cron_job_inner(job)
        except Exception as exc:
            return f"error: {exc}"


async def _execute_cron_job_inner(job: dict[str, Any]) -> str:
    from sediman.agent.loop import AgentLoop
    from sediman.skills.executor import execute_skill as run_skill
    from sediman.skills.engine import SkillEngine

    job_provider = job.get("provider", "openai")
    job_model = job.get("model")
    job_base_url = job.get("base_url")

    if job_provider != "openai" or job_model or job_base_url:
        from sediman.llm.provider import create_provider
        from sediman.store.db import init_db

        await init_db()
        llm = create_provider(provider=job_provider, model=job_model, base_url=job_base_url)
        browser = None
    else:
        resources = _get_shared_resources()
        await resources.ensure_initialized()
        llm = resources.llm
        browser = resources.browser

    from sediman.browser.session import BrowserSession

    owns_browser = browser is None
    if owns_browser:
        browser = BrowserSession(
            headless=True,
            stealth=True,
            user_data_dir=str(Path.home() / ".sediman" / "browser-profile-cron"),
        )
        await browser.start()

    try:
        if job.get("skill_name"):
            engine = SkillEngine()
            skill_data = engine.read(job["skill_name"])
            if skill_data:
                result = await run_skill(skill_data, browser, llm)
            else:
                result = f"Skill '{job['skill_name']}' not found"
        else:
            agent = AgentLoop(llm_provider=llm, browser_session=browser)
            agent_result = await agent.run(job["task"])
            result = agent_result.result

        cron = CronManager()
        cron.update_job_result(job["id"], result)

        notify = job.get("notify")
        if notify and ":" in notify:
            try:
                integration_name, target = notify.split(":", 1)
                from sediman.integrations import get_integration
                inst = get_integration(integration_name)
                if inst:
                    summary = result[:500] if result else "No result"
                    await inst.send(target, f"Cron job [{job['id'][:8]}] completed:\n\n{summary}")
            except Exception as e:
                logger.warning("cron_notification_failed", notify=notify, error=str(e))

        logger.info("cron_job_executed", job_id=job["id"], result_length=len(result))
        return result

    finally:
        if owns_browser:
            await browser.stop()


class CronScheduler:
    """Scheduler with hot-reload support."""

    def __init__(self) -> None:
        self._scheduler: Any = None
        self._cron = CronManager()
        self._running = False

    def start(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self._scheduler = AsyncIOScheduler()
        self._load_jobs()
        self._scheduler.start()
        self._running = True
        logger.info("scheduler_started")

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown()
            self._scheduler = None
            self._running = False
            logger.info("scheduler_stopped")

    def reload(self) -> None:
        """Hot-reload all jobs from disk without restarting the process."""
        if not self._scheduler:
            return
        self._scheduler.remove_all_jobs()
        _list_jobs_cache.pop(str(self._cron.jobs_dir), None)
        self._load_jobs()
        logger.info("scheduler_reloaded")

    def _load_jobs(self) -> None:
        from apscheduler.triggers.cron import CronTrigger

        jobs = self._cron.list_jobs()
        loaded = 0
        for job in jobs:
            if not job.get("enabled", True):
                continue
            parts = job["cron"].split()
            if len(parts) != 5:
                logger.warning("invalid_cron", job_id=job["id"], cron=job["cron"])
                continue
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
            self._scheduler.add_job(
                _run_scheduled_task,
                trigger=trigger,
                id=job["id"],
                args=[job],
                replace_existing=True,
            )
            loaded += 1
        logger.info("cron_jobs_loaded", total=len(jobs), loaded=loaded)


def start_scheduler() -> None:
    """Start the cron daemon (blocking)."""
    sched = CronScheduler()
    sched.start()

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        sched.stop()


async def _run_scheduled_task(job: dict[str, Any]) -> None:
    """Wrapper for APScheduler to run a cron job."""
    try:
        await execute_cron_job(job)
        logger.info("scheduled_task_complete", job_id=job["id"])
    except Exception as e:
        logger.error("scheduled_task_failed", job_id=job["id"], error=str(e), exc_info=True)
