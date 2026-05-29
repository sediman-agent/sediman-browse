from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Milestone:
    description: str
    index: int
    achieved: bool = False
    failed_count: int = 0


@dataclass
class ProgressReport:
    score: float
    loop_detected: bool = False
    milestone_achieved: str | None = None
    milestone_failed: str | None = None
    promise_score: float = 0.5
    url_progress: bool = False
    element_present: bool = False
    should_replan: bool = False
    reason: str = ""


class LoopDetector:
    def __init__(self, max_repeats: int = 2, window: int = 10):
        self._history: list[str] = []
        self._max_repeats = max_repeats
        self._window = window

    def record(self, action: str, page_url: str = "", page_text_hash: str = "") -> bool:
        key = _hash_state(action, page_url, page_text_hash)
        self._history.append(key)
        if len(self._history) > self._window * 2:
            self._history = self._history[-self._window:]
        recent = self._history[-self._window:]
        return recent.count(key) >= self._max_repeats

    def reset(self) -> None:
        self._history.clear()


class MilestoneTracker:
    def __init__(self, milestones: list[str] | None = None):
        self._milestones: list[Milestone] = []
        if milestones:
            for i, m in enumerate(milestones):
                self._milestones.append(Milestone(description=m, index=i))

    @property
    def milestones(self) -> list[Milestone]:
        return list(self._milestones)

    def next_unachieved(self) -> Milestone | None:
        for m in self._milestones:
            if not m.achieved:
                return m
        return None

    def mark_achieved(self, index: int) -> None:
        for m in self._milestones:
            if m.index == index:
                m.achieved = True
                return

    def mark_failed(self, index: int) -> None:
        for m in self._milestones:
            if m.index == index:
                m.failed_count += 1
                return

    def progress_fraction(self) -> float:
        if not self._milestones:
            return 0.0
        achieved = sum(1 for m in self._milestones if m.achieved)
        return achieved / len(self._milestones)

    def summaries(self) -> list[str]:
        return [
            f"{'✓' if m.achieved else '○'} {m.description}"
            for m in self._milestones
        ]


class ProgressTracker:
    def __init__(
        self,
        milestones: list[str] | None = None,
        check_interval: int = 3,
        replan_threshold: float = 0.3,
        max_milestone_failures: int = 2,
    ):
        self._milestone_tracker = MilestoneTracker(milestones)
        self._loop_detector = LoopDetector()
        self._check_interval = check_interval
        self._replan_threshold = replan_threshold
        self._max_milestone_failures = max_milestone_failures
        self._step_count = 0
        self._last_url: str = ""
        self._heuristic_elements: list[str] = []

    @property
    def milestones(self) -> MilestoneTracker:
        return self._milestone_tracker

    @property
    def loop_detector(self) -> LoopDetector:
        return self._loop_detector

    def check_heuristics(
        self,
        action: str,
        page_url: str = "",
        page_text: str = "",
        expected_elements: list[str] | None = None,
    ) -> ProgressReport:
        self._step_count += 1

        loop = self._loop_detector.record(action, page_url, _hash_text(page_text))

        url_progress = False
        if page_url and self._last_url and page_url != self._last_url:
            url_progress = True
        self._last_url = page_url

        element_present = False
        if expected_elements and page_text:
            for elem in expected_elements:
                if elem.lower() in page_text.lower():
                    element_present = True
                    break

        score = 0.5
        if loop:
            score -= 0.4
        if url_progress:
            score += 0.2
        if element_present:
            score += 0.2
        score = max(0.0, min(1.0, score))

        should_replan = loop or score < self._replan_threshold
        reason = ""
        if loop:
            reason = "Loop detected: same action+state repeated"
        elif score < self._replan_threshold:
            reason = f"Low progress score: {score:.2f}"

        return ProgressReport(
            score=score,
            loop_detected=loop,
            url_progress=url_progress,
            element_present=element_present,
            should_replan=should_replan,
            reason=reason,
        )

    async def check_milestone(
        self,
        llm: Any,
        milestone: Milestone,
        page_snapshot: str = "",
        page_url: str = "",
    ) -> ProgressReport:
        if milestone.achieved:
            return ProgressReport(score=1.0, milestone_achieved=milestone.description)

        prompt = (
            "You are evaluating whether a milestone in a web task has been achieved.\n\n"
            f"Milestone: {milestone.description}\n\n"
        )
        if page_url:
            prompt += f"Current URL: {page_url}\n\n"
        if page_snapshot:
            prompt += f"Current page state (first 2000 chars):\n{page_snapshot[:2000]}\n\n"
        prompt += (
            "Has this milestone been achieved? Respond with JSON:\n"
            '{"achieved": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}'
        )

        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
            )
            text = response.text or ""
            from sediman.utils import extract_json_from_text
            data = extract_json_from_text(text)
            if data is None:
                return ProgressReport(score=0.3, reason="Milestone check parse failed")

            achieved = bool(data.get("achieved", False))
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            if achieved:
                self._milestone_tracker.mark_achieved(milestone.index)
                return ProgressReport(
                    score=0.8 + 0.2 * confidence,
                    milestone_achieved=milestone.description,
                )
            else:
                self._milestone_tracker.mark_failed(milestone.index)
                should_replan = milestone.failed_count >= self._max_milestone_failures
                return ProgressReport(
                    score=0.2 * confidence,
                    milestone_failed=milestone.description,
                    should_replan=should_replan,
                    reason=f"Milestone not achieved (attempt {milestone.failed_count}): {data.get('reasoning', '')}",
                )
        except Exception as e:
            logger.warning("milestone_check_failed", error=str(e))
            return ProgressReport(score=0.3, reason=f"Milestone check error: {e}")

    async def evaluate_promise(
        self,
        llm: Any,
        task: str,
        current_step_description: str,
        page_snapshot: str = "",
    ) -> float:
        prompt = (
            "Rate how likely the overall task will succeed from the current state.\n\n"
            f"Task: {task}\n"
            f"Current step: {current_step_description}\n"
        )
        if page_snapshot:
            prompt += f"Page state (first 1000 chars):\n{page_snapshot[:1000]}\n"
        prompt += (
            "\nRespond with ONLY a number 1-5 where:\n"
            "1 = Definitely stuck/wrong path\n"
            "2 = Likely stuck\n"
            "3 = Uncertain\n"
            "4 = Making progress\n"
            "5 = Nearly done"
        )

        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=[],
            )
            text = (response.text or "").strip()
            for char in text:
                if char in "12345":
                    return int(char) / 5.0
            return 0.5
        except Exception:
            return 0.5

    def should_check_milestone(self) -> bool:
        return (
            self._step_count > 0
            and self._step_count % self._check_interval == 0
            and self._milestone_tracker.next_unachieved() is not None
        )

    def reset(self) -> None:
        self._loop_detector.reset()
        self._step_count = 0
        self._last_url = ""


def generate_milestones_prompt(task: str) -> str:
    return (
        "Break this task into 3-5 concrete milestones that indicate progress.\n"
        "Each milestone should be a verifiable state (e.g., 'navigated to search page', "
        "'search results visible', 'item added to cart').\n\n"
        f"Task: {task}\n\n"
        'Respond with JSON: {"milestones": ["milestone 1", "milestone 2", ...]}'
    )


def parse_milestones(text: str) -> list[str]:
    from sediman.utils import extract_json_from_text
    data = extract_json_from_text(text)
    if data and isinstance(data.get("milestones"), list):
        return [str(m) for m in data["milestones"] if str(m).strip()]
    return []


def _hash_state(action: str, url: str, text_hash: str) -> str:
    raw = f"{action}|{url}|{text_hash}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _hash_text(text: str) -> str:
    if not text:
        return ""
    return hashlib.md5(text[:2000].encode()).hexdigest()[:12]
