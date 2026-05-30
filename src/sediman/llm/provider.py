from __future__ import annotations

import os
import json
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


class LLMProvider(ABC):
    def __init__(self) -> None:
        self._token_callback: Any = None

    def set_token_callback(self, callback: Any) -> None:
        self._token_callback = callback

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> LLMResponse: ...

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from the LLM. Default implementation calls chat() and yields the full response."""
        response = await self.chat(messages=messages, tools=tools, system=system)
        if response.text:
            yield response.text

    @abstractmethod
    def get_browser_use_llm(self) -> Any:
        """Return a LangChain-compatible LLM for BrowserUse's Agent."""
        raise NotImplementedError

    def get_planning_provider(self) -> LLMProvider:
        if not _USE_PLANNING_MODEL_MAP:
            return self
        planning_model = PLANNING_MODEL_MAP.get(self.model, self.model)
        if planning_model == self.model:
            return self
        return OpenAICompatibleProvider(
            model=planning_model,
            api_key=self.api_key,
            base_url=self.base_url,
        )


class OpenAICompatibleProvider(LLMProvider):
    """Works with OpenAI, Ollama, and any OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__()
        from openai import AsyncOpenAI

        self.model = model
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

        if not self.api_key:
            if not base_url:
                raise ValueError(
                    "No API key provided. Set OPENAI_API_KEY env var or pass api_key=."
                )
            # Ollama and other local providers don't need a real key,
            # but the OpenAI SDK requires one. Use a sentinel.
            self.api_key = "not-needed"

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
        )
        self._cached_browser_llm: Any | None = None

    def get_browser_use_llm(self) -> Any:
        if self._cached_browser_llm is not None:
            return self._cached_browser_llm

        from browser_use.llm.openai.chat import ChatOpenAI as _BUChatOpenAI

        llm = _BUChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

        # Caches to avoid redundant work in the hot loop
        _schema_cache: dict[int, str] = {}
        _strip_thinking_re = re.compile(r'<think\b[^>]*>.*?</think\s*>', re.DOTALL)

        # Monkey-patch: replace the strict json_schema path with prompt-based JSON.
        # This is needed because non-OpenAI providers don't support
        # response_format: { type: "json_schema", strict: true }.
        original_ainvoke = llm.ainvoke

        async def patched_ainvoke(messages, output_format=None, **kwargs):
            from browser_use.llm.base import ChatInvokeCompletion

            def _strip_thinking(text: str) -> str:
                text = _strip_thinking_re.sub('', text).strip()
                if text and text[0] not in ('{', '['):
                    for i, ch in enumerate(text):
                        if ch in ('{', '['):
                            text = text[i:]
                            break
                return text

            if output_format is None:
                result = await original_ainvoke(messages, output_format=None, **kwargs)
                if isinstance(result.completion, str):
                    cleaned = _strip_thinking(result.completion)
                    if cleaned != result.completion:
                        return ChatInvokeCompletion(
                            completion=cleaned,
                            usage=result.usage,
                            stop_reason=result.stop_reason,
                        )
                return result

            # Prompt-based approach: inject schema into the messages,
            # call without response_format, parse raw JSON from response.
            import json as _json
            from browser_use.llm.schema import SchemaOptimizer

            # Cache schema instruction by output_format class identity
            schema_key = id(output_format) if not isinstance(output_format, type) else id(output_format)
            json_instruction = _schema_cache.get(schema_key)
            if json_instruction is None:
                schema = SchemaOptimizer.create_optimized_json_schema(output_format)
                json_instruction = (
                    '\n\nIMPORTANT: You must respond with ONLY a valid JSON object '
                    '(no markdown, no code blocks, no explanations) that exactly matches this schema:\n'
                    + _json.dumps(schema, indent=2)
                )
                _schema_cache[schema_key] = json_instruction

            modified_messages = []
            for m in messages:
                modified_messages.append(m.model_copy(deep=True))

            if modified_messages and modified_messages[0].role == 'system':
                if isinstance(modified_messages[0].content, str):
                    modified_messages[0].content += json_instruction
                else:
                    from browser_use.llm.vercel.chat import ContentPartTextParam
                    modified_messages[0].content.append(
                        ContentPartTextParam(text=json_instruction)
                    )
            else:
                from langchain_core.messages import SystemMessage
                modified_messages.insert(0, SystemMessage(content=json_instruction))

            # Call without output_format to skip response_format
            result = await original_ainvoke(modified_messages, output_format=None, **kwargs)

            # Parse the JSON from the raw text response
            content = result.completion if isinstance(result.completion, str) else str(result.completion)
            content = _strip_thinking(content).strip()
            if content.startswith('```json'):
                content = content[7:]
            elif content.startswith('```'):
                content = content[3:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()

            parsed = output_format.model_validate_json(content)
            return ChatInvokeCompletion(
                completion=parsed,
                usage=result.usage,
                stop_reason=result.stop_reason,
            )

        llm.ainvoke = patched_ainvoke
        self._cached_browser_llm = llm
        return llm

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> AsyncIterator[str]:
        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def chat_stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Stream tokens from the LLM while also handling tool calls.

        If the LLM produces text tokens, they are yielded via on_token.
        If the LLM produces tool calls, the full LLMResponse is returned.
        This enables real-time streaming of the LLM's text output.
        """
        import typing

        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        stream = await self.client.chat.completions.create(**kwargs)

        text_parts: list[str] = []
        tool_calls_map: dict[int, dict[str, Any]] = {}
        has_tool_calls = False

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta and delta.content:
                text_parts.append(delta.content)
                if on_token:
                    try:
                        on_token(delta.content)
                    except Exception:
                        pass

            if delta and delta.tool_calls:
                has_tool_calls = True
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index if tc_delta.index is not None else 0
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = tool_calls_map[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            if choice.finish_reason in ("stop", "tool_calls"):
                break

        text = "".join(text_parts)
        tool_calls: list[ToolCall] = []
        if has_tool_calls:
            for idx in sorted(tool_calls_map.keys()):
                entry = tool_calls_map[idx]
                try:
                    args = json.loads(entry["arguments"]) if entry["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(id=entry["id"], name=entry["name"], arguments=args)
                )

        return LLMResponse(
            text=text if text else None,
            tool_calls=tool_calls,
            done=not tool_calls,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> LLMResponse:
        all_messages: list[dict[str, Any]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": all_messages,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools

        response = await self._chat_with_retry(kwargs)
        choice = response.choices[0]
        message = choice.message

        if self._token_callback and response.usage:
            total = (response.usage.prompt_tokens or 0) + (response.usage.completion_tokens or 0)
            try:
                self._token_callback(total)
            except Exception:
                pass

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(
            text=message.content,
            tool_calls=tool_calls,
            done=not tool_calls,
        )

    async def _chat_with_retry(self, kwargs: dict[str, Any], max_retries: int = 3) -> Any:
        import asyncio as _asyncio

        retryable_errors = (
            ConnectionError,
            TimeoutError,
        )
        for attempt in range(max_retries + 1):
            try:
                return await self.client.chat.completions.create(**kwargs)
            except retryable_errors as e:
                if attempt >= max_retries:
                    raise
                wait = min(2 ** attempt + 0.5, 10)
                logger.warning("llm_retry", attempt=attempt + 1, error=str(e)[:100], wait=wait)
                await _asyncio.sleep(wait)
            except Exception as e:
                err_type = type(e).__name__
                if "RateLimit" in err_type or "429" in str(e):
                    if attempt >= max_retries:
                        raise
                    wait = min(2 ** (attempt + 1), 30)
                    logger.warning("llm_rate_limited", attempt=attempt + 1, wait=wait)
                    await _asyncio.sleep(wait)
                elif any(code in str(e) for code in ("500", "502", "503", "504")):
                    if attempt >= max_retries:
                        raise
                    wait = min(2 ** attempt + 0.5, 10)
                    logger.warning("llm_server_error", attempt=attempt + 1, wait=wait)
                    await _asyncio.sleep(wait)
                else:
                    raise
        return await self.client.chat.completions.create(**kwargs)

    async def chat_with_failover(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
        fallback_provider: LLMProvider | None = None,
    ) -> LLMResponse:
        """Try primary provider, fall back to fallback on failure."""
        try:
            return await self.chat(messages, tools, system)
        except Exception as e:
            if fallback_provider:
                logger.warning("provider_failover", error=str(e), fallback=True)
                return await fallback_provider.chat(messages, tools, system)
            raise


PROVIDERS: dict[str, dict[str, str | None]] = {
    "openai": {
        "model": "gpt-4o",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
    },
    "ollama": {
        "model": "qwen3",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
    },
    "minimax": {
        "model": "MiniMax-Text-01",
        "base_url": "https://api.minimaxi.com/v1",
        "api_key_env": "MINIMAX_API_KEY",
    },
}

PLANNING_MODEL_MAP: dict[str, str] = {
    "gpt-4o": "gpt-4o-mini",
    "gpt-4o-mini": "gpt-4o-mini",
    "claude-3.5-sonnet": "claude-3-haiku",
    "claude-3-sonnet": "claude-3-haiku",
}

_USE_PLANNING_MODEL_MAP = os.environ.get("SEDIMAN_USE_PLANNING_MODEL_MAP", "true").lower() in ("true", "1", "yes")


def create_provider(
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> OpenAICompatibleProvider:
    preset = PROVIDERS.get(provider)
    if not preset:
        raise ValueError(
            f"Unknown provider: {provider}. Available: {', '.join(PROVIDERS.keys())}"
        )

    resolved_model = model or preset["model"]
    resolved_base_url = base_url or preset.get("base_url")
    resolved_key = api_key

    if not resolved_key and preset.get("api_key_env"):
        resolved_key = os.environ.get(preset["api_key_env"])

    return OpenAICompatibleProvider(
        model=resolved_model,
        api_key=resolved_key,
        base_url=resolved_base_url,
    )
