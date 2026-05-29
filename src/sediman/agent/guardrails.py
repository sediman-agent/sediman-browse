from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class TraceSpan:
    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    operation: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 1),
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class Trace:
    trace_id: str
    spans: list[TraceSpan] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def new_span(self, operation: str, parent: TraceSpan | None = None, **attrs: Any) -> TraceSpan:
        span = TraceSpan(
            span_id=uuid.uuid4().hex[:16],
            trace_id=self.trace_id,
            parent_span_id=parent.span_id if parent else None,
            operation=operation,
            start_time=time.time(),
            attributes=attrs,
        )
        self.spans.append(span)
        return span

    def finish_span(self, span: TraceSpan, status: str = "ok", **attrs: Any) -> None:
        span.end_time = time.time()
        span.status = status
        span.attributes.update(attrs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "start_time": self.start_time,
            "duration_ms": round((time.time() - self.start_time) * 1000, 1),
            "spans": [s.to_dict() for s in self.spans],
            "span_count": len(self.spans),
        }


class TraceCollector:
    _instance: TraceCollector | None = None

    def __init__(self, max_traces: int = 100):
        self._traces: list[Trace] = []
        self._max_traces = max_traces
        self._current_trace: Trace | None = None

    @classmethod
    def get(cls) -> TraceCollector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_trace(self, operation: str = "", **attrs: Any) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex[:16])
        self._current_trace = trace
        if operation:
            span = trace.new_span(operation, **attrs)
            span.start_time = trace.start_time
        self._traces.append(trace)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces:]
        return trace

    @property
    def current_trace(self) -> Trace | None:
        return self._current_trace

    @property
    def traces(self) -> list[Trace]:
        return list(self._traces)

    def clear(self) -> None:
        self._traces.clear()


@dataclass
class AuditEntry:
    timestamp: float
    category: str
    decision: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "category": self.category,
            "decision": self.decision,
            "reason": self.reason,
            "details": self.details,
        }


class AuditLog:
    _instance: AuditLog | None = None

    def __init__(self, max_entries: int = 500):
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries

    @classmethod
    def get(cls) -> AuditLog:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record(self, category: str, decision: str, reason: str, **details: Any) -> None:
        entry = AuditEntry(
            timestamp=time.time(),
            category=category,
            decision=decision,
            reason=reason,
            details=details,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        logger.debug("audit", category=category, decision=decision, reason=reason)

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


@dataclass
class SharedScratchpad:
    _data: dict[str, Any] = field(default_factory=dict)
    _version: int = 0

    def write(self, key: str, value: Any, agent_name: str = "") -> None:
        self._data[key] = {"value": value, "author": agent_name, "version": self._version}
        self._version += 1

    def read(self, key: str) -> Any | None:
        entry = self._data.get(key)
        return entry["value"] if entry else None

    def read_all(self) -> dict[str, Any]:
        return {k: v["value"] for k, v in self._data.items()}

    def keys(self) -> list[str]:
        return list(self._data.keys())


@dataclass
class Budget:
    max_replans: int = 3
    max_retries_total: int = 8
    max_wall_seconds: float = 600.0
    max_llm_tokens: int = 200_000
    max_browser_actions: int = 100

    _replans_used: int = 0
    _retries_used: int = 0
    _start_time: float = 0.0
    _tokens_used: int = 0
    _actions_used: int = 0

    def start(self) -> None:
        self._start_time = time.time()

    def check_replan(self) -> bool:
        return self._replans_used < self.max_replans

    def use_replan(self) -> None:
        self._replans_used += 1

    def check_retry(self) -> bool:
        return self._retries_used < self.max_retries_total

    def use_retry(self) -> None:
        self._retries_used += 1

    def check_time(self) -> bool:
        if self._start_time == 0:
            return True
        return (time.time() - self._start_time) < self.max_wall_seconds

    def add_tokens(self, n: int) -> None:
        self._tokens_used += n

    def check_tokens(self) -> bool:
        return self._tokens_used < self.max_llm_tokens

    def add_action(self) -> None:
        self._actions_used += 1

    def check_actions(self) -> bool:
        return self._actions_used < self.max_browser_actions

    def is_exhausted(self) -> tuple[bool, str]:
        if not self.check_time():
            return True, "wall_time"
        if not self.check_tokens():
            return True, "llm_tokens"
        if not self.check_actions():
            return True, "browser_actions"
        return False, ""

    def summary(self) -> dict[str, Any]:
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "replans": f"{self._replans_used}/{self.max_replans}",
            "retries": f"{self._retries_used}/{self.max_retries_total}",
            "elapsed_sec": round(elapsed, 1),
            "tokens": f"{self._tokens_used}/{self.max_llm_tokens}",
            "actions": f"{self._actions_used}/{self.max_browser_actions}",
        }


def plan_hash(description: str, strategy: str) -> str:
    return hashlib.md5(f"{strategy}:{description}".encode()).hexdigest()[:12]


@dataclass
class ApprovalCallback:
    _callback: Callable[[str, dict[str, Any]], Awaitable[bool]] | None = None

    def set_callback(self, cb: Callable[[str, dict[str, Any]], Awaitable[bool]]) -> None:
        self._callback = cb

    async def request(self, action: str, details: dict[str, Any]) -> bool:
        if self._callback is None:
            return True
        try:
            return await self._callback(action, details)
        except Exception:
            return False


GLOBAL_APPROVAL = ApprovalCallback()

_DESTRUCTIVE_TOOLS = {"write_file", "patch", "skill_manage"}
_SAFE_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "pwd", "echo", "which", "whoami",
    "env", "printenv", "date", "uname", "hostname", "id", "df", "du",
    "grep", "rg", "find", "wc", "sort", "uniq", "diff", "file",
    "stat", "tree", "type", "git status", "git log", "git diff",
    "git branch", "git remote", "git show", "git stash list",
})
_RISKY_URL_PATTERNS = [
    "delete", "remove", "unsubscribe", "cancel",
    "purchase", "checkout", "pay", "buy",
    "logout", "signout",
]


def assess_risk(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "terminal":
        command = arguments.get("command", "").strip()
        first_word = command.split()[0] if command.split() else ""
        if first_word in _SAFE_COMMANDS:
            return "low"
        if any(p in command.lower() for p in _RISKY_URL_PATTERNS):
            return "high"
        if any(p in command.lower() for p in ("rm ", "rmdir", "del ", "format", "mkfs", "dd ", "> ", ">> ")):
            return "high"
        return "medium"
    if tool_name in _DESTRUCTIVE_TOOLS:
        return "high"
    if tool_name in ("browser_navigate", "browser_click", "browser_type"):
        url = arguments.get("url", "")
        text = arguments.get("text", "")
        text_lower = (text + " " + url).lower()
        if any(p in text_lower for p in _RISKY_URL_PATTERNS):
            return "high"
    return "low"
