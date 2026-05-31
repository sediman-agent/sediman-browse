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


PROVIDERS: dict[str, dict[str, Any]] = {
    # ── Cloud Providers (matching OpenCode model catalog) ──
    "openai": {
        "model": "gpt-4o",
        "model_name": "GPT 4o",
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "gpt-4.1", "name": "GPT 4.1"},
            {"id": "gpt-4.1-mini", "name": "GPT 4.1 mini"},
            {"id": "gpt-4.1-nano", "name": "GPT 4.1 nano"},
            {"id": "gpt-4.5-preview", "name": "GPT 4.5 preview"},
            {"id": "gpt-4o-mini", "name": "GPT 4o mini"},
            {"id": "o1", "name": "O1"},
            {"id": "o1-pro", "name": "o1 pro"},
            {"id": "o1-mini", "name": "o1 mini"},
            {"id": "o3", "name": "o3"},
            {"id": "o3-mini", "name": "o3 mini"},
            {"id": "o4-mini", "name": "o4 mini"},
        ],
    },
    "anthropic": {
        "model": "claude-sonnet-4-20250514",
        "model_name": "Claude 4 Sonnet",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "claude-opus-4-20250514", "name": "Claude 4 Opus"},
            {"id": "claude-3-7-sonnet-latest", "name": "Claude 3.7 Sonnet"},
            {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku"},
            {"id": "claude-3-opus-latest", "name": "Claude 3 Opus"},
            {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
        ],
    },
    "gemini": {
        "model": "gemini-2.5-pro",
        "model_name": "Gemini 2.5 Pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
            {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite"},
        ],
    },
    "mistral": {
        "model": "mistral-large-latest",
        "model_name": "Mistral Large",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "mistral-medium-latest", "name": "Mistral Medium"},
            {"id": "mistral-small-latest", "name": "Mistral Small"},
            {"id": "codestral-latest", "name": "Codestral"},
            {"id": "open-mistral-nemo", "name": "Mistral Nemo"},
        ],
    },
    "xai": {
        "model": "grok-3",
        "model_name": "Grok3",
        "base_url": "https://api.x.ai/v1",
        "api_key_env": "XAI_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "grok-3-mini", "name": "Grok3 Mini"},
            {"id": "grok-2", "name": "Grok2"},
            {"id": "grok-2-mini", "name": "Grok2 Mini"},
        ],
    },
    "cohere": {
        "model": "command-r-plus",
        "model_name": "Command R+",
        "base_url": "https://api.cohere.ai/v2",
        "api_key_env": "COHERE_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "command-r", "name": "Command R"},
        ],
    },
    # ── Chinese Cloud Providers ──
    "glm": {
        "model": "glm-4-flash",
        "model_name": "GLM 4 Flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "category": "cloud-cn",
        "extra_models": [
            {"id": "glm-4-plus", "name": "GLM 4 Plus"},
            {"id": "glm-4-long", "name": "GLM 4 Long"},
            {"id": "glm-4-air", "name": "GLM 4 Air"},
            {"id": "glm-4-airx", "name": "GLM 4 AirX"},
            {"id": "glm-4-flashx", "name": "GLM 4 FlashX"},
            {"id": "glm-4", "name": "GLM 4"},
        ],
    },
    "deepseek": {
        "model": "deepseek-chat",
        "model_name": "DeepSeek Chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "category": "cloud-cn",
        "extra_models": [
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner"},
            {"id": "deepseek-chat-v3-0324", "name": "DeepSeek Chat V3"},
        ],
    },
    "dashscope": {
        "model": "qwen-plus",
        "model_name": "Qwen Plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "category": "cloud-cn",
        "extra_models": [
            {"id": "qwen-turbo", "name": "Qwen Turbo"},
            {"id": "qwen-max", "name": "Qwen Max"},
            {"id": "qwen-long", "name": "Qwen Long"},
            {"id": "qwen3-235b-a22b", "name": "Qwen3 235B"},
            {"id": "qwen3-30b-a3b", "name": "Qwen3 30B"},
            {"id": "qwq-plus", "name": "QwQ Plus"},
        ],
    },
    "siliconflow": {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "model_name": "Qwen 2.5 72B",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key_env": "SILICONFLOW_API_KEY",
        "category": "cloud-cn",
        "extra_models": [
            {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3"},
            {"id": "deepseek-ai/DeepSeek-R1", "name": "DeepSeek R1"},
            {"id": "Qwen/Qwen3-235B-A22B", "name": "Qwen3 235B"},
            {"id": "Qwen/Qwen2.5-Coder-32B-Instruct", "name": "Qwen 2.5 Coder 32B"},
            {"id": "meta-llama/Meta-Llama-3.1-405B-Instruct", "name": "Llama 3.1 405B"},
        ],
    },
    "minimax": {
        "model": "MiniMax-Text-01",
        "model_name": "MiniMax Text 01",
        "base_url": "https://api.minimaxi.com/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "category": "cloud-cn",
        "extra_models": [
            {"id": "MiniMax-M1", "name": "MiniMax M1"},
        ],
    },
    "minimax-global": {
        "model": "MiniMax-Text-01",
        "model_name": "MiniMax Text 01",
        "base_url": "https://api.minimaxi.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "category": "cloud",
        "extra_models": [
            {"id": "MiniMax-M1", "name": "MiniMax M1"},
        ],
    },
    # ── Inference Platforms ──
    "openrouter": {
        "model": "openai/gpt-4o",
        "model_name": "GPT 4o",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "openai/gpt-4.1", "name": "GPT 4.1"},
            {"id": "openai/gpt-4.1-mini", "name": "GPT 4.1 mini"},
            {"id": "openai/gpt-4.1-nano", "name": "GPT 4.1 nano"},
            {"id": "openai/gpt-4.5-preview", "name": "GPT 4.5 preview"},
            {"id": "openai/gpt-4o-mini", "name": "GPT 4o mini"},
            {"id": "openai/o1", "name": "O1"},
            {"id": "openai/o1-pro", "name": "o1 pro"},
            {"id": "openai/o1-mini", "name": "o1 mini"},
            {"id": "openai/o3", "name": "o3"},
            {"id": "openai/o3-mini", "name": "o3 mini"},
            {"id": "openai/o4-mini", "name": "o4 mini"},
            {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
            {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
            {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"},
            {"id": "anthropic/claude-3.7-sonnet", "name": "Claude 3.7 Sonnet"},
            {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku"},
            {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
            {"id": "deepseek/deepseek-r1-0528:free", "name": "DeepSeek R1 Free"},
        ],
    },
    "groq": {
        "model": "llama-3.3-70b-versatile",
        "model_name": "Llama 3.3 70B",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "qwen-qwq-32b", "name": "Qwen QwQ"},
            {"id": "meta-llama/llama-4-scout-17b-16e-instruct", "name": "Llama4 Scout"},
            {"id": "meta-llama/llama-4-maverick-17b-128e-instruct", "name": "Llama4 Maverick"},
            {"id": "deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 70B"},
        ],
    },
    "together": {
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "model_name": "Llama 3.3 70B",
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": "TOGETHER_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "meta-llama/Llama-3.3-8B-Instruct-Turbo", "name": "Llama 3.3 8B"},
            {"id": "meta-llama/Llama-3.1-405B-Instruct-Turbo", "name": "Llama 3.1 405B"},
            {"id": "Qwen/Qwen2.5-72B-Instruct-Turbo", "name": "Qwen 2.5 72B"},
            {"id": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "name": "DeepSeek R1 70B"},
        ],
    },
    "fireworks": {
        "model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "model_name": "Llama 3.3 70B",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_env": "FIREWORKS_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "accounts/fireworks/models/llama-v3p3-8b-instruct", "name": "Llama 3.3 8B"},
            {"id": "accounts/fireworks/models/qwen2p5-72b-instruct", "name": "Qwen 2.5 72B"},
            {"id": "accounts/fireworks/models/deepseek-r1", "name": "DeepSeek R1"},
        ],
    },
    "cerebras": {
        "model": "llama-3.3-70b",
        "model_name": "Llama 3.3 70B",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "llama-3.3-8b", "name": "Llama 3.3 8B"},
            {"id": "llama3.1-8b", "name": "Llama 3.1 8B"},
            {"id": "llama3.1-70b", "name": "Llama 3.1 70B"},
        ],
    },
    "deepinfra": {
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "model_name": "Llama 3.1 70B",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "api_key_env": "DEEPINFRA_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "meta-llama/Meta-Llama-3.1-8B-Instruct", "name": "Llama 3.1 8B"},
            {"id": "meta-llama/Meta-Llama-3.1-405B-Instruct", "name": "Llama 3.1 405B"},
            {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B"},
            {"id": "deepseek-ai/DeepSeek-R1", "name": "DeepSeek R1"},
        ],
    },
    "perplexity": {
        "model": "sonar-pro",
        "model_name": "Sonar Pro",
        "base_url": "https://api.perplexity.ai",
        "api_key_env": "PERPLEXITY_API_KEY",
        "category": "inference",
        "extra_models": [
            {"id": "sonar", "name": "Sonar"},
            {"id": "sonar-reasoning", "name": "Sonar Reasoning"},
            {"id": "sonar-reasoning-pro", "name": "Sonar Reasoning Pro"},
        ],
    },
    # ── Local / Self-hosted ──
    "ollama": {
        "model": "qwen3",
        "model_name": "Qwen3",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "category": "local",
        "extra_models": [
            {"id": "llama3.3", "name": "Llama 3.3"},
            {"id": "llama3.1", "name": "Llama 3.1"},
            {"id": "mistral", "name": "Mistral"},
            {"id": "codellama", "name": "Code Llama"},
            {"id": "deepseek-r1", "name": "DeepSeek R1"},
            {"id": "gemma3", "name": "Gemma 3"},
            {"id": "phi4", "name": "Phi 4"},
            {"id": "qwen2.5-coder", "name": "Qwen 2.5 Coder"},
        ],
    },
    "vllm": {
        "model": "auto",
        "base_url": "http://localhost:8000/v1",
        "api_key_env": None,
        "category": "local",
    },
    "sglang": {
        "model": "auto",
        "base_url": "http://localhost:30000/v1",
        "api_key_env": None,
        "category": "local",
    },
    "llamacpp": {
        "model": "auto",
        "base_url": "http://127.0.0.1:8080/v1",
        "api_key_env": None,
        "category": "local",
    },
    "lmstudio": {
        "model": "auto",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key_env": None,
        "category": "local",
    },
}

PROVIDER_CATEGORIES: dict[str, str] = {
    "cloud": "Cloud Providers",
    "cloud-cn": "Chinese Cloud Providers",
    "inference": "Inference Platforms",
    "local": "Local / Self-hosted",
}


def list_providers() -> list[dict[str, Any]]:
    from sediman.auth import has_key

    result: list[dict[str, Any]] = []
    for name, preset in PROVIDERS.items():
        needs_key = preset.get("api_key_env") is not None
        result.append({
            "name": name,
            "default_model": preset.get("model"),
            "default_base_url": preset.get("base_url"),
            "category": preset.get("category", "cloud"),
            "needs_api_key": needs_key,
            "api_key_env": preset.get("api_key_env"),
            "has_key": has_key(name) or (not needs_key),
        })
    return result


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
    from sediman.auth import get_key as _get_auth_key

    preset = PROVIDERS.get(provider)
    if not preset:
        raise ValueError(
            f"Unknown provider: {provider}. Available: {', '.join(sorted(PROVIDERS.keys()))}"
        )

    resolved_model = model or preset["model"]
    resolved_base_url = base_url or preset.get("base_url")
    resolved_key = api_key

    if not resolved_key:
        resolved_key = _get_auth_key(provider)

    if not resolved_key and preset.get("api_key_env"):
        resolved_key = os.environ.get(preset["api_key_env"])

    return OpenAICompatibleProvider(
        model=resolved_model,
        api_key=resolved_key,
        base_url=resolved_base_url,
    )
