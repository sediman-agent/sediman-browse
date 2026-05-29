from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from sediman.agent.screen_recorder import (
    ActionEvent,
    RecordedFrame,
    RecordingSession,
    ScreenRecorder,
)


def _make_jpeg_b64(w: int = 100, h: int = 100) -> str:
    try:
        from PIL import Image
        img = Image.new("RGB", (w, h), "white")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return base64.b64encode(b"\xff\xd8\xff\xe0\x00\x10JFIF").decode()


def _make_frame(**overrides) -> RecordedFrame:
    defaults = dict(
        timestamp=time.monotonic(),
        screenshot_b64=_make_jpeg_b64(),
        cursor_x=0,
        cursor_y=0,
        url="https://example.com",
        title="Test",
        action=None,
        action_detail="",
        dom_summary=[],
        page_events=[],
    )
    defaults.update(overrides)
    return RecordedFrame(**defaults)


def _mock_browser_with_page(mock_page=None):
    mock_browser = MagicMock()
    mock_browser.is_started = True
    if mock_page is None:
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


class TestScreenRecorderInjectTrackers:
    @pytest.mark.asyncio
    async def test_inject_trackers_no_page(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._page = None
        await recorder._inject_trackers()
        assert not recorder._tracker_injected

    @pytest.mark.asyncio
    async def test_inject_trackers_failure_handled(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("JS error"))
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("test")
        assert not recorder._tracker_injected
        await recorder.stop()


class TestScreenRecorderRemoveOverlay:
    @pytest.mark.asyncio
    async def test_remove_overlay_no_page(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._page = None
        await recorder._remove_overlay()

    @pytest.mark.asyncio
    async def test_remove_overlay_error_handled(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("gone"))
        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("test")
        recorder._page = mock_page
        await recorder._remove_overlay()
        await recorder.stop()


class TestScreenRecorderCaptureFrameEdgeCases:
    @pytest.mark.asyncio
    async def test_capture_frame_no_page(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._page = None
        result = await recorder._capture_frame("")
        assert result is None

    @pytest.mark.asyncio
    async def test_capture_frame_cursor_eval_fails(self):
        mock_page = AsyncMock()
        call_count = [0]

        async def evaluate_side_effect(script):
            call_count[0] += 1
            if "__sediman_cursor" in script:
                raise Exception("cursor fail")
            if "sediman_cursor_dot" in script:
                return None
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                return []
            return None

        mock_page.evaluate = evaluate_side_effect
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Test")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("cursor-fail")

        await asyncio.sleep(0.4)
        await recorder.stop()

        assert session.frame_count > 0
        for f in session.frames:
            assert f.cursor_x == 0
            assert f.cursor_y == 0

    @pytest.mark.asyncio
    async def test_capture_frame_url_access_fails(self):
        mock_page = AsyncMock()
        type(mock_page).url = property(lambda self: (_ for _ in ()).throw(Exception("url fail")))

        async def evaluate_ok(script):
            return {"x": 0, "y": 0}

        mock_page.evaluate = evaluate_ok
        mock_page.screenshot = AsyncMock(return_value=b"\xff\xd8")
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("url-fail")

        await asyncio.sleep(0.4)
        await recorder.stop()

        assert session.frame_count > 0
        for f in session.frames:
            assert f.url == ""

    @pytest.mark.asyncio
    async def test_capture_frame_title_fails(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_page.screenshot = AsyncMock(return_value=b"\xff")
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(side_effect=Exception("title fail"))

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("title-fail")

        await asyncio.sleep(0.4)
        await recorder.stop()

        assert session.frame_count > 0

    @pytest.mark.asyncio
    async def test_capture_frame_screenshot_exception(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
        mock_page.screenshot = AsyncMock(side_effect=Exception("screenshot fail"))
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("screenshot-fail")

        await asyncio.sleep(0.4)
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_capture_frame_dom_eval_fails(self):
        mock_page = AsyncMock()

        async def evaluate_dom(script):
            if "__sediman_cursor" in script:
                return {"x": 10, "y": 20}
            if "sediman_cursor_dot" in script:
                return None
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                raise Exception("DOM fail")
            return None

        mock_page.evaluate = evaluate_dom
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("dom-fail")

        await asyncio.sleep(0.4)
        await recorder.stop()

        assert session.frame_count > 0
        for f in session.frames:
            assert f.dom_summary == []

    @pytest.mark.asyncio
    async def test_capture_frame_with_cursor_coords(self):
        mock_page = AsyncMock()

        async def evaluate_cursor(script):
            if "__sediman_cursor" in script:
                return {"x": 42, "y": 99}
            if "sediman_cursor_dot" in script:
                return None
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                return []
            return None

        mock_page.evaluate = evaluate_cursor
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("cursor-coords")

        await asyncio.sleep(0.4)
        await recorder.stop()

        frames_with_cursor = [f for f in session.frames if f.cursor_x > 0 or f.cursor_y > 0]
        assert len(frames_with_cursor) > 0
        assert frames_with_cursor[0].cursor_x == 42
        assert frames_with_cursor[0].cursor_y == 99


class TestScreenRecorderInternalDrainPageEvents:
    def test_drain_from_frame_page_events(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        evt1 = ActionEvent(timestamp=1.0, action_type="click", detail="btn")
        evt2 = ActionEvent(timestamp=2.0, action_type="input", detail="type")
        frame = _make_frame(page_events=[evt1, evt2])

        result = recorder._drain_page_events(frame)
        assert len(result) == 2
        assert result[0].action_type == "click"
        assert result[1].action_type == "input"
        assert frame.page_events == []


class TestScreenRecorderDrainPageEventsAsync:
    @pytest.mark.asyncio
    async def test_drain_no_session_returns_empty(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = None
        result = await recorder.drain_page_events()
        assert result == []

    @pytest.mark.asyncio
    async def test_drain_page_eval_fails(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("eval fail"))
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-fail")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert result == []
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_non_list_returns_empty(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="not a list")
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-notlist")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert result == []
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_empty_list_returns_empty(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[])
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-empty")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert result == []
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_unknown_event_type_skipped(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"type": "unknown_event", "x": 1, "y": 2},
            {"type": "scroll", "x": 0, "y": 100},
        ])
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-unknown")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert result == []
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_url_filled_from_page(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"type": "click", "tag": "A", "text": "Link", "id": "",
             "href": "/path", "ariaLabel": "", "role": "", "cls": "",
             "x": 10, "y": 20, "ts": 1},
        ])
        mock_page.url = "https://example.com/page"
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-url")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert len(result) == 1
        assert result[0].url == "https://example.com/page"
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_page_url_access_fails(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"type": "click", "tag": "A", "text": "Link", "id": "",
             "href": "/path", "ariaLabel": "", "role": "", "cls": "",
             "x": 10, "y": 20, "ts": 1},
        ])
        type(mock_page).url = property(lambda self: (_ for _ in ()).throw(Exception("url fail")))
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("drain-url-fail")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert len(result) == 1
        assert result[0].url == ""
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_drain_events_added_to_session_actions(self):
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=[
            {"type": "input", "tag": "INPUT", "inputName": "q", "id": "",
             "placeholder": "Search", "ariaLabel": "", "inputType": "text",
             "value": "test", "ts": 1},
        ])
        mock_page.url = "https://example.com"
        mock_browser = _mock_browser_with_page(mock_page)

        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        session = await recorder.start("drain-session")
        recorder._page = mock_page

        result = await recorder.drain_page_events()
        assert len(result) == 1
        assert len(session.actions) >= 1
        assert session.actions[-1].action_type == "input"
        await recorder.stop()


class TestScreenRecorderDescribeClickVariants:
    def test_click_submit_input(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "INPUT", "type": "submit", "id": "go",
        })
        assert "submit" in result.lower() or "go" in result

    def test_click_radio_input(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "INPUT", "type": "radio", "id": "opt1",
        })
        assert "radio" in result.lower()

    def test_click_generic_element(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "DIV", "id": "container",
        })
        assert "container" in result

    def test_click_aria_label(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "SPAN", "aria_label": "Close dialog",
        })
        assert "Close dialog" in result

    def test_click_link_with_href(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "A", "href": "/about", "text": "About Us",
        })
        assert "About Us" in result

    def test_click_link_no_text_uses_aria(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "A", "href": "/home", "aria_label": "Go Home",
        })
        assert "Go Home" in result

    def test_click_link_no_text_no_aria_uses_href(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "A", "href": "https://example.com/page",
        })
        assert "example.com" in result

    def test_click_button_role(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_click({
            "tag": "DIV", "role": "button", "text": "Expand",
        })
        assert "Expand" in result


class TestScreenRecorderDescribeInputVariants:
    def test_input_with_name(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input({"tag": "INPUT", "name": "email"}, "user@test.com")
        assert "user@test.com" in result
        assert "email" in result

    def test_input_with_placeholder(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input(
            {"tag": "INPUT", "placeholder": "Your name"}, "John"
        )
        assert "Your name" in result
        assert "John" in result

    def test_input_with_aria(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input(
            {"tag": "INPUT", "aria_label": "Search field"}, "query"
        )
        assert "Search field" in result

    def test_input_no_identifying_field(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input({"tag": "INPUT"}, "text")
        assert "text" in result

    def test_input_empty_value(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        result = recorder._describe_input({"tag": "INPUT", "name": "q"}, "")
        assert "empty" in result.lower()


class TestScreenRecorderStreamToDiskEdgeCases:
    @pytest.mark.asyncio
    async def test_stream_no_session(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = None
        recorder._stream_frame_to_disk(_make_frame(), 0)

    @pytest.mark.asyncio
    async def test_stream_no_disk_dir(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = RecordingSession(id="x", name="t", started_at=1.0)
        recorder._session._disk_dir = None
        recorder._stream_frame_to_disk(_make_frame(), 0)

    @pytest.mark.asyncio
    async def test_stream_write_error_handled(self, tmp_path):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = RecordingSession(id="x", name="t", started_at=1.0)
        recorder._session._disk_dir = tmp_path
        bad_frame = _make_frame(screenshot_b64="not-valid-b64!!!")
        recorder._stream_frame_to_disk(bad_frame, 0)


class TestScreenRecorderFlushManifest:
    @pytest.mark.asyncio
    async def test_flush_no_session(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = None
        recorder._flush_manifest()

    @pytest.mark.asyncio
    async def test_flush_no_disk_dir(self):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = RecordingSession(id="x", name="t", started_at=1.0)
        recorder._session._disk_dir = None
        recorder._flush_manifest()

    @pytest.mark.asyncio
    async def test_flush_with_actions(self, tmp_path):
        recorder = ScreenRecorder(browser_session=MagicMock())
        recorder._session = RecordingSession(
            id="abc", name="manifest-test", started_at=time.monotonic() - 5.0
        )
        recorder._session._disk_dir = tmp_path
        recorder._session.actions.append(ActionEvent(
            timestamp=1.0, action_type="click", detail="btn",
            url="https://x.com", text="Submit",
        ))
        recorder._session.actions.append(ActionEvent(
            timestamp=2.0, action_type="input", detail="type",
            url="https://x.com", text="hello",
            element_info={"tag": "INPUT", "name": "q"},
        ))

        recorder._flush_manifest()

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["name"] == "manifest-test"
        assert manifest["action_count"] == 2
        assert manifest["actions"][0]["action_type"] == "click"
        assert manifest["actions"][1]["element_info"]["tag"] == "INPUT"


class TestScreenRecorderInjectActionMarkerEdgeCases:
    @pytest.mark.asyncio
    async def test_inject_with_empty_frames(self):
        mock_browser = _mock_browser_with_page()
        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("empty-frames")

        assert len(recorder.session.frames) == 0
        await recorder.inject_action_marker("navigate", "to page")

        assert len(recorder.session.actions) == 1
        await recorder.stop()

    @pytest.mark.asyncio
    async def test_inject_no_page(self):
        mock_browser = _mock_browser_with_page()
        recorder = ScreenRecorder(browser_session=mock_browser, fps=1)
        await recorder.start("no-page")
        recorder._page = None

        await recorder.inject_action_marker("click", "button")
        await recorder.stop()


class TestScreenRecorderCaptureLoopPageEvents:
    @pytest.mark.asyncio
    async def test_capture_loop_page_events_attached_to_frame(self):
        mock_page = AsyncMock()

        evt1 = ActionEvent(timestamp=1.0, action_type="click", detail="btn")

        async def evaluate_with_events(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "sediman_cursor_dot" in script:
                return None
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                return []
            return None

        mock_page.evaluate = evaluate_with_events
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)

        original_capture = recorder._capture_frame

        async def patched_capture(last_url):
            frame = await original_capture(last_url)
            if frame and recorder.session and not recorder.session.frames:
                frame.page_events = [evt1]
            return frame

        recorder._capture_frame = patched_capture
        session = await recorder.start("events-loop")

        await asyncio.sleep(0.5)
        await recorder.stop()

        click_actions = [a for a in session.actions if a.action_type == "click"]
        assert len(click_actions) >= 1
        assert click_actions[0].detail == "btn"


class TestScreenRecorderCaptureLoopNavigationDetection:
    @pytest.mark.asyncio
    async def test_navigate_action_detected(self):
        mock_page = AsyncMock()
        url_seq = ["https://a.com", "https://b.com"]
        idx = [0]

        async def evaluate_nav(script):
            if "__sediman_cursor" in script:
                return {"x": 0, "y": 0}
            if "sediman_cursor_dot" in script:
                return None
            if "__sediman_events" in script:
                return []
            if "document.body" in script or "walk(document" in script:
                return []
            return None

        mock_page.evaluate = evaluate_nav
        mock_page.screenshot = AsyncMock(return_value=_make_jpeg_b64().encode())

        def get_url():
            i = min(idx[0], len(url_seq) - 1)
            idx[0] += 1
            return url_seq[i]

        type(mock_page).url = property(lambda self: get_url())
        mock_page.title = AsyncMock(return_value="T")

        mock_browser = _mock_browser_with_page(mock_page)
        recorder = ScreenRecorder(browser_session=mock_browser, fps=10)
        session = await recorder.start("nav-detect")

        await asyncio.sleep(0.6)
        await recorder.stop()

        nav_frames = [f for f in session.frames if f.action == "navigate"]
        assert len(nav_frames) > 0
        assert "b.com" in nav_frames[0].action_detail
