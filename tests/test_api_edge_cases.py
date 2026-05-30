"""Edge-case tests for api/app.py — request validation, missing fields, status endpoint."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from sediman.api.app import app, init_state, TaskRequest, ScheduleRequest, HubInstallRequest


@pytest.fixture
def client(tmp_sediman_dir):
    with patch("sediman.skills.engine.GLOBAL_SKILLS_DIR", tmp_sediman_dir / "skills"), \
         patch("sediman.scheduler.cron.JOBS_DIR", tmp_sediman_dir / "cron"), \
         patch("sediman.store.db.DEFAULT_DATA_DIR", tmp_sediman_dir), \
         patch("sediman.memory.prompt.MEMORY_FILE", tmp_sediman_dir / "MEMORY.md"), \
         patch("sediman.memory.prompt.USER_FILE", tmp_sediman_dir / "USER.md"):
        init_state(provider="openai", model="test", base_url=None)
        with TestClient(app) as c:
            yield c


class TestTaskRequestValidation:
    def test_missing_task_field(self, client):
        resp = client.post("/api/task", json={})
        assert resp.status_code == 422  # Validation error

    def test_empty_task(self, client):
        resp = client.post("/api/task", json={"task": ""})
        # Should process but may fail on the agent side
        # The request itself is valid with empty string


class TestScheduleRequestValidation:
    def test_missing_cron_field(self, client):
        resp = client.post("/api/schedule", json={"task": "test"})
        assert resp.status_code == 422

    def test_missing_task_field(self, client):
        resp = client.post("/api/schedule", json={"cron": "0 * * * *"})
        assert resp.status_code == 422

    def test_valid_request_with_skill(self, client):
        resp = client.post("/api/schedule", json={
            "cron": "0 9 * * *",
            "task": "daily report",
            "skill": "report-gen",
        })
        assert resp.status_code == 200

    def test_valid_request_without_skill(self, client):
        resp = client.post("/api/schedule", json={
            "cron": "*/30 * * * *",
            "task": "check stocks",
        })
        assert resp.status_code == 200


class TestHubInstallRequestValidation:
    def test_missing_name_field(self, client):
        resp = client.post("/api/hub/install", json={})
        assert resp.status_code == 422

    def test_force_defaults_to_false(self, client):
        req = HubInstallRequest(name="test")
        assert req.force is False

    def test_force_explicit_true(self, client):
        req = HubInstallRequest(name="test", force=True)
        assert req.force is True


class TestSkillsEndpointsEdgeCases:
    def test_get_skill_returns_json(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="api-test", description="API skill", steps=["s1", "s2"])

        resp = client.get("/api/skills/api-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "api-test"
        assert data["steps"] == ["s1", "s2"]

    def test_delete_skill_twice(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="double-del", description="delete me", steps=[])

        resp1 = client.delete("/api/skills/double-del")
        assert resp1.status_code == 200

        resp2 = client.delete("/api/skills/double-del")
        assert resp2.status_code == 404

    def test_list_skills_returns_list(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="skill-1", description="first", steps=[])
        engine.create(name="skill-2", description="second", steps=[])

        resp = client.get("/api/skills")
        skills = resp.json()["skills"]
        assert len(skills) == 2
        names = [s["name"] for s in skills]
        assert "skill-1" in names
        assert "skill-2" in names


class TestScheduleEndpointsEdgeCases:
    def test_schedule_contains_cron_field(self, client):
        resp = client.post("/api/schedule", json={
            "cron": "0 * * * *",
            "task": "test",
        })
        data = resp.json()
        assert data["cron"] == "0 * * * *"

    def test_remove_nonexistent_schedule(self, client):
        resp = client.delete("/api/schedule/fake-id")
        assert resp.status_code == 404

    def test_schedule_list_after_add(self, client):
        client.post("/api/schedule", json={"cron": "0 * * * *", "task": "t1"})
        client.post("/api/schedule", json={"cron": "0 0 * * *", "task": "t2"})

        resp = client.get("/api/schedule")
        jobs = resp.json()["jobs"]
        assert len(jobs) == 2

    def test_add_schedule_returns_job_id(self, client):
        resp = client.post("/api/schedule", json={
            "cron": "0 * * * *",
            "task": "test",
        })
        data = resp.json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0


class TestMemoryEndpointEdgeCases:
    def test_memory_returns_entries_and_usage(self, client):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert "usage" in data
        assert "memory" in data["entries"]
        assert "user" in data["entries"]

    def test_memory_after_save(self, client, tmp_sediman_dir):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text("saved fact")
        resp = client.get("/api/memory")
        entries = resp.json()["entries"]["memory"]
        assert any("saved fact" in e for e in entries)


class TestSessionsEndpointEdgeCases:
    def test_sessions_returns_list(self, client):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", Path("/tmp/test-sessions")):
            resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert "sessions" in resp.json()


class TestHubEndpointsEdgeCases:
    def test_hub_browse_returns_list(self, client):
        with patch("sediman.skills.hub.HubClient.browse", return_value=[]):
            resp = client.get("/api/hub/browse")
        assert resp.status_code == 200
        assert "skills" in resp.json()

    def test_hub_search_requires_query(self, client):
        resp = client.get("/api/hub/search")
        assert resp.status_code == 422

    def test_hub_info_missing_skill(self, client):
        with patch("sediman.skills.hub.HubClient.info", return_value=None):
            resp = client.get("/api/hub/nonexistent")
        assert resp.status_code == 404
