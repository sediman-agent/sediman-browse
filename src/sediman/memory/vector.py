"""Vector store with SQLite backend for persistent vector embeddings.

Replaces the single JSON file approach with SQLite for better concurrency,
atomicity, and scalability. Falls back to JSON if SQLite is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

import structlog

from sediman.config import DATA_DIR

logger = structlog.get_logger()

_VECTOR_DB_PATH = DATA_DIR / "vectors.db"
_LEGACY_INDEX_PATH = DATA_DIR / "vector_index.json"

_VEC_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL UNIQUE,
    vector BLOB NOT NULL,
    provider TEXT NOT NULL DEFAULT 'unknown',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_vectors_text ON vectors(text);
CREATE INDEX IF NOT EXISTS idx_vectors_provider ON vectors(provider);
"""

_VEC_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'long_term',
    channel TEXT NOT NULL DEFAULT 'declarative',
    importance REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'unknown',
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_vec_meta_text ON vector_meta(text);
CREATE INDEX IF NOT EXISTS idx_vec_meta_importance ON vector_meta(importance);
"""

_SQLITE_VEC_AVAILABLE: bool | None = None


def _check_sqlite_vec() -> bool:
    global _SQLITE_VEC_AVAILABLE
    if _SQLITE_VEC_AVAILABLE is not None:
        return _SQLITE_VEC_AVAILABLE
    try:
        import sqlite_vec
        _SQLITE_VEC_AVAILABLE = True
    except ImportError:
        _SQLITE_VEC_AVAILABLE = False
    return _SQLITE_VEC_AVAILABLE


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


def _vec_to_blob(vec: list[float]) -> bytes:
    import struct
    return struct.pack(f'{len(vec)}f', *vec)


def _blob_to_vec(blob: bytes) -> list[float]:
    import struct
    n = len(blob) // 4
    return list(struct.unpack(f'{n}f', blob))


class VectorStore:
    def __init__(self, similarity_threshold: float = 0.3, lazy: bool = True):
        self._provider = None
        self._provider_name: str | None = None
        self._similarity_threshold = similarity_threshold
        self._lazy = lazy
        self._db_path = _VECTOR_DB_PATH
        self._use_sqlite = True
        self._legacy_entries: list[dict[str, Any]] = []
        self._legacy_dirty = False
        self._legacy_loaded = False

        if not lazy:
            self._ensure_provider()
            self._ensure_loaded()

    def _ensure_provider(self) -> Any:
        if self._provider is None:
            from sediman.memory.embeddings import create_embedding_provider
            self._provider = create_embedding_provider()
            self._provider_name = self._provider.name
        return self._provider

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")

        if _check_sqlite_vec():
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception:
                pass

        return conn

    def _ensure_loaded(self) -> None:
        self._ensure_db_schema()
        if not self._use_sqlite:
            self._legacy_load()

    def _ensure_db_schema(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._get_conn()
            try:
                conn.executescript(_VEC_SCHEMA)
                conn.executescript(_VEC_META_SCHEMA)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("vector_sqlite_init_failed", error=str(e))
            self._use_sqlite = False
            self._migrate_from_legacy()

    def _migrate_from_legacy(self) -> None:
        if not _LEGACY_INDEX_PATH.exists():
            return
        try:
            raw = _LEGACY_INDEX_PATH.read_text()
            data = json.loads(raw)
            entries = data.get("entries", [])
            if entries:
                self._legacy_entries = entries
                logger.info("vector_legacy_loaded", entries=len(entries))
        except Exception as e:
            logger.debug("vector_legacy_load_failed", error=str(e))

    def _legacy_load(self) -> None:
        if self._legacy_loaded:
            return
        if not _LEGACY_INDEX_PATH.exists():
            self._legacy_loaded = True
            return
        try:
            raw = _LEGACY_INDEX_PATH.read_text()
            data = json.loads(raw)
            self._legacy_entries = data.get("entries", [])
        except Exception:
            self._legacy_entries = []
        self._legacy_loaded = True

    def _legacy_save(self) -> None:
        if not self._legacy_dirty:
            return
        try:
            _LEGACY_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(_LEGACY_INDEX_PATH.parent), prefix=".tmp-", suffix=".json"
            )
            with os.fdopen(fd, "w") as f:
                json.dump({"entries": self._legacy_entries}, f, default=str)
            Path(tmp).rename(_LEGACY_INDEX_PATH)
            self._legacy_dirty = False
        except OSError as e:
            logger.warning("vector_legacy_save_failed", error=str(e))

    # ── Async API ───────────────────────────────────────────────

    async def async_add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        self._ensure_loaded()
        metadata = metadata or {}

        if self._use_sqlite:
            existing = self._sql_find_exact(text)
            if existing is not None:
                return existing

            provider = self._ensure_provider()
            vecs = await provider.embed([text])
            vec = _normalize(vecs[0])
            blob = _vec_to_blob(vec)
            meta_json = json.dumps(metadata, default=str)

            try:
                conn = self._get_conn()
                try:
                    cursor = conn.execute(
                        "INSERT INTO vectors (text, vector, provider, metadata) VALUES (?, ?, ?, ?)",
                        (text, blob, self._provider_name or "unknown", meta_json),
                    )
                    conn.commit()
                    return cursor.lastrowid
                finally:
                    conn.close()
            except sqlite3.IntegrityError:
                return self._sql_find_exact(text) or 0
            except Exception as e:
                logger.debug("vector_sql_insert_failed", error=str(e))
                return self._legacy_add(text, vec, metadata)

        return self._legacy_add_sync(text, metadata)

    async def async_add_batch(
        self, items: list[tuple[str, dict[str, Any]]],
    ) -> list[int]:
        self._ensure_loaded()
        if not items:
            return []

        texts = [t for t, _ in items]
        metas = [m for _, m in items]

        new_indices: list[int] = []
        new_texts: list[str] = []
        new_metas: list[dict[str, Any]] = []

        for i, text in enumerate(texts):
            existing = self._sql_find_exact(text) if self._use_sqlite else self._legacy_find_exact(text)
            if existing is not None:
                new_indices.append(existing)
            else:
                new_texts.append(text)
                new_metas.append(metas[i] if i < len(metas) else {})
                new_indices.append(-1)

        if new_texts:
            provider = self._ensure_provider()
            vecs = await provider.embed(new_texts)
            for text, meta, vec in zip(new_texts, new_metas, vecs):
                idx = self._add_vector(text, vec, meta)
                new_indices = [idx if x == -1 else x for x in new_indices]

        return new_indices

    async def async_search(
        self,
        query: str,
        k: int = 5,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_loaded()
        if not query.strip():
            return []

        threshold = threshold if threshold is not None else self._similarity_threshold
        provider = self._ensure_provider()
        vecs = await provider.embed([query])
        query_vec = _normalize(vecs[0])

        if self._use_sqlite:
            return self._sql_search_with_vec(query_vec, k, threshold)
        return self._legacy_search_with_vec(query_vec, k, threshold)

    # ── Sync API (backward-compat) ────────────────────────────────

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        self._ensure_loaded()
        metadata = metadata or {}

        if self._use_sqlite:
            existing = self._sql_find_exact(text)
            if existing is not None:
                return existing

            provider = self._ensure_provider()
            vec = provider.embed_sync([text])[0]
            vec = _normalize(vec)
            return self._add_vector(text, vec, metadata)

        return self._legacy_add_sync(text, metadata)

    def search(
        self,
        query: str,
        k: int = 5,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_loaded()
        if not query.strip():
            return []

        threshold = threshold if threshold is not None else self._similarity_threshold
        provider = self._ensure_provider()
        query_vec = _normalize(provider.embed_sync([query])[0])

        if self._use_sqlite:
            return self._sql_search_with_vec(query_vec, k, threshold)
        return self._legacy_search_with_vec(query_vec, k, threshold)

    # ── Shared vector add ──────────────────────────────────────

    def _add_vector(self, text: str, vec: list[float], metadata: dict[str, Any]) -> int:
        blob = _vec_to_blob(vec)
        meta_json = json.dumps(metadata, default=str)

        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    cursor = conn.execute(
                        "INSERT INTO vectors (text, vector, provider, metadata) VALUES (?, ?, ?, ?)",
                        (text, blob, self._provider_name or "unknown", meta_json),
                    )
                    row_id = cursor.lastrowid
                    importance = metadata.get("importance", 0.5) if metadata else 0.5
                    channel = metadata.get("channel", "declarative") if metadata else "declarative"
                    conn.execute(
                        "INSERT OR REPLACE INTO vector_meta (text, tier, channel, importance, source) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (text, metadata.get("tier", "long_term"), channel, importance, self._provider_name or "unknown"),
                    )
                    conn.commit()
                    return row_id
                finally:
                    conn.close()
            except sqlite3.IntegrityError:
                return self._sql_find_exact(text) or 0
            except Exception as e:
                logger.debug("vector_sql_insert_fallback", error=str(e))
                return self._legacy_add(text, vec, metadata)

        return self._legacy_add(text, vec, metadata)

    # ── SQLite search ──────────────────────────────────────────

    def _sql_search_with_vec(
        self,
        query_vec: list[float],
        k: int,
        threshold: float,
    ) -> list[dict[str, Any]]:
        if _check_sqlite_vec():
            results = self._sql_search_native(query_vec, k, threshold)
            if results is not None:
                return results

        SAMPLE_LIMIT = 500
        try:
            conn = self._get_conn()
            try:
                row_count = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
                if row_count <= SAMPLE_LIMIT:
                    rows = conn.execute(
                        "SELECT id, text, vector, metadata FROM vectors"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT v.id, v.text, v.vector, v.metadata FROM vectors v "
                        "LEFT JOIN vector_meta m ON v.text = m.text "
                        "ORDER BY COALESCE(m.importance, 0.5) DESC, v.created_at DESC "
                        "LIMIT ?", (SAMPLE_LIMIT,)
                    ).fetchall()
            finally:
                conn.close()

            scored: list[tuple[float, dict[str, Any]]] = []
            for row_id, text, blob, meta_json in rows:
                vec = _blob_to_vec(blob)
                sim = _cosine_similarity(query_vec, vec)
                if sim >= threshold:
                    try:
                        meta = json.loads(meta_json)
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                    scored.append((sim, {"text": text, "score": round(sim, 4), "metadata": meta}))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [s[1] for s in scored[:k]]
        except Exception as e:
            logger.debug("vector_sql_search_failed", error=str(e))
            return self._legacy_search_with_vec(query_vec, k, threshold)

    def _sql_search_native(
        self,
        query_vec: list[float],
        k: int,
        threshold: float,
    ) -> list[dict[str, Any]] | None:
        try:
            blob = _vec_to_blob(query_vec)
            conn = self._get_conn()
            try:
                dim = len(query_vec)
                rows = conn.execute(
                    f"SELECT v.text, vec_distance_cosine(v.vector, ?) as distance, v.metadata "
                    f"FROM vectors v "
                    f"WHERE vec_distance_cosine(v.vector, ?) < ? "
                    f"ORDER BY distance ASC LIMIT ?",
                    (blob, blob, 1.0 - threshold, k),
                ).fetchall()
                results = []
                for text, distance, meta_json in rows:
                    try:
                        meta = json.loads(meta_json) if meta_json else {}
                    except (json.JSONDecodeError, TypeError):
                        meta = {}
                    score = max(0.0, 1.0 - distance)
                    results.append({"text": text, "score": round(score, 4), "metadata": meta})
                return results
            finally:
                conn.close()
        except Exception as e:
            logger.debug("vector_native_search_failed", error=str(e))
            return None

    def _sql_find_exact(self, text: str) -> int | None:
        try:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT id FROM vectors WHERE text = ?", (text,)
                ).fetchone()
                return row[0] if row else None
            finally:
                conn.close()
        except Exception:
            return None

    # ── Legacy fallback ────────────────────────────────────────

    def _legacy_add(self, text: str, vec: list[float], metadata: dict[str, Any]) -> int:
        entry = {
            "text": text,
            "vector": vec,
            "provider": self._provider_name,
            "metadata": metadata,
        }
        self._legacy_entries.append(entry)
        self._legacy_dirty = True
        self._legacy_save()
        return len(self._legacy_entries) - 1

    def _legacy_add_sync(self, text: str, metadata: dict[str, Any]) -> int:
        self._ensure_loaded()
        existing = self._legacy_find_exact(text)
        if existing is not None:
            return existing

        provider = self._ensure_provider()
        vec = _normalize(provider.embed_sync([text])[0])
        return self._legacy_add(text, vec, metadata)

    def _legacy_find_exact(self, text: str) -> int | None:
        for i, entry in enumerate(self._legacy_entries):
            if entry["text"] == text:
                return i
        return None

    def _legacy_search_with_vec(
        self,
        query_vec: list[float],
        k: int,
        threshold: float,
    ) -> list[dict[str, Any]]:
        if not self._legacy_entries:
            return []
        entries = self._legacy_entries
        if len(entries) > 500:
            entries = entries[-500:]
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            vec = entry.get("vector", [])
            if not vec:
                continue
            sim = _cosine_similarity(query_vec, vec)
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

    # ── Mutation ────────────────────────────────────────────────

    def upsert_meta(
        self,
        text: str,
        tier: str = "long_term",
        channel: str = "declarative",
        importance: float = 0.5,
        source: str = "unknown",
    ) -> None:
        if not self._use_sqlite:
            return
        try:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO vector_meta (text, tier, channel, importance, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (text, tier, channel, importance, source),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.debug("vector_meta_upsert_failed", error=str(e))

    def remove(self, text: str) -> bool:
        self._ensure_loaded()
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    cursor = conn.execute("DELETE FROM vectors WHERE text = ?", (text,))
                    conn.commit()
                    if cursor.rowcount > 0:
                        return True
                finally:
                    conn.close()
            except Exception as e:
                logger.debug("vector_sql_remove_failed", error=str(e))

        idx = self._legacy_find_exact(text)
        if idx is not None:
            self._legacy_entries.pop(idx)
            self._legacy_dirty = True
            self._legacy_save()
            return True
        return False

    def remove_by_metadata(self, key: str, value: Any) -> int:
        self._ensure_loaded()
        removed = 0

        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    rows = conn.execute("SELECT id, metadata FROM vectors").fetchall()
                    ids_to_remove = []
                    for row_id, meta_json in rows:
                        try:
                            meta = json.loads(meta_json)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if meta.get(key) == value:
                            ids_to_remove.append(row_id)
                    if ids_to_remove:
                        placeholders = ",".join("?" for _ in ids_to_remove)
                        cursor = conn.execute(
                            f"DELETE FROM vectors WHERE id IN ({placeholders})",
                            ids_to_remove,
                        )
                        conn.commit()
                        removed = cursor.rowcount
                finally:
                    conn.close()
                return removed
            except Exception:
                pass

        before = len(self._legacy_entries)
        self._legacy_entries = [
            e for e in self._legacy_entries
            if e.get("metadata", {}).get(key) != value
        ]
        removed = before - len(self._legacy_entries)
        if removed > 0:
            self._legacy_dirty = True
            self._legacy_save()
        return removed

    def clear(self) -> None:
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    conn.execute("DELETE FROM vectors")
                    conn.commit()
                finally:
                    conn.close()
                return
            except Exception:
                pass
        self._legacy_entries.clear()
        self._legacy_dirty = True
        self._legacy_save()

    # ── Properties / queries ─────────────────────────────────────

    @property
    def count(self) -> int:
        self._ensure_loaded()
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    row = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
                    return row[0] if row else 0
                finally:
                    conn.close()
            except Exception:
                pass
        return len(self._legacy_entries)

    @property
    def provider(self) -> Any:
        return self._ensure_provider()

    def get_all(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                try:
                    rows = conn.execute("SELECT text, metadata, provider FROM vectors").fetchall()
                    return [
                        {"text": r[0], "metadata": json.loads(r[1]) if r[1] else {}, "provider": r[2]}
                        for r in rows
                    ]
                finally:
                    conn.close()
            except Exception:
                pass
        return [
            {"text": e["text"], "metadata": e.get("metadata", {}), "provider": e.get("provider", "unknown")}
            for e in self._legacy_entries
        ]

    def search_by_metadata(
        self,
        metadata_filter: dict[str, Any],
        k: int = 20,
    ) -> list[dict[str, Any]]:
        self._ensure_loaded()
        matching = []
        all_entries = self.get_all()
        for entry in all_entries:
            meta = entry.get("metadata", {})
            if all(meta.get(k) == v for k, v in metadata_filter.items()):
                matching.append({"text": entry["text"], "score": 1.0, "metadata": meta})
        return matching[:k]

    async def async_rebuild_index(self) -> None:
        self._ensure_loaded()
        all_entries = self.get_all()
        if not all_entries:
            return
        texts = [e["text"] for e in all_entries]
        try:
            provider = self._ensure_provider()
            vectors = await provider.embed(texts)
            for entry_dict, vec in zip(all_entries, vectors):
                normalized = _normalize(vec)
                if self._use_sqlite:
                    try:
                        conn = self._get_conn()
                        try:
                            conn.execute(
                                "UPDATE vectors SET vector = ?, provider = ? WHERE text = ?",
                                (_vec_to_blob(normalized), self._provider_name, entry_dict["text"]),
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("vector_index_rebuild_failed", error=str(e))

    def rebuild_index(self) -> None:
        self._ensure_loaded()
        all_entries = self.get_all()
        if not all_entries:
            return
        texts = [e["text"] for e in all_entries]
        try:
            provider = self._ensure_provider()
            vectors = provider.embed_sync(texts)
            for entry_dict, vec in zip(all_entries, vectors):
                normalized = _normalize(vec)
                if self._use_sqlite:
                    try:
                        conn = self._get_conn()
                        try:
                            conn.execute(
                                "UPDATE vectors SET vector = ?, provider = ? WHERE text = ?",
                                (_vec_to_blob(normalized), self._provider_name, entry_dict["text"]),
                            )
                            conn.commit()
                        finally:
                            conn.close()
                    except Exception:
                        pass
            logger.info("vector_index_rebuilt", entries=len(all_entries))
        except Exception as e:
            logger.warning("vector_index_rebuild_failed", error=str(e))
