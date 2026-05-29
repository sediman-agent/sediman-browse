from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

from sediman.config import DATA_DIR

logger = structlog.get_logger()

def _get_index_path() -> Path:
    return DATA_DIR / "vector_index.json"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class VectorStore:
    def __init__(self, similarity_threshold: float = 0.3):
        from sediman.memory.embeddings import create_embedding_provider

        self._provider = create_embedding_provider()
        self._entries: list[dict[str, Any]] = []
        self._similarity_threshold = similarity_threshold
        self._dirty = False
        self._load()

    def _load(self) -> None:
        index_file = _get_index_path()
        if not index_file.exists():
            return
        try:
            raw = index_file.read_text()
            data = json.loads(raw)
            self._entries = data.get("entries", [])
            logger.info("vector_index_loaded", entries=len(self._entries))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("vector_index_load_failed", error=str(e))

    def _save(self) -> None:
        if not self._dirty:
            return
        try:
            index_file = _get_index_path()
            index_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(index_file.parent), prefix=".tmp-", suffix=".json"
            )
            with os.fdopen(fd, "w") as f:
                json.dump({"entries": self._entries}, f, default=str)
            Path(tmp).rename(index_file)
            self._dirty = False
        except OSError as e:
            logger.warning("vector_index_save_failed", error=str(e))

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        metadata = metadata or {}
        existing_idx = self._find_exact(text)
        if existing_idx is not None:
            return existing_idx

        vec = self._provider.embed_sync([text])[0]
        vec = _normalize(vec)
        entry: dict[str, Any] = {
            "text": text,
            "vector": vec,
            "provider": self._provider.name,
            "metadata": metadata,
        }
        self._entries.append(entry)
        self._dirty = True
        self._save()
        return len(self._entries) - 1

    def _find_exact(self, text: str) -> int | None:
        for i, entry in enumerate(self._entries):
            if entry["text"] == text:
                return i
        return None

    def search(
        self,
        query: str,
        k: int = 5,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        if not self._entries:
            return []
        if not query.strip():
            return []

        threshold = threshold if threshold is not None else self._similarity_threshold
        query_vec = self._provider.embed_sync([query])[0]
        query_vec = _normalize(query_vec)

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._entries:
            sim = _cosine_similarity(query_vec, entry["vector"])
            if sim >= threshold:
                scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for sim, entry in scored[:k]:
            results.append({
                "text": entry["text"],
                "score": round(sim, 4),
                "metadata": entry.get("metadata", {}),
            })
        return results

    def remove(self, text: str) -> bool:
        idx = self._find_exact(text)
        if idx is not None:
            self._entries.pop(idx)
            self._dirty = True
            self._save()
            return True
        return False

    def clear(self) -> None:
        self._entries.clear()
        self._dirty = True
        self._save()

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def provider(self) -> Any:
        return self._provider

    def get_all(self) -> list[dict[str, Any]]:
        return [
            {
                "text": e["text"],
                "metadata": e.get("metadata", {}),
                "provider": e.get("provider", "unknown"),
            }
            for e in self._entries
        ]

    def search_by_metadata(
        self,
        metadata_filter: dict[str, Any],
        k: int = 20,
    ) -> list[dict[str, Any]]:
        matching = []
        for entry in self._entries:
            meta = entry.get("metadata", {})
            if all(meta.get(k) == v for k, v in metadata_filter.items()):
                matching.append({
                    "text": entry["text"],
                    "score": 1.0,
                    "metadata": meta,
                })
        return matching[:k]

    def rebuild_index(self) -> None:
        if not self._entries:
            return
        texts = [e["text"] for e in self._entries]
        try:
            vectors = self._provider.embed_sync(texts)
            for entry, vec in zip(self._entries, vectors):
                entry["vector"] = _normalize(vec)
                entry["provider"] = self._provider.name
            self._dirty = True
            self._save()
            logger.info("vector_index_rebuilt", entries=len(self._entries))
        except Exception as e:
            logger.warning("vector_index_rebuild_failed", error=str(e))
