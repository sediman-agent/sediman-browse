from __future__ import annotations

import json
from typing import Any

import structlog

from sediman.agent.prompts.builder import _load_template
from sediman.agent.screen_recorder import (
    ActionEvent,
    RecordedFrame,
    RecordingSession,
    draw_cursor_on_frame,
)
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()


class TraceToSkill:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def convert(
        self,
        session: RecordingSession,
        max_frames: int = 25,
    ) -> dict[str, Any] | None:
        if len(session.frames) < 3:
            logger.debug("trace_too_short", frames=len(session.frames))
            return None

        key_frames = session.get_key_frames(max_frames=max_frames)
        if not key_frames:
            return None

        system_prompt = _load_template("trace_to_skill.md")
        if not system_prompt:
            logger.warning("trace_to_skill_template_missing")
            return None

        user_message = self._build_user_message(session, key_frames)

        messages = [
            {"role": "system", "content": system_prompt},
            user_message,
        ]

        try:
            response = await self.llm.chat(messages=messages, tools=[])
            if not response.text:
                return None

            data = self._parse_response(response.text)
            if not data:
                return None

            data = await self._extract_variables(session, data)

            if data.get("should_learn") and data.get("steps"):
                data = await self._refine_steps(session, data)

            return data
        except Exception as e:
            logger.warning("trace_to_skill_failed", error=str(e))
            return None

    def _build_user_message(
        self,
        session: RecordingSession,
        key_frames: list[RecordedFrame],
    ) -> dict[str, Any]:
        content_parts: list[dict[str, Any]] = []

        header = (
            f'Screen Recording: "{session.name}"\n'
            f"Duration: {session.duration_seconds:.1f}s\n"
            f"Total frames captured: {session.frame_count}\n"
            f"Actions detected: {len(session.actions)}\n"
        )

        if session.description:
            header += f"User-provided description: {session.description}\n"

        action_summary = self._summarize_actions(session.actions)
        if action_summary:
            header += f"\nAction summary:\n{action_summary}\n"

        header += "\n--- Frame Sequence ---\n\n"

        content_parts.append({"type": "text", "text": header})

        for i, frame in enumerate(key_frames, 1):
            elapsed = frame.timestamp - session.started_at

            frame_text = f"\n[Frame {i}] t={elapsed:.1f}s"
            frame_text += f"\nURL: {frame.url or '(no URL)'}"
            if frame.title:
                frame_text += f"\nPage title: {frame.title}"
            if frame.has_cursor():
                frame_text += f"\nCursor position: ({frame.cursor_x}, {frame.cursor_y})"
            if frame.action:
                frame_text += f"\nAction: {frame.action}"
                if frame.action_detail:
                    frame_text += f" — {frame.action_detail}"

            if frame.dom_summary:
                dom_text = self._format_dom_summary(frame.dom_summary)
                if dom_text:
                    frame_text += f"\nDOM elements:\n{dom_text}"

            frame_text += "\nScreenshot:\n"

            content_parts.append({"type": "text", "text": frame_text})

            frame_b64 = draw_cursor_on_frame(
                frame.screenshot_b64, frame.cursor_x, frame.cursor_y
            )

            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "low",
                    },
                }
            )

        content_parts.append(
            {
                "type": "text",
                "text": (
                    "\n--- End of Recording ---\n\n"
                    "Analyze the recording above and extract a reusable skill.\n\n"
                    "IMPORTANT: Include these fields in your JSON response:\n"
                    '- "variables": a list of parameter names that vary between runs '
                    "(e.g. search queries, URLs, form values, dates). "
                    "Use {{variable_name}} placeholders in steps.\n"
                    '- "verification": a short description of how to verify the skill worked.\n'
                    '- "when_to_use": when this skill should be triggered automatically.\n'
                    '- "pitfalls": a list of things that could go wrong.'
                ),
            }
        )

        return {"role": "user", "content": content_parts}

    def _summarize_actions(self, actions: list[ActionEvent]) -> str:
        if not actions:
            return ""
        lines = []
        for i, a in enumerate(actions[:30], 1):
            detail = a.detail or a.action_type
            url_part = f" [{a.url[:60]}]" if a.url else ""
            lines.append(f"  {i}. {a.action_type}: {detail}{url_part}")
        return "\n".join(lines)

    def _format_dom_summary(self, dom_summary: list[dict[str, str]]) -> str:
        if not dom_summary:
            return ""
        lines = []
        for el in dom_summary[:20]:
            tag = el.get("tag", "").upper()
            parts = [tag]
            text = el.get("text", "").strip()
            if text:
                parts.append(f'"{text[:40]}"')
            el_id = el.get("id", "")
            if el_id:
                parts.append(f"#{el_id}")
            role = el.get("role", "")
            if role:
                parts.append(f"[role={role}]")
            aria = el.get("aria-label", "")
            if aria:
                parts.append(f'[aria="{aria[:30]}"]')
            href = el.get("href", "")
            if href:
                parts.append(f"→ {href[:60]}")
            placeholder = el.get("placeholder", "")
            if placeholder:
                parts.append(f'placeholder="{placeholder[:30]}"')
            el_type = el.get("type", "")
            if el_type:
                parts.append(f"type={el_type}")
            lines.append(f"  - {' '.join(parts)}")
        return "\n".join(lines)

    async def _extract_variables(
        self, session: RecordingSession, data: dict[str, Any]
    ) -> dict[str, Any]:
        if not data.get("should_learn"):
            return data

        actions = session.actions
        if not actions:
            return data

        variable_prompt = (
            "Given these user actions from a screen recording, identify reusable variables/parameters.\n\n"
            "Actions:\n"
        )
        for i, a in enumerate(actions[:20], 1):
            variable_prompt += f"{i}. {a.action_type}: {a.detail}"
            if a.text:
                variable_prompt += f" (value: {a.text[:50]})"
            variable_prompt += "\n"

        variable_prompt += (
            "\nSteps extracted so far:\n"
            + "\n".join(f"- {s}" for s in data.get("steps", []))
            + "\n\n"
            'Respond with JSON: {"variables": ["var1", "var2", ...]}\n'
            "Only include values that would change between runs (search queries, URLs, names, dates, etc.).\n"
            "Do NOT include fixed navigation or static labels."
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": "You extract reusable variables from browser automation traces."},
                    {"role": "user", "content": variable_prompt},
                ],
                tools=[],
            )
            if response.text:
                var_text = response.text.strip()
                if "```json" in var_text:
                    var_text = var_text.split("```json")[1].split("```")[0].strip()
                elif "```" in var_text:
                    var_text = var_text.split("```")[1].split("```")[0].strip()

                if "{" in var_text:
                    start = var_text.find("{")
                    end = var_text.rfind("}")
                    if end > start:
                        var_data = json.loads(var_text[start : end + 1])
                        if isinstance(var_data.get("variables"), list):
                            data["variables"] = var_data["variables"]
        except Exception as e:
            logger.debug("variable_extraction_failed", error=str(e))

        if "variables" not in data:
            data["variables"] = []

        return data

    async def _refine_steps(
        self, session: RecordingSession, data: dict[str, Any]
    ) -> dict[str, Any]:
        steps = data.get("steps", [])
        if len(steps) < 3:
            return data

        refine_prompt = (
            "Refine these skill steps to be more robust and reusable.\n\n"
            f"Original task: {session.description or session.name}\n\n"
            f"Current steps:\n"
            + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
            + "\n\n"
            "DOM context from key frames:\n"
        )

        action_frames = session.get_action_frames()
        for f in action_frames[:10]:
            if f.dom_summary:
                refine_prompt += f"\nAt {f.url}:\n"
                refine_prompt += self._format_dom_summary(f.dom_summary) + "\n"

        refine_prompt += (
            "\nRefine the steps to:\n"
            "1. Use CSS selectors or aria-labels from the DOM where possible\n"
            "2. Add wait/verify steps between critical actions\n"
            "3. Replace specific values with {{variable}} placeholders\n"
            '4. Return the refined steps as JSON: {"steps": ["step1", "step2", ...]}'
        )

        try:
            response = await self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You refine browser automation steps for robustness.",
                    },
                    {"role": "user", "content": refine_prompt},
                ],
                tools=[],
            )
            if response.text:
                refined = response.text.strip()
                if "```json" in refined:
                    refined = refined.split("```json")[1].split("```")[0].strip()
                elif "```" in refined:
                    refined = refined.split("```")[1].split("```")[0].strip()

                if "{" in refined:
                    start = refined.find("{")
                    end = refined.rfind("}")
                    if end > start:
                        refined_data = json.loads(refined[start : end + 1])
                        if isinstance(refined_data.get("steps"), list) and len(refined_data["steps"]) >= 2:
                            data["steps"] = refined_data["steps"]
        except Exception as e:
            logger.debug("step_refinement_failed", error=str(e))

        return data

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        text = text.strip()

        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        text = text.strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
            else:
                return None

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.debug("trace_to_skill_json_parse_failed", text=text[:200])
            return None

        if not isinstance(data, dict):
            return None

        if not data.get("should_learn"):
            reason = data.get("reason", "Not worth learning")
            logger.info("trace_to_skill_skipped", reason=reason)
            return None

        required = ["skill_name", "description", "steps"]
        for field_name in required:
            if field_name not in data:
                logger.debug("trace_to_skill_missing_field", field=field_name)
                return None

        if not isinstance(data["steps"], list) or len(data["steps"]) < 2:
            logger.debug("trace_to_skill_too_few_steps")
            return None

        return data
