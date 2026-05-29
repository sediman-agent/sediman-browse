from __future__ import annotations

import os
import json
from abc import ABC, abstractmethod
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
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        system: str | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def get_browser_use_llm(self) -> Any:
        """Return a LangChain-compatible LLM for BrowserUse's Agent."""
        raise NotImplementedError

    def get_planning_provider(self) -> LLMProvider:
        return self


class OpenAICompatibleProvider(LLMProvider):
    """Works with OpenAI, Ollama, and any OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
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

        # Monkey-patch: replace the strict json_schema path with prompt-based JSON.
        # This is needed because non-OpenAI providers don't support
        # response_format: { type: "json_schema", strict: true }.
        original_ainvoke = llm.ainvoke

        async def patched_ainvoke(messages, output_format=None, **kwargs):
            import re
            from browser_use.llm.base import ChatInvokeCompletion

            def _strip_thinking(text: str) -> str:
                # Remove <think...</think< blocks (reasoning models)
                text = re.sub(r'<think\b[^>]*>.*?</think\s*>', '', text, flags=re.DOTALL)
                text = text.strip()
                # Extract JSON if model prefixed it with thinking text
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

            schema = SchemaOptimizer.create_optimized_json_schema(output_format)
            json_instruction = (
                '\n\nIMPORTANT: You must respond with ONLY a valid JSON object '
                '(no markdown, no code blocks, no explanations) that exactly matches this schema:\n'
                + _json.dumps(schema, indent=2)
            )

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
            content = _strip_thinking(content)
            content = content.strip()
            if content.startswith('```json'):
                content = content[7:]
            if content.startswith('```'):
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

    def get_planning_provider(self) -> OpenAICompatibleProvider:
        planning_model = PLANNING_MODEL_MAP.get(self.model, self.model)
        if planning_model == self.model:
            return self
        return OpenAICompatibleProvider(
            model=planning_model,
            api_key=self.api_key,
            base_url=self.base_url,
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
            "tools": openai_tools,
        }

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

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
}

PLANNING_MODEL_MAP: dict[str, str] = {
    "gpt-4o": "gpt-4o-mini",
    "gpt-4o-mini": "gpt-4o-mini",
    "claude-3.5-sonnet": "claude-3-haiku",
    "claude-3-sonnet": "claude-3-haiku",
}


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
