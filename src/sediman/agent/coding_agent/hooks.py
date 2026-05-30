from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

import structlog

from sediman.agent.tool_dispatch import ToolResult

logger = structlog.get_logger()


@dataclass
class HookContext:
    tool_name: str
    tool_input: dict[str, Any]
    session_id: str = ""
    agent_name: str = "coding_agent"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreHookResult:
    allowed: bool = True
    modified_input: dict[str, Any] | None = None
    reason: str = ""
    enrichments: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostHookResult:
    should_continue: bool = True
    modified_output: ToolResult | None = None
    reason: str = ""
    actions: list[str] = field(default_factory=list)


PreHook = Callable[[HookContext], Awaitable[PreHookResult]]
PostHook = Callable[[HookContext, ToolResult], Awaitable[PostHookResult]]


class HookPipeline:
    def __init__(self) -> None:
        self._pre_hooks: dict[str, list[PreHook]] = {}
        self._post_hooks: dict[str, list[PostHook]] = {}
        self._global_pre: list[PreHook] = []
        self._global_post: list[PostHook] = []
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_pre(self, tool_name: str, hook: PreHook) -> None:
        if tool_name not in self._pre_hooks:
            self._pre_hooks[tool_name] = []
        self._pre_hooks[tool_name].append(hook)
        logger.debug("hook_registered", type="pre", tool=tool_name)

    def register_post(self, tool_name: str, hook: PostHook) -> None:
        if tool_name not in self._post_hooks:
            self._post_hooks[tool_name] = []
        self._post_hooks[tool_name].append(hook)
        logger.debug("hook_registered", type="post", tool=tool_name)

    def register_global_pre(self, hook: PreHook) -> None:
        self._global_pre.append(hook)

    def register_global_post(self, hook: PostHook) -> None:
        self._global_post.append(hook)

    async def run_pre(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        ctx: HookContext | None = None,
    ) -> PreHookResult:
        if not self._enabled:
            return PreHookResult(allowed=True)

        if ctx is None:
            ctx = HookContext(tool_name=tool_name, tool_input=tool_input)

        current_input = dict(tool_input)

        for hook in self._global_pre:
            try:
                result = await hook(ctx)
                if not result.allowed:
                    logger.warning(
                        "hook_blocked_pre", tool=tool_name, reason=result.reason
                    )
                    return result
                if result.modified_input:
                    current_input.update(result.modified_input)
                    ctx.tool_input = current_input
            except Exception as e:
                logger.error("global_pre_hook_error", tool=tool_name, error=str(e))

        for hook in self._pre_hooks.get(tool_name, []):
            try:
                result = await hook(ctx)
                if not result.allowed:
                    logger.warning(
                        "hook_blocked_pre", tool=tool_name, reason=result.reason
                    )
                    return result
                if result.modified_input:
                    current_input.update(result.modified_input)
                    ctx.tool_input = current_input
            except Exception as e:
                logger.error("pre_hook_error", tool=tool_name, error=str(e))

        return PreHookResult(allowed=True, modified_input=current_input)

    async def run_post(
        self,
        tool_name: str,
        tool_result: ToolResult,
        ctx: HookContext | None = None,
    ) -> PostHookResult:
        if not self._enabled:
            return PostHookResult(should_continue=True)

        if ctx is None:
            ctx = HookContext(tool_name=tool_name, tool_input={})

        current_result = tool_result
        actions: list[str] = []

        for hook in self._global_post:
            try:
                result = await hook(ctx, current_result)
                if not result.should_continue:
                    return result
                if result.modified_output:
                    current_result = result.modified_output
                actions.extend(result.actions)
            except Exception as e:
                logger.error("global_post_hook_error", tool=tool_name, error=str(e))

        for hook in self._post_hooks.get(tool_name, []):
            try:
                result = await hook(ctx, current_result)
                if not result.should_continue:
                    return result
                if result.modified_output:
                    current_result = result.modified_output
                actions.extend(result.actions)
            except Exception as e:
                logger.error("post_hook_error", tool=tool_name, error=str(e))

        return PostHookResult(
            should_continue=True,
            modified_output=current_result,
            actions=actions,
        )


_SENSITIVE_PATTERNS = [
    (r'(?:api[_-]?key|apikey|api_secret|secret[_-]?key)\s*[:=]\s*["\'][\w-]{20,}["\']', "API key"),
    (r'(?:password|passwd|pwd)\s*[:=]\s*["\'][^"\']+["\']', "password"),
    (r'(?:token|auth[_-]?token|access[_-]?token)\s*[:=]\s*["\'][\w-]{20,}["\']', "token"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub personal access token"),
    (r'gho_[a-zA-Z0-9]{36}', "GitHub OAuth token"),
    (r'(?:-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----)', "private key"),
    (r'(?:-----BEGIN CERTIFICATE-----)', "certificate"),
    (r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}', "JWT token"),
]


async def secret_detection_pre_hook(ctx: HookContext) -> PreHookResult:
    if ctx.tool_name not in ("write_file", "patch"):
        return PreHookResult(allowed=True)

    content = ctx.tool_input.get("content", "")
    if ctx.tool_name == "patch":
        content = ctx.tool_input.get("new", "")

    content_str = str(content)

    for pattern, name in _SENSITIVE_PATTERNS:
        match = re.search(pattern, content_str, re.IGNORECASE)
        if match:
            logger.warning(
                "secret_detected",
                tool=ctx.tool_name,
                secret_type=name,
                path=ctx.tool_input.get("path", "unknown"),
            )
            return PreHookResult(
                allowed=False,
                reason=(
                    f"DETECTED {name} in content about to be written. "
                    f"This looks like a secret that should NOT be committed. "
                    f"Use environment variables or a config file in .gitignore "
                    f"instead. If this is intentional (e.g., example/test value), "
                    f"explicitly confirm before proceeding."
                ),
            )

    return PreHookResult(allowed=True)


async def audit_log_post_hook(ctx: HookContext, result: ToolResult) -> PostHookResult:
    logger.info(
        "tool_audit",
        tool=ctx.tool_name,
        success=result.success,
        input_preview=_preview(ctx.tool_input),
        output_preview=result.output[:200] if result.output else "",
    )
    return PostHookResult(should_continue=True)


async def destructive_command_pre_hook(ctx: HookContext) -> PreHookResult:
    if ctx.tool_name != "terminal":
        return PreHookResult(allowed=True)

    command = str(ctx.tool_input.get("command", "")).strip()
    command_lower = command.lower()

    destructive_patterns = [
        (r'\brm\s+-rf?\b', "recursive delete (rm -rf)"),
        (r'\bgit\s+push\s+.*--force', "force push"),
        (r'\bgit\s+push\s+.*-f\b', "force push"),
        (r'\bdrop\s+database\b', "drop database"),
        (r'\bdrop\s+table\b', "drop table"),
        (r'\btruncate\s+table\b', "truncate table"),
        (r'\bchmod\s+777\b', "world-writable permissions"),
        (r':\(\)\s*\{', "fork bomb pattern"),
        (r'\bdd\s+if=', "disk destroyer"),
        (r'\bmkfs\.', "make filesystem"),
        (r'\b>/\s*dev/\w+', "writing to device files"),
    ]

    for pattern, description in destructive_patterns:
        if re.search(pattern, command_lower):
            logger.warning(
                "destructive_command_detected",
                command=command[:200],
                pattern=description,
            )
            return PreHookResult(
                allowed=False,
                reason=(
                    f"Command contains potentially destructive operation: {description}. "
                    f"If this is intentional and necessary for the task, "
                    f"please confirm explicitly."
                ),
            )

    return PreHookResult(allowed=True)


async def file_size_pre_hook(ctx: HookContext) -> PreHookResult:
    if ctx.tool_name != "write_file":
        return PreHookResult(allowed=True)

    content = str(ctx.tool_input.get("content", ""))
    path = str(ctx.tool_input.get("path", "unknown"))

    if len(content) > 500_000:
        return PreHookResult(
            allowed=False,
            reason=(
                f"File content is {len(content):,} bytes which is unusually large. "
                f"Writing this much to '{path}' may cause issues. "
                f"If intentional, split into multiple files or confirm."
            ),
        )

    if path.endswith((".env", ".env.local", ".env.production", ".secret", ".credentials")):
        return PreHookResult(
            allowed=False,
            reason=(
                f"Writing to '{path}' which looks like a secrets/credentials file. "
                f"These should be managed through environment variables or secret "
                f"management tools, not written as files. If this is intentional, "
                f"please confirm."
            ),
        )

    return PreHookResult(allowed=True)


def create_default_pipeline() -> HookPipeline:
    pipeline = HookPipeline()

    pipeline.register_global_pre(destructive_command_pre_hook)
    pipeline.register_global_post(audit_log_post_hook)

    pipeline.register_pre("write_file", secret_detection_pre_hook)
    pipeline.register_pre("patch", secret_detection_pre_hook)
    pipeline.register_pre("write_file", file_size_pre_hook)

    return pipeline


def _preview(data: dict[str, Any], max_len: int = 200) -> str:
    if "command" in data:
        return data["command"][:max_len]
    if "content" in data:
        return str(data["content"])[:max_len]
    if "path" in data:
        return data["path"][:max_len]
    return str(data)[:max_len]
