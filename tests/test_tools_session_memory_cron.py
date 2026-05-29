from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from sediman.agent.tools import (
    create_agent_tool_registry,
    set_memory_manager,
)
from sediman.memory.sessions import save_session
from sediman.scheduler.cron import CronManager
from sediman.store.db import init_db


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_sediman_dir):
    with patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir):
        await init_db()
    yield tmp_sediman_dir


@pytest_asyncio.fixture
async def db_with_sessions(db):
    with patch("sediman.store.db.DEFAULT_DATA_DIR", db):
        sid1 = await save_session(
            task="search for python tutorials on youtube",
            steps=[
                {"action": "navigate to youtube.com", "observation": "page loaded"},
                {"action": "type 'python tutorial' in search", "observation": "results shown"},
            ],
            result="found 3 good python tutorials",
        )
        sid2 = await save_session(
            task="check apple stock price on yahoo finance",
            steps=[
                {"action": "go to finance.yahoo.com", "observation": "loaded"},
                {"action": "type AAPL in search", "observation": "stock page shown"},
            ],
            result="AAPL price is $198.50",
        )
        sid3 = await save_session(
            task="order pizza from dominos",
            steps=[
                {"action": "navigate to dominos.com", "observation": "loaded"},
                {"action": "click order online", "observation": "menu shown"},
            ],
            result="pizza ordered successfully",
        )
    return {"session_ids": [sid1, sid2, sid3], "tmp_dir": db}


# ── Session Search Tool Tests ───────────────────────────────────────────

class TestSessionSearchTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.registry = create_agent_tool_registry()

    @pytest.mark.asyncio
    async def test_search_by_query(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"query": "python"},
            )
        assert result.success
        assert "python" in result.output.lower()
        assert len(result.data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_search_no_match(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"query": "zzzznonexistent"},
            )
        assert result.success
        assert "No sessions found" in result.output
        assert result.data["results"] == []

    @pytest.mark.asyncio
    async def test_search_matches_result_text(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"query": "AAPL"},
            )
        assert result.success
        assert len(result.data["results"]) >= 1

    @pytest.mark.asyncio
    async def test_browse_recent_sessions(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch("session_search", {})
        assert result.success
        assert "Recent sessions" in result.output
        assert result.data["count"] >= 2

    @pytest.mark.asyncio
    async def test_browse_limit(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"limit": 1},
            )
        assert result.success
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_scroll_session_by_id(self, db_with_sessions):
        sid = db_with_sessions["session_ids"][0]
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"session_id": sid},
            )
        assert result.success
        assert "search for python tutorials" in result.output
        assert "youtube" in result.output

    @pytest.mark.asyncio
    async def test_scroll_nonexistent_session(self, db_with_sessions):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db_with_sessions["tmp_dir"]):
            result = await self.registry.dispatch(
                "session_search",
                {"session_id": "nonexistent"},
            )
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failure(self):
        with patch(
            "sediman.memory.sessions.search_sessions",
            new_callable=AsyncMock,
            side_effect=Exception("db error"),
        ):
            result = await self.registry.dispatch(
                "session_search",
                {"query": "test"},
            )
        assert not result.success
        assert "db error" in result.output

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, db):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db):
            result = await self.registry.dispatch(
                "session_search",
                {"query": "anything"},
            )
        assert result.success
        assert result.data["results"] == []

    @pytest.mark.asyncio
    async def test_empty_db_browse(self, db):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", db):
            result = await self.registry.dispatch("session_search", {})
        assert result.success
        assert "No sessions found" in result.output


# ── Memory Tool Tests ──────────────────────────────────────────────────

class TestMemoryTool:
    _saved_mgr: object = None

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.registry = create_agent_tool_registry()

    @pytest.mark.asyncio
    async def test_add_entry(self):
        mgr = MagicMock()
        mgr.handle_tool_call = AsyncMock(return_value="Added to memory.\n  MEMORY usage: 10%/2200 chars, 1 entries\n  1. test fact")
        set_memory_manager(mgr)
        result = await self.registry.dispatch(
            "memory",
            {"action": "add", "target": "memory", "content": "test fact"},
        )
        assert result.success
        assert "Added to memory" in result.output
        mgr.handle_tool_call.assert_called_once_with(
            "memory",
            {"action": "add", "target": "memory", "content": "test fact", "old_entry": ""},
        )

    @pytest.mark.asyncio
    async def test_replace_entry(self):
        mgr = MagicMock()
        mgr.handle_tool_call = AsyncMock(return_value="Replaced in memory.")
        set_memory_manager(mgr)
        result = await self.registry.dispatch(
            "memory",
            {
                "action": "replace",
                "target": "memory",
                "content": "updated fact",
                "old_entry": "old fact",
            },
        )
        assert result.success
        assert "Replaced" in result.output
        mgr.handle_tool_call.assert_called_once_with(
            "memory",
            {"action": "replace", "target": "memory", "content": "updated fact", "old_entry": "old fact"},
        )

    @pytest.mark.asyncio
    async def test_remove_entry(self):
        mgr = MagicMock()
        mgr.handle_tool_call = AsyncMock(return_value="Removed from memory.")
        set_memory_manager(mgr)
        result = await self.registry.dispatch(
            "memory",
            {"action": "remove", "target": "memory", "old_entry": "old fact"},
        )
        assert result.success
        assert "Removed" in result.output

    @pytest.mark.asyncio
    async def test_add_to_user_target(self):
        mgr = MagicMock()
        mgr.handle_tool_call = AsyncMock(return_value="Added to user.")
        set_memory_manager(mgr)
        result = await self.registry.dispatch(
            "memory",
            {"action": "add", "target": "user", "content": "user preference"},
        )
        assert result.success
        mgr.handle_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_manager_returns_error(self):
        set_memory_manager(None)
        result = await self.registry.dispatch(
            "memory",
            {"action": "add", "target": "memory", "content": "test"},
        )
        assert not result.success
        assert "not available" in result.output

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failure(self):
        mgr = MagicMock()
        mgr.handle_tool_call = AsyncMock(side_effect=Exception("memory error"))
        set_memory_manager(mgr)
        result = await self.registry.dispatch(
            "memory",
            {"action": "add", "target": "memory", "content": "test"},
        )
        assert not result.success
        assert "memory error" in result.output


# ── Cronjob Tool Tests ────────────────────────────────────────────────

class TestCronjobTool:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_sediman_dir):
        self.registry = create_agent_tool_registry()

    @pytest.mark.asyncio
    async def test_create_job(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "create", "cron": "0 9 * * *", "task": "daily report"},
            )
        assert result.success
        assert "created" in result.output.lower()
        assert "0 9 * * *" in result.output
        assert "daily report" in result.output
        assert result.data["job_id"] is not None

    @pytest.mark.asyncio
    async def test_create_with_skill(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {
                    "action": "create",
                    "cron": "*/30 * * * *",
                    "task": "check stock",
                    "skill_name": "stock-checker",
                },
            )
        assert result.success
        assert result.data["job_id"] is not None

    @pytest.mark.asyncio
    async def test_create_missing_cron(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "create", "task": "no cron"},
            )
        assert not result.success
        assert "cron and task" in result.output

    @pytest.mark.asyncio
    async def test_create_missing_task(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "create", "cron": "0 * * * *"},
            )
        assert not result.success
        assert "cron and task" in result.output

    @pytest.mark.asyncio
    async def test_create_invalid_cron(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "create", "cron": "bad", "task": "test"},
            )
        assert not result.success
        assert "Invalid cron" in result.output

    @pytest.mark.asyncio
    async def test_list_jobs(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            cron.add_job(cron_expr="0 9 * * *", task="morning task")
            cron.add_job(cron_expr="0 18 * * *", task="evening task")
            result = await self.registry.dispatch("cronjob", {"action": "list"})
        assert result.success
        assert "Scheduled jobs" in result.output
        assert "morning task" in result.output
        assert "evening task" in result.output
        assert result.data["jobs"] is not None

    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch("cronjob", {"action": "list"})
        assert result.success
        assert "No scheduled jobs" in result.output
        assert result.data["jobs"] == []

    @pytest.mark.asyncio
    async def test_view_job(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="hourly check")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "view", "job_id": jid},
            )
        assert result.success
        assert "hourly check" in result.output
        assert "0 * * * *" in result.output

    @pytest.mark.asyncio
    async def test_view_nonexistent(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "view", "job_id": "nonexistent"},
            )
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_view_missing_id(self):
        result = await self.registry.dispatch("cronjob", {"action": "view"})
        assert not result.success
        assert "job_id is required" in result.output

    @pytest.mark.asyncio
    async def test_update_cron(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="t")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": jid, "cron": "*/5 * * * *"},
            )
        assert result.success
        assert "updated" in result.output.lower()
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            job = cron.get_job(jid)
        assert job["cron"] == "*/5 * * * *"

    @pytest.mark.asyncio
    async def test_update_task(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="old")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": jid, "task": "new"},
            )
        assert result.success
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            job = cron.get_job(jid)
        assert job["task"] == "new"

    @pytest.mark.asyncio
    async def test_update_enabled(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="t")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": jid, "enabled": False},
            )
        assert result.success
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            job = cron.get_job(jid)
        assert job["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="old")
            result = await self.registry.dispatch(
                "cronjob",
                {
                    "action": "update",
                    "job_id": jid,
                    "cron": "0 9 * * *",
                    "task": "new",
                    "enabled": False,
                },
            )
        assert result.success
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            job = cron.get_job(jid)
        assert job["cron"] == "0 9 * * *"
        assert job["task"] == "new"
        assert job["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_no_fields(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="t")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": jid},
            )
        assert not result.success
        assert "Nothing to update" in result.output

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": "nonexistent", "task": "new"},
            )
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_update_invalid_cron(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="t")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "update", "job_id": jid, "cron": "bad"},
            )
        assert not result.success
        assert "Invalid cron" in result.output

    @pytest.mark.asyncio
    async def test_remove_job(self, tmp_sediman_dir):
        cron_dir = tmp_sediman_dir / "cron"
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            cron = CronManager()
            jid = cron.add_job(cron_expr="0 * * * *", task="t")
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "remove", "job_id": jid},
            )
        assert result.success
        assert "removed" in result.output.lower()
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            assert cron.get_job(jid) is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            result = await self.registry.dispatch(
                "cronjob",
                {"action": "remove", "job_id": "nonexistent"},
            )
        assert not result.success
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_remove_missing_id(self):
        result = await self.registry.dispatch("cronjob", {"action": "remove"})
        assert not result.success
        assert "job_id is required" in result.output

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        result = await self.registry.dispatch(
            "cronjob",
            {"action": "unknown_action"},
        )
        assert not result.success
        assert "Unknown action" in result.output

    @pytest.mark.asyncio
    async def test_create_and_list_roundtrip(self, tmp_sediman_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"):
            await self.registry.dispatch(
                "cronjob",
                {"action": "create", "cron": "0 9 * * *", "task": "daily summary"},
            )
            result = await self.registry.dispatch("cronjob", {"action": "list"})
        assert result.success
        assert "daily summary" in result.output

    @pytest.mark.asyncio
    async def test_handler_exception_returns_failure(self):
        with patch(
            "sediman.scheduler.cron.CronManager.list_jobs",
            side_effect=Exception("cron error"),
        ):
            result = await self.registry.dispatch("cronjob", {"action": "list"})
        assert not result.success
        assert "cron error" in result.output
