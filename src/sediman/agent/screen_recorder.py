from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

logger = structlog.get_logger()

_CAPTURE_DIR = Path.home() / ".sediman" / "recordings"

_MOUSE_TRACKER_JS = """
(window.__sediman_cursor = {x: 0, y: 0, ts: 0});
document.addEventListener('mousemove', function(e) {
    window.__sediman_cursor = {x: e.clientX, y: e.clientY, ts: Date.now()};
});
document.addEventListener('click', function(e) {
    window.__sediman_cursor = {x: e.clientX, y: e.clientY, ts: Date.now()};
    if (!window.__sediman_events) window.__sediman_events = [];
    var el = e.target;
    var tag = el.tagName || '';
    var text = (el.textContent || '').trim().slice(0, 80);
    var href = el.getAttribute('href') || '';
    var id = el.id || '';
    var cls = el.className || '';
    var type = el.getAttribute('type') || '';
    var name = el.getAttribute('name') || '';
    var placeholder = el.getAttribute('placeholder') || '';
    var label = el.getAttribute('aria-label') || '';
    var role = el.getAttribute('role') || '';
    window.__sediman_events.push({
        type: 'click',
        tag: tag,
        text: text,
        href: href,
        id: id,
        cls: cls,
        inputType: type,
        inputName: name,
        placeholder: placeholder,
        ariaLabel: label,
        role: role,
        x: e.clientX,
        y: e.clientY,
        ts: Date.now()
    });
    if (window.__sediman_events.length > 200) {
        window.__sediman_events = window.__sediman_events.slice(-100);
    }
});
document.addEventListener('input', function(e) {
    if (!window.__sediman_events) window.__sediman_events = [];
    var el = e.target;
    var tag = el.tagName || '';
    var name = el.getAttribute('name') || '';
    var id = el.id || '';
    var placeholder = el.getAttribute('placeholder') || '';
    var ariaLabel = el.getAttribute('aria-label') || '';
    var inputType = el.getAttribute('type') || '';
    var value = '';
    if (inputType === 'password') {
        value = '********';
    } else {
        value = (el.value || '').slice(0, 100);
    }
    window.__sediman_events.push({
        type: 'input',
        tag: tag,
        inputName: name,
        id: id,
        placeholder: placeholder,
        ariaLabel: ariaLabel,
        inputType: inputType,
        value: value,
        ts: Date.now()
    });
    if (window.__sediman_events.length > 200) {
        window.__sediman_events = window.__sediman_events.slice(-100);
    }
});
"""

_GET_CURSOR_JS = """
(() => {
    try { return window.__sediman_cursor || {x: 0, y: 0}; }
    catch(e) { return {x: 0, y: 0}; }
})()
"""

_DRAIN_EVENTS_JS = """
(() => {
    try {
        var events = window.__sediman_events || [];
        window.__sediman_events = [];
        return events;
    } catch(e) { return []; }
})()
"""

_GET_ACCESSIBILITY_JS = """
(() => {
    try {
        var result = [];
        function walk(el, depth) {
            if (depth > 6 || result.length > 80) return;
            if (!el || el.nodeType !== 1) return;
            var tag = el.tagName;
            if (!tag) return;
            var skip = ['SCRIPT','STYLE','NOSCRIPT','SVG','PATH','BR','HR','META','LINK','HEAD'];
            if (skip.indexOf(tag) >= 0) return;
            var text = (el.innerText || '').trim().slice(0, 60);
            var attrs = {};
            var interesting = ['id','class','href','type','name','placeholder','aria-label','role','value','alt','title','src','action','method','for'];
            for (var i = 0; i < interesting.length; i++) {
                var v = el.getAttribute(interesting[i]);
                if (v) attrs[interesting[i]] = v.slice(0, 100);
            }
            var entry = {tag: tag};
            if (text && text.length < 200) entry.text = text;
            for (var k in attrs) entry[k] = attrs[k];
            if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'BUTTON' || tag === 'A') {
                result.push(entry);
            } else if (result.length < 40 && el.children && el.children.length === 0 && text) {
                result.push(entry);
            }
            if (el.children) {
                for (var c = 0; c < el.children.length && c < 20; c++) {
                    walk(el.children[c], depth + 1);
                }
            }
        }
        walk(document.body, 0);
        return result;
    } catch(e) { return []; }
})()
"""

_SCROLL_TRACKER_JS = """
document.addEventListener('scroll', function(e) {
    if (!window.__sediman_scroll_events) window.__sediman_scroll_events = [];
    window.__sediman_scroll_events.push({
        x: window.scrollX,
        y: window.scrollY,
        ts: Date.now()
    });
    if (window.__sediman_scroll_events.length > 100) {
        window.__sediman_scroll_events = window.__sediman_scroll_events.slice(-50);
    }
});
"""

_CURSOR_OVERLAY_JS = """
(cursorX, cursorY) => {
    const el = document.getElementById('__sediman_cursor_dot');
    if (el) el.remove();
    if (cursorX === 0 && cursorY === 0) return;
    const dot = document.createElement('div');
    dot.id = '__sediman_cursor_dot';
    dot.style.cssText = `
        position: fixed;
        left: ${cursorX}px;
        top: ${cursorY}px;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: rgba(255, 0, 0, 0.6);
        border: 3px solid rgba(255, 255, 255, 0.9);
        transform: translate(-50%, -50%);
        pointer-events: none;
        z-index: 2147483647;
        box-shadow: 0 0 8px rgba(255,0,0,0.8);
    `;
    document.body.appendChild(dot);
}
"""

_REMOVE_OVERLAY_JS = """
(() => {
    const el = document.getElementById('__sediman_cursor_dot');
    if (el) el.remove();
})()
"""


@dataclass
class RecordedFrame:
    timestamp: float
    screenshot_b64: str
    cursor_x: int
    cursor_y: int
    url: str
    title: str = ""
    action: str | None = None
    action_detail: str = ""
    dom_summary: list[dict[str, str]] = field(default_factory=list)
    page_events: list[dict[str, Any]] = field(default_factory=list)

    def has_cursor(self) -> bool:
        return self.cursor_x > 0 or self.cursor_y > 0


@dataclass
class ActionEvent:
    timestamp: float
    action_type: str
    detail: str
    url: str = ""
    selector: str = ""
    text: str = ""
    element_info: dict[str, str] = field(default_factory=dict)


@dataclass
class RecordingSession:
    id: str
    name: str
    frames: list[RecordedFrame] = field(default_factory=list)
    actions: list[ActionEvent] = field(default_factory=list)
    started_at: float = 0.0
    stopped_at: float | None = None
    description: str | None = None
    _disk_dir: Path | None = None

    @property
    def duration_seconds(self) -> float:
        end = self.stopped_at or time.monotonic()
        return max(0.0, end - self.started_at)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def get_action_frames(self) -> list[RecordedFrame]:
        return [f for f in self.frames if f.action is not None]

    def get_key_frames(self, max_frames: int = 25) -> list[RecordedFrame]:
        action_frames = self.get_action_frames()
        action_indices = {id(f) for f in action_frames}

        if len(action_frames) >= max_frames:
            step = len(action_frames) / max_frames
            return [action_frames[int(i * step)] for i in range(max_frames)]

        idle_frames = [f for f in self.frames if id(f) not in action_indices]
        remaining = max_frames - len(action_frames)

        sampled_idle: list[RecordedFrame] = []
        if idle_frames and remaining > 0:
            step = max(1, len(idle_frames) // remaining)
            for i in range(0, len(idle_frames), step):
                if len(sampled_idle) < remaining:
                    sampled_idle.append(idle_frames[i])

        result = []
        idle_idx = 0
        for f in self.frames:
            if id(f) in action_indices:
                result.append(f)
            elif idle_idx < len(sampled_idle) and id(f) == id(sampled_idle[idle_idx]):
                result.append(f)
                idle_idx += 1
            if len(result) >= max_frames:
                break

        return result[:max_frames]


class ScreenRecorder:
    FPS = 3
    MAX_DURATION_SECONDS = 300

    def __init__(
        self,
        browser_session: Any,
        fps: int = 3,
        max_duration: int = 300,
        on_frame: Callable[[RecordedFrame], None] | None = None,
    ):
        self.browser = browser_session
        self.fps = min(max(fps, 1), 10)
        self.max_duration = max_duration
        self.on_frame = on_frame
        self._session: RecordingSession | None = None
        self._recording = False
        self._capture_task: asyncio.Task | None = None
        self._page: Any = None
        self._tracker_injected = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def session(self) -> RecordingSession | None:
        return self._session

    async def start(
        self, name: str, description: str | None = None
    ) -> RecordingSession:
        if self._recording:
            raise RuntimeError("Already recording. Stop the current session first.")

        if not self.browser.is_started:
            await self.browser.start()

        browser = self.browser.browser
        session = await browser.create_session()
        self._page = session.agent_current_page

        if not self._page:
            contexts = (
                browser.browser_contexts if hasattr(browser, "browser_contexts") else []
            )
            if contexts:
                ctx = contexts[0]
                pages = ctx.pages if hasattr(ctx, "pages") else []
                if pages:
                    self._page = pages[-1]

        if not self._page:
            self._page = await browser.new_page()

        disk_dir = _CAPTURE_DIR / name
        disk_dir.mkdir(parents=True, exist_ok=True)

        self._session = RecordingSession(
            id=str(uuid.uuid4())[:12],
            name=name,
            started_at=time.monotonic(),
            description=description,
            _disk_dir=disk_dir,
        )

        await self._inject_trackers()

        self._recording = True
        self._capture_task = asyncio.create_task(self._capture_loop())

        logger.info(
            "screen_recording_started",
            session_id=self._session.id,
            name=name,
            fps=self.fps,
        )
        return self._session

    async def stop(self) -> RecordingSession:
        if not self._recording or not self._session:
            raise RuntimeError("Not recording.")

        self._recording = False

        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
            self._capture_task = None

        await self._remove_overlay()
        self._flush_manifest()

        self._session.stopped_at = time.monotonic()

        logger.info(
            "screen_recording_stopped",
            session_id=self._session.id,
            frames=len(self._session.frames),
            actions=len(self._session.actions),
            duration=self._session.duration_seconds,
        )
        return self._session

    async def inject_action_marker(self, action_type: str, detail: str = "") -> None:
        if not self._session or not self._page:
            return

        self._session.actions.append(
            ActionEvent(
                timestamp=time.monotonic(),
                action_type=action_type,
                detail=detail,
                url=self._page.url if self._page else "",
            )
        )

        if self._session.frames:
            last_frame = self._session.frames[-1]
            if not last_frame.action:
                last_frame.action = action_type
                last_frame.action_detail = detail

    async def _inject_trackers(self) -> None:
        if not self._page:
            return
        try:
            await self._page.evaluate(_MOUSE_TRACKER_JS)
            await self._page.evaluate(_SCROLL_TRACKER_JS)
            self._tracker_injected = True
        except Exception as e:
            logger.debug("tracker_inject_failed", error=str(e))

    async def _remove_overlay(self) -> None:
        if not self._page:
            return
        try:
            await self._page.evaluate(_REMOVE_OVERLAY_JS)
        except Exception:
            pass

    async def _capture_loop(self) -> None:
        interval = 1.0 / self.fps
        last_url = ""
        frame_idx = 0

        while self._recording:
            try:
                start = time.monotonic()

                if self._session and self._session.duration_seconds > self.max_duration:
                    logger.info("recording_max_duration_reached", max=self.max_duration)
                    break

                frame = await self._capture_frame(last_url)
                if frame and self._session:
                    self._session.frames.append(frame)
                    last_url = frame.url

                    page_events = self._drain_page_events(frame)
                    for evt in page_events:
                        self._session.actions.append(evt)
                        if not frame.action:
                            frame.action = evt.action_type
                            frame.action_detail = evt.detail

                    self._stream_frame_to_disk(frame, frame_idx)
                    frame_idx += 1

                    if self.on_frame:
                        try:
                            self.on_frame(frame)
                        except Exception:
                            pass

                elapsed = time.monotonic() - start
                sleep_time = max(0.0, interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("capture_frame_error", error=str(e))
                await asyncio.sleep(interval)

    async def _capture_frame(self, last_url: str) -> RecordedFrame | None:
        if not self._page:
            return None

        try:
            cursor = {"x": 0, "y": 0}
            try:
                cursor = await self._page.evaluate(_GET_CURSOR_JS)
            except Exception:
                pass

            try:
                await self._page.evaluate(
                    f"({_CURSOR_OVERLAY_JS})({cursor.get('x', 0)}, {cursor.get('y', 0)})"
                )
            except Exception:
                pass

            screenshot_bytes = await self._page.screenshot(type="jpeg", quality=60)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            try:
                await self._page.evaluate(_REMOVE_OVERLAY_JS)
            except Exception:
                pass

            url = ""
            try:
                url = self._page.url or ""
            except Exception:
                pass

            title = ""
            try:
                title = await self._page.title() or ""
            except Exception:
                pass

            dom_summary: list[dict[str, str]] = []
            try:
                dom_summary = await self._page.evaluate(_GET_ACCESSIBILITY_JS) or []
            except Exception:
                pass

            action = None
            action_detail = ""
            if url != last_url and last_url:
                action = "navigate"
                action_detail = f"Navigated to {url[:100]}"

            return RecordedFrame(
                timestamp=time.monotonic(),
                screenshot_b64=screenshot_b64,
                cursor_x=int(cursor.get("x", 0)),
                cursor_y=int(cursor.get("y", 0)),
                url=url,
                title=title,
                action=action,
                action_detail=action_detail,
                dom_summary=dom_summary,
            )

        except Exception as e:
            logger.debug("frame_capture_failed", error=str(e))
            return None

    def _drain_page_events(self, frame: RecordedFrame) -> list[ActionEvent]:
        events = list(frame.page_events)
        frame.page_events = []
        return events

    async def drain_page_events(self) -> list[ActionEvent]:
        if not self._page or not self._session:
            return []

        try:
            raw_events = await self._page.evaluate(_DRAIN_EVENTS_JS)
        except Exception:
            return []

        if not raw_events or not isinstance(raw_events, list):
            return []

        events = []
        for evt in raw_events:
            evt_type = evt.get("type", "")
            if evt_type == "click":
                el_info = {
                    "tag": evt.get("tag", ""),
                    "text": evt.get("text", "")[:60],
                    "id": evt.get("id", ""),
                    "href": evt.get("href", ""),
                    "aria_label": evt.get("ariaLabel", ""),
                    "role": evt.get("role", ""),
                    "class": evt.get("cls", "")[:80],
                }
                detail = self._describe_click(el_info)
                events.append(ActionEvent(
                    timestamp=time.monotonic(),
                    action_type="click",
                    detail=detail,
                    url="",
                    text=el_info.get("text", ""),
                    element_info=el_info,
                ))
            elif evt_type == "input":
                el_info = {
                    "tag": evt.get("tag", ""),
                    "name": evt.get("inputName", ""),
                    "id": evt.get("id", ""),
                    "placeholder": evt.get("placeholder", ""),
                    "aria_label": evt.get("ariaLabel", ""),
                    "type": evt.get("inputType", ""),
                }
                value = evt.get("value", "")
                detail = self._describe_input(el_info, value)
                events.append(ActionEvent(
                    timestamp=time.monotonic(),
                    action_type="input",
                    detail=detail,
                    url="",
                    text=value,
                    element_info=el_info,
                ))

        self._session.actions.extend(events)

        current_url = ""
        if self._page:
            try:
                current_url = self._page.url or ""
            except Exception:
                pass
        for evt in events:
            if not evt.url and current_url:
                evt.url = current_url

        return events

    def _describe_click(self, el: dict[str, str]) -> str:
        tag = el.get("tag", "").upper()
        text = el.get("text", "").strip()
        aria = el.get("aria_label", "")
        role = el.get("role", "")
        el_id = el.get("id", "")
        href = el.get("href", "")

        if tag == "A" and href:
            label = text or aria or href[:60]
            return f"Click link '{label}'"
        if tag == "BUTTON" or role == "button":
            label = text or aria or el_id or "button"
            return f"Click button '{label}'"
        if tag == "INPUT":
            itype = el.get("inputType", el.get("type", ""))
            if itype in ("submit", "button", "reset"):
                label = aria or el_id or itype
                return f"Click submit '{label}'"
            if itype == "checkbox":
                return f"Click checkbox '{aria or el_id or text}'"
            if itype == "radio":
                return f"Click radio '{aria or el_id or text}'"
        label = text or aria or el_id or tag.lower()
        return f"Click '{label}'"

    def _describe_input(self, el: dict[str, str], value: str) -> str:
        tag = el.get("tag", "").upper()
        name = el.get("name", "")
        placeholder = el.get("placeholder", "")
        aria = el.get("aria_label", "")
        el_id = el.get("id", "")
        field_label = aria or placeholder or name or el_id or tag.lower()
        display_val = value[:50] if value else "(empty)"
        return f"Type '{display_val}' into '{field_label}'"

    def _stream_frame_to_disk(self, frame: RecordedFrame, idx: int) -> None:
        if not self._session or not self._session._disk_dir:
            return
        try:
            frame_path = self._session._disk_dir / f"frame_{idx:04d}.jpg"
            frame_path.write_bytes(base64.b64decode(frame.screenshot_b64))

            meta = {
                "idx": idx,
                "timestamp": frame.timestamp,
                "url": frame.url,
                "title": frame.title,
                "cursor_x": frame.cursor_x,
                "cursor_y": frame.cursor_y,
                "action": frame.action,
                "action_detail": frame.action_detail,
                "dom_summary": frame.dom_summary[:30] if frame.dom_summary else [],
            }
            meta_path = self._session._disk_dir / f"frame_{idx:04d}.json"
            meta_path.write_text(json.dumps(meta, default=str))
        except Exception as e:
            logger.debug("frame_stream_to_disk_failed", error=str(e))

    def _flush_manifest(self) -> None:
        if not self._session or not self._session._disk_dir:
            return
        try:
            actions_data = []
            for a in self._session.actions:
                actions_data.append({
                    "action_type": a.action_type,
                    "detail": a.detail,
                    "url": a.url,
                    "text": a.text,
                    "element_info": a.element_info,
                })

            manifest = {
                "session_id": self._session.id,
                "name": self._session.name,
                "description": self._session.description,
                "frame_count": self._session.frame_count,
                "action_count": len(self._session.actions),
                "duration_seconds": self._session.duration_seconds,
                "actions": actions_data,
            }
            manifest_path = self._session._disk_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
        except Exception as e:
            logger.debug("manifest_flush_failed", error=str(e))


def draw_cursor_on_frame(screenshot_b64: str, cursor_x: int, cursor_y: int) -> str:
    if cursor_x == 0 and cursor_y == 0:
        return screenshot_b64

    try:
        from PIL import Image, ImageDraw

        img_bytes = base64.b64decode(screenshot_b64)
        img = Image.open(io.BytesIO(img_bytes))
        draw = ImageDraw.Draw(img)

        radius = 10
        bbox = [
            cursor_x - radius,
            cursor_y - radius,
            cursor_x + radius,
            cursor_y + radius,
        ]
        draw.ellipse(
            bbox, fill=(255, 50, 50, 180), outline=(255, 255, 255, 230), width=3
        )

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError:
        return screenshot_b64
    except Exception:
        return screenshot_b64
