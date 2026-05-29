from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.agent.manager import ManagerAgent, ManagerPlan
from sediman.agent.planner import ScheduleIntent
from sediman.llm.provider import LLMResponse


class TestManagerAgentRegexFastPath:
    @pytest.mark.asyncio
    async def test_every_5_minutes_uses_regex(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock()
        manager = ManagerAgent(llm)

        plan = await manager.plan("get nvidia stock price every 5 minutes")

        assert plan.browser_task == ""
        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"
        assert plan.schedule.task == "get nvidia stock price"
        llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_every_hour_uses_regex(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock()
        manager = ManagerAgent(llm)

        plan = await manager.plan("check server status every hour")

        assert plan.schedule is not None
        assert plan.schedule.cron == "0 * * * *"
        llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_uses_regex(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock()
        manager = ManagerAgent(llm)

        plan = await manager.plan("send report daily")

        assert plan.schedule is not None
        llm.chat.assert_not_called()


class TestManagerAgentLLMPlanning:
    @pytest.mark.asyncio
    async def test_simple_task_passes_through(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "go to hacker news", "schedule": null, "memory": null, "skill_name": null, "skill_description": null}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        plan = await manager.plan("go to hacker news")

        assert plan.browser_task == "go to hacker news"
        assert plan.schedule is None

    @pytest.mark.asyncio
    async def test_llm_extracts_schedule(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "check GPU prices on Amazon", "schedule": {"cron": "0 */2 * * *", "task": "check GPU prices"}, "memory": null, "skill_name": "gpu-price-checker", "skill_description": "Check GPU prices on Amazon"}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        plan = await manager.plan("track GPU prices on Amazon as a recurring task with 2-hour intervals")

        assert plan.browser_task == "check GPU prices on Amazon"
        assert plan.schedule is not None
        assert plan.schedule.cron == "0 */2 * * *"
        assert plan.skill_name == "gpu-price-checker"

    @pytest.mark.asyncio
    async def test_llm_extracts_memory(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "search for apartments", "schedule": null, "memory": "User is looking for 2BR apartments under $2000", "skill_name": null, "skill_description": null}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        conversation = [
            {"role": "user", "content": "I'm moving to a new city"},
        ]
        plan = await manager.plan("I need a 2BR apartment under $2000, search for me", conversation)

        assert plan.memory == "User is looking for 2BR apartments under $2000"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_passthrough(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=Exception("API error"))
        manager = ManagerAgent(llm)

        plan = await manager.plan("go to google and search for cats")

        assert plan.browser_task == "go to google and search for cats"
        assert plan.schedule is None

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text="I can't do JSON sorry",
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        plan = await manager.plan("go to google")

        assert plan.browser_task == "go to google"

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='```json\n{"browser_task": "go to reddit", "schedule": null, "memory": null, "skill_name": null, "skill_description": null}\n```',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        plan = await manager.plan("go to reddit")

        assert plan.browser_task == "go to reddit"


class TestManagerAgentConversationContext:
    @pytest.mark.asyncio
    async def test_follow_up_understood_with_context(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "go to ebay and buy xyz", "schedule": null, "memory": null, "skill_name": null, "skill_description": null}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        conversation = [
            {"role": "user", "content": "go to amazon and buy me xyz"},
            {"role": "assistant", "content": "I went to amazon and found xyz for $29.99"},
        ]

        plan = await manager.plan("ah sorry should be ebay", conversation)

        assert "ebay" in plan.browser_task.lower()
        call_args = llm.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1].get("messages", [])
        system_msg = messages[0]["content"]
        assert "<conversation_history>" in system_msg
        assert "amazon" in system_msg

    @pytest.mark.asyncio
    async def test_follow_up_without_context_goes_to_llm(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "go to ebay and buy xyz", "schedule": null, "memory": null, "skill_name": null, "skill_description": null}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        plan = await manager.plan("ah sorry should be ebay")

        assert plan.browser_task == "go to ebay and buy xyz"

    @pytest.mark.asyncio
    async def test_scheduling_with_conversation_goes_to_llm(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=LLMResponse(
            text='{"browser_task": "check nvidia stock price on yahoo finance", "schedule": {"cron": "*/5 * * * *", "task": "check nvidia stock price"}, "memory": null, "skill_name": null, "skill_description": null}',
            tool_calls=[],
        ))
        manager = ManagerAgent(llm)

        conversation = [
            {"role": "user", "content": "what is nvidia stock price"},
            {"role": "assistant", "content": "NVDA is $131.28"},
        ]

        plan = await manager.plan("check it every 5 minutes", conversation)

        assert "nvidia" in plan.browser_task.lower() or "stock" in plan.browser_task.lower()
        assert plan.schedule is not None

    @pytest.mark.asyncio
    async def test_regex_schedule_without_conversation_skips_llm(self, tmp_sediman_dir):
        llm = MagicMock()
        llm.chat = AsyncMock()
        manager = ManagerAgent(llm)

        plan = await manager.plan("get nvidia stock price every 5 minutes")

        assert plan.schedule is not None
        assert plan.schedule.cron == "*/5 * * * *"
        llm.chat.assert_not_called()


class TestManagerAgentJSONExtraction:
    def test_extracts_plain_json(self):
        manager = ManagerAgent(MagicMock())
        result = manager._extract_json('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_extracts_from_markdown(self):
        manager = ManagerAgent(MagicMock())
        result = manager._extract_json('```json\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_extracts_embedded_json(self):
        manager = ManagerAgent(MagicMock())
        result = manager._extract_json('Here is my plan: {"key": "value"} done')
        assert result == '{"key": "value"}'

    def test_returns_none_for_no_json(self):
        manager = ManagerAgent(MagicMock())
        result = manager._extract_json("no json here")
        assert result is None


class TestManagerPlanDataclass:
    def test_defaults(self):
        plan = ManagerPlan(browser_task="do stuff")
        assert plan.browser_task == "do stuff"
        assert plan.schedule is None
        assert plan.memory is None
        assert plan.skill_name is None
        assert plan.skill_description is None

    def test_with_all_fields(self):
        plan = ManagerPlan(
            browser_task="check price",
            schedule=ScheduleIntent(cron="*/5 * * * *", task="check price"),
            memory="user prefers Amazon",
            skill_name="price-checker",
            skill_description="Check price on Amazon",
        )
        assert plan.schedule.cron == "*/5 * * * *"
        assert plan.memory == "user prefers Amazon"
        assert plan.skill_name == "price-checker"
