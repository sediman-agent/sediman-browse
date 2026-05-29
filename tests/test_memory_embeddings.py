from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sediman.memory.embeddings import (
    OpenAIEmbeddingProvider,
    FastEmbedProvider,
    TfidfEmbeddingProvider,
    create_embedding_provider,
)


class TestOpenAIEmbeddingProvider:
    def test_provider_name(self):
        p = OpenAIEmbeddingProvider(api_key="test-key")
        assert "openai" in p.name

    def test_dimension_default(self):
        p = OpenAIEmbeddingProvider(api_key="test-key")
        assert p.dimension == 1536

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        p = OpenAIEmbeddingProvider(api_key="test-key")
        result = await p.embed([])
        assert result == []

    def test_embed_sync_empty(self):
        p = OpenAIEmbeddingProvider(api_key="test-key")
        result = p.embed_sync([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        p = OpenAIEmbeddingProvider(api_key="test-key")
        fake_response = MagicMock()
        fake_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]

        client_mock = MagicMock()
        client_mock.embeddings.create = AsyncMock(return_value=fake_response)

        with patch.object(p, "_lazy_client", return_value=client_mock):
            result = await p.embed(["hello world"])
            assert len(result) == 1
            assert len(result[0]) == 3

    def test_no_api_key_initializes_without_error(self):
        with patch("os.environ", {}):
            p = OpenAIEmbeddingProvider()
            assert p._api_key is None or p._api_key == ""


class TestFastEmbedProvider:
    def test_provider_name(self):
        p = FastEmbedProvider()
        assert "fastembed" in p.name

    def test_dimension_default(self):
        p = FastEmbedProvider()
        assert p.dimension == 384

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        p = FastEmbedProvider()
        result = await p.embed([])
        assert result == []

    def test_embed_sync_empty(self):
        p = FastEmbedProvider()
        result = p.embed_sync([])
        assert result == []

    def test_raises_when_not_installed(self):
        p = FastEmbedProvider()
        with patch.dict("sys.modules", {"fastembed": None}):
            with pytest.raises(RuntimeError, match="fastembed not installed"):
                p.embed_sync(["test"])

    def test_embed_returns_vectors(self):
        p = FastEmbedProvider()
        mock_model = MagicMock()
        mock_model.dimension = 384
        mock_model.embed.return_value = [MagicMock(tolist=lambda: [0.1, 0.2, 0.3])]

        with patch.object(p, "_lazy_model", return_value=mock_model):
            result = p.embed_sync(["hello world"])
            assert len(result) == 1
            assert len(result[0]) == 3


class TestTfidfEmbeddingProvider:
    def test_provider_name(self):
        p = TfidfEmbeddingProvider()
        assert p.name == "tfidf"

    def test_embed_empty(self):
        p = TfidfEmbeddingProvider()
        result = p.embed_sync([])
        assert result == []

    def test_embed_returns_normalized_vectors(self):
        p = TfidfEmbeddingProvider()
        result = p.embed_sync(["hello world", "goodbye world"])
        assert len(result) == 2
        for vec in result:
            norm = sum(v * v for v in vec) ** 0.5
            assert abs(norm - 1.0) < 1e-6

    def test_embed_same_text_returns_same_vector(self):
        p = TfidfEmbeddingProvider()
        v1 = p.embed_sync(["hello world"])[0]
        v2 = p.embed_sync(["hello world"])[0]
        assert v1 == v2

    def test_dimension_after_fit(self):
        p = TfidfEmbeddingProvider()
        p.embed_sync(["hello world", "foo bar baz"])
        assert p.dimension > 0


class TestCreateEmbeddingProvider:
    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_creates_openai_when_key_set(self):
        provider = create_embedding_provider()
        assert "openai" in provider.name

    @patch.dict("os.environ", {}, clear=True)
    def test_falls_back_to_fastembed_or_tfidf(self):
        with patch("sediman.memory.embeddings.FastEmbedProvider") as mock_fast:
            mock_fast.return_value.name = "fastembed/test"
            provider = create_embedding_provider()
            assert provider is not None
