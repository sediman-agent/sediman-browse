from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sediman.api.app import app, init_state, _task_store


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


@pytest.fixture(autouse=True)
def reset_recording_manager():
    from sediman.agent.recording_manager import RecordingManager
    RecordingManager._instance = None
    yield
    RecordingManager._instance = None


class TestRecordStartEndpoint:
    def test_start_recording_returns_session(self, client):
        from sediman.agent.recording_manager import RecordingManager
        from sediman.agent.screen_recorder import RecordingSession

        mock_browser = MagicMock()
        mock_browser.is_started = True
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        with patch("sediman.api.app._get_browser", new_callable=AsyncMock, return_value=mock_browser):
            resp = client.post("/api/skills/record/start", json={
                "name": "test-rec-skill",
                "description": "Test recording",
                "fps": 3,
                "max_duration": 60,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-rec-skill"
        assert data["status"] == "recording"
        assert "session_id" in data

        mgr = RecordingManager.get_instance()
        r = mgr.get_recorder("test-rec-skill")
        if r and r.is_recording:
            r._recording = False
            if r._capture_task:
                r._capture_task.cancel()
                r._capture_task = None
            if r._session:
                r._session.stopped_at = time.monotonic()
            mgr.cleanup("test-rec-skill")

    def test_start_recording_invalid_name(self, client):
        resp = client.post("/api/skills/record/start", json={
            "name": "INVALID NAME!",
        })
        assert resp.status_code == 422

    def test_start_recording_missing_name(self, client):
        resp = client.post("/api/skills/record/start", json={})
        assert resp.status_code == 422

    def test_start_recording_invalid_fps(self, client):
        resp = client.post("/api/skills/record/start", json={
            "name": "bad-fps",
            "fps": 0,
        })
        assert resp.status_code == 422

    def test_start_recording_fps_too_high(self, client):
        resp = client.post("/api/skills/record/start", json={
            "name": "high-fps",
            "fps": 20,
        })
        assert resp.status_code == 422

    def test_start_recording_invalid_max_duration(self, client):
        resp = client.post("/api/skills/record/start", json={
            "name": "bad-dur",
            "max_duration": 5,
        })
        assert resp.status_code == 422

    def test_start_recording_duplicate(self, client):
        from sediman.agent.recording_manager import RecordingManager

        mock_browser = MagicMock()
        mock_browser.is_started = True
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        with patch("sediman.api.app._get_browser", new_callable=AsyncMock, return_value=mock_browser):
            resp1 = client.post("/api/skills/record/start", json={"name": "dup-skill"})
            assert resp1.status_code == 200

            resp2 = client.post("/api/skills/record/start", json={"name": "dup-skill"})
            assert resp2.status_code == 409

        mgr = RecordingManager.get_instance()
        r = mgr.get_recorder("dup-skill")
        if r and r.is_recording:
            r._recording = False
            if r._capture_task:
                r._capture_task.cancel()
                r._capture_task = None
            if r._session:
                r._session.stopped_at = time.monotonic()
            mgr.cleanup("dup-skill")


class TestRecordStopEndpoint:
    def test_stop_not_found(self, client):
        resp = client.post("/api/skills/record/nonexistent-session/stop")
        assert resp.status_code == 404

    def test_stop_not_recording(self, client):
        from sediman.agent.recording_manager import RecordingManager
        from sediman.agent.screen_recorder import RecordingSession

        mgr = RecordingManager.get_instance()
        session = RecordingSession(id="stopped-session", name="stopped-skill")
        mgr._sessions["stopped-session"] = session

        resp = client.post("/api/skills/record/stopped-session/stop")
        assert resp.status_code == 409


class TestActiveRecordingsEndpoint:
    def test_no_active_recordings(self, client):
        resp = client.get("/api/skills/record/active")
        assert resp.status_code == 200
        assert resp.json() == {"recordings": []}

    def test_active_recording_shown(self, client):
        from sediman.agent.recording_manager import RecordingManager
        from sediman.agent.screen_recorder import RecordingSession

        mgr = RecordingManager.get_instance()
        session = RecordingSession(
            id="active-123",
            name="active-skill",
            started_at=time.monotonic(),
        )
        mock_recorder = MagicMock()
        mock_recorder.is_recording = True
        mock_recorder.session = session
        mgr._recorders["active-skill"] = mock_recorder
        mgr._sessions["active-123"] = session

        resp = client.get("/api/skills/record/active")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recordings"]) == 1
        assert data["recordings"][0]["session_id"] == "active-123"
        assert data["recordings"][0]["name"] == "active-skill"
