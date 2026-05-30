from __future__ import annotations

import asyncio
import hashlib
import time

import pytest
import pytest_asyncio

from sediman.agent.guardrails import (
    ApprovalCallback,
    assess_risk,
    AuditEntry,
    AuditLog,
    Budget,
    plan_hash,
    SharedScratchpad,
    Trace,
    TraceCollector,
    TraceSpan,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    TraceCollector._instance = None
    AuditLog._instance = None
    yield
    TraceCollector._instance = None
    AuditLog._instance = None


class TestTraceSpan:
    def test_duration_ms(self):
        span = TraceSpan(
            span_id="s1",
            trace_id="t1",
            start_time=1.0,
            end_time=2.5,
        )
        assert span.duration_ms == 1500.0

    def test_duration_ms_zero(self):
        span = TraceSpan(span_id="s1", trace_id="t1", start_time=5.0, end_time=5.0)
        assert span.duration_ms == 0.0

    def test_to_dict_keys(self):
        span = TraceSpan(
            span_id="s1",
            trace_id="t1",
            parent_span_id="p1",
            operation="op",
            start_time=1.0,
            end_time=2.0,
            status="ok",
            attributes={"k": "v"},
            events=[{"e": 1}],
        )
        d = span.to_dict()
        assert set(d.keys()) == {
            "span_id", "trace_id", "parent_span_id", "operation",
            "start_time", "end_time", "duration_ms", "status",
            "attributes", "events",
        }
        assert d["span_id"] == "s1"
        assert d["parent_span_id"] == "p1"
        assert d["duration_ms"] == 1000.0

    def test_defaults(self):
        span = TraceSpan(span_id="x", trace_id="y")
        assert span.parent_span_id is None
        assert span.operation == ""
        assert span.status == "ok"
        assert span.attributes == {}
        assert span.events == []


class TestTrace:
    def test_new_span_basic(self):
        trace = Trace(trace_id="t1")
        span = trace.new_span("do_stuff", foo="bar")
        assert span.trace_id == "t1"
        assert span.operation == "do_stuff"
        assert span.parent_span_id is None
        assert span.attributes == {"foo": "bar"}
        assert len(trace.spans) == 1

    def test_new_span_with_parent(self):
        trace = Trace(trace_id="t1")
        parent = trace.new_span("parent")
        child = trace.new_span("child", parent=parent)
        assert child.parent_span_id == parent.span_id
        assert len(trace.spans) == 2

    def test_finish_span(self):
        trace = Trace(trace_id="t1")
        span = trace.new_span("op")
        trace.finish_span(span, status="error", extra="val")
        assert span.end_time > 0
        assert span.status == "error"
        assert span.attributes["extra"] == "val"

    def test_to_dict_span_count(self):
        trace = Trace(trace_id="t1")
        trace.new_span("a")
        trace.new_span("b")
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert d["span_count"] == 2
        assert len(d["spans"]) == 2
        assert d["duration_ms"] >= 0


class TestTraceCollector:
    def test_singleton(self):
        a = TraceCollector.get()
        b = TraceCollector.get()
        assert a is b

    def test_start_trace(self):
        col = TraceCollector.get()
        trace = col.start_trace("init", step=1)
        assert col.current_trace is trace
        assert len(trace.spans) == 1
        assert trace.spans[0].operation == "init"

    def test_start_trace_no_operation(self):
        col = TraceCollector.get()
        trace = col.start_trace()
        assert col.current_trace is trace
        assert len(trace.spans) == 0

    def test_traces_property_returns_copy(self):
        col = TraceCollector.get()
        col.start_trace("a")
        t = col.traces
        assert len(t) == 1
        t.clear()
        assert len(col.traces) == 1

    def test_clear(self):
        col = TraceCollector.get()
        col.start_trace("x")
        col.start_trace("y")
        assert len(col.traces) == 2
        col.clear()
        assert len(col.traces) == 0

    def test_max_traces_trims_oldest(self):
        col = TraceCollector()
        col._max_traces = 5
        for i in range(8):
            col.start_trace(f"op_{i}")
        assert len(col.traces) == 5
        assert col.traces[0].spans[0].operation == "op_3"

    def test_current_trace_updates(self):
        col = TraceCollector.get()
        t1 = col.start_trace("first")
        assert col.current_trace is t1
        t2 = col.start_trace("second")
        assert col.current_trace is t2
        assert col.current_trace is not t1


class TestAuditEntry:
    def test_to_dict(self):
        entry = AuditEntry(
            timestamp=1000.0,
            category="security",
            decision="allowed",
            reason="safe command",
            details={"tool": "terminal"},
        )
        d = entry.to_dict()
        assert d["timestamp"] == 1000.0
        assert d["category"] == "security"
        assert d["decision"] == "allowed"
        assert d["reason"] == "safe command"
        assert d["details"] == {"tool": "terminal"}

    def test_defaults(self):
        entry = AuditEntry(
            timestamp=0.0, category="x", decision="y", reason="z"
        )
        assert entry.details == {}


class TestAuditLog:
    def test_singleton(self):
        a = AuditLog.get()
        b = AuditLog.get()
        assert a is b

    def test_record_and_entries(self):
        log = AuditLog.get()
        log.record("security", "blocked", "risky command", tool="terminal")
        entries = log.entries
        assert len(entries) == 1
        assert entries[0].category == "security"
        assert entries[0].decision == "blocked"
        assert entries[0].details == {"tool": "terminal"}
        assert entries[0].timestamp > 0

    def test_entries_returns_copy(self):
        log = AuditLog.get()
        log.record("cat", "dec", "reason")
        e = log.entries
        e.clear()
        assert len(log.entries) == 1

    def test_max_entries_trims(self):
        log = AuditLog()
        log._max_entries = 10
        for i in range(15):
            log.record("cat", "dec", f"reason_{i}")
        assert len(log.entries) == 10
        assert log.entries[0].reason == "reason_5"


class TestSharedScratchpad:
    def test_write_and_read(self):
        pad = SharedScratchpad()
        pad.write("key1", "val1", "agent_a")
        assert pad.read("key1") == "val1"

    def test_read_missing_key(self):
        pad = SharedScratchpad()
        assert pad.read("nonexistent") is None

    def test_read_all(self):
        pad = SharedScratchpad()
        pad.write("a", 1, "x")
        pad.write("b", 2, "y")
        assert pad.read_all() == {"a": 1, "b": 2}

    def test_keys(self):
        pad = SharedScratchpad()
        pad.write("x", 1, "a")
        pad.write("y", 2, "b")
        assert set(pad.keys()) == {"x", "y"}

    def test_version_increments(self):
        pad = SharedScratchpad()
        assert pad._version == 0
        pad.write("k", "v", "a")
        assert pad._version == 1
        pad.write("k2", "v2", "a")
        assert pad._version == 2

    def test_overwrite_key(self):
        pad = SharedScratchpad()
        pad.write("k", "old", "a")
        pad.write("k", "new", "b")
        assert pad.read("k") == "new"
        assert pad._version == 2


class TestBudget:
    def test_defaults(self):
        b = Budget()
        assert b.max_replans == 3
        assert b.max_retries_total == 8
        assert b.max_wall_seconds == 600.0
        assert b.max_llm_tokens == 200_000
        assert b.max_browser_actions == 100

    def test_replan_budget(self):
        b = Budget(max_replans=2)
        assert b.check_replan() is True
        b.use_replan()
        assert b.check_replan() is True
        b.use_replan()
        assert b.check_replan() is False

    def test_retry_budget(self):
        b = Budget(max_retries_total=1)
        assert b.check_retry() is True
        b.use_retry()
        assert b.check_retry() is False

    def test_token_budget(self):
        b = Budget(max_llm_tokens=100)
        b.add_tokens(99)
        assert b.check_tokens() is True
        b.add_tokens(1)
        assert b.check_tokens() is False

    def test_action_budget(self):
        b = Budget(max_browser_actions=2)
        b.add_action()
        assert b.check_actions() is True
        b.add_action()
        assert b.check_actions() is False

    def test_check_time_before_start(self):
        b = Budget()
        assert b.check_time() is True

    def test_check_time_after_start(self):
        b = Budget(max_wall_seconds=600)
        b.start()
        assert b.check_time() is True

    def test_is_exhausted_healthy(self):
        b = Budget()
        b.start()
        exhausted, reason = b.is_exhausted()
        assert exhausted is False
        assert reason == ""

    def test_is_exhausted_tokens(self):
        b = Budget(max_llm_tokens=10)
        b.add_tokens(20)
        exhausted, reason = b.is_exhausted()
        assert exhausted is True
        assert reason == "llm_tokens"

    def test_is_exhausted_actions(self):
        b = Budget(max_browser_actions=1)
        b.add_action()
        b.add_action()
        exhausted, reason = b.is_exhausted()
        assert exhausted is True
        assert reason == "browser_actions"

    def test_summary(self):
        b = Budget()
        b.start()
        b.use_replan()
        b.use_retry()
        b.add_tokens(500)
        b.add_action()
        s = b.summary()
        assert s["replans"] == "1/3"
        assert s["retries"] == "1/8"
        assert s["tokens"] == "500/200000"
        assert s["actions"] == "1/100"
        assert s["elapsed_sec"] >= 0


class TestPlanHash:
    def test_deterministic(self):
        h1 = plan_hash("do the thing", "direct")
        h2 = plan_hash("do the thing", "direct")
        assert h1 == h2

    def test_length(self):
        assert len(plan_hash("desc", "strat")) == 12

    def test_different_inputs_different_hash(self):
        h1 = plan_hash("desc a", "direct")
        h2 = plan_hash("desc b", "direct")
        assert h1 != h2

    def test_matches_md5(self):
        desc, strat = "my task", "decompose"
        expected = hashlib.md5(f"{strat}:{desc}".encode()).hexdigest()[:12]
        assert plan_hash(desc, strat) == expected


class TestApprovalCallback:
    @pytest.mark.asyncio
    async def test_no_callback_returns_true(self):
        cb = ApprovalCallback()
        assert await cb.request("action", {}) is True

    @pytest.mark.asyncio
    async def test_callback_approves(self):
        async def approve(action, details):
            return True

        cb = ApprovalCallback()
        cb.set_callback(approve)
        assert await cb.request("action", {"k": "v"}) is True

    @pytest.mark.asyncio
    async def test_callback_rejects(self):
        async def reject(action, details):
            return False

        cb = ApprovalCallback()
        cb.set_callback(reject)
        assert await cb.request("action", {}) is False

    @pytest.mark.asyncio
    async def test_callback_exception_returns_false(self):
        async def boom(action, details):
            raise RuntimeError("fail")

        cb = ApprovalCallback()
        cb.set_callback(boom)
        assert await cb.request("action", {}) is False


class TestAssessRisk:
    def test_terminal_safe_command(self):
        for cmd in ["ls", "pwd", "cat file.txt", "echo hello"]:
            assert assess_risk("terminal", {"command": cmd}) == "low"

    def test_terminal_git_commands_medium(self):
        assert assess_risk("terminal", {"command": "git status"}) == "medium"

    def test_terminal_risky_rm(self):
        assert assess_risk("terminal", {"command": "rm -rf /"}) == "high"

    def test_terminal_risky_pattern_delete(self):
        assert assess_risk("terminal", {"command": "curl -X delete url"}) == "high"

    def test_terminal_medium_default(self):
        assert assess_risk("terminal", {"command": "curl https://example.com"}) == "medium"

    def test_terminal_empty_command(self):
        assert assess_risk("terminal", {"command": ""}) == "medium"

    def test_destructive_tools_high(self):
        for tool in ["write_file", "patch", "skill_manage"]:
            assert assess_risk(tool, {}) == "high"

    def test_browser_risky_url(self):
        assert assess_risk("browser_navigate", {"url": "https://example.com/delete"}) == "high"

    def test_browser_risky_text(self):
        assert assess_risk("browser_click", {"text": "Purchase now"}) == "high"

    def test_browser_safe(self):
        assert assess_risk("browser_navigate", {"url": "https://example.com/search"}) == "low"

    def test_browser_type_risky(self):
        assert assess_risk("browser_type", {"text": "checkout", "url": ""}) == "high"

    def test_unknown_tool_low(self):
        assert assess_risk("read_file", {}) == "low"

    def test_terminal_risky_dd(self):
        assert assess_risk("terminal", {"command": "dd if=/dev/zero of=/dev/sda"}) == "high"

    def test_terminal_risky_redirect(self):
        assert assess_risk("terminal", {"command": "> /etc/passwd"}) == "high"

    def test_terminal_risky_format(self):
        assert assess_risk("terminal", {"command": "format C:"}) == "high"
