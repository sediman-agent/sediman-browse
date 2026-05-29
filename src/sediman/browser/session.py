from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Callable

import structlog

logger = structlog.get_logger()

SESSION_DIR = Path.home() / ".sediman" / "sessions"
DATA_DIR = Path.home() / ".sediman"


class BrowserSession:
    """Persistent browser session — stays open across tasks, never closes tabs."""

    def __init__(
        self,
        headless: bool = False,
        user_data_dir: str | None = None,
        on_screenshot: Callable[[str], None] | None = None,
    ):
        self.headless = headless
        self.user_data_dir = user_data_dir or str(DATA_DIR / "browser-profile")
        self._browser: Any = None
        self._started = False
        self._start_lock = asyncio.Lock()
        self.on_screenshot = on_screenshot

    @property
    def is_started(self) -> bool:
        return self._started and self._browser is not None

    async def start(self) -> None:
        async with self._start_lock:
            if self._started and self._browser:
                return

            from browser_use import Browser

            kwargs: dict[str, Any] = {
                "headless": self.headless,
                "highlight_elements": True,
                "user_data_dir": self.user_data_dir,
                "keep_alive": True,
            }

            self._browser = Browser(**kwargs)
            self._started = True
            logger.info("browser_session_started", headless=self.headless, vision=True)

    async def stop(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("browser_close_failed", error=str(e))
            self._browser = None
            self._started = False
            logger.info("browser_session_stopped")

    @property
    def browser(self) -> Any:
        return self._browser

    async def take_screenshot(self) -> str | None:
        try:
            if not self._browser:
                return None
            session = await self._browser.create_session()
            page = session.agent_current_page
            if not page:
                return None
            screenshot_bytes = await page.screenshot()
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.debug("screenshot_failed", error=str(e))
            return None

    async def save_state(self, name: str) -> None:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        try:
            session = await self._browser.create_session()
            state = await session.browser_context.storage_state()
            state_path = SESSION_DIR / f"{name}.json"
            state_path.write_text(json.dumps(state, indent=2))
            logger.info("session_state_saved", name=name)
        except Exception as e:
            logger.warning("save_state_failed", error=str(e))

    async def load_state(self, name: str) -> bool:
        state_path = SESSION_DIR / f"{name}.json"
        if not state_path.exists():
            return False
        try:
            state = json.loads(state_path.read_text())
            session = await self._browser.create_session()
            cookies = state.get("cookies", [])
            if cookies:
                await session.browser_context.add_cookies(cookies)
            origins = state.get("origins", [])
            if origins:
                for origin in origins:
                    for entry in origin.get("localStorage", []):
                        await session.browser_context.evaluate(
                            "localStorage.setItem(key, value)",
                            arg={
                                "key": entry.get("name", ""),
                                "value": entry.get("value", ""),
                            },
                        )
            logger.info("session_state_loaded", name=name, cookies=len(cookies))
            return True
        except Exception as e:
            logger.warning("load_state_failed", name=name, error=str(e))
            return False


def extract_result(raw_result: Any) -> str:
    _NO_RESULT = "The browser agent could not extract a result from the page. The task may not have produced visible output."

    if raw_result is None:
        return _NO_RESULT

    if isinstance(raw_result, str):
        return raw_result if raw_result.strip() else _NO_RESULT

    try:
        fr = raw_result.final_result
        if callable(fr):
            fr = fr()
        if fr and isinstance(fr, str) and fr.strip():
            return fr
    except Exception:
        pass

    parts = []
    if hasattr(raw_result, "all_results"):
        for r in raw_result.all_results:
            if hasattr(r, "extracted_content") and r.extracted_content:
                parts.append(r.extracted_content)
            elif hasattr(r, "long_term_memory") and r.long_term_memory:
                parts.append(r.long_term_memory)

    if parts:
        return "\n".join(parts)

    if hasattr(raw_result, "all_model_outputs"):
        outputs = raw_result.all_model_outputs
        if outputs:
            return json.dumps(outputs[-1], indent=2, default=str)

    return _NO_RESULT


async def run_browser_task(
    task: str,
    browser_session: BrowserSession,
    llm: Any,
    max_steps: int = 50,
    history: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    flash_mode: bool = True,
    on_step: Callable[[str, str], None] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    from browser_use import Agent

    step_callback = None
    if on_step:

        def step_callback(browser_state: Any, agent_output: Any, step_num: int) -> None:
            url = ""
            try:
                url = getattr(browser_state, "url", "") or ""
            except Exception:
                pass
            action_name = ""
            action_detail = ""
            try:
                if hasattr(agent_output, "action"):
                    action_obj = agent_output.action
                    if hasattr(action_obj, "name"):
                        action_name = action_obj.name
                    else:
                        action_name = (
                            type(action_obj)
                            .__name__.replace("Action", "")
                            .replace("AgentOutputAction", "done")
                        )
                    if hasattr(action_obj, "index"):
                        action_detail = f"element {action_obj.index}"
                    if hasattr(action_obj, "text"):
                        t = action_obj.text or ""
                        if t:
                            action_detail = f"{action_detail}: {t[:80]}" if action_detail else t[:80]
                    if hasattr(action_obj, "url"):
                        u = action_obj.url or ""
                        if u:
                            action_detail = f"navigate to {u[:100]}"
                elif isinstance(agent_output, dict):
                    action_name = agent_output.get(
                        "action", agent_output.get("type", "")
                    )
                    args = agent_output.get("arguments", agent_output)
                    if isinstance(args, dict):
                        u = args.get("url", "")
                        if u:
                            action_detail = f"navigate to {u[:100]}"
                        t = args.get("text", "")
                        if t:
                            action_detail = f"type '{t[:50]}'"
                        sel = args.get("selector", "")
                        if sel:
                            action_detail = f"{action_detail} in {sel[:50]}" if action_detail else f"click {sel[:50]}"
            except Exception:
                action_name = f"step {step_num}"
            detail = action_detail if action_detail else url
            on_step(action_name, detail)

    agent_kwargs: dict[str, Any] = {
        "task": task,
        "llm": llm,
        "browser": browser_session.browser,
        "use_vision": True,
        "max_failures": max_steps,
        "max_actions_per_step": 5,
        "flash_mode": flash_mode,
        "step_timeout": 120,
        "llm_timeout": 60,
        "loop_detection_enabled": True,
    }

    if system_prompt:
        agent_kwargs["override_system_message"] = system_prompt

    if step_callback:
        agent_kwargs["register_new_step_callback"] = step_callback

    agent = Agent(**agent_kwargs)
    try:
        raw_result = await agent.run()
    except Exception as e:
        logger.warning("browser_task_failed", error=str(e))
        return str(e), []

    action_history = _extract_actions(raw_result)

    result_text = extract_result(raw_result)
    return result_text, action_history


def _extract_actions(raw_result: Any) -> list[dict[str, Any]]:
    actions = []
    if hasattr(raw_result, "all_model_outputs") and raw_result.all_model_outputs is not None:
        for output in raw_result.all_model_outputs:
            if isinstance(output, dict):
                actions.append(output)
    return actions
