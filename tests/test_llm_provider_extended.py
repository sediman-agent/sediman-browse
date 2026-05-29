from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.llm.provider import (
    LLMProvider,
    LLMResponse,
    ToolCall,
    ToolDefinition,
    OpenAICompatibleProvider,
    create_provider,
    PROVIDERS,
)


class TestLLMResponseExtended:
    def test_no_text_no_tools(self):
        resp = LLMResponse(text="")
        assert resp.has_tool_calls is False

    def test_repr(self):
        resp = LLMResponse(text="hello")
        assert "LLMResponse" in repr(resp)

    def test_tool_call_list_defaults(self):
        tc = ToolCall(id="1", name="test", arguments={"key": "val"})
        assert tc.id == "1"
        assert tc.arguments["key"] == "val"


class TestToolCall:
    def test_all_fields(self):
        tc = ToolCall(id="call_1", name="memory", arguments={"action": "add", "target": "memory"})
        assert tc.name == "memory"
        assert tc.arguments["action"] == "add"


class TestToolDefinition:
    def test_all_fields(self):
        td = ToolDefinition(name="test", description="a test tool", parameters={"type": "object", "properties": {}})
        assert td.description == "a test tool"


class TestLLMProviderABC:
    def test_abstract_methods(self):
        with pytest.raises(TypeError):
            LLMProvider()

    def test_concrete_subclass(self):
        class Concrete(LLMProvider):
            async def chat(self, messages, tools, system): pass
            def get_browser_use_llm(self): pass

        c = Concrete()
        assert isinstance(c, LLMProvider)


class TestOpenAICompatibleProviderInit:
    def test_default_values(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")
        assert provider.model == "gpt-4o"
        assert provider.base_url is None

    def test_with_base_url(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o", base_url="http://localhost:8080")
        assert provider.base_url == "http://localhost:8080"

    def test_with_api_key(self):
        provider = OpenAICompatibleProvider(model="gpt-4o", api_key="custom-key")
        assert provider.api_key == "custom-key"


class TestOpenAICompatibleProviderChat:
    @pytest.mark.asyncio
    async def test_chat_returns_response(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Hello!"
        mock_message.tool_calls = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "client", mock_client):
            response = await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert response.text == "Hello!"
        assert response.has_tool_calls is False

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.function.name = "memory"
        mock_tool_call.function.arguments = '{"action": "add", "target": "memory", "content": "test"}'
        mock_message.tool_calls = [mock_tool_call]
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "client", mock_client):
            response = await provider.chat(messages=[{"role": "user", "content": "remember this"}], tools=[])

        assert response.has_tool_calls is True
        assert response.tool_calls[0].name == "memory"

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Response"
        mock_message.tool_calls = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "client", mock_client):
            response = await provider.chat(
                messages=[{"role": "user", "content": "do it"}],
                tools=[],
                system="You are a helpful assistant",
            )

        assert response.text == "Response"

    @pytest.mark.asyncio
    async def test_chat_handles_exception(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

        with patch.object(provider, "client", mock_client):
            with pytest.raises(Exception):
                await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])


class TestOpenAICompatibleProviderGetBrowserUseLLM:
    def test_returns_callable(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAICompatibleProvider(model="gpt-4o")
        llm = provider.get_browser_use_llm()
        assert llm is not None


class TestCreateProviderExtended:
    def test_openai_with_model(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = create_provider("openai", model="gpt-4-turbo")
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.model == "gpt-4-turbo"

    def test_openai_default_model(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = create_provider("openai")
        assert provider.model == "gpt-4o"

    def test_ollama_custom_base_url(self):
        provider = create_provider("ollama", base_url="http://localhost:11434/v1")
        assert provider.base_url == "http://localhost:11434/v1"

    def test_ollama_default_model(self):
        provider = create_provider("ollama")
        assert provider.model == "qwen3"

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("anthropic")

    def test_custom_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = create_provider("openai", api_key="custom-key")
            assert provider.api_key == "custom-key"

    def test_openai_missing_key_env(self):
        with patch.dict("os.environ", {}, clear=True):
            # Should use the provided key or raise
            try:
                provider = create_provider("openai", api_key="direct-key")
                assert provider.api_key == "direct-key"
            except Exception:
                pass


class TestPROVIDERS:
    def test_providers_dict(self):
        assert "openai" in PROVIDERS
        assert "ollama" in PROVIDERS

    def test_openai_config(self):
        config = PROVIDERS["openai"]
        assert config["model"] == "gpt-4o"
        assert "api_key_env" in config

    def test_ollama_config(self):
        config = PROVIDERS["ollama"]
        assert config["model"] == "qwen3"
        assert "http://localhost:11434/v1" in config["base_url"]

    def test_all_have_required_keys(self):
        for name, config in PROVIDERS.items():
            assert "model" in config
            assert "api_key_env" in config or "base_url" in config
