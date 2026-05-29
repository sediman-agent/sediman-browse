from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.scheduler.cron import (
    CronManager,
    CronScheduler,
    _CronResources,
    _suppress_logging,
    _SUPRESSED_LOGGERS,
    execute_cron_job,
    _get_shared_resources,
)


class TestSuppressLogging:
    def test_suppresses_specified_loggers(self):
        for name in _SUPRESSED_LOGGERS:
            logging.getLogger(name).setLevel(logging.DEBUG)

        with _suppress_logging():
            for name in _SUPRESSED_LOGGERS:
                assert logging.getLogger(name).level == logging.CRITICAL

    def test_restores_original_levels(self):
        test_logger = logging.getLogger("browser_use")
        original = test_logger.level
        if original == logging.CRITICAL:
            test_logger.setLevel(logging.DEBUG)
            original = logging.DEBUG

        with _suppress_logging():
            pass

        assert logging.getLogger("browser_use").level == original

    def test_restores_on_exception(self):
        test_logger = logging.getLogger("sediman")
        test_logger.setLevel(logging.WARNING)
        original = test_logger.level

        try:
            with _suppress_logging():
                raise ValueError("test")
        except ValueError:
            pass

        assert logging.getLogger("sediman").level == original

    def test_does_not_affect_unrelated_loggers(self):
        lg = logging.getLogger("my_custom_logger")
        lg.setLevel(logging.INFO)

        with _suppress_logging():
            assert lg.level == logging.INFO


class TestCronResources:
    @pytest.mark.asyncio
    async def test_initializes_once(self):
        resources = _CronResources()
        assert resources._initialized is False

        with patch("sediman.store.db.init_db", new_callable=AsyncMock), \
             patch("sediman.llm.provider.create_provider", return_value=MagicMock()), \
             patch("sediman.browser.session.BrowserSession") as MockBS:
            mock_bs = AsyncMock()
            MockBS.return_value = mock_bs

            await resources.ensure_initialized()
            assert resources._initialized is True
            assert resources.llm is not None
            assert resources.browser is not None

            first_llm = resources.llm
            await resources.ensure_initialized()
            assert resources.llm is first_llm

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        resources = _CronResources()
        resources._initialized = True
        mock_browser = AsyncMock()
        resources.browser = mock_browser
        resources.llm = MagicMock()

        await resources.shutdown()
        assert resources._initialized is False
        assert resources.browser is None
        mock_browser.stop.assert_awaited()

    @pytest.mark.asyncio
    async def test_shutdown_noop_when_not_initialized(self):
        resources = _CronResources()
        await resources.shutdown()
        assert resources._initialized is False

    @pytest.mark.asyncio
    async def test_concurrent_initialize_only_runs_once(self):
        resources = _CronResources()
        init_count = 0

        async def mock_init():
            nonlocal init_count
            init_count += 1

        with patch("sediman.store.db.init_db", new_callable=AsyncMock, side_effect=mock_init), \
             patch("sediman.llm.provider.create_provider", return_value=MagicMock()), \
             patch("sediman.browser.session.BrowserSession") as MockBS:
            MockBS.return_value = AsyncMock()

            await asyncio.gather(
                resources.ensure_initialized(),
                resources.ensure_initialized(),
                resources.ensure_initialized(),
            )

        assert init_count == 1


class TestGetSharedResources:
    def test_returns_singleton(self):
        import sediman.scheduler.cron as mod
        old = mod._shared_resources
        try:
            mod._shared_resources = None
            r1 = _get_shared_resources()
            r2 = _get_shared_resources()
            assert r1 is r2
        finally:
            mod._shared_resources = old

    def test_creates_new_if_none(self):
        import sediman.scheduler.cron as mod
        old = mod._shared_resources
        try:
            mod._shared_resources = None
            r = _get_shared_resources()
            assert isinstance(r, _CronResources)
        finally:
            mod._shared_resources = old


class TestExecuteCronJobResourceReuse:
    @pytest.mark.asyncio
    async def test_uses_shared_resources_for_default_provider(self):
        job = {"id": "abc123", "task": "test", "provider": "openai"}

        mock_resources = MagicMock()
        mock_resources.ensure_initialized = AsyncMock()
        mock_resources.llm = MagicMock()
        mock_resources.browser = MagicMock()

        with patch("sediman.scheduler.cron._get_shared_resources", return_value=mock_resources), \
             patch("sediman.agent.loop.AgentLoop") as MockAL:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=MagicMock(result="done"))
            MockAL.return_value = mock_instance

            result = await execute_cron_job(job)

        mock_resources.ensure_initialized.assert_awaited_once()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_creates_own_resources_for_custom_provider(self):
        job = {"id": "abc123", "task": "test", "provider": "ollama", "model": "qwen"}

        with patch("sediman.llm.provider.create_provider", return_value=MagicMock()) as mock_cp, \
             patch("sediman.store.db.init_db", new_callable=AsyncMock), \
             patch("sediman.browser.session.BrowserSession") as MockBS, \
             patch("sediman.agent.loop.AgentLoop") as MockAL:
            mock_bs = AsyncMock()
            MockBS.return_value = mock_bs
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=MagicMock(result="done"))
            MockAL.return_value = mock_instance

            result = await execute_cron_job(job)

        mock_cp.assert_called_once_with(provider="ollama", model="qwen", base_url=None)
        mock_bs.start.assert_awaited_once()
        mock_bs.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_closes_own_browser_on_custom_provider(self):
        job = {"id": "abc123", "task": "test", "provider": "ollama", "model": "qwen"}

        with patch("sediman.llm.provider.create_provider", return_value=MagicMock()), \
             patch("sediman.store.db.init_db", new_callable=AsyncMock), \
             patch("sediman.browser.session.BrowserSession") as MockBS, \
             patch("sediman.agent.loop.AgentLoop") as MockAL:
            mock_bs = AsyncMock()
            MockBS.return_value = mock_bs
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=MagicMock(result="ok"))
            MockAL.return_value = mock_instance

            await execute_cron_job(job)

        mock_bs.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_close_shared_browser(self):
        job = {"id": "abc123", "task": "test", "provider": "openai"}

        mock_browser = MagicMock()
        mock_resources = MagicMock()
        mock_resources.ensure_initialized = AsyncMock()
        mock_resources.llm = MagicMock()
        mock_resources.browser = mock_browser

        with patch("sediman.scheduler.cron._get_shared_resources", return_value=mock_resources), \
             patch("sediman.agent.loop.AgentLoop") as MockAL:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=MagicMock(result="done"))
            MockAL.return_value = mock_instance

            await execute_cron_job(job)

        assert not hasattr(mock_browser, 'stop') or not mock_browser.stop.called

    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        job = {"id": "abc123", "task": "test"}

        with patch("sediman.scheduler.cron._execute_cron_job_inner", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            result = await execute_cron_job(job)

        assert "error" in result
        assert "boom" in result

    @pytest.mark.asyncio
    async def test_skill_not_found(self):
        job = {"id": "abc123", "task": "test", "provider": "openai", "skill_name": "missing-skill"}

        mock_resources = MagicMock()
        mock_resources.ensure_initialized = AsyncMock()
        mock_resources.llm = MagicMock()
        mock_resources.browser = MagicMock()

        with patch("sediman.scheduler.cron._get_shared_resources", return_value=mock_resources), \
             patch("sediman.skills.engine.SkillEngine") as MockSE:
            mock_engine = MagicMock()
            mock_engine.read.return_value = None
            MockSE.return_value = mock_engine

            with patch("sediman.scheduler.cron.CronManager") as MockCM:
                mock_cm = MagicMock()
                MockCM.return_value = mock_cm

                result = await execute_cron_job(job)

        assert "not found" in result


class TestCronSchedulerHotReload:
    @pytest.fixture
    def cron_dir(self, tmp_path: Path):
        d = tmp_path / "cron"
        d.mkdir()
        return d

    @pytest.mark.asyncio
    async def test_start_and_stop(self, cron_dir):
        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            sched = CronScheduler()
            mock_aps = MagicMock()
            sched._scheduler = mock_aps

            sched.stop()
            mock_aps.shutdown.assert_called_once()
            assert sched._scheduler is None
            assert sched._running is False

    def test_stop_noop_when_not_started(self):
        sched = CronScheduler()
        sched.stop()
        assert sched._scheduler is None

    def test_reload_noop_when_not_started(self):
        sched = CronScheduler()
        sched.reload()
        assert sched._scheduler is None

    def test_reload_removes_and_reloads_jobs(self, cron_dir):
        job_file = cron_dir / "abc123456789.json"
        job_file.write_text(json.dumps({
            "id": "abc123456789",
            "cron": "0 * * * *",
            "task": "test",
            "enabled": True,
        }))

        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            sched = CronScheduler()
            mock_aps = MagicMock()
            sched._scheduler = mock_aps

            sched.reload()

            mock_aps.remove_all_jobs.assert_called_once()
            mock_aps.add_job.assert_called_once()
            call_args = mock_aps.add_job.call_args
            assert call_args.kwargs["id"] == "abc123456789"

    def test_reload_skips_disabled_jobs(self, cron_dir):
        job_file = cron_dir / "disabled.json"
        job_file.write_text(json.dumps({
            "id": "disabled1234",
            "cron": "0 * * * *",
            "task": "test",
            "enabled": False,
        }))

        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            sched = CronScheduler()
            mock_aps = MagicMock()
            sched._scheduler = mock_aps

            sched.reload()

            mock_aps.add_job.assert_not_called()

    def test_reload_skips_invalid_cron(self, cron_dir):
        job_file = cron_dir / "bad.json"
        job_file.write_text(json.dumps({
            "id": "bad123456789",
            "cron": "invalid",
            "task": "test",
            "enabled": True,
        }))

        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            sched = CronScheduler()
            mock_aps = MagicMock()
            sched._scheduler = mock_aps

            sched.reload()

            mock_aps.add_job.assert_not_called()

    def test_load_jobs_with_multiple(self, cron_dir):
        for i in range(3):
            job_file = cron_dir / f"job{i:012x}.json"
            job_file.write_text(json.dumps({
                "id": f"job{i:012x}",
                "cron": "0 * * * *",
                "task": f"task {i}",
                "enabled": True,
            }))

        with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
            sched = CronScheduler()
            mock_aps = MagicMock()
            sched._scheduler = mock_aps

            sched._load_jobs()

            assert mock_aps.add_job.call_count == 3
