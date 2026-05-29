from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sediman.memory.vector import VectorStore


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.name = "test-provider"
    provider.dimension = 4
    provider.embed_sync.return_value = [[0.1, 0.2, 0.3, 0.4]]
    return provider


@pytest.fixture
def vector_store(mock_provider, tmp_path):
    with patch("sediman.memory.vector.DATA_DIR", tmp_path):
        with patch("sediman.memory.embeddings.create_embedding_provider") as creator:
            creator.return_value = mock_provider
            store = VectorStore(similarity_threshold=0.1)
            store._entries = []
            store._dirty = False
            yield store


class TestVectorStoreBasic:
    def test_init_empty(self, vector_store):
        assert vector_store.count == 0
        assert vector_store.provider.name == "test-provider"

    def test_add_returns_index(self, vector_store):
        idx = vector_store.add("hello world")
        assert idx == 0

    def test_add_increments_count(self, vector_store):
        vector_store.add("first")
        vector_store.add("second")
        assert vector_store.count == 2

    def test_add_duplicate_returns_same_index(self, vector_store):
        idx1 = vector_store.add("hello world")
        idx2 = vector_store.add("hello world")
        assert idx1 == idx2
        assert vector_store.count == 1

    def test_add_with_metadata(self, vector_store):
        idx = vector_store.add("test", metadata={"source": "test"})
        assert vector_store._entries[idx]["metadata"]["source"] == "test"

    def test_search_empty_store(self, vector_store):
        results = vector_store.search("test", k=5)
        assert results == []

    def test_search_empty_query(self, vector_store):
        vector_store.add("hello world")
        results = vector_store.search("", k=5)
        assert results == []

    def test_search_returns_results_with_scores(self, vector_store):
        vector_store.add("hello world")
        vector_store._entries[0]["vector"] = [1.0, 0.0, 0.0, 0.0]

        results = vector_store.search("hello", k=5, threshold=0.0)
        assert len(results) >= 1
        assert "score" in results[0]
        assert "text" in results[0]

    def test_remove_existing(self, vector_store):
        vector_store.add("hello")
        assert vector_store.remove("hello") is True
        assert vector_store.count == 0

    def test_remove_missing(self, vector_store):
        assert vector_store.remove("nonexistent") is False

    def test_clear_empties_store(self, vector_store):
        vector_store.add("a")
        vector_store.add("b")
        vector_store.clear()
        assert vector_store.count == 0

    def test_get_all(self, vector_store):
        vector_store.add("hello", metadata={"source": "test"})
        all_entries = vector_store.get_all()
        assert len(all_entries) == 1
        assert all_entries[0]["text"] == "hello"
        assert all_entries[0]["metadata"]["source"] == "test"
        assert all_entries[0]["provider"] == "test-provider"


class TestVectorStorePersistence:
    def test_persists_to_disk(self, mock_provider, tmp_path):
        old_path = Path(tmp_path / "vector_index.json")
        if old_path.exists():
            old_path.unlink()

        with patch("sediman.memory.vector.DATA_DIR", tmp_path):
            with patch("sediman.memory.embeddings.create_embedding_provider") as creator:
                creator.return_value = mock_provider
                store = VectorStore()
                store._entries = []
                store.add("test text")
                store._save()

        index_file = tmp_path / "vector_index.json"
        assert index_file.exists()
        data = json.loads(index_file.read_text())
        assert len(data["entries"]) == 1
        assert data["entries"][0]["text"] == "test text"

    def test_loads_from_existing_file(self, mock_provider, tmp_path):
        index_file = tmp_path / "vector_index.json"
        index_file.write_text(
            json.dumps({
                "entries": [
                    {
                        "text": "saved",
                        "vector": [0.1, 0.2, 0.3, 0.4],
                        "provider": "test-provider",
                        "metadata": {},
                    }
                ]
            })
        )

        with patch("sediman.memory.vector.DATA_DIR", tmp_path):
            with patch("sediman.memory.embeddings.create_embedding_provider") as creator:
                creator.return_value = mock_provider
                store = VectorStore()
                assert store.count == 1
                assert store._entries[0]["text"] == "saved"

    def test_missing_file_does_not_crash(self, tmp_path):
        with patch("sediman.memory.vector.DATA_DIR", tmp_path):
            with patch("sediman.memory.embeddings.create_embedding_provider") as creator:
                mock_provider = MagicMock()
                mock_provider.name = "test"
                mock_provider.dimension = 4
                creator.return_value = mock_provider
                store = VectorStore()
                assert store.count == 0

    def test_corrupted_file_does_not_crash(self, tmp_path):
        (tmp_path / "vector_index.json").write_text("corrupted json")
        with patch("sediman.memory.vector.DATA_DIR", tmp_path):
            with patch("sediman.memory.embeddings.create_embedding_provider") as creator:
                mock_provider = MagicMock()
                mock_provider.name = "test"
                mock_provider.dimension = 4
                creator.return_value = mock_provider
                store = VectorStore()
                assert store.count == 0


class TestVectorStoreSearchByMetadata:
    def test_search_by_metadata(self, vector_store):
        vector_store.add("item 1", metadata={"category": "A"})
        vector_store.add("item 2", metadata={"category": "B"})
        vector_store.add("item 3", metadata={"category": "A"})

        results = vector_store.search_by_metadata({"category": "A"})
        assert len(results) == 2

    def test_search_by_metadata_no_match(self, vector_store):
        vector_store.add("item 1", metadata={"category": "A"})
        results = vector_store.search_by_metadata({"category": "Z"})
        assert results == []


class TestVectorStoreRebuild:
    def test_rebuild_empty_does_nothing(self, vector_store):
        vector_store.rebuild_index()
        assert vector_store.count == 0

    def test_rebuild_updates_vectors(self, vector_store, mock_provider):
        vector_store.add("test text")
        vector_store._entries[0]["vector"] = [0.5, 0.5, 0.5, 0.5]
        mock_provider.embed_sync.return_value = [[0.9, 0.1, 0.0, 0.0]]

        vector_store.rebuild_index()
        assert vector_store._entries[0]["vector"] != [0.5, 0.5, 0.5, 0.5]


class TestVectorStoreCosineSimilarity:
    def test_similar_texts_rank_higher(self, vector_store):
        from sediman.memory.vector import _cosine_similarity, _normalize

        a = _normalize([1.0, 0.0, 0.0, 0.0])
        b = _normalize([0.9, 0.1, 0.0, 0.0])
        c = _normalize([0.0, 0.0, 1.0, 1.0])

        sim_ab = _cosine_similarity(a, b)
        sim_ac = _cosine_similarity(a, c)
        assert sim_ab > sim_ac

    def test_identical_vectors_have_cosine_1(self):
        from sediman.memory.vector import _cosine_similarity, _normalize

        v = _normalize([0.5, 0.5, 0.5, 0.5])
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors_have_cosine_0(self):
        from sediman.memory.vector import _cosine_similarity, _normalize

        a = _normalize([1.0, 0.0])
        b = _normalize([0.0, 1.0])
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_empty_vectors_return_zero(self):
        from sediman.memory.vector import _cosine_similarity

        assert _cosine_similarity([], []) == 0.0
        assert _cosine_similarity([1.0], []) == 0.0

    def test_normalize_zero_vector(self):
        from sediman.memory.vector import _normalize

        result = _normalize([0.0, 0.0, 0.0])
        assert result == [0.0, 0.0, 0.0]
