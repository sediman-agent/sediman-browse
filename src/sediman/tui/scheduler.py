"""Scheduler manager extracted from tui.py — handles APScheduler lifecycle."""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from sediman.tui.logging import suppress_logging


def cleanup_loop(loop: asyncio.AbstractEventLoop) -> None:
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


class SchedulerManager:
    """Manages APScheduler lifecycle and cron job execution."""

    def __init__(self):
        self._scheduler: Any = None
        self._scheduler_lock = threading.Lock()
        self._cron_messages: queue.Queue[str] = queue.Queue()
        self._cron_loops: list[Any] = []
        self._cron_loops_lock = threading.Lock()

    def start(self) -> None:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            with self._scheduler_lock:
                if self._scheduler is not None:
                    self.refresh()
                    return
                self._scheduler = BackgroundScheduler(daemon=True)
                self._reload_jobs()
                self._scheduler.start()
        except ImportError:
            pass
        except Exception:
            pass

    def stop(self) -> None:
        with self._scheduler_lock:
            if self._scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:
                    pass
                self._scheduler = None

        with self._cron_loops_lock:
            for loop in self._cron_loops:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except Exception:
                    pass
            self._cron_loops.clear()

    def refresh(self) -> None:
        try:

            with self._scheduler_lock:
                if self._scheduler is None:
                    return
                self._scheduler.remove_all_jobs()
                self._reload_jobs()
        except Exception:
            pass

    def _reload_jobs(self) -> int:
        from apscheduler.triggers.cron import CronTrigger
        from sediman.scheduler.cron import CronManager

        cron = CronManager()
        jobs = cron.list_jobs()
        for job in jobs:
            if not job.get("enabled", True):
                continue
            parts = job["cron"].split()
            if len(parts) != 5:
                continue
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
            self._scheduler.add_job(
                self._run_scheduled_job,
                trigger=trigger,
                id=job["id"],
                args=[job],
                replace_existing=True,
            )
        active = sum(1 for j in jobs if j.get("enabled", True))
        if jobs:
            print(f"  \033[36m[Scheduler]\033[0m {active} active job(s)")
        return active

    def _run_scheduled_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"][:8]
        task_desc = job.get("task", "")[:60]

        self._cron_messages.put(f"  [Cron] [{job_id}] {task_desc}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._cron_loops_lock:
            self._cron_loops.append(loop)
        with suppress_logging():
            try:
                result = loop.run_until_complete(self._execute_scheduled_job(job))
                result_preview = (result or "No result")[:200]
                self._cron_messages.put(f"  [Done]  [{job_id}] {result_preview}")
            except Exception as e:
                self._cron_messages.put(f"  [Fail]  [{job_id}] {e}")
            finally:
                with self._cron_loops_lock:
                    if loop in self._cron_loops:
                        self._cron_loops.remove(loop)
                cleanup_loop(loop)

    async def _execute_scheduled_job(self, job: dict[str, Any]) -> str:
        from sediman.scheduler.cron import CronManager, execute_cron_job

        result = await execute_cron_job(job)
        cron = CronManager()
        cron.update_job_result(job["id"], result)
        return result

    def flush_messages(self) -> None:
        while True:
            try:
                msg = self._cron_messages.get_nowait()
                print(msg)
            except queue.Empty:
                break
