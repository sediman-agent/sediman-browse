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


def _cjk_minutes(m: re.Match) -> str:
    return f"*/{m.group(1)} * * * *"


def _cjk_hours(m: re.Match) -> str:
    return f"0 */{m.group(1)} * * *"


def _cjk_daily(_m: re.Match) -> str:
    return "0 9 * * *"


def _cjk_hourly(_m: re.Match) -> str:
    return "0 * * * *"


def _cjk_weekly(_m: re.Match) -> str:
    return "0 9 * * 1"


def _monitor_cron(_m: re.Match) -> str:
    return "*/5 * * * *"


def _n_minutes(m: re.Match) -> str:
    return f"*/{m.group(1)} * * * *"


def _n_hours(m: re.Match) -> str:
    return f"0 */{m.group(1)} * * *"


_CRON_FIELD = r"(?:\*|(?:\d+,)*\d+|\*/?\d+)"
_CRON_RE = re.compile(
    r"(?:^|\s)(("
    + _CRON_FIELD + r"\s+"
    + _CRON_FIELD + r"\s+"
    + _CRON_FIELD + r"\s+"
    + _CRON_FIELD + r"(?:\s+"
    + _CRON_FIELD + r")?"
    r"))(?:\s|$)"
)

_SCHEDULE_PATTERNS: list[tuple[re.Pattern, object]] = [
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
    (re.compile(r"monitor\b", re.I), _monitor_cron),
    (re.compile(r"cada\s+(\d+)\s+minutos?", re.I), _n_minutes),
    (re.compile(r"cada\s+(\d+)\s+horas?", re.I), _n_hours),
    (re.compile(r"\bdiariamente\b", re.I), _cjk_daily),
    (re.compile(r"cada\s+día\b", re.I), _cjk_daily),
    (re.compile(r"\bsemanalmente\b", re.I), _cjk_weekly),
    (re.compile(r"cada\s+semana\b", re.I), _cjk_weekly),
    (re.compile(r"chaque\s+(\d+)\s+minutes?", re.I), _n_minutes),
    (re.compile(r"toutes?\s+les?\s+(\d+)\s+minutes?", re.I), _n_minutes),
    (re.compile(r"toutes?\s+les?\s+(\d+)\s+heures?", re.I), _n_hours),
    (re.compile(r"chaque\s+heure\b", re.I), _cjk_hourly),
    (re.compile(r"\bquotidienne?(?:ment)?\b", re.I), _cjk_daily),
    (re.compile(r"tous\s+les\s+jours\b", re.I), _cjk_daily),
    (re.compile(r"\bhebdomadaire\b", re.I), _cjk_weekly),
    (re.compile(r"tous?\s+les?\s+(\d+)\s+minutes?", re.I), _n_minutes),
    (re.compile(r"alle\s+(\d+)\s+minuten?", re.I), _n_minutes),
    (re.compile(r"alle\s+(\d+)\s+stunden?", re.I), _n_hours),
    (re.compile(r"alle\s+(\d+)\s+stunden?", re.I), _n_hours),
    (re.compile(r"\btäglich\b", re.I), _cjk_daily),
    (re.compile(r"\bstündlich\b", re.I), _cjk_hourly),
    (re.compile(r"wöchentlich", re.I), _cjk_weekly),
    (re.compile(r"每(\d+)分钟"), _cjk_minutes),
    (re.compile(r"每(\d+)小[时時]"), _cjk_hours),
    (re.compile(r"每天"), _cjk_daily),
    (re.compile(r"每小[时時]"), _cjk_hourly),
    (re.compile(r"每[周週]"), _cjk_weekly),
    (re.compile(r"监控"), _monitor_cron),
    (re.compile(r"監控"), _monitor_cron),
    (re.compile(r"毎日"), _cjk_daily),
    (re.compile(r"毎時"), _cjk_hourly),
    (re.compile(r"毎(\d+)分"), _cjk_minutes),
    (re.compile(r"毎(\d+)時間"), _cjk_hours),
    (re.compile(r"毎週"), _cjk_weekly),
    (re.compile(r"モニターリング?"), _monitor_cron),
    (re.compile(r"매\s*(\d+)\s*분"), _cjk_minutes),
    (re.compile(r"매\s*(\d+)\s*시간"), _cjk_hours),
    (re.compile(r"매일"), _cjk_daily),
    (re.compile(r"매시간?"), _cjk_hourly),
    (re.compile(r"매주"), _cjk_weekly),
    (re.compile(r"모니터링"), _monitor_cron),
    (re.compile(r"toda\s+hora\b", re.I), _cjk_hourly),
    (re.compile(r"todos?\s+os?\s+dias?\b", re.I), _cjk_daily),
    (re.compile(r"\bsemanal(?:mente)?\b", re.I), _cjk_weekly),
    (re.compile(r"كل\s+(\d+)\s+دقيق[ةه]"), _n_minutes),
    (re.compile(r"كل\s+(\d+)\s+ساع[ةه]"), _n_hours),
    (re.compile(r"يومياً?"), _cjk_daily),
    (re.compile(r"كل\s+يوم"), _cjk_daily),
    (re.compile(r"كل\s+ساع[ةه]"), _cjk_hourly),
    (re.compile(r"أسبوعياً?"), _cjk_weekly),
    (re.compile(r"كل\s+أسبوع"), _cjk_weekly),
    (re.compile(r"مراقب[ةه]"), _monitor_cron),
    (re.compile(r"हर\s*(\d+)\s*मिनट"), _n_minutes),
    (re.compile(r"हर\s*(\d+)\s*घंट"), _n_hours),
    (re.compile(r"रोज़?"), _cjk_daily),
    (re.compile(r"हर\s*घंट"), _cjk_hourly),
    (re.compile(r"हर\s*हफ़्त"), _cjk_weekly),
    (re.compile(r"निगरानी"), _monitor_cron),
    (re.compile(r"setiap\s+(\d+)\s+menit", re.I), _n_minutes),
    (re.compile(r"setiap\s+(\d+)\s+jam", re.I), _n_hours),
    (re.compile(r"setiap\s+hari\b", re.I), _cjk_daily),
    (re.compile(r"setiap\s+jam\b", re.I), _cjk_hourly),
    (re.compile(r"setiap\s+minggu\b", re.I), _cjk_weekly),
    (re.compile(r"pantau", re.I), _monitor_cron),
    (re.compile(r"каждые?\s*(\d+)\s*минут"), _n_minutes),
    (re.compile(r"каждые?\s*(\d+)\s*час"), _n_hours),
    (re.compile(r"ежедневно"), _cjk_daily),
    (re.compile(r"каждый\s+день"), _cjk_daily),
    (re.compile(r"каждый\s+час"), _cjk_hourly),
    (re.compile(r"еженедельно"), _cjk_weekly),
    (re.compile(r"каждую\s+неделю"), _cjk_weekly),
    (re.compile(r"мониторинг"), _monitor_cron),
    (re.compile(r"her\s+(\d+)\s+dakika", re.I), _n_minutes),
    (re.compile(r"her\s+(\d+)\s+saat", re.I), _n_hours),
    (re.compile(r"her\s+gün\b", re.I), _cjk_daily),
    (re.compile(r"\bgünlük\b", re.I), _cjk_daily),
    (re.compile(r"her\s+saat\b", re.I), _cjk_hourly),
    (re.compile(r"her\s+hafta\b", re.I), _cjk_weekly),
    (re.compile(r"\bhaftalık\b", re.I), _cjk_weekly),
    (re.compile(r"\bizle\b", re.I), _monitor_cron),
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
    re.compile(r"\s*并?\s*(?:每|每隔?)\s*\d+\s*(?:分钟|小时|秒|天|周|週)"),
    re.compile(r"\s*(?:每|每隔?)\s*(?:天|小[时時]|周|週|分钟|分鐘)"),
    re.compile(r"\s*(?:监控|監控)"),
    re.compile(r"\s*毎\d+分"),
    re.compile(r"\s*毎\d+時間"),
    re.compile(r"\s*(?:毎日|毎時|毎週)"),
    re.compile(r"\s*(?:モニターリング?|監視)"),
    re.compile(r"\s*매\s*\d+\s*(?:분|시간)"),
    re.compile(r"\s*(?:매일|매시간?|매주|모니터링)"),
    re.compile(r"\s*(?:cada|todos?\s*los?)\s+\d+\s*(?:minutos?|horas?|días?)", re.I),
    re.compile(r"\s*(?:diariamente|semanalmente|cada\s+(?:día|semana))", re.I),
    re.compile(r"\s*(?:chaque|tous\s*les?)\s+\d+\s*(?:minutes?|heures?)", re.I),
    re.compile(r"\s*(?:quotidienne?ment?|hebdomadaire|chaque\s+(?:jour|heure))", re.I),
    re.compile(r"\s*(?:alle|jede[rs]?)\s+\d+\s*(?:minuten?|stunden?)", re.I),
    re.compile(r"\s*(?:täglich|stündlich|wöchentlich)", re.I),
    re.compile(r"\s*(?:كل|كُل)\s*\d*\s*(?:دقيق[ةه]|ساع[ةه]|يوم|أسبوع)"),
    re.compile(r"\s*(?:يومياً?|أسبوعياً?|كل\s+(?:يوم|ساع[ةه]|أسبوع))"),
    re.compile(r"\s*(?:مراقب[ةه])"),
    re.compile(r"\s*(?:हर|के?\s*हर)\s*\d*\s*(?:मिनट|घंट|हफ़्त)"),
    re.compile(r"\s*(?:रोज़?|निगरानी)"),
    re.compile(r"\s*(?:setiap)\s+\d+\s*(?:menit|jam)", re.I),
    re.compile(r"\s*(?:setiap)\s+(?:hari|jam|minggu)", re.I),
    re.compile(r"\s*(?:pantau)", re.I),
    re.compile(r"\s*(?:каждые?\s*каждую?)\s*\d*\s*(?:минут|час|день|неделю)"),
    re.compile(r"\s*(?:ежедневно|еженедельно|каждый\s+(?:день|час)|каждую\s+неделю|мониторинг)"),
    re.compile(r"\s*(?:her)\s+\d+\s*(?:dakika|saat)", re.I),
    re.compile(r"\s*(?:her\s+(?:gün|saat|hafta)|günlük|haftalık|izle)", re.I),
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
        cron_expr = self._detect_raw_cron(task)
        if cron_expr:
            schedule_task = self._extract_schedule_task(task)
            return ScheduleIntent(cron=cron_expr, task=schedule_task)

        for pattern, cron_fn in _SCHEDULE_PATTERNS:
            m = pattern.search(task)
            if m:
                cron_expr = cron_fn(m)
                schedule_task = self._extract_schedule_task(task)
                return ScheduleIntent(cron=cron_expr, task=schedule_task)
        return None

    def _detect_raw_cron(self, task: str) -> str | None:
        m = _CRON_RE.search(task)
        if m:
            candidate = m.group(1).strip()
            parts = candidate.split()
            if 4 <= len(parts) <= 5:
                from sediman.scheduler.cron import validate_cron_expr
                try:
                    if validate_cron_expr(candidate):
                        return candidate
                except Exception:
                    pass
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
