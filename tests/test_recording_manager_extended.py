from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.recording_manager import RecordingManager
from sediman.agent.screen_recorder import (
    ActionEvent,
    RecordingSession,
    ScreenRecorder,
)


def _make_mock_browser():
    mock_browser = MagicMock()
    mock_browser.is_started = True
    mock_page = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
    mock_page.screenshot = AsyncMock(return_value=b"\xff\xd8\xff")
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Test")
    mock_session_obj = MagicMock()
    mock_session_obj.agent_current_page = mock_page
    mock_browser.browser = MagicMock()
    mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)
    return mock_browser


class TestRecordingManagerActiveRecorder:
    def setup_method(self):
        RecordingManager._instance = None

    def teardown_method(self):
        RecordingManager._instance = None

    @pytest.mark.asyncio
    async def test_get_active_recorder_returns_none_when_empty(self):
        mgr = RecordingManager()
        assert mgr.get_active_recorder() is None

    @pytest.mark.asyncio
    async def test_get_active_recorder_returns_recorder(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("active-test", mock_browser)

        recorder = mgr.get_active_recorder()
        assert recorder is not None
        assert recorder.is_recording

        await mgr.stop_recording("active-test")

    @pytest.mark.asyncio
    async def test_get_active_recorder_cleared_on_stop(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("clear-test", mock_browser)
        await mgr.stop_recording("clear-test")

        assert mgr.get_active_recorder() is None


class TestRecordingManagerOnStepCallback:
    def setup_method(self):
        RecordingManager._instance = None

    def teardown_method(self):
        RecordingManager._instance = None

    @pytest.mark.asyncio
    async def test_create_on_step_callback_returns_none_when_not_recording(self):
        mgr = RecordingManager()
        callback = mgr.create_on_step_callback("nonexistent")
        assert callback is None

    @pytest.mark.asyncio
    async def test_create_on_step_callback_returns_callable(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("callback-test", mock_browser)

        callback = mgr.create_on_step_callback("callback-test")
        assert callable(callback)

        await mgr.stop_recording("callback-test")

    @pytest.mark.asyncio
    async def test_create_on_step_callback_uses_active_recorder(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("auto-cb", mock_browser)

        callback = mgr.create_on_step_callback()
        assert callable(callback)

        await mgr.stop_recording("auto-cb")

    @pytest.mark.asyncio
    async def test_on_step_callback_injects_action(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("inject-test", mock_browser)

        callback = mgr.create_on_step_callback("inject-test")
        assert callback is not None

        import asyncio
        callback("navigate", "https://example.com/page")
        await asyncio.sleep(0.2)

        recorder = mgr.get_recorder("inject-test")
        if recorder and recorder.session:
            assert len(recorder.session.actions) >= 1

        await mgr.stop_recording("inject-test")


class TestRecordingManagerDrainEvents:
    def setup_method(self):
        RecordingManager._instance = None

    def teardown_method(self):
        RecordingManager._instance = None

    @pytest.mark.asyncio
    async def test_drain_active_events_no_recorder(self):
        mgr = RecordingManager()
        events = await mgr.drain_active_events()
        assert events == []


class TestRecordingManagerCleanup:
    def setup_method(self):
        RecordingManager._instance = None

    def teardown_method(self):
        RecordingManager._instance = None

    @pytest.mark.asyncio
    async def test_cleanup_clears_active_recorder(self):
        mgr = RecordingManager()
        mock_browser = _make_mock_browser()
        await mgr.start_recording("cleanup-active", mock_browser)
        await mgr.stop_recording("cleanup-active")

        assert mgr.get_active_recorder() is None
        mgr.cleanup("cleanup-active")
        assert mgr.get_recorder("cleanup-active") is None
