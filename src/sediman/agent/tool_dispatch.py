from __future__ import annotations

import asyncio
import functools
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import structlog

from sediman.agent.interrupt import InterruptSignal
from sediman.agent.guardrails import assess_risk, GLOBAL_APPROVAL, AuditLog
from sediman.llm.provider import LLMProvider, LLMResponse, ToolDefinition

logger = structlog.get_logger()

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(func: Callable | None = None, *, name: str | None = None, description: str | None = None):
    """Decorator that registers a function as a callable tool.

    Can be used as @tool or @tool(name="my_name", description="Does X").
    The function's type annotations and docstring are auto-extracted
    to build the OpenAI tool schema.

    Example:
        @tool
        def get_stock_price(symbol: str) -> float:
            \"\"\"Get current price for a stock symbol.\"\"\"
            ...

        @tool(name="send_email", description="Send an email via SMTP")
        def send_email_handler(to: str, subject: str, body: str) -> str:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_desc = description or (inspect.getdoc(fn) or fn.__name__).split("\n")[0].strip()

        sig = inspect.signature(fn)
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            if param_name == "return" or param_name.startswith("_"):
                continue
            param_type = param.annotation if param.annotation is not inspect.Parameter.empty else str
            json_type = _py_type_to_json_type(param_type)
            prop: dict[str, Any] = {"type": json_type}
            if param.default is not inspect.Parameter.empty:
                prop["default"] = param.default
            else:
                required.append(param_name)
            properties[param_name] = prop

        parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required

        definition = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
        )

        @functools.wraps(fn)
        async def async_wrapper(**kwargs: Any) -> Any:
            if asyncio.iscoroutinefunction(fn):
                return await fn(**kwargs)
            return fn(**kwargs)

        _TOOL_REGISTRY[tool_name] = {
            "fn": async_wrapper,
            "definition": definition,
            "handler": async_wrapper,
        }
        return fn

    if func is not None:
        return decorator(func)
    return decorator


def _py_type_to_json_type(py_type: type) -> str:
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }
    origin = getattr(py_type, "__origin__", None)
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    return type_map.get(py_type, "string")


def discover_tools(module: str | None = None) -> list[tuple[str, Callable, ToolDefinition]]:
    """Discover all registered @tool functions and their schemas.
    If module is given, only return tools from that module.
    """
    results: list[tuple[str, Callable, ToolDefinition]] = []
    for tool_name, entry in _TOOL_REGISTRY.items():
        results.append((tool_name, entry["handler"], entry["definition"]))
    return results


def register_tool_fn(
    name: str,
    handler: Callable,
    definition: ToolDefinition,
) -> None:
    """Manually register a tool function (used for non-decorator tools)."""
    _TOOL_REGISTRY[name] = {
        "fn": handler,
        "definition": definition,
        "handler": handler,
    }


def get_decorated_tool_definitions() -> list[ToolDefinition]:
    """Get ToolDefinitions for all @tool-decorated functions."""
    return [entry["definition"] for entry in _TOOL_REGISTRY.values()]


def get_decorated_tool_handlers() -> dict[str, Callable]:
    """Get handler dict for all @tool-decorated functions."""
    return {name: entry["handler"] for name, entry in _TOOL_REGISTRY.items()}


@dataclass
class ToolResult:
    success: bool
    output: str
    data: dict[str, Any] | None = None


ToolHandler = Callable[..., Awaitable[ToolResult]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._checkpoint_manager: Any | None = None

    def set_checkpoint_manager(self, manager: Any) -> None:
        self._checkpoint_manager = manager

    def register(
        self,
        definition: ToolDefinition,
        handler: ToolHandler,
    ) -> None:
        self._tools[definition.name] = definition
        self._handlers[definition.name] = handler

    def get_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        handler = self._handlers.get(tool_name)
        if not handler:
            return ToolResult(success=False, output=f"Unknown tool: {tool_name}")
        try:
            risk = assess_risk(tool_name, arguments)
            if risk == "high":
                AuditLog.get().record("tool", "risk_assessment", f"high_risk: {tool_name}", args=str(arguments)[:200])
                approved = await GLOBAL_APPROVAL.request(tool_name, arguments)
                if not approved:
                    AuditLog.get().record("tool", "blocked", f"user_denied: {tool_name}")
                    return ToolResult(success=False, output=f"Tool '{tool_name}' was not approved for this action.")

            if self._checkpoint_manager is not None:
                cwd = arguments.get("cwd") if tool_name == "terminal" else None
                await self._checkpoint_manager.maybe_checkpoint(tool_name, arguments, cwd=cwd)

            result = await handler(**arguments)
            logger.info("tool_dispatched", tool=tool_name, success=result.success, risk=risk)
            return result
        except Exception as e:
            logger.warning("tool_dispatch_failed", tool=tool_name, error=str(e))
            return ToolResult(success=False, output=f"Tool error: {e}")

    def register_decorated(self) -> None:
        """Auto-register all @tool-decorated functions."""
        for name, handler, definition in discover_tools():
            if name not in self._tools:
                self._tools[name] = definition
                self._handlers[name] = handler

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_definition(self, name: str) -> ToolDefinition:
        return self._tools[name]


class ToolLoop:
    def __init__(self, llm: LLMProvider, registry: ToolRegistry, max_rounds: int = 30, budget: Any = None, max_context_tokens: int = 16000):
        self.llm = llm
        self.registry = registry
        self.max_rounds = max_rounds
        self._budget = budget
        self._max_context_tokens = max_context_tokens

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for m in messages:
            content = str(m.get("content", ""))
            tool_calls = m.get("tool_calls", [])
            total += len(content) // 3
            for tc in tool_calls:
                args_str = str(tc.get("function", {}).get("arguments", ""))
                total += len(args_str) // 3
        return max(total, 1)

    def _compress_tool_results(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compressed = []
        for m in messages:
            if m.get("role") == "tool":
                content = str(m.get("content", ""))
                if len(content) > 2000:
                    compressed.append({
                        **m,
                        "content": content[:2000] + f"\n... ({len(content) - 2000} more chars truncated)",
                    })
                else:
                    compressed.append(m)
            else:
                compressed.append(m)
        return compressed

    def _maybe_compress(self, messages: list[dict[str, Any]], system_len: int = 0) -> list[dict[str, Any]]:
        current_tokens = self._estimate_tokens(messages) + system_len
        if current_tokens <= self._max_context_tokens:
            return messages

        logger.info(
            "tool_loop_compressing",
            current_tokens=current_tokens,
            max_tokens=self._max_context_tokens,
            message_count=len(messages),
        )

        compressed = self._compress_tool_results(messages)
        new_tokens = self._estimate_tokens(compressed) + system_len
        if new_tokens > self._max_context_tokens:
            early = []
            recent_count = 0
            for m in reversed(compressed):
                if m.get("role") == "tool":
                    recent_count += 1
                early.insert(0, m)
                if recent_count >= 6 and m.get("role") == "user":
                    break
            remaining = [m for m in compressed if m not in early]
            if remaining and len(early) < len(compressed):
                early.insert(0, {
                    "role": "system",
                    "content": (
                        f"[{len(remaining)} earlier messages were truncated to "
                        f"conserve context. Key results from those rounds are "
                        f"preserved in the most recent messages below.]"
                    ),
                })
            compressed = early

        logger.info(
            "tool_loop_compressed",
            new_tokens=self._estimate_tokens(compressed) + system_len,
            new_count=len(compressed),
        )
        return compressed

    async def run(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> LLMResponse:
        from sediman.agent.guardrails import Budget

        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        response: LLMResponse | None = None
        system_tokens = len(system or "") // 3
        for _round in range(self.max_rounds):
            if self._budget is not None:
                exhausted, reason = self._budget.is_exhausted()
                if exhausted:
                    logger.warning("tool_loop_budget_exhausted", reason=reason, round=_round)
                    break

            InterruptSignal.get().check()

            all_messages = self._maybe_compress(all_messages, system_tokens)

            response = await self.llm.chat(
                messages=all_messages,
                tools=self.registry.get_definitions(),
            )

            if not response.tool_calls:
                InterruptSignal.get().check()
                return response

            all_messages.append(
                {
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )

            if len(response.tool_calls) > 1:
                async def _dispatch_one(tc: Any) -> tuple[str, ToolResult]:
                    if on_tool_call:
                        on_tool_call(tc.name, tc.arguments)
                    result = await self.registry.dispatch(tc.name, tc.arguments)
                    return (tc.id, result)

                dispatch_results = await asyncio.gather(
                    *[_dispatch_one(tc) for tc in response.tool_calls]
                )
                for tc_id, result in dispatch_results:
                    all_messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "content": result.output}
                    )
            else:
                tc = response.tool_calls[0]
                if on_tool_call:
                    on_tool_call(tc.name, tc.arguments)
                result = await self.registry.dispatch(tc.name, tc.arguments)
                all_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result.output}
                )

        if response and response.tool_calls:
            tool_summary = "; ".join(f"{tc.name}({list(tc.arguments.keys())})" for tc in response.tool_calls)
            return LLMResponse(
                text=f"[Tool loop exhausted after {self.max_rounds} rounds. Pending: {tool_summary}]",
                tool_calls=[],
                done=True,
            )

        return response or LLMResponse(text="", tool_calls=[], done=True)

    async def run_streaming(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
        on_streaming_text: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Like run() but streams text tokens via on_streaming_text callback.

        Each LLM call uses chat_stream_with_tools() so the caller sees
        tokens as they arrive. Tool calls are still dispatched normally.
        """
        from sediman.agent.guardrails import Budget

        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        response: LLMResponse | None = None
        system_tokens = len(system or "") // 3
        for _round in range(self.max_rounds):
            if self._budget is not None:
                exhausted, reason = self._budget.is_exhausted()
                if exhausted:
                    logger.warning("tool_loop_budget_exhausted", reason=reason, round=_round)
                    break

            InterruptSignal.get().check()

            all_messages = self._maybe_compress(all_messages, system_tokens)

            response = await self.llm.chat_stream_with_tools(
                messages=all_messages,
                tools=self.registry.get_definitions(),
                on_token=on_streaming_text,
            )

            if not response.tool_calls:
                InterruptSignal.get().check()
                return response

            if response.text and on_streaming_text:
                pass

            all_messages.append(
                {
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )

            if len(response.tool_calls) > 1:
                async def _dispatch_one(tc: Any) -> tuple[str, ToolResult]:
                    if on_tool_call:
                        on_tool_call(tc.name, tc.arguments)
                    result = await self.registry.dispatch(tc.name, tc.arguments)
                    return (tc.id, result)

                dispatch_results = await asyncio.gather(
                    *[_dispatch_one(tc) for tc in response.tool_calls]
                )
                for tc_id, result in dispatch_results:
                    all_messages.append(
                        {"role": "tool", "tool_call_id": tc_id, "content": result.output}
                    )
            else:
                tc = response.tool_calls[0]
                if on_tool_call:
                    on_tool_call(tc.name, tc.arguments)
                result = await self.registry.dispatch(tc.name, tc.arguments)
                all_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result.output}
                )

        if response and response.tool_calls:
            tool_summary = "; ".join(f"{tc.name}({list(tc.arguments.keys())})" for tc in response.tool_calls)
            return LLMResponse(
                text=f"[Tool loop exhausted after {self.max_rounds} rounds. Pending: {tool_summary}]",
                tool_calls=[],
                done=True,
            )

        return response or LLMResponse(text="", tool_calls=[], done=True)
