from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


def _daily_cron(m: re.Match) -> str:
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{minute} {hour} * * *"


_SCHEDULE_PATTERNS = [
    (re.compile(r"every\s+(\d+)\s+mins?", re.I), lambda m: f"*/{m.group(1)} * * * *"),
    (re.compile(r"every\s+(\d+)\s+minutes?", re.I), lambda m: f"*/{m.group(1)} * * * *"),
    (re.compile(r"every\s+minute", re.I), lambda _: "*/1 * * * *"),
    (re.compile(r"every\s+min\b", re.I), lambda _: "*/1 * * * *"),
    (re.compile(r"every\s+(\d+)\s+hours?", re.I), lambda m: f"0 */{m.group(1)} * * *"),
    (re.compile(r"every\s+hour", re.I), lambda _: "0 * * * *"),
    (re.compile(r"every\s+half\s+hour", re.I), lambda _: "*/30 * * * *"),
    (re.compile(r"every\s+30\s+minutes?", re.I), lambda _: "*/30 * * * *"),
    (re.compile(r"hourly", re.I), lambda _: "0 * * * *"),
    (re.compile(r"daily\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I), _daily_cron),
    (re.compile(r"\bdaily\b", re.I), lambda _: "0 9 * * *"),
    (re.compile(r"every\s+day", re.I), lambda _: "0 9 * * *"),
    (re.compile(r"\bweekly\b", re.I), lambda _: "0 9 * * 1"),
    (re.compile(r"every\s+(\d+)\s+seconds?", re.I), lambda m: f"*/{max(int(m.group(1)) // 60, 1)} * * * *"),
    (re.compile(r"monitor\b", re.I), lambda _: "*/5 * * * *"),
]

_STRIP_PATTERNS = [
    re.compile(r"^.*?(?:please\s+)?(?:add|create|set\s+up|set)\s+(?:a\s+)?(?:new\s+)?(?:task|job|schedule)\s*:?\s*", re.I),
    re.compile(r"\s*(?:and\s+)?(?:schedule|set\s+it(?:\s+up)?)\s+(?:it\s+)?(?:to\s+run\s+)?(?:every|each)\s+.*$", re.I),
    re.compile(r"\s*(?:and\s+)?(?:every|each)\s+\d+\s*(?:minute|hour|second|day)s?\s*$", re.I),
    re.compile(r"\s*(?:and\s+)?(?:run|repeat|check)\s+(?:it\s+)?(?:every|each)\s+.*$", re.I),
    re.compile(r"\s*(?:and\s+)?schedule\s+(?:it\s+)?(?:every|each)\s+.*$", re.I),
    re.compile(r"\s+every\s+\d+\s*(?:minute|min|hour|second|day)s?", re.I),
    re.compile(r"\s+every\s+(?:minute|min|hour|day|week)\b", re.I),
    re.compile(r"\s+hourly$", re.I),
    re.compile(r"\s+daily$", re.I),
    re.compile(r"\s+weekly$", re.I),
]


@dataclass
class ScheduleIntent:
    cron: str
    task: str


@dataclass
class Plan:
    browser_task: str
    schedule: ScheduleIntent | None = None
    needs_memory: bool = True
    needs_skill_eval: bool = True


class TaskPlanner:
    def plan(self, task: str) -> Plan:
        schedule = self._detect_schedule(task)
        browser_task = self._extract_browser_task(task, schedule)
        plan = Plan(
            browser_task=browser_task,
            schedule=schedule,
        )
        logger.info(
            "task_planned",
            browser_task=browser_task[:80],
            schedule=schedule.cron if schedule else None,
        )
        return plan

    def _detect_schedule(self, task: str) -> ScheduleIntent | None:
        for pattern, cron_fn in _SCHEDULE_PATTERNS:
            m = pattern.search(task)
            if m:
                cron_expr = cron_fn(m)
                schedule_task = self._extract_schedule_task(task)
                return ScheduleIntent(cron=cron_expr, task=schedule_task)
        return None

    def _extract_schedule_task(self, task: str) -> str:
        cleaned = task
        for pat in _STRIP_PATTERNS:
            cleaned = pat.sub("", cleaned)
        return cleaned.strip() or task.strip()

    def _extract_browser_task(self, task: str, schedule: ScheduleIntent | None) -> str:
        if schedule is None:
            return task
        cleaned = task
        for pat in _STRIP_PATTERNS:
            cleaned = pat.sub("", cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return task
        return cleaned
