from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class EmbeddingProvider(ABC):

    @property
    def _cache(self) -> dict[str, list[list[float]]]:
        if not hasattr(self, "_embed_cache"):
            self._embed_cache: dict[str, list[list[float]]] = {}
        return self._embed_cache

    def _cache_key(self, texts: list[str]) -> str:
        return hashlib.sha256("|".join(texts).encode()).hexdigest()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        key = self._cache_key(texts)
        cache = self._cache
        if key in cache:
            return cache[key]
        result = await self._embed_impl(texts)
        if len(cache) < 512:
            cache[key] = result
        return result

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        key = self._cache_key(texts)
        cache = self._cache
        if key in cache:
            return cache[key]
        result = self._embed_sync_impl(texts)
        if len(cache) < 512:
            cache[key] = result
        return result

    @abstractmethod
    async def _embed_impl(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def _embed_sync_impl(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...



class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None):
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Any | None = None
        self._sync_client: Any | None = None
        self._dim = 1536 if model == "text-embedding-3-small" else 3072

    def _lazy_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key)
            self._sync_client = None
        return self._client

    def _lazy_sync_client(self) -> Any:
        if self._sync_client is None:
            from openai import OpenAI
            self._sync_client = OpenAI(api_key=self._api_key)
        return self._sync_client

    async def _embed_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._lazy_client()
        try:
            resp = await client.embeddings.create(model=self.model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            logger.warning("openai_embed_failed", error=str(e))
            raise

    def _embed_sync_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._lazy_sync_client()
        try:
            resp = client.embeddings.create(model=self.model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            logger.warning("openai_embed_sync_failed", error=str(e))
            raise

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return f"openai/{self.model}"


class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model
        self._model: Any | None = None
        self._dim = 384
        self._TextEmbedding = None

    def _lazy_model(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
                self._TextEmbedding = TextEmbedding
                self._model = TextEmbedding(model_name=self.model_name, max_length=512)
                self._dim = self._model.dimension
            except ImportError:
                raise RuntimeError(
                    "fastembed not installed. Run: pip install fastembed"
                )
        return self._model

    async def _embed_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import asyncio as _asyncio
        return await _asyncio.to_thread(self._embed_sync_impl, texts)

    def _embed_sync_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._lazy_model()
        results = list(model.embed(texts))
        return [r.tolist() for r in results]

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return f"fastembed/{self.model_name}"


class TfidfEmbeddingProvider(EmbeddingProvider):
    _VOCAB_FILE = Path.home() / ".sediman" / "tfidf_vocab.json"

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            max_features=512,
            stop_words="english",
            analyzer="word",
            ngram_range=(1, 2),
        )
        self._fitted = False
        self._dim = 512
        self._vocab: set[str] = set()
        self._try_load_persisted_vocab()

    def _try_load_persisted_vocab(self) -> None:
        if not self._VOCAB_FILE.exists():
            return
        try:
            data = json.loads(self._VOCAB_FILE.read_text())
            vocab_list = data.get("vocabulary", [])
            idf = data.get("idf")
            if vocab_list:
                vocab_dict = {word: i for i, word in enumerate(vocab_list)}
                self._vectorizer.vocabulary_ = vocab_dict
                if idf and len(idf) == len(vocab_list):
                    import numpy as np
                    self._vectorizer.idf_ = np.array(idf)
                self._vectorizer.stop_words_ = set()
                self._fitted = True
                self._vocab = set(vocab_list)
                self._dim = len(vocab_list)
                logger.debug("tfidf_vocab_loaded", words=len(vocab_list))
        except Exception as e:
            logger.debug("tfidf_vocab_load_failed", error=str(e))

    def _persist_vocab(self) -> None:
        try:
            if not self._fitted:
                return
            vocab_list = list(self._vectorizer.get_feature_names_out())
            idf = self._vectorizer.idf_.tolist() if hasattr(self._vectorizer, 'idf_') else None
            self._VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._VOCAB_FILE.write_text(json.dumps({
                "vocabulary": vocab_list,
                "idf": idf,
            }))
        except Exception as e:
            logger.debug("tfidf_vocab_persist_failed", error=str(e))

    def _fit_if_needed(self, texts: list[str]) -> None:
        if not self._fitted and texts:
            self._vectorizer.fit(texts)
            self._fitted = True
            self._vocab = set(self._vectorizer.get_feature_names_out())
            self._dim = len(self._vocab)
            self._persist_vocab()
            self._cache.clear()

    async def _embed_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import asyncio as _asyncio
        return await _asyncio.to_thread(self._embed_sync_impl, texts)

    def _embed_sync_impl(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._fitted:
            self._fit_if_needed(texts)
        if not self._fitted:
            return [[0.0] * self._dim for _ in texts]
        try:
            matrix = self._vectorizer.transform(texts)
        except ValueError:
            self._fit_if_needed(texts)
            if not self._fitted:
                return [[0.0] * self._dim for _ in texts]
            matrix = self._vectorizer.transform(texts)
        rows: list[list[float]] = []
        for i in range(matrix.shape[0]):
            row = matrix[i].toarray()[0].tolist()
            norm = sum(v * v for v in row) ** 0.5
            if norm > 0:
                row = [v / norm for v in row]
            rows.append(row)
        return rows

    @property
    def dimension(self) -> int:
        return max(self._dim, 1)

    @property
    def name(self) -> str:
        return "tfidf"


def create_embedding_provider() -> EmbeddingProvider:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            provider = OpenAIEmbeddingProvider()
            logger.info("embedding_provider_selected", name=provider.name)
            return provider
        except Exception as e:
            logger.warning("openai_embed_init_failed_falling_back", error=str(e))

    try:
        provider = FastEmbedProvider()
        logger.info("embedding_provider_selected", name=provider.name)
        return provider
    except Exception as e:
        logger.warning("fastembed_init_failed_falling_back_to_tfidf", error=str(e))

    provider = TfidfEmbeddingProvider()
    logger.info("embedding_provider_selected", name=provider.name)
    return provider
