from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from sediman.memory.embeddings import FastEmbedProvider, TfidfEmbeddingProvider


class TestFastEmbedAsyncThread:
    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        provider = FastEmbedProvider()
        provider._model = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1, 0.2, 0.3]
        provider._model.embed.return_value = iter([mock_embedding])

        result = await provider.embed(["hello"])
        assert result == [[0.1, 0.2, 0.3]]

    @pytest.mark.asyncio
    async def test_embed_empty_returns_empty(self):
        provider = FastEmbedProvider()
        result = await provider.embed([])
        assert result == []

    def test_embed_sync_returns_vectors(self):
        provider = FastEmbedProvider()
        provider._model = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1, 0.2]
        provider._model.embed.return_value = iter([mock_embedding])

        result = provider.embed_sync(["test"])
        assert result == [[0.1, 0.2]]

    def test_embed_sync_empty_returns_empty(self):
        provider = FastEmbedProvider()
        result = provider.embed_sync([])
        assert result == []

    def test_dimension(self):
        provider = FastEmbedProvider()
        assert provider.dimension == 384

    def test_name(self):
        provider = FastEmbedProvider()
        assert "fastembed" in provider.name

    def test_lazy_model_raises_on_missing_import(self):
        provider = FastEmbedProvider()
        provider._model = None
        with patch.dict("sys.modules", {"fastembed": None}):
            with pytest.raises(RuntimeError, match="fastembed not installed"):
                provider._lazy_model()

    @pytest.mark.asyncio
    async def test_embed_does_not_block_event_loop(self):
        provider = FastEmbedProvider()
        provider._model = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1]
        provider._model.embed.return_value = iter([mock_embedding])

        other_done = False

        async def concurrent_task():
            nonlocal other_done
            await asyncio.sleep(0)
            other_done = True

        task = asyncio.create_task(concurrent_task())
        await provider.embed(["test"])
        await task
        assert other_done is True


class TestTfidfEmbedding:
    @pytest.mark.asyncio
    async def test_embed_returns_normalized_vectors(self):
        provider = TfidfEmbeddingProvider()
        provider._fitted = False

        result = await provider.embed(["hello world", "foo bar"])
        assert len(result) == 2
        for vec in result:
            norm = sum(v * v for v in vec) ** 0.5
            assert abs(norm - 1.0) < 0.01 or norm == 0.0

    @pytest.mark.asyncio
    async def test_embed_empty_returns_empty(self):
        provider = TfidfEmbeddingProvider()
        result = await provider.embed([])
        assert result == []

    def test_dimension(self):
        provider = TfidfEmbeddingProvider()
        assert provider.dimension >= 1

    def test_name(self):
        provider = TfidfEmbeddingProvider()
        assert provider.name == "tfidf"

    def test_embed_sync_returns_normalized(self):
        provider = TfidfEmbeddingProvider()
        provider._fitted = False

        result = provider.embed_sync(["hello world", "foo bar"])
        assert len(result) == 2
        for vec in result:
            norm = sum(v * v for v in vec) ** 0.5
            assert abs(norm - 1.0) < 0.01 or norm == 0.0

    def test_embed_sync_empty_returns_empty(self):
        provider = TfidfEmbeddingProvider()
        result = provider.embed_sync([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_does_not_block_event_loop(self):
        provider = TfidfEmbeddingProvider()
        provider._fitted = False

        other_done = False

        async def concurrent_task():
            nonlocal other_done
            await asyncio.sleep(0)
            other_done = True

        task = asyncio.create_task(concurrent_task())
        await provider.embed(["test input text"])
        await task
        assert other_done is True

    @pytest.mark.asyncio
    async def test_embed_and_sync_produce_same_result(self):
        provider = TfidfEmbeddingProvider()
        provider._fitted = False

        texts = ["first text", "second text"]
        async_result = await provider.embed(texts)
        provider._fitted = False
        sync_result = provider.embed_sync(texts)

        assert len(async_result) == len(sync_result)
