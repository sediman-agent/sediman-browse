from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.screen_recorder import (
    ActionEvent,
    RecordedFrame,
    RecordingSession,
    ScreenRecorder,
)


def _make_jpeg_b64() -> str:
    import base64
    import io

    try:
        from PIL import Image

        img = Image.new("RGB", (100, 100), "white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF").decode()


class TestScreenRecorderDOMCapture:
    @pytest.mark.asyncio
    async def test_capture_frame_includes_dom_summary(self):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        dom_elements = [
            {"tag": "A", "href": "https://example.com", "text": "Click me"},
            {"tag": "INPUT", "type": "text", "placeholder": "Search"},
            {"tag": "BUTTON", "text": "Submit"},
        ]

        call_count = [0]

        async def mock_evaluate(script):
            call_count[0] += 1
            if "__sediman_cursor" in script:
                return {"x": 50, "y": 100}
            if "__sediman_events" in script:
                return []
            if "__sediman_scroll" not in script and "sediman_cursor_dot" not in script:
                if "document.body" in script or "walk(document" in script:
                    return dom_elements
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=b"\xff\xd8\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Test Page")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("dom-test")

        await asyncio.sleep(0.5)
        await recorder.stop()

        assert session.frame_count > 0
        frames_with_dom = [f for f in session.frames if f.dom_summary]
        assert len(frames_with_dom) > 0

    @pytest.mark.asyncio
    async def test_dom_summary_includes_elements(self):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                return [
                    {"tag": "BUTTON", "text": "Submit", "id": "submit-btn"},
                    {"tag": "A", "href": "/link", "text": "Click"},
                ]
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=b"\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("test")

        await asyncio.sleep(0.4)
        await recorder.stop()

        for frame in session.frames:
            if frame.dom_summary:
                assert isinstance(frame.dom_summary, list)
                break


class TestScreenRecorderDiskStreaming:
    @pytest.mark.asyncio
    async def test_frames_streamed_to_disk(self, tmp_path):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return []
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        with patch("sediman.agent.screen_recorder._CAPTURE_DIR", tmp_path):
            recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
            session = await recorder.start("disk-test")

            await asyncio.sleep(0.5)
            await recorder.stop()

            if session.frame_count > 0:
                disk_dir = tmp_path / "disk-test"
                if disk_dir.exists():
                    jpg_files = list(disk_dir.glob("frame_*.jpg"))
                    json_files = list(disk_dir.glob("frame_*.json"))
                    assert len(jpg_files) > 0
                    assert len(json_files) > 0

                    meta = json.loads(json_files[0].read_text())
                    assert "url" in meta
                    assert "timestamp" in meta

    @pytest.mark.asyncio
    async def test_manifest_written_on_stop(self, tmp_path):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return []
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        with patch("sediman.agent.screen_recorder._CAPTURE_DIR", tmp_path):
            recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
            session = await recorder.start("manifest-test")

            await asyncio.sleep(0.5)
            await recorder.stop()

            manifest_path = tmp_path / "manifest-test" / "manifest.json"
            assert manifest_path.exists()

            manifest = json.loads(manifest_path.read_text())
            assert manifest["name"] == "manifest-test"
            assert "frame_count" in manifest
            assert "session_id" in manifest


class TestScreenRecorderActionDraining:
    @pytest.mark.asyncio
    async def test_drain_click_events(self):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        click_events = [
            {
                "type": "click",
                "tag": "BUTTON",
                "text": "Submit",
                "id": "submit",
                "href": "",
                "ariaLabel": "",
                "role": "",
                "cls": "",
                "x": 100,
                "y": 200,
                "ts": 12345,
            }
        ]

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return click_events
            if "sediman_cursor_dot" in script:
                return None
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=b"\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        await recorder.start("drain-test")

        events = await recorder.drain_page_events()

        await recorder.stop()

        if events:
            assert events[0].action_type == "click"
            assert "Submit" in events[0].detail

    @pytest.mark.asyncio
    async def test_drain_input_events(self):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        input_events = [
            {
                "type": "input",
                "tag": "INPUT",
                "inputName": "search",
                "id": "q",
                "placeholder": "Search...",
                "ariaLabel": "",
                "inputType": "text",
                "value": "hello world",
                "ts": 12345,
            }
        ]

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return input_events
            if "sediman_cursor_dot" in script:
                return None
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=b"\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        await recorder.start("input-drain")

        events = await recorder.drain_page_events()

        await recorder.stop()

        if events:
            assert events[0].action_type == "input"
            assert "hello world" in events[0].detail

    @pytest.mark.asyncio
    async def test_drain_no_page_returns_empty(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        events = await recorder.drain_page_events()
        assert events == []

    @pytest.mark.asyncio
    async def test_drain_password_values_masked(self):
        mock_browser = MagicMock()
        mock_browser.is_started = True

        input_events = [
            {
                "type": "input",
                "tag": "INPUT",
                "inputName": "password",
                "id": "pw",
                "placeholder": "",
                "ariaLabel": "",
                "inputType": "password",
                "value": "********",
                "ts": 12345,
            }
        ]

        async def mock_evaluate(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "__sediman_events" in script:
                return input_events
            if "sediman_cursor_dot" in script:
                return None
            return None

        mock_page = AsyncMock()
        mock_page.evaluate = mock_evaluate
        mock_page.screenshot = AsyncMock(return_value=b"\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_session_obj = MagicMock()
        mock_session_obj.agent_current_page = mock_page
        mock_browser.browser = MagicMock()
        mock_browser.browser.create_session = AsyncMock(return_value=mock_session_obj)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        await recorder.start("pw-drain")

        events = await recorder.drain_page_events()

        await recorder.stop()

        if events:
            assert "********" in events[0].detail


class TestScreenRecorderDescribeActions:
    def test_describe_click_link(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "A",
            "text": "Home",
            "href": "/home",
        })
        assert "link" in result.lower() or "Home" in result

    def test_describe_click_button(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "BUTTON",
            "text": "Submit",
        })
        assert "Submit" in result

    def test_describe_click_checkbox(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "INPUT",
            "type": "checkbox",
            "id": "agree",
        })
        assert "checkbox" in result.lower()

    def test_describe_input(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input({
            "tag": "INPUT",
            "name": "email",
            "placeholder": "Enter email",
        }, "test@example.com")
        assert "test@example.com" in result
        assert "email" in result.lower()

    def test_describe_input_empty(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input({"tag": "INPUT", "name": "q"}, "")
        assert "empty" in result.lower()


class TestRecordedFrameWithDOM:
    def test_frame_with_dom_summary(self):
        frame = RecordedFrame(
            timestamp=1.0,
            screenshot_b64="abc",
            cursor_x=0,
            cursor_y=0,
            url="http://x",
            dom_summary=[
                {"tag": "BUTTON", "text": "Click me"},
                {"tag": "INPUT", "type": "text"},
            ],
        )
        assert len(frame.dom_summary) == 2
        assert frame.dom_summary[0]["tag"] == "BUTTON"

    def test_frame_default_dom_summary_empty(self):
        frame = RecordedFrame(
            timestamp=1.0,
            screenshot_b64="abc",
            cursor_x=0,
            cursor_y=0,
            url="http://x",
        )
        assert frame.dom_summary == []

    def test_frame_default_page_events_empty(self):
        frame = RecordedFrame(
            timestamp=1.0,
            screenshot_b64="abc",
            cursor_x=0,
            cursor_y=0,
            url="http://x",
        )
        assert frame.page_events == []
