from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_sync(self, texts: list[str]) -> list[list[float]]:
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
        self._dim = 1536 if model == "text-embedding-3-small" else 3072

    def _lazy_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key)
            self._sync_client = type(self._client)(
                api_key=self._api_key
            ) if self._api_key != "not-needed" else None
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._lazy_client()
        try:
            resp = await client.embeddings.create(model=self.model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            logger.warning("openai_embed_failed", error=str(e))
            raise

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_sync(texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
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

    def _fit_if_needed(self, texts: list[str]) -> None:
        if not self._fitted and texts:
            self._vectorizer.fit(texts)
            self._fitted = True
            self._vocab = set(self._vectorizer.get_feature_names_out())
            self._dim = len(self._vocab)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_sync(texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
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
