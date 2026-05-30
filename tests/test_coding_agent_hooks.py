from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sediman.agent.coding_agent.hooks import (
    HookPipeline,
    HookContext,
    PreHookResult,
    PostHookResult,
    secret_detection_pre_hook,
    audit_log_post_hook,
    destructive_command_pre_hook,
    file_size_pre_hook,
    create_default_pipeline,
)
from sediman.agent.tool_dispatch import ToolResult


class TestHookPipeline:
    def test_default_pipeline_created(self):
        pipeline = create_default_pipeline()
        assert pipeline is not None
        assert pipeline.enabled

    def test_pipeline_enable_disable(self):
        pipeline = create_default_pipeline()
        pipeline.enabled = False
        assert not pipeline.enabled

    @pytest.mark.asyncio
    async def test_run_pre_allows_safe_tool(self):
        pipeline = create_default_pipeline()
        ctx = HookContext(
            tool_name="read_file",
            tool_input={"path": "/tmp/test.py"},
        )
        result = await pipeline.run_pre("read_file", {"path": "/tmp/test.py"}, ctx)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_run_post_allows_safe_result(self):
        pipeline = create_default_pipeline()
        ctx = HookContext(tool_name="read_file", tool_input={})
        result = await pipeline.run_post(
            "read_file",
            ToolResult(success=True, output="file contents"),
            ctx,
        )
        assert result.should_continue is True

    @pytest.mark.asyncio
    async def test_custom_pre_hook_registered(self):
        pipeline = HookPipeline()

        async def my_hook(ctx):
            return PreHookResult(allowed=False, reason="test block")

        pipeline.register_pre("write_file", my_hook)
        ctx = HookContext(tool_name="write_file", tool_input={})
        result = await pipeline.run_pre("write_file", {}, ctx)
        assert not result.allowed
        assert result.reason == "test block"

    @pytest.mark.asyncio
    async def test_custom_post_hook_registered(self):
        pipeline = HookPipeline()

        async def my_post_hook(ctx, result):
            return PostHookResult(
                should_continue=False,
                actions=["format"],
            )

        pipeline.register_post("write_file", my_post_hook)
        ctx = HookContext(tool_name="write_file", tool_input={})
        result = await pipeline.run_post(
            "write_file",
            ToolResult(success=True, output="ok"),
            ctx,
        )
        assert not result.should_continue
        assert "format" in result.actions

    @pytest.mark.asyncio
    async def test_pipeline_disabled_skips_hooks(self):
        pipeline = HookPipeline()
        pipeline.enabled = False

        async def blocking_hook(ctx):
            return PreHookResult(allowed=False, reason="should not run")

        pipeline.register_pre("read_file", blocking_hook)
        result = await pipeline.run_pre("read_file", {}, None)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_global_pre_hook_runs(self):
        pipeline = HookPipeline()

        async def global_pre(ctx):
            return PreHookResult(
                allowed=True,
                modified_input={"enriched": True},
            )

        pipeline.register_global_pre(global_pre)
        ctx = HookContext(tool_name="read_file", tool_input={"path": "test.py"})
        result = await pipeline.run_pre("read_file", {"path": "test.py"}, ctx)
        assert result.allowed
        assert result.modified_input
        assert result.modified_input.get("enriched") is True

    @pytest.mark.asyncio
    async def test_hook_error_does_not_crash(self):
        pipeline = HookPipeline()

        async def crashing_hook(ctx):
            raise RuntimeError("hook error")

        pipeline.register_pre("read_file", crashing_hook)
        result = await pipeline.run_pre("read_file", {}, None)
        assert result.allowed is True


class TestSecretDetectionHook:
    @pytest.mark.asyncio
    async def test_blocks_api_key(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": "config.py",
                "content": 'API_KEY = "sk-1234567890abcdef1234567890abcdef"',
            },
        )
        result = await secret_detection_pre_hook(ctx)
        assert not result.allowed
        assert "secret" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_blocks_github_token(self):
        ctx = HookContext(
            tool_name="patch",
            tool_input={
                "path": ".env",
                "new": "GITHUB_TOKEN=ghp_1234567890abcdef1234567890abcdef1234",
            },
        )
        result = await secret_detection_pre_hook(ctx)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_allows_safe_content(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": "README.md",
                "content": "# Hello World\nThis is a document.",
            },
        )
        result = await secret_detection_pre_hook(ctx)
        assert result.allowed

    @pytest.mark.asyncio
    async def test_skips_non_file_tools(self):
        ctx = HookContext(
            tool_name="terminal",
            tool_input={"command": "echo hello"},
        )
        result = await secret_detection_pre_hook(ctx)
        assert result.allowed

    @pytest.mark.asyncio
    async def test_blocks_password_assignment(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": "config.py",
                "content": 'password = "my-secret-password-123"',
            },
        )
        result = await secret_detection_pre_hook(ctx)
        assert not result.allowed


class TestDestructiveCommandHook:
    @pytest.mark.asyncio
    async def test_blocks_rm_rf(self):
        ctx = HookContext(
            tool_name="terminal",
            tool_input={"command": "rm -rf /important/dir"},
        )
        result = await destructive_command_pre_hook(ctx)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_blocks_force_push(self):
        ctx = HookContext(
            tool_name="terminal",
            tool_input={"command": "git push --force origin main"},
        )
        result = await destructive_command_pre_hook(ctx)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_allows_safe_command(self):
        ctx = HookContext(
            tool_name="terminal",
            tool_input={"command": "npm install express"},
        )
        result = await destructive_command_pre_hook(ctx)
        assert result.allowed

    @pytest.mark.asyncio
    async def test_skips_non_terminal(self):
        ctx = HookContext(
            tool_name="read_file",
            tool_input={"command": "rm -rf /"},
        )
        result = await destructive_command_pre_hook(ctx)
        assert result.allowed


class TestFileSizeHook:
    @pytest.mark.asyncio
    async def test_blocks_huge_file(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": "large.py",
                "content": "x" * 600_000,
            },
        )
        result = await file_size_pre_hook(ctx)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_blocks_env_file(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": ".env.production",
                "content": "DEBUG=false",
            },
        )
        result = await file_size_pre_hook(ctx)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_allows_normal_file(self):
        ctx = HookContext(
            tool_name="write_file",
            tool_input={
                "path": "app.py",
                "content": "print('hello')",
            },
        )
        result = await file_size_pre_hook(ctx)
        assert result.allowed
