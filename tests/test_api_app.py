from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sediman.api.app import app, init_state


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


class TestSkillsEndpoints:
    def test_list_skills_empty(self, client):
        resp = client.get("/api/skills")
        assert resp.status_code == 200
        assert resp.json() == {"skills": []}

    def test_create_and_list_skill(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="api-skill", description="from api", steps=["s1"])

        resp = client.get("/api/skills")
        data = resp.json()
        assert len(data["skills"]) == 1
        assert data["skills"][0]["name"] == "api-skill"

    def test_get_skill_existing(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="get-me", description="gettable", steps=["s1"])

        resp = client.get("/api/skills/get-me")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    def test_get_skill_missing(self, client):
        resp = client.get("/api/skills/nonexistent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_delete_skill(self, client, tmp_sediman_dir):
        from sediman.skills.engine import SkillEngine

        engine = SkillEngine(skills_dir=tmp_sediman_dir / "skills")
        engine.create(name="del-me", description="deletable", steps=[])

        resp = client.delete("/api/skills/del-me")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "del-me"

    def test_delete_skill_missing(self, client):
        resp = client.delete("/api/skills/nope")
        assert resp.status_code == 404
        assert "detail" in resp.json()


class TestScheduleEndpoints:
    def test_list_schedule_empty(self, client):
        resp = client.get("/api/schedule")
        assert resp.status_code == 200
        assert resp.json() == {"jobs": []}

    def test_add_schedule(self, client):
        resp = client.post("/api/schedule", json={
            "cron": "0 * * * *",
            "task": "test task",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["task"] == "test task"

    def test_add_and_list_schedule(self, client):
        client.post("/api/schedule", json={
            "cron": "0 * * * *",
            "task": "scheduled task",
        })
        resp = client.get("/api/schedule")
        jobs = resp.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["task"] == "scheduled task"

    def test_remove_schedule(self, client):
        add_resp = client.post("/api/schedule", json={
            "cron": "0 * * * *",
            "task": "to remove",
        })
        job_id = add_resp.json()["job_id"]

        resp = client.delete(f"/api/schedule/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["removed"] == job_id

    def test_remove_schedule_missing(self, client):
        resp = client.delete("/api/schedule/fake")
        assert resp.status_code == 404
        assert "detail" in resp.json()


class TestMemoryEndpoint:
    def test_get_memory_empty(self, client):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"]["memory"] == []
        assert data["entries"]["user"] == []
        assert data["usage"]["memory"]["chars"] == 0

    def test_get_memory_with_content(self, client, tmp_sediman_dir):
        mem_dir = tmp_sediman_dir / "memories"
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "MEMORY.md").write_text("remembered content")
        resp = client.get("/api/memory")
        assert "remembered content" in resp.json()["entries"]["memory"][0]


class TestSessionsEndpoint:
    def test_list_sessions_empty(self, client):
        with patch("sediman.store.db.DEFAULT_DATA_DIR", client.app.state.__dict__.get("_tmp_dir", Path("/tmp"))):
            resp = client.get("/api/sessions")
        assert resp.status_code == 200
