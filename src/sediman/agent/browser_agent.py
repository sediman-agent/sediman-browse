from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import structlog

from sediman.agent.prompts.builder import PromptBuilder
from sediman.browser.session import BrowserSession, run_browser_task
from sediman.llm.provider import LLMProvider

logger = structlog.get_logger()


@dataclass
class BrowserResult:
    text: str
    actions: list[dict[str, Any]]


class BrowserSubagent:
    def __init__(
        self,
        browser_session: BrowserSession,
        llm_provider: LLMProvider,
        max_steps: int = 50,
        flash_mode: bool = True,
        on_browser_step: Callable[[str, str], None] | None = None,
        conversation: list[dict[str, str]] | None = None,
        recording_name: str | None = None,
        memory_context: str | None = None,
    ):
        self.browser = browser_session
        self.llm = llm_provider
        self.max_steps = max_steps
        self.flash_mode = flash_mode
        self._prompt_builder = PromptBuilder(flash_mode=flash_mode)
        self._on_browser_step = on_browser_step
        self._conversation = conversation or []
        self._recording_name = recording_name
        self._memory_context = memory_context

    async def run(
        self,
        task: str,
        skill_summaries: str | None = None,
    ) -> BrowserResult:
        from sediman.memory.store import MemoryStore

        memory_ctx = self._memory_context
        if memory_ctx is None:
            memory_store = MemoryStore()
            memory_ctx = memory_store.format_for_system_prompt()

        system_prompt = self._prompt_builder.build_system_prompt(
            skill_summaries=skill_summaries,
            memory_context=memory_ctx,
        )

        if self._conversation:
            from sediman.utils import format_conversation_context

            context = format_conversation_context(self._conversation, limit=8)
            system_prompt += (
                f"\n\n<conversation_context>\n"
                f"This task is part of an ongoing conversation. "
                f"Use this context to understand references and follow-ups:\n"
                f"{context}\n"
                f"</conversation_context>"
            )

        on_step = self._on_browser_step
        recording_callback = self._get_recording_callback()
        if recording_callback and on_step:
            original = on_step
            def merged_on_step(action: str, url: str) -> None:
                original(action, url)
                recording_callback(action, url)
            on_step = merged_on_step
        elif recording_callback:
            on_step = recording_callback

        logger.info("browser_subagent_start", task=task[:80])

        result_text, actions = await run_browser_task(
            task=task,
            browser_session=self.browser,
            llm=self.llm.get_browser_use_llm(),
            max_steps=self.max_steps,
            system_prompt=system_prompt,
            flash_mode=self.flash_mode,
            on_step=on_step,
        )

        logger.info(
            "browser_subagent_done",
            result_length=len(result_text),
            actions=len(actions),
        )

        return BrowserResult(text=result_text, actions=actions)

    def _get_recording_callback(self) -> Callable[[str, str], None] | None:
        if not self._recording_name:
            return None
        try:
            from sediman.agent.recording_manager import RecordingManager
            mgr = RecordingManager.get_instance()
            return mgr.create_on_step_callback(self._recording_name)
        except Exception:
            return None
