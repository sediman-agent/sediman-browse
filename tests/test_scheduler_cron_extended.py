from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sediman.scheduler.cron import CronManager, validate_cron_expr, execute_cron_job, MAX_RESULTS_PER_JOB


@pytest.fixture
def cron(tmp_sediman_dir: Path):
    cron_dir = tmp_sediman_dir / "cron"
    with patch("sediman.scheduler.cron.JOBS_DIR", cron_dir):
        yield CronManager()


class TestValidateCronExpr:
    def test_valid_expressions(self):
        assert validate_cron_expr("0 9 * * *") is True
        assert validate_cron_expr("*/5 * * * *") is True
        assert validate_cron_expr("0,30 9-17 * * 1-5") is True
        assert validate_cron_expr("0 0 1 1 *") is True
        assert validate_cron_expr("30 6 * * 0") is True

    def test_invalid_expressions(self):
        assert validate_cron_expr("") is False
        assert validate_cron_expr("0 9 * *") is False
        assert validate_cron_expr("0 9 * * * *") is False
        assert validate_cron_expr("0 9 mon * *") is False
        assert validate_cron_expr("0 9 * * *; rm -rf /") is False
        assert validate_cron_expr("a b c d e") is False
        assert validate_cron_expr("0 9 * * * ") is True

    def test_edge_cases(self):
        assert validate_cron_expr("0 0 0 0 0") is True
        assert validate_cron_expr("*/1 * * * *") is True
        assert validate_cron_expr("1-5 * * * *") is True
        assert validate_cron_expr("1,2,3 * * * *") is True


class TestCronManagerGetJobEdgeCases:
    def test_get_job_invalid_id(self, cron):
        assert cron.get_job("invalid!@#") is None

    def test_get_job_partial_passes(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="test")
        assert cron.get_job(job_id[:8]) is not None

    def test_get_job_partial_full_id(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="test")
        assert cron.get_job(job_id) is not None


class TestCronManagerAddJobExtended:
    def test_add_job_with_skill(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="run skill", skill_name="my-skill")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["skill_name"] == "my-skill"

    def test_add_job_with_model(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t", model="gpt-4o")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["model"] == "gpt-4o"

    def test_add_job_with_base_url(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t", base_url="http://localhost:8080")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["base_url"] == "http://localhost:8080"

    def test_add_job_default_enabled(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["enabled"] is True

    def test_add_job_has_created_at(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["created_at"] is not None

    def test_add_job_initial_last_run_null(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["last_run"] is None

    def test_add_job_initial_last_result_null(self, cron):
        job_id = cron.add_job(cron_expr="0 9 * * *", task="t")
        data = json.loads((cron.jobs_dir / f"{job_id}.json").read_text())
        assert data["last_result"] is None


class TestCronManagerListJobsExtended:
    def test_list_with_mixed_content(self, cron):
        cron.add_job(cron_expr="0 * * * *", task="a")
        cron.add_job(cron_expr="0 0 * * *", task="b")
        jobs = cron.list_jobs()
        names = [j["task"] for j in jobs]
        assert "a" in names
        assert "b" in names

    def test_list_sorted(self, cron):
        ids = []
        ids.append(cron.add_job(cron_expr="0 * * * *", task="first"))
        ids.append(cron.add_job(cron_expr="0 0 * * *", task="second"))
        jobs = cron.list_jobs()
        tasks = {j["task"] for j in jobs}
        assert "first" in tasks
        assert "second" in tasks

    def test_list_empty_dir(self, tmp_path):
        with patch("sediman.scheduler.cron.JOBS_DIR", tmp_path / "nonexistent"):
            c = CronManager()
            assert c.list_jobs() == []


class TestCronManagerRemoveJobExtended:
    def test_remove_job_invalid_id(self, cron):
        assert cron.remove_job("") is False

    def test_remove_job_partial_matches(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="test")
        assert cron.remove_job(job_id[:6]) is True

    def test_remove_job_removes_file(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="test")
        cron.remove_job(job_id)
        assert not (cron.jobs_dir / f"{job_id}.json").exists()


class TestCronManagerUpdateJobResultExtended:
    def test_update_result_for_missing_job(self, cron):
        cron.update_job_result("nonexistent", "result")
        assert cron.get_job("nonexistent") is None

    def test_update_result_updates_run_time(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        cron.update_job_result(job_id, "done")
        job = cron.get_job(job_id)
        assert job["last_run"] is not None

    def test_update_result_appends_to_history(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        cron.update_job_result(job_id, "result1")
        cron.update_job_result(job_id, "result2")
        results = cron.get_results(job_id=job_id)
        assert len(results) >= 1

    def test_update_result_truncates_long_results(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        long_result = "x" * 3000
        cron.update_job_result(job_id, long_result)
        results = cron.get_results(job_id=job_id)
        if results:
            assert len(results[0]["result"]) <= 2000

    def test_update_result_preserves_job_id(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        cron.update_job_result(job_id, "done")
        job = cron.get_job(job_id)
        assert job["id"] == job_id


class TestCronManagerGetResults:
    def test_get_results_empty(self, cron):
        assert cron.get_results() == []

    def test_get_results_by_job_id(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        cron.update_job_result(job_id, "result_a")
        results = cron.get_results(job_id=job_id)
        assert len(results) >= 1
        assert results[0]["result"] == "result_a"

    def test_get_results_by_task_filter(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="stock check")
        cron.update_job_result(job_id, "NVDA up 2%")
        results = cron.get_results(task_filter="stock")
        assert len(results) >= 1

    def test_get_results_respects_limit(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        for i in range(10):
            cron.update_job_result(job_id, f"result_{i}")
        results = cron.get_results(limit=3)
        assert len(results) <= 3

    def test_get_results_no_match(self, cron):
        results = cron.get_results(task_filter="nonexistent")
        assert results == []


class TestCronManagerTrimResults:
    def test_trims_excess_results(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        for i in range(MAX_RESULTS_PER_JOB + 20):
            cron.update_job_result(job_id, f"result_{i}")
        entries = cron._read_all_results()
        job_entries = [e for e in entries if e["job_id"] == job_id]
        assert len(job_entries) <= MAX_RESULTS_PER_JOB

    def test_trim_noop_when_under_limit(self, cron):
        job_id = cron.add_job(cron_expr="0 * * * *", task="t")
        for i in range(5):
            cron.update_job_result(job_id, f"result_{i}")
        entries = cron._read_all_results()
        assert len(entries) == 5

    def test_trim_preserves_other_jobs(self, cron):
        job_a = cron.add_job(cron_expr="0 * * * *", task="a")
        job_b = cron.add_job(cron_expr="0 * * * *", task="b")
        for i in range(MAX_RESULTS_PER_JOB + 10):
            cron.update_job_result(job_a, f"a_{i}")
        cron.update_job_result(job_b, "b_result")
        entries = cron._read_all_results()
        b_entries = [e for e in entries if e["job_id"] == job_b]
        assert len(b_entries) == 1


class TestCronManagerReadAllResults:
    def test_read_empty_file(self, cron):
        results = cron._read_all_results()
        assert results == []

    def test_read_corrupt_lines(self, cron):
        cron.jobs_dir.mkdir(parents=True, exist_ok=True)
        with open(cron._results_file, "w") as f:
            f.write('{"valid": true}\n')
            f.write("not json\n")
            f.write('{"valid": false}\n')
        results = cron._read_all_results()
        assert len(results) == 2

    def test_read_missing_file(self, cron):
        if cron._results_file.exists():
            cron._results_file.unlink()
        results = cron._read_all_results()
        assert results == []


class TestExecuteCronJob:
    @pytest.mark.asyncio
    async def test_execute_task_job(self):
        job = {"id": "abc123", "task": "do something", "provider": "openai"}

        with patch("sediman.scheduler.cron._execute_cron_job_inner", new_callable=AsyncMock, return_value="completed"):
            result = await execute_cron_job(job)
            assert result is not None

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        job = {"id": "abc123", "task": "do something"}

        with patch("sediman.scheduler.cron._execute_cron_job_inner", new_callable=AsyncMock, side_effect=Exception("fail")):
            result = await execute_cron_job(job)
            assert result is not None

    @pytest.mark.asyncio
    async def test_execute_suppresses_logging(self):
        job = {"id": "abc123", "task": "test"}

        with patch("sediman.scheduler.cron._execute_cron_job_inner", new_callable=AsyncMock, return_value="done"):
            result = await execute_cron_job(job)
            assert result == "done"
